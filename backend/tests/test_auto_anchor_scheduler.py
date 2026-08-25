import logging

import pytest
from eth_typing import ChecksumAddress

from app.anchoring import (
    AnchorMetadataMismatchError,
    AnchorReceiptPendingError,
    AnchorTransactionFailedError,
    AnchoringConfig,
    BatchAnchoredLog,
    OnchainBatch,
)
from app.auto_anchor_scheduler import (
    AutoAnchorConfig,
    get_auto_anchor_ops_status,
    reset_scheduler_state_for_tests,
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
    get_event_lifecycle_status,
    get_pending_anchor_transaction,
    list_unanchored_batches,
    list_unbatched_events,
    store_audit_event,
)
from tests.support import sample_event_payload

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xC034625CAd2fc3143C52E33d7A5fdbe864C3FfCb")
FAKE_TX_HASH = "0x" + "ef" * 32
FAKE_TX_HASH_2 = "0x" + "ab" * 32
FAKE_BLOCK_NUMBER = 42
FAKE_CHAIN_TIMESTAMP = 1_760_000_000

DEFAULT_CONFIG = AutoAnchorConfig(
    enabled=True,
    interval_seconds=300,
    min_events=1,
)


@pytest.fixture(autouse=True)
def _reset_ops_state():
    reset_scheduler_state_for_tests()
    yield
    reset_scheduler_state_for_tests()


def _store_event(event_id: str, *, db_path):
    event = AuditEvent(**sample_event_payload(event_id=event_id))
    canonical = canonicalize_event(event).decode("utf-8")
    store_audit_event(
        event.event_id,
        canonical,
        hash_event(event),
        db_path=db_path,
    )


def _default_config_mock():
    return AnchoringConfig(
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=ANCHOR_CONTRACT,
        private_key="0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
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
        "app.batch_anchoring.anchoring.is_batch_anchored",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.load_anchoring_config",
        _default_config_mock,
    )


def test_auto_anchor_cycle_no_events(isolated_db, caplog):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")

    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)

    assert "auto anchor: checking unbatched events" in caplog.text
    assert "auto anchor: unbatched event count=0" in caplog.text
    assert "auto anchor: no events" in caplog.text
    assert list_unbatched_events(isolated_db) == []
    assert list_unanchored_batches(isolated_db) == []


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
    assert "auto anchor: anchor_succeeded" in caplog.text
    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is not None
    assert len(list_unbatched_events(isolated_db)) == 0


def test_auto_anchor_cycle_anchor_failure_retries_unanchored_batch(
    monkeypatch,
    isolated_db,
    caplog,
):
    """Failed anchor leaves the batch; next cycle retries it (not no_events-only)."""
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    _store_event("event-auto-anchor-fail", db_path=isolated_db)

    batch_holder: dict[str, object] = {}
    original_create = create_batch_from_unbatched
    submit_calls = {"count": 0}

    def create_and_capture(*args, **kwargs):
        batch = original_create(*args, **kwargs)
        batch_holder["batch"] = batch
        return batch

    monkeypatch.setattr(
        "app.auto_anchor_scheduler.create_batch_from_unbatched",
        create_and_capture,
    )

    def fake_anchor_batch(*_args, **_kwargs):
        submit_calls["count"] += 1
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
        "app.batch_anchoring.anchoring.is_batch_anchored",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.load_anchoring_config",
        _default_config_mock,
    )

    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)

    assert "auto anchor: batch created" in caplog.text
    assert "auto anchor: anchor failed" in caplog.text

    batch = batch_holder["batch"]
    assert get_batch(batch.batch_id, db_path=isolated_db) is not None
    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None
    assert list_unanchored_batches(isolated_db)

    ops = get_auto_anchor_ops_status(service="veriagent", version="test")
    assert ops["last_status"] == "anchor_failed"
    assert ops["last_error"] is not None

    caplog.clear()
    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)
    assert "auto anchor: found unanchored batch" in caplog.text
    assert "auto anchor: no events" not in caplog.text
    assert submit_calls["count"] == 2

    ops_after = get_auto_anchor_ops_status(service="veriagent", version="test")
    assert ops_after["last_status"] == "anchor_failed"
    assert ops_after["last_error"] is not None


def test_scheduler_processes_stranded_batch_with_zero_unbatched(
    monkeypatch,
    isolated_db,
    caplog,
):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    _store_event("event-stranded", db_path=isolated_db)
    batch = create_batch_from_unbatched(isolated_db)
    assert list_unbatched_events(isolated_db) == []
    assert list_unanchored_batches(isolated_db)

    onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )
    anchored_log = BatchAnchoredLog(
        batch_id_bytes=b"\x11" * 32,
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
        tx_hash=FAKE_TX_HASH,
        block_number=FAKE_BLOCK_NUMBER,
    )

    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.is_batch_anchored",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        lambda *_a, **_k: onchain,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.find_batch_anchored_log",
        lambda *_a, **_k: anchored_log,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.load_anchoring_config",
        _default_config_mock,
    )

    def fail_if_submitted(*_a, **_k):
        raise AssertionError("must not submit AnchorBatch for stranded on-chain batch")

    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fail_if_submitted)

    run_auto_anchor_cycle(db_path=isolated_db, config=DEFAULT_CONFIG)

    assert "auto anchor: found unanchored batch" in caplog.text
    assert "auto anchor: anchor_reconciled" in caplog.text
    stored = get_batch_anchor(batch.batch_id, db_path=isolated_db)
    assert stored is not None
    assert stored.tx_hash == FAKE_TX_HASH

    ops = get_auto_anchor_ops_status(service="veriagent", version="test")
    assert ops["last_status"] == "anchor_reconciled"
    assert ops["last_batch_id"] == batch.batch_id
    assert ops["last_anchor_tx"] == FAKE_TX_HASH
    assert ops["last_error"] is None

    lifecycle = get_event_lifecycle_status("event-stranded", db_path=isolated_db)
    assert lifecycle is not None
    assert lifecycle.anchored is True
    assert lifecycle.tx_hash == FAKE_TX_HASH
    assert lifecycle.block_number == FAKE_BLOCK_NUMBER


def test_start_auto_anchor_scheduler_logs_disabled(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_ENABLED", "false")

    task, stop_event = start_auto_anchor_scheduler()

    assert task is None
    assert stop_event is None
    assert "auto anchor: enabled=False" in caplog.text
    assert "auto anchor: scheduler disabled" in caplog.text


def test_start_auto_anchor_scheduler_logs_enabled_and_starts_task(monkeypatch, caplog):
    import asyncio

    caplog.set_level(logging.INFO, logger="app.auto_anchor_scheduler")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_ENABLED", "true")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_MIN_EVENTS", "3")

    async def run():
        task, stop_event = start_auto_anchor_scheduler()
        try:
            assert task is not None
            assert stop_event is not None
            assert "auto anchor: enabled=True" in caplog.text
            assert "auto anchor: scheduler task started" in caplog.text
        finally:
            await stop_auto_anchor_scheduler(task, stop_event)

    asyncio.run(run())
