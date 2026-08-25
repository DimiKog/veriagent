import pytest
from eth_typing import ChecksumAddress

from app.anchoring import (
    AnchorMetadataMismatchError,
    AnchorReceiptPendingError,
    AnchorReconciliationError,
    AnchorTransactionFailedError,
    AnchoringConfig,
    BatchAnchoredLog,
    OnchainBatch,
)
from app.batch_anchoring import BatchNotFoundError, perform_batch_anchor
from app.hashing import canonicalize_event, hash_event
from app.models import AuditEvent
from app.storage import (
    create_batch_from_unbatched,
    get_batch,
    get_batch_anchor,
    get_pending_anchor_transaction,
    store_audit_event,
)
from tests.support import sample_event_payload

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xC034625CAd2fc3143C52E33d7A5fdbe864C3FfCb")
FAKE_TX_HASH = "0x" + "ef" * 32
FAKE_BLOCK_NUMBER = 42
FAKE_CHAIN_TIMESTAMP = 1_760_000_000


def _store_one_batch(event_id: str = "event-batch-anchor-unit"):
    event = AuditEvent(**sample_event_payload(event_id=event_id))
    canonical = canonicalize_event(event).decode("utf-8")
    store_audit_event(event.event_id, canonical, hash_event(event))
    return create_batch_from_unbatched()


def _default_config_mock():
    return AnchoringConfig(
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=ANCHOR_CONTRACT,
        private_key="0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
    )


def _install_base_mocks(monkeypatch, *, is_anchored: bool = False):
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.is_batch_anchored",
        lambda *_a, **_k: is_anchored,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.load_anchoring_config",
        _default_config_mock,
    )


def _install_successful_anchor_mocks(monkeypatch, batch, *, onchain_batch: OnchainBatch):
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
    _install_base_mocks(monkeypatch, is_anchored=False)


def test_perform_batch_anchor_raises_and_persists_failed_pending_on_reverted_receipt(
    monkeypatch,
    isolated_db,
):
    batch = _store_one_batch()
    _install_base_mocks(monkeypatch, is_anchored=False)

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

    with pytest.raises(AnchorTransactionFailedError, match="reverted"):
        perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None
    assert get_batch(batch.batch_id, db_path=isolated_db) is not None
    pending = get_pending_anchor_transaction(batch.batch_id, db_path=isolated_db)
    assert pending is not None
    assert pending.status == "failed"
    assert pending.tx_hash == FAKE_TX_HASH


def test_perform_batch_anchor_existing_local_anchor_skips_chain(monkeypatch, isolated_db):
    batch = _store_one_batch("event-local-anchor")
    onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )
    _install_successful_anchor_mocks(monkeypatch, batch, onchain_batch=onchain)
    first = perform_batch_anchor(batch.batch_id, db_path=isolated_db)
    assert first.already_anchored is False

    def fail_submit(*_a, **_k):
        raise AssertionError("must not submit when local anchor exists")

    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fail_submit)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.is_batch_anchored",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not query chain")),
    )

    second = perform_batch_anchor(batch.batch_id, db_path=isolated_db)
    assert second.already_anchored is True
    assert second.reconciled is False
    assert second.anchor.tx_hash == FAKE_TX_HASH


def test_perform_batch_anchor_stores_non_zero_onchain_metadata(monkeypatch, isolated_db):
    batch = _store_one_batch()
    onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )
    _install_successful_anchor_mocks(monkeypatch, batch, onchain_batch=onchain)

    result = perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert result.already_anchored is False
    assert result.anchor.anchored_at == FAKE_CHAIN_TIMESTAMP
    assert result.anchor.anchored_by == ANCHOR_SENDER

    stored = get_batch_anchor(batch.batch_id, db_path=isolated_db)
    assert stored is not None
    assert stored.anchored_at == FAKE_CHAIN_TIMESTAMP
    assert stored.anchored_by == ANCHOR_SENDER
    pending = get_pending_anchor_transaction(batch.batch_id, db_path=isolated_db)
    assert pending is not None
    assert pending.status == "confirmed"


