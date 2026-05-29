from eth_typing import ChecksumAddress

from fastapi.testclient import TestClient

from app.anchoring import AnchoringConfig, OnchainBatch
from app.main import app
from tests.test_api import sample_event_payload

client = TestClient(app)

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
FAKE_TX_HASH = "0x" + "ab" * 32
FAKE_BLOCK_NUMBER = 42
FAKE_CHAIN_TIMESTAMP = 1_700_000_000


def _create_batch(event_id: str = "event-anchor-1") -> dict:
    response = client.post("/audit/events", json=sample_event_payload(event_id=event_id))
    assert response.status_code == 200
    batch_response = client.post("/audit/batches")
    assert batch_response.status_code == 200
    return batch_response.json()


def _fake_anchoring_config() -> AnchoringConfig:
    return AnchoringConfig(
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=ANCHOR_CONTRACT,
        private_key="0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
    )


def _install_anchor_mocks(monkeypatch, batch: dict):
    anchor_calls: list[tuple] = []

    def fake_anchor_batch(batch_id, merkle_root, event_count, metadata_hash, **kwargs):
        anchor_calls.append((batch_id, merkle_root, event_count, metadata_hash))
        return FAKE_TX_HASH

    def fake_wait_for_transaction_receipt(tx_hash, **kwargs):
        assert tx_hash == FAKE_TX_HASH
        return {"blockNumber": FAKE_BLOCK_NUMBER, "status": 1}

    def fake_get_onchain_batch(batch_id, **kwargs):
        assert batch_id == batch["batch_id"]
        return OnchainBatch(
            merkle_root=bytes.fromhex(batch["merkle_root"]),
            event_count=batch["event_count"],
            metadata_hash=b"\x01" * 32,
            anchored_at=FAKE_CHAIN_TIMESTAMP,
            anchored_by=ANCHOR_SENDER,
        )

    monkeypatch.setattr("app.batch_anchoring.load_anchoring_config", _fake_anchoring_config)
    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fake_anchor_batch)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.wait_for_transaction_receipt",
        fake_wait_for_transaction_receipt,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        fake_get_onchain_batch,
    )
    return anchor_calls


def test_get_anchor_returns_404_before_anchoring():
    batch = _create_batch()

    response = client.get(f"/audit/batches/{batch['batch_id']}/anchor")

    assert response.status_code == 404


def test_post_anchor_returns_404_for_missing_batch(monkeypatch):
    _install_anchor_mocks(monkeypatch, {"batch_id": "unused", "merkle_root": "a" * 64, "event_count": 1})

    response = client.post("/audit/batches/missing-batch-id/anchor")

    assert response.status_code == 404


def test_post_anchor_stores_record_when_anchoring_succeeds(monkeypatch):
    batch = _create_batch()
    anchor_calls = _install_anchor_mocks(monkeypatch, batch)

    response = client.post(f"/audit/batches/{batch['batch_id']}/anchor")

    assert response.status_code == 200
    body = response.json()
    assert body["already_anchored"] is False
    assert body["batch_id"] == batch["batch_id"]
    assert body["anchor_address"] == ANCHOR_CONTRACT
    assert body["tx_hash"] == FAKE_TX_HASH
    assert body["block_number"] == FAKE_BLOCK_NUMBER
    assert body["anchored_at"] == FAKE_CHAIN_TIMESTAMP
    assert body["anchored_by"] == ANCHOR_SENDER
    assert body["chain_id"] == 31337
    assert len(anchor_calls) == 1


def test_post_anchor_is_idempotent(monkeypatch):
    batch = _create_batch()
    anchor_calls = _install_anchor_mocks(monkeypatch, batch)

    first = client.post(f"/audit/batches/{batch['batch_id']}/anchor")
    second = client.post(f"/audit/batches/{batch['batch_id']}/anchor")

    assert first.status_code == 200
    assert first.json()["already_anchored"] is False
    assert second.status_code == 200
    assert second.json()["already_anchored"] is True
    assert second.json()["tx_hash"] == first.json()["tx_hash"]
    assert len(anchor_calls) == 1


def test_get_anchor_returns_stored_record_after_anchoring(monkeypatch):
    batch = _create_batch()
    _install_anchor_mocks(monkeypatch, batch)

    post_response = client.post(f"/audit/batches/{batch['batch_id']}/anchor")
    assert post_response.status_code == 200

    get_response = client.get(f"/audit/batches/{batch['batch_id']}/anchor")

    assert get_response.status_code == 200
    stored = get_response.json()
    posted = post_response.json()
    assert stored == {
        key: value for key, value in posted.items() if key != "already_anchored"
    }
