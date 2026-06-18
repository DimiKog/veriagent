"""Background scheduler for automatic Merkle batching and on-chain anchoring."""

import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

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

AutoAnchorLastStatus = Literal[
    "idle",
    "no_events",
    "below_threshold",
    "batch_created",
    "anchor_succeeded",
    "anchor_failed",
]

logger = logging.getLogger(__name__)
_state_lock = threading.Lock()
_scheduler_task: asyncio.Task[None] | None = None


@dataclass
class AutoAnchorConfig:
    enabled: bool
    interval_seconds: int
    min_events: int


@dataclass
class SchedulerRuntimeState:
    last_run_at: str | None = None
    last_status: AutoAnchorLastStatus = "idle"
    last_batch_id: str | None = None
    last_anchor_tx: str | None = None
    last_error: str | None = None


_runtime_state = SchedulerRuntimeState()


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


def _record_cycle_start() -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _state_lock:
        _runtime_state.last_run_at = now


def _record_scheduler_state(
    status: AutoAnchorLastStatus,
    *,
    last_batch_id: str | None = None,
    last_anchor_tx: str | None = None,
    last_error: str | None = None,
    update_batch_id: bool = False,
    update_anchor_tx: bool = False,
    update_error: bool = False,
) -> None:
    with _state_lock:
        _runtime_state.last_status = status
        if update_batch_id:
            _runtime_state.last_batch_id = last_batch_id
        if update_anchor_tx:
            _runtime_state.last_anchor_tx = last_anchor_tx
        if update_error:
            _runtime_state.last_error = last_error


def get_auto_anchor_ops_status(*, service: str, version: str) -> dict[str, Any]:
    config = load_auto_anchor_config()
    task = _scheduler_task
    scheduler_running = task is not None and not task.done()
    with _state_lock:
        return {
            "service": service,
            "version": version,
            "auto_anchor_enabled": config.enabled,
            "interval_seconds": config.interval_seconds,
            "min_events": config.min_events,
            "scheduler_running": scheduler_running,
            "last_run_at": _runtime_state.last_run_at,
            "last_status": _runtime_state.last_status,
            "last_batch_id": _runtime_state.last_batch_id,
            "last_anchor_tx": _runtime_state.last_anchor_tx,
            "last_error": _runtime_state.last_error,
        }


def reset_scheduler_state_for_tests() -> None:
    global _scheduler_task
    with _state_lock:
        _runtime_state.last_run_at = None
        _runtime_state.last_status = "idle"
        _runtime_state.last_batch_id = None
        _runtime_state.last_anchor_tx = None
        _runtime_state.last_error = None
    _scheduler_task = None


def run_auto_anchor_cycle(
    *,
    db_path: Any = None,
    config: AutoAnchorConfig | None = None,
) -> None:
    cfg = config or load_auto_anchor_config()
    _record_cycle_start()
    logger.info("auto anchor: checking unbatched events")
    unbatched_count = len(list_unbatched_events(db_path))
    logger.info("auto anchor: unbatched event count=%d", unbatched_count)

    if unbatched_count == 0:
        _record_scheduler_state("no_events", update_error=True, last_error=None)
        logger.info("auto anchor: no events")
        return

    if unbatched_count < cfg.min_events:
        _record_scheduler_state("below_threshold", update_error=True, last_error=None)
        logger.info(
            "auto anchor: below threshold (count=%d, min=%d)",
            unbatched_count,
            cfg.min_events,
        )
        return

    try:
        batch = create_batch_from_unbatched(db_path)
    except NoUnbatchedEventsError:
        _record_scheduler_state("no_events", update_error=True, last_error=None)
        logger.info("auto anchor: no events")
        return

    _record_scheduler_state(
        "batch_created",
        last_batch_id=batch.batch_id,
        update_batch_id=True,
        update_error=True,
        last_error=None,
    )
    logger.info(
        "auto anchor: batch created batch_id=%s event_count=%d",
        batch.batch_id,
        batch.event_count,
    )

    try:
        result = perform_batch_anchor(batch.batch_id, db_path=db_path)
    except (AnchoringConfigError, AnchorTransactionFailedError) as exc:
        _record_scheduler_state(
            "anchor_failed",
            update_error=True,
            last_error=str(exc),
        )
        logger.error(
            "auto anchor: anchor failed batch_id=%s: %s",
            batch.batch_id,
            exc,
        )
        return

    anchor = result.anchor
    _record_scheduler_state(
        "anchor_succeeded",
        last_anchor_tx=anchor.tx_hash,
        update_anchor_tx=True,
        update_error=True,
        last_error=None,
    )
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
    global _scheduler_task
    _configure_scheduler_logging()
    try:
        config = load_auto_anchor_config()
    except Exception:
        logger.exception("auto anchor scheduler failed to start")
        _scheduler_task = None
        return None, None

    _log_auto_anchor_startup(config)

    if not config.enabled:
        logger.info("auto anchor: scheduler disabled")
        _scheduler_task = None
        return None, None

    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _auto_anchor_scheduler_loop(stop_event, config),
        name="auto-anchor-scheduler",
    )
    _scheduler_task = task
    logger.info("auto anchor: scheduler task started")
    return task, stop_event


async def stop_auto_anchor_scheduler(
    task: asyncio.Task[None] | None,
    stop_event: asyncio.Event | None,
) -> None:
    global _scheduler_task
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
    finally:
        _scheduler_task = None

    logger.info("auto anchor: scheduler stopped")