def test_perform_batch_anchor_falls_back_to_receipt_event_when_getbatch_is_zero(
    monkeypatch,
    isolated_db,
):
    batch = _store_one_batch("event-fallback-zero")
    zero_onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=0,
        anchored_by=ChecksumAddress("0x0000000000000000000000000000000000000000"),
    )
    _install_successful_anchor_mocks(monkeypatch, batch, onchain_batch=zero_onchain)

    def fake_read_anchor_metadata_from_receipt(receipt, batch_id, **kwargs):
        assert batch_id == batch.batch_id
        assert receipt["blockNumber"] == FAKE_BLOCK_NUMBER
        return FAKE_CHAIN_TIMESTAMP, ANCHOR_SENDER

    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.read_anchor_metadata_from_receipt",
        fake_read_anchor_metadata_from_receipt,
    )

    result = perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert result.anchor.anchored_at == FAKE_CHAIN_TIMESTAMP
    assert result.anchor.anchored_by == ANCHOR_SENDER


def test_pending_tx_resume_without_duplicate_submit(monkeypatch, isolated_db):
    batch = _store_one_batch("event-pending-resume")
    _install_base_mocks(monkeypatch, is_anchored=False)
    submit_calls = {"count": 0}
    wait_calls = {"count": 0}

    def fake_anchor_batch(*_args, **_kwargs):
        submit_calls["count"] += 1
        return FAKE_TX_HASH

    def fake_wait_pending(_tx_hash, **_kwargs):
        wait_calls["count"] += 1
        if wait_calls["count"] == 1:
            raise AnchorReceiptPendingError(
                FAKE_TX_HASH,
                f"receipt not yet available: {FAKE_TX_HASH}",
            )
        return {"blockNumber": FAKE_BLOCK_NUMBER, "status": 1}

    onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )

    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fake_anchor_batch)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.wait_for_transaction_receipt",
        fake_wait_pending,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        lambda *_a, **_k: onchain,
    )

    with pytest.raises(AnchorReceiptPendingError):
        perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    pending = get_pending_anchor_transaction(batch.batch_id, db_path=isolated_db)
    assert pending is not None
    assert pending.status == "submitted"
    assert pending.tx_hash == FAKE_TX_HASH
    assert submit_calls["count"] == 1
    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None

    result = perform_batch_anchor(batch.batch_id, db_path=isolated_db)
    assert submit_calls["count"] == 1
    assert wait_calls["count"] == 2
    assert result.anchor.tx_hash == FAKE_TX_HASH
    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is not None


def test_reconcile_onchain_without_second_submit(monkeypatch, isolated_db):
    batch = _store_one_batch("event-reconcile")
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
    _install_base_mocks(monkeypatch, is_anchored=True)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        lambda *_a, **_k: onchain,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.find_batch_anchored_log",
        lambda *_a, **_k: anchored_log,
    )

    def fail_submit(*_a, **_k):
        raise AssertionError("must not submit AnchorBatch during reconciliation")

    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fail_submit)

    result = perform_batch_anchor(batch.batch_id, db_path=isolated_db)
    assert result.reconciled is True
    assert result.already_anchored is True
    assert result.anchor.tx_hash == FAKE_TX_HASH
    assert result.anchor.block_number == FAKE_BLOCK_NUMBER


def test_reconcile_zero_matching_events_fails(monkeypatch, isolated_db):
    batch = _store_one_batch("event-reconcile-zero")
    onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )
    _install_base_mocks(monkeypatch, is_anchored=True)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        lambda *_a, **_k: onchain,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.find_batch_anchored_log",
        lambda *_a, **_k: None,
    )

    with pytest.raises(AnchorReconciliationError, match="no BatchAnchored log"):
        perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None


def test_reconcile_multiple_matching_events_fails(monkeypatch, isolated_db):
    batch = _store_one_batch("event-reconcile-multi")
    onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )
    _install_base_mocks(monkeypatch, is_anchored=True)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        lambda *_a, **_k: onchain,
    )

    def multi_logs(*_a, **_k):
        raise AnchorReconciliationError(
            f"Multiple BatchAnchored events found for batch {batch.batch_id} "
            "(count=2); refusing reconciliation"
        )

    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.find_batch_anchored_log",
        multi_logs,
    )

    with pytest.raises(AnchorReconciliationError, match="Multiple BatchAnchored"):
        perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None


