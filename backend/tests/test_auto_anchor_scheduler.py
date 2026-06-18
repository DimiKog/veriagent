import asyncio
import logging
import time

from eth_typing import ChecksumAddress

from app.anchoring import AnchorTransactionFailedError, AnchoringConfig, OnchainBatch
from app.auto_anchor_scheduler import (
    AutoAnchorConfig,
    _auto_anchor_scheduler_loop,
    run_auto_anchor_cycle,
    start_auto_anchor_scheduler,
    stop_auto_anchor_scheduler,
)
from app.hashing import canonicalize_event, hash_event
from app.models import AuditEvent
from app.storage import (
    create_batch_from_unbatched,
    get_batch,
    get_batch_anchor,
    list_unbatched_events,
    store_audit_event,
)
from tests.support import sample_event_payload

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xC034625CAd2fc3143C52E33d7A5fdbe864C3FfCb")
FAKE_TX_HASH = "0x" + "ef" * 32
FAKE_BLOCK_NUMBER = 42
FAKE_CHAIN_TIMESTAMP = 1_760_000_000

DEFAULT_CONFIG = AutoAnchorConfig(
    enabled=True,
    interval_seconds=300,
    min_events=1,
)


def _store_event(event_id: str, *, db_path):
    event = AuditEvent(**sample_event_payload(event_id=event_id))
    canonical = canonicalize_event(event).decode("utf-8")
    store_audit_event(
        event.event_id,
        canonical,
        hash_event(event),
        db_path=db_path,
    )


def _install_successful_anchor_mocks(monkeypatch, batch):
    onchain_batch = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )

    def fake_anchor_batch(*_args, **_kwargs):
        return FAKE_TX_HASH

    def fake_wait(_tx_hash, **_kwargs):
        return {"blockNumber": FAKE_BLOCK_NUMBER, "status": 1}

    def fake_get_onchain_batch(batch_id, **kwargs):
        assert batch_id == batch.batch_id
        assert kwargs.get("block_identifier") == FAKE_BLOCK_NUMBER
        return onchain_batch

    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fake_anchor_batch)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.wait_for_transaction_receipt",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        fake_get_onchain_batch,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.load_anchoring_config",
        lambda: AnchoringConfig(
            rpc_url="http://127.0.0.1:8545",
            chain_id=31337,
            contract_address=ANCHOR_CONTRACT,
            private_key="0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
        ),
    )


def test_auto_anchor_cycle_no_events(isolated_db, caplog):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")

    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)

    assert "auto anchor: checking unbatched events" in caplog.text
    assert "auto anchor: unbatched event count=0" in caplog.text
    assert "auto anchor: no events" in caplog.text
    assert list_unbatched_events(isolated_db) == []


def test_auto_anchor_cycle_below_threshold(isolated_db, caplog):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    _store_event("event-below-threshold", db_path=isolated_db)

    config = AutoAnchorConfig(enabled=True, interval_seconds=300, min_events=2)
    run_auto_anchor_cycle(db_path=isolated_db, config=config)

    assert "auto anchor: no events" not in caplog.text
    assert "auto anchor: below threshold" in caplog.text
    assert "auto anchor: batch created" not in caplog.text
    assert len(list_unbatched_events(isolated_db)) == 1


def test_auto_anchor_cycle_threshold_reached_batches_and_anchors(
    monkeypatch,
    isolated_db,
    caplog,
):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    _store_event("event-auto-anchor-cycle", db_path=isolated_db)

    batch_holder: dict[str, object] = {}
    original_create = create_batch_from_unbatched

    def create_and_capture(*args, **kwargs):
        batch = original_create(*args, **kwargs)
        batch_holder["batch"] = batch
        _install_successful_anchor_mocks(monkeypatch, batch)
        return batch

    monkeypatch.setattr(
        "app.auto_anchor_scheduler.create_batch_from_unbatched",
        create_and_capture,
    )

    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)

    batch = batch_holder["batch"]
    assert batch is not None
    assert "auto anchor: batch created" in caplog.text
    assert "auto anchor: anchor succeeded" in caplog.text
    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is not None
    assert len(list_unbatched_events(isolated_db)) == 0


