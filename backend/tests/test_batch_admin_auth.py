from eth_typing import ChecksumAddress

from fastapi.testclient import TestClient

from app.anchoring import OnchainBatch
from app.main import app
from tests.conftest import TEST_ADMIN_API_KEY
from tests.support import (
    post_audit_batch,
    post_audit_event,
    post_batch_anchor,
    register_test_agent,
    sample_event_payload,
)

client = TestClient(app)

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
FAKE_TX_HASH = "0x" + "ab" * 32


def _store_event(event_id: str = "event-admin-batch") -> None:
    api_key = register_test_agent(client)
    response = post_audit_event(
        client,
        payload=sample_event_payload(event_id=event_id),
        api_key=api_key,
    )
    assert response.status_code == 200


def _create_batch() -> dict:
    _store_event()
    response = post_audit_batch(client)
    assert response.status_code == 200
    return response.json()


def test_create_batch_missing_admin_key_returns_401():
    _store_event()

    response = client.post("/audit/batches")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing admin API key"


def test_create_batch_invalid_admin_key_returns_401():
    _store_event()

    response = post_audit_batch(client, admin_key="wrong-admin-key")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing admin API key"


def test_create_batch_valid_admin_key_succeeds():
    _store_event()

    response = post_audit_batch(client, admin_key=TEST_ADMIN_API_KEY)

    assert response.status_code == 200
    body = response.json()
    assert body["event_count"] == 1
    assert len(body["merkle_root"]) == 64


def test_anchor_batch_missing_admin_key_returns_401():
    batch = _create_batch()

    response = client.post(f"/audit/batches/{batch['batch_id']}/anchor")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing admin API key"


def test_anchor_batch_invalid_admin_key_returns_401():
    batch = _create_batch()

    response = post_batch_anchor(client, batch["batch_id"], admin_key="wrong-admin-key")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing admin API key"


def test_anchor_batch_valid_admin_key_succeeds(monkeypatch):
    batch = _create_batch()

    def fake_anchor_batch(batch_id, merkle_root, event_count, metadata_hash, **kwargs):
        return FAKE_TX_HASH

    def fake_wait_for_transaction_receipt(tx_hash, **kwargs):
        return {"blockNumber": 42, "status": 1}

    def fake_get_onchain_batch(batch_id, **kwargs):
        return OnchainBatch(
            merkle_root=bytes.fromhex(batch["merkle_root"]),
            event_count=batch["event_count"],
            metadata_hash=b"\x01" * 32,
            anchored_at=1_700_000_000,
            anchored_by=ANCHOR_SENDER,
        )

    def fake_anchoring_config():
        from app.anchoring import AnchoringConfig

        return AnchoringConfig(
            rpc_url="http://127.0.0.1:8545",
            chain_id=31337,
            contract_address=ANCHOR_CONTRACT,
            private_key="0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
        )

    monkeypatch.setattr("app.batch_anchoring.load_anchoring_config", fake_anchoring_config)
    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fake_anchor_batch)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.wait_for_transaction_receipt",
        fake_wait_for_transaction_receipt,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        fake_get_onchain_batch,
    )

    response = post_batch_anchor(client, batch["batch_id"], admin_key=TEST_ADMIN_API_KEY)

    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"] == batch["batch_id"]
    assert body["tx_hash"] == FAKE_TX_HASH
    assert body["already_anchored"] is False
