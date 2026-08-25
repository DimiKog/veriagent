import json

from eth_typing import ChecksumAddress
from fastapi.testclient import TestClient

from app.anchoring import AnchoringConfig, OnchainBatch
from app.main import app
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
FAKE_BLOCK_NUMBER = 42
FAKE_CHAIN_TIMESTAMP = 1_700_000_000

EXPECTED_FIELDS = {
    "event_id",
    "event_hash",
    "created_at",
    "batched",
    "batch_id",
    "merkle_root",
    "anchored",
    "tx_hash",
    "block_number",
    "chain_id",
    "anchored_at",
    "anchored_by",
}

SECRET_MARKERS = (
    "canonical_event_json",
    "signature",
    "verification_method",
    "api_key",
    "va_agent_",
    "super-secret-receipt-value",
    "super-secret-admin-value",
    "0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
    "organization_name",
    "contact_email",
    "challenge_nonce",
    "retrieval_token",
)


def _install_anchor_mocks(monkeypatch, batch: dict):
    def fake_anchor_batch(batch_id, merkle_root, event_count, metadata_hash, **kwargs):
        return FAKE_TX_HASH

    def fake_wait_for_transaction_receipt(tx_hash, **kwargs):
        return {"blockNumber": FAKE_BLOCK_NUMBER, "status": 1}

    def fake_get_onchain_batch(batch_id, **kwargs):
        return OnchainBatch(
            merkle_root=bytes.fromhex(batch["merkle_root"]),
            event_count=batch["event_count"],
            metadata_hash=b"\x01" * 32,
            anchored_at=FAKE_CHAIN_TIMESTAMP,
            anchored_by=ANCHOR_SENDER,
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
    monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fake_anchor_batch)
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.wait_for_transaction_receipt",
        fake_wait_for_transaction_receipt,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.get_onchain_batch",
        fake_get_onchain_batch,
    )
    monkeypatch.setattr(
        "app.batch_anchoring.anchoring.is_batch_anchored",
        lambda *_a, **_k: False,
    )


def test_event_status_unknown_event_returns_404():
    response = client.get("/audit/events/missing-event/status")

    assert response.status_code == 404
    assert "missing-event" in response.json()["detail"]


def test_event_status_unbatched_event():
    api_key = register_test_agent(client)
    event_id = "event-status-unbatched"
    store_response = post_audit_event(
        client,
        payload=sample_event_payload(event_id=event_id),
        api_key=api_key,
    )
    assert store_response.status_code == 200
    stored = store_response.json()

    response = client.get(f"/audit/events/{event_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == EXPECTED_FIELDS
    assert body["event_id"] == event_id
    assert body["event_hash"] == stored["event_hash"]
    assert body["created_at"] == stored["created_at"]
    assert body["batched"] is False
    assert body["anchored"] is False
    assert body["batch_id"] is None
    assert body["merkle_root"] is None
    assert body["tx_hash"] is None
    assert body["block_number"] is None
    assert body["chain_id"] is None
    assert body["anchored_at"] is None
    assert body["anchored_by"] is None


def test_event_status_batched_unanchored_event():
    api_key = register_test_agent(client)
    event_id = "event-status-batched"
    post_audit_event(
        client,
        payload=sample_event_payload(event_id=event_id),
        api_key=api_key,
    )
    batch = post_audit_batch(client).json()

    response = client.get(f"/audit/events/{event_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["batched"] is True
    assert body["anchored"] is False
    assert body["batch_id"] == batch["batch_id"]
    assert body["merkle_root"] == batch["merkle_root"]
    assert body["tx_hash"] is None
    assert body["block_number"] is None
    assert body["chain_id"] is None
    assert body["anchored_at"] is None
    assert body["anchored_by"] is None


def test_event_status_anchored_event(monkeypatch):
    api_key = register_test_agent(client)
    event_id = "event-status-anchored"
    post_audit_event(
        client,
        payload=sample_event_payload(event_id=event_id),
        api_key=api_key,
    )
    batch = post_audit_batch(client).json()
    _install_anchor_mocks(monkeypatch, batch)

    anchor_response = post_batch_anchor(client, batch["batch_id"])
    assert anchor_response.status_code == 200
    anchored = anchor_response.json()

    response = client.get(f"/audit/events/{event_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["batched"] is True
    assert body["anchored"] is True
    assert body["batch_id"] == batch["batch_id"]
    assert body["merkle_root"] == batch["merkle_root"]
    assert body["tx_hash"] == anchored["tx_hash"]
    assert body["block_number"] == anchored["block_number"]
    assert body["chain_id"] == anchored["chain_id"]
    assert body["anchored_at"] == anchored["anchored_at"]
    assert body["anchored_by"] == anchored["anchored_by"]


def test_event_status_does_not_expose_secrets(monkeypatch):
    api_key = register_test_agent(client)
    event_id = "event-status-secrets"
    post_audit_event(
        client,
        payload=sample_event_payload(event_id=event_id),
        api_key=api_key,
    )
    batch = post_audit_batch(client).json()
    _install_anchor_mocks(monkeypatch, batch)
    post_batch_anchor(client, batch["batch_id"])

    monkeypatch.setenv("VERIAGENT_RECEIPT_SECRET", "super-secret-receipt-value")
    monkeypatch.setenv("VERIAGENT_ADMIN_API_KEY", "super-secret-admin-value")

    response = client.get(f"/audit/events/{event_id}/status")
    assert response.status_code == 200

    payload = json.dumps(response.json())
    for marker in SECRET_MARKERS:
        assert marker not in payload

    get_event_response = client.get(f"/audit/events/{event_id}")
    assert "canonical_event_json" in get_event_response.json()
    assert "canonical_event_json" not in response.json()
    assert api_key not in payload
