import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.receipts import verify_receipt
from tests.conftest import TEST_RECEIPT_SECRET
from tests.support import (
    SAMPLE_AGENT_DID,
    post_audit_event,
    register_test_agent,
    sample_event_payload,
)

client = TestClient(app)


def test_post_audit_event_without_api_key_returns_401():
    response = client.post("/audit/events", json=sample_event_payload())

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing agent API key"


def test_post_audit_event_invalid_api_key_returns_401():
    response = post_audit_event(client, api_key="va_agent_invalid-key")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing agent API key"


def test_post_audit_event_valid_agent_key_stores_event():
    api_key = register_test_agent(client)
    payload = sample_event_payload(event_id="event-auth-ok")

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "event-auth-ok"
    assert len(body["event_hash"]) == 64
    assert body["created_at"]
    assert verify_receipt(
        event_id=body["receipt"]["event_id"],
        event_hash=body["receipt"]["event_hash"],
        created_at=body["receipt"]["created_at"],
        signature=body["receipt"]["signature"],
        secret=TEST_RECEIPT_SECRET,
    )


def test_post_audit_event_agent_id_mismatch_returns_403():
    api_key = register_test_agent(client)
    payload = sample_event_payload(agent_id="did:key:other-agent")

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 403
    assert "agent_id" in response.json()["detail"]


def test_post_audit_event_inactive_agent_key_returns_403(isolated_db):
    api_key = register_test_agent(client)

    with sqlite3.connect(isolated_db) as conn:
        conn.execute(
            "UPDATE agents SET status = 'inactive' WHERE agent_did = ?",
            (SAMPLE_AGENT_DID,),
        )
        conn.commit()

    response = post_audit_event(
        client,
        payload=sample_event_payload(event_id="event-inactive-agent"),
        api_key=api_key,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Agent is not active"


def test_public_read_and_verify_endpoints_still_work_without_agent_key():
    api_key = register_test_agent(client)
    payload = sample_event_payload(event_id="event-public-read")

    store_response = post_audit_event(client, payload=payload, api_key=api_key)
    assert store_response.status_code == 200

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["version"] == "0.9B"

    hash_response = client.post("/audit/hash", json=payload)
    assert hash_response.status_code == 200

    get_response = client.get("/audit/events/event-public-read")
    assert get_response.status_code == 200
    assert get_response.json()["event_id"] == "event-public-read"

    verify_response = client.post("/audit/verify", json=payload)
    assert verify_response.status_code == 200
    assert verify_response.json()["verified"] is True

    batch_response = client.post("/audit/batches")
    assert batch_response.status_code == 200
    batch = batch_response.json()

    get_batch_response = client.get(f"/audit/batches/{batch['batch_id']}")
    assert get_batch_response.status_code == 200

    proof_response = client.get(
        f"/audit/batches/{batch['batch_id']}/proof/event-public-read"
    )
    assert proof_response.status_code == 200

    merkle_response = client.post(
        "/audit/merkle/verify",
        json={
            "event_hash": proof_response.json()["event_hash"],
            "merkle_root": batch["merkle_root"],
            "proof": proof_response.json()["proof"],
        },
    )
    assert merkle_response.status_code == 200
    assert merkle_response.json()["verified"] is True