def test_auto_anchor_cycle_anchor_failure_keeps_batch_and_next_run_continues(
    monkeypatch,
    isolated_db,
    caplog,
):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    _store_event("event-auto-anchor-fail", db_path=isolated_db)

    batch_holder: dict[str, object] = {}
    original_create = create_batch_from_unbatched

    def create_and_capture(*args, **kwargs):
        batch = original_create(*args, **kwargs)
        batch_holder["batch"] = batch
        return batch

    monkeypatch.setattr(
        "app.auto_anchor_scheduler.create_batch_from_unbatched",
        create_and_capture,
    )

    def fake_anchor_batch(*_args, **_kwargs):
        return FAKE_TX_HASH

    def fake_wait(_tx_hash, **_kwargs):
        raise AnchorTransactionFailedError(
            f"Anchor transaction reverted (status=0): tx_hash={FAKE_TX_HASH}"
        )

    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fake_anchor_batch)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.wait_for_transaction_receipt",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.load_anchoring_config",
        lambda: AnchoringConfig(
            rpc_url="http://127.0.0.1:8545",
            chain_id=31337,
            contract_address=ANCHOR_CONTRACT,
            private_key="0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
        ),
    )

    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)

    assert "auto anchor: batch created" in caplog.text
    assert "auto anchor: anchor failed" in caplog.text

    batch = batch_holder["batch"]
    assert get_batch(batch.batch_id, db_path=isolated_db) is not None
    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None

    caplog.clear()
    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)
    assert "auto anchor: no events" in caplog.text


def test_start_auto_anchor_scheduler_logs_disabled(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_ENABLED", "false")

    task, stop_event = start_auto_anchor_scheduler()

    assert task is None
    assert stop_event is None
    assert "auto anchor: enabled=False" in caplog.text
    assert "auto anchor: scheduler disabled" in caplog.text


def test_start_auto_anchor_scheduler_logs_enabled_and_starts_task(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_ENABLED", "true")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_MIN_EVENTS", "3")

    async def run():
        task, stop_event = start_auto_anchor_scheduler()

        assert task is not None
        assert stop_event is not None
        assert "auto anchor: enabled=True" in caplog.text
        assert "auto anchor: interval_seconds=3600" in caplog.text
        assert "auto anchor: min_events=3" in caplog.text
        assert "auto anchor: scheduler task started" in caplog.text

        await stop_auto_anchor_scheduler(task, stop_event)
        assert task.done()

    asyncio.run(run())


def test_scheduler_loop_runs_initial_cycle_before_first_wait(monkeypatch):
    calls: list[int] = []

    def track_cycle(**kwargs):
        calls.append(1)

    monkeypatch.setattr("app.auto_anchor_scheduler.run_auto_anchor_cycle", track_cycle)

    async def run():
        stop_event = asyncio.Event()
        config = AutoAnchorConfig(enabled=True, interval_seconds=3600, min_events=1)
        task = asyncio.create_task(_auto_anchor_scheduler_loop(stop_event, config))
        await asyncio.sleep(0.05)
        await stop_auto_anchor_scheduler(task, stop_event)

    asyncio.run(run())
    assert len(calls) >= 1


def test_stop_auto_anchor_scheduler_graceful_when_idle():
    async def run():
        stop_event = asyncio.Event()
        config = AutoAnchorConfig(enabled=True, interval_seconds=3600, min_events=1)
        task = asyncio.create_task(_auto_anchor_scheduler_loop(stop_event, config))
        await asyncio.sleep(0.05)
        await stop_auto_anchor_scheduler(task, stop_event)
        assert task.done()

    asyncio.run(run())


def test_stop_auto_anchor_scheduler_handles_timeout_without_raising(monkeypatch):
    monkeypatch.setattr("app.auto_anchor_scheduler.SHUTDOWN_GRACE_SECONDS", 0.1)

    def slow_cycle(**kwargs):
        time.sleep(2)

    monkeypatch.setattr("app.auto_anchor_scheduler.run_auto_anchor_cycle", slow_cycle)

    async def run():
        stop_event = asyncio.Event()
        config = AutoAnchorConfig(enabled=True, interval_seconds=3600, min_events=1)
        task = asyncio.create_task(_auto_anchor_scheduler_loop(stop_event, config))
        await asyncio.sleep(0.05)
        await stop_auto_anchor_scheduler(task, stop_event)
        assert task.done()

    asyncio.run(run())


def test_app_lifespan_shutdown_with_scheduler_enabled(monkeypatch):
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_ENABLED", "true")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS", "3600")
    monkeypatch.setattr(
        "app.auto_anchor_scheduler.run_auto_anchor_cycle",
        lambda **kwargs: None,
    )

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