def test_find_batch_anchored_log_integrity_zero_one_and_multiple(monkeypatch):
    """Unit-level integrity: 0 → None, 1 → log, >1 → AnchorReconciliationError."""
    from types import SimpleNamespace

    from app.anchoring import (
        AnchorReconciliationError,
        BatchAnchoredLog,
        find_batch_anchored_log,
    )

    cfg = _default_config_mock()
    monkeypatch.setattr("app.anchoring.load_anchoring_config", lambda: cfg)
    monkeypatch.setattr(
        "app.anchoring._get_web3",
        lambda _cfg: SimpleNamespace(eth=SimpleNamespace(block_number=100)),
    )

    def _event(tx_suffix: str, block: int):
        return {
            "args": {
                "batchId": b"\x11" * 32,
                "merkleRoot": b"\xaa" * 32,
                "eventCount": 1,
                "metadataHash": b"\xbb" * 32,
                "anchoredAt": FAKE_CHAIN_TIMESTAMP,
                "anchoredBy": ANCHOR_SENDER,
            },
            "transactionHash": bytes.fromhex(tx_suffix * 32),
            "blockNumber": block,
        }

    class FakeEvent:
        """Return scripted get_logs results keyed by (from_block, to_block)."""

        def __init__(self, by_range: dict[tuple[int, int], list]):
            self._by_range = by_range

        def get_logs(self, **kwargs):
            key = (int(kwargs["from_block"]), int(kwargs["to_block"]))
            return list(self._by_range.get(key, []))

    # zero matches across all chunks (newest-first: 6-10, 1-5, 0-0)
    zero_event = FakeEvent({})
    monkeypatch.setattr(
        "app.anchoring.get_anchor_contract",
        lambda *_a, **_k: SimpleNamespace(
            events=SimpleNamespace(BatchAnchored=zero_event)
        ),
    )
    assert (
        find_batch_anchored_log("batch-zero", from_block=0, to_block=10, chunk_size=5)
        is None
    )

    # exactly one match in middle chunk
    one_event = FakeEvent({(1, 5): [_event("cc", 3)]})
    monkeypatch.setattr(
        "app.anchoring.get_anchor_contract",
        lambda *_a, **_k: SimpleNamespace(
            events=SimpleNamespace(BatchAnchored=one_event)
        ),
    )
    found = find_batch_anchored_log(
        "batch-one", from_block=0, to_block=10, chunk_size=5
    )
    assert isinstance(found, BatchAnchoredLog)
    assert found.block_number == 3
    assert found.tx_hash.startswith("0x")

    # multiple matches in one chunk → refuse
    multi_event = FakeEvent({(0, 10): [_event("dd", 4), _event("ee", 5)]})
    monkeypatch.setattr(
        "app.anchoring.get_anchor_contract",
        lambda *_a, **_k: SimpleNamespace(
            events=SimpleNamespace(BatchAnchored=multi_event)
        ),
    )
    with pytest.raises(AnchorReconciliationError, match="Multiple BatchAnchored"):
        find_batch_anchored_log(
            "batch-multi", from_block=0, to_block=10, chunk_size=20
        )

    # one in newer chunk, another in older chunk → refuse after second sighting
    split_event = FakeEvent(
        {
            (6, 10): [_event("ff", 8)],
            (1, 5): [_event("aa", 2)],
        }
    )
    monkeypatch.setattr(
        "app.anchoring.get_anchor_contract",
        lambda *_a, **_k: SimpleNamespace(
            events=SimpleNamespace(BatchAnchored=split_event)
        ),
    )
    with pytest.raises(AnchorReconciliationError, match="Multiple BatchAnchored"):
        find_batch_anchored_log(
            "batch-split", from_block=0, to_block=10, chunk_size=5
        )


def test_reconcile_merkle_mismatch_does_not_store(monkeypatch, isolated_db):
    batch = _store_one_batch("event-mismatch-root")
    onchain = OnchainBatch(
        merkle_root=b"\xff" * 32,
        event_count=batch.event_count,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )
    _install_base_mocks(monkeypatch, is_anchored=True)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        lambda *_a, **_k: onchain,
    )

    with pytest.raises(AnchorMetadataMismatchError, match="merkle_root"):
        perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None


def test_reconcile_event_count_mismatch_does_not_store(monkeypatch, isolated_db):
    batch = _store_one_batch("event-mismatch-count")
    onchain = OnchainBatch(
        merkle_root=bytes.fromhex(batch.merkle_root),
        event_count=batch.event_count + 1,
        metadata_hash=b"\x03" * 32,
        anchored_at=FAKE_CHAIN_TIMESTAMP,
        anchored_by=ANCHOR_SENDER,
    )
    _install_base_mocks(monkeypatch, is_anchored=True)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        lambda *_a, **_k: onchain,
    )

    with pytest.raises(AnchorMetadataMismatchError, match="event_count"):
        perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None


def test_perform_batch_anchor_raises_for_missing_batch(isolated_db):
    with pytest.raises(BatchNotFoundError):
        perform_batch_anchor("does-not-exist", db_path=isolated_db)
