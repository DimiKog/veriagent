import pytest
from eth_typing import ChecksumAddress

from app.anchoring import AnchorTransactionFailedError, AnchoringConfig, OnchainBatch
from app.batch_anchoring import BatchNotFoundError, perform_batch_anchor
from app.storage import get_batch, get_batch_anchor, store_audit_event
from tests.support import sample_event_payload
from app.hashing import canonicalize_event, hash_event
from app.models import AuditEvent
from app.storage import create_batch_from_unbatched

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xC034625CAd2fc3143C52E33d7A5fdbe864C3FfCb")
FAKE_TX_HASH = "0x" + "ef" * 32
FAKE_BLOCK_NUMBER = 42
FAKE_CHAIN_TIMESTAMP = 1_760_000_000


def _store_one_batch():
    event = AuditEvent(**sample_event_payload(event_id="event-batch-anchor-unit"))
    canonical = canonicalize_event(event).decode("utf-8")
    store_audit_event(event.event_id, canonical, hash_event(event))
    return create_batch_from_unbatched()


def test_perform_batch_anchor_raises_and_does_not_store_on_reverted_receipt(
    monkeypatch,
    isolated_db,
):
    batch = _store_one_batch()

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

    with pytest.raises(AnchorTransactionFailedError, match="reverted"):
        perform_batch_anchor(batch.batch_id, db_path=isolated_db)

    assert get_batch_anchor(batch.batch_id, db_path=isolated_db) is None
    assert get_batch(batch.batch_id, db_path=isolated_db) is not None


def _install_successful_anchor_mocks(monkeypatch, batch, *, onchain_batch: OnchainBatch):
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


def test_perform_batch_anchor_falls_back_to_receipt_event_when_getbatch_is_zero(
    monkeypatch,
    isolated_db,
):
    batch = _store_one_batch()
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
