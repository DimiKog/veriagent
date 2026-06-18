"""Background scheduler for automatic Merkle batching and on-chain anchoring."""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from app.anchoring import AnchorTransactionFailedError, AnchoringConfigError
from app.batch_anchoring import perform_batch_anchor
from app.storage import (
    NoUnbatchedEventsError,
    create_batch_from_unbatched,
    list_unbatched_events,
)

AUTO_ANCHOR_ENABLED_ENV = "VERIAGENT_AUTO_ANCHOR_ENABLED"
AUTO_ANCHOR_INTERVAL_ENV = "VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS"
AUTO_ANCHOR_MIN_EVENTS_ENV = "VERIAGENT_AUTO_ANCHOR_MIN_EVENTS"

DEFAULT_INTERVAL_SECONDS = 300
DEFAULT_MIN_EVENTS = 1
SHUTDOWN_GRACE_SECONDS = 10

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoAnchorConfig:
    enabled: bool
    interval_seconds: int
    min_events: int


def _configure_scheduler_logging() -> None:
    scheduler_logger = logging.getLogger("app.auto_anchor_scheduler")
    scheduler_logger.setLevel(logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_positive_int(name: str, raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        parsed = int(raw.strip())
    except ValueError:
        logger.warning(
            "auto anchor: invalid %s=%r; using default %s",
            name,
            raw,
            default,
        )
        return default
    if parsed < 1:
        logger.warning(
            "auto anchor: invalid %s=%r; must be >= 1, using default %s",
            name,
            raw,
            default,
        )
        return default
    return parsed


def load_auto_anchor_config() -> AutoAnchorConfig:
    enabled_raw = os.environ.get(AUTO_ANCHOR_ENABLED_ENV, "false")
    interval_raw = os.environ.get(AUTO_ANCHOR_INTERVAL_ENV)
    min_events_raw = os.environ.get(AUTO_ANCHOR_MIN_EVENTS_ENV)
    return AutoAnchorConfig(
        enabled=_parse_bool(enabled_raw),
        interval_seconds=_parse_positive_int(
            AUTO_ANCHOR_INTERVAL_ENV,
            interval_raw,
            DEFAULT_INTERVAL_SECONDS,
        ),
        min_events=_parse_positive_int(
            AUTO_ANCHOR_MIN_EVENTS_ENV,
            min_events_raw,
            DEFAULT_MIN_EVENTS,
        ),
    )


def _log_auto_anchor_startup(config: AutoAnchorConfig) -> None:
    logger.info("auto anchor: enabled=%s", config.enabled)
    logger.info("auto anchor: interval_seconds=%s", config.interval_seconds)
    logger.info("auto anchor: min_events=%s", config.min_events)


def run_auto_anchor_cycle(
    *,
    db_path: Any = None,
    config: AutoAnchorConfig | None = None,
) -> None:
    cfg = config or load_auto_anchor_config()
    logger.info("auto anchor: checking unbatched events")
    unbatched_count = len(list_unbatched_events(db_path))
    logger.info("auto anchor: unbatched event count=%d", unbatched_count)

    if unbatched_count == 0:
        logger.info("auto anchor: no events")
        return

    if unbatched_count < cfg.min_events:
        logger.info(
            "auto anchor: below threshold (count=%d, min=%d)",
            unbatched_count,
            cfg.min_events,
        )
        return

    try:
        batch = create_batch_from_unbatched(db_path)
    except NoUnbatchedEventsError:
        logger.info("auto anchor: no events")
        return

    logger.info(
        "auto anchor: batch created batch_id=%s event_count=%d",
        batch.batch_id,
        batch.event_count,
    )

    try:
        result = perform_batch_anchor(batch.batch_id, db_path=db_path)
    except (AnchoringConfigError, AnchorTransactionFailedError) as exc:
        logger.error(
            "auto anchor: anchor failed batch_id=%s: %s",
            batch.batch_id,
            exc,
        )
        return

    anchor = result.anchor
    logger.info(
        "auto anchor: anchor succeeded batch_id=%s tx_hash=%s already_anchored=%s",
        batch.batch_id,
        anchor.tx_hash,
        result.already_anchored,
    )


async def _auto_anchor_scheduler_loop(
    stop_event: asyncio.Event,
    config: AutoAnchorConfig,
) -> None:
    try:
        while not stop_event.is_set():
            try:
                await asyncio.to_thread(run_auto_anchor_cycle, config=config)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("auto anchor scheduler cycle failed")

            if stop_event.is_set():
                break

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=config.interval_seconds,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
    except asyncio.CancelledError:
        logger.info("auto anchor: scheduler task cancelled")
        raise


def start_auto_anchor_scheduler() -> tuple[asyncio.Task[None] | None, asyncio.Event | None]:
    _configure_scheduler_logging()
    try:
        config = load_auto_anchor_config()
    except Exception:
        logger.exception("auto anchor scheduler failed to start")
        return None, None

    _log_auto_anchor_startup(config)

    if not config.enabled:
        logger.info("auto anchor: scheduler disabled")
        return None, None

    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _auto_anchor_scheduler_loop(stop_event, config),
        name="auto-anchor-scheduler",
    )
    logger.info("auto anchor: scheduler task started")
    return task, stop_event


async def stop_auto_anchor_scheduler(
    task: asyncio.Task[None] | None,
    stop_event: asyncio.Event | None,
) -> None:
    if task is None or stop_event is None:
        return

    logger.info("auto anchor: scheduler stopping")
    stop_event.set()

    try:
        await asyncio.wait_for(task, timeout=SHUTDOWN_GRACE_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            "auto anchor: scheduler did not stop within %ss; cancelling task",
            SHUTDOWN_GRACE_SECONDS,
        )
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("auto anchor: scheduler stop encountered an error")

    logger.info("auto anchor: scheduler stopped")
