from fastapi.testclient import TestClient

from app.main import app
from app.hashing import hash_event
from app.models import AuditEvent
from app.receipts import verify_receipt
from tests.conftest import TEST_RECEIPT_SECRET
from tests.support import post_audit_event, register_test_agent, sample_event_payload, SAMPLE_VERIFICATION_METHOD

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.9.6"


def test_audit_hash_endpoint():
    response = client.post("/audit/hash", json=sample_event_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "event-001"
    assert len(body["event_hash"]) == 64
    assert body["canonicalization"] == "RFC8785-JCS"


def test_store_and_get_audit_event():
    api_key = register_test_agent(client)
    payload = sample_event_payload()

    store_response = post_audit_event(client, payload=payload, api_key=api_key)
    assert store_response.status_code == 200
    stored = store_response.json()
    assert stored["event_id"] == "event-001"
    assert len(stored["event_hash"]) == 64
    assert stored["created_at"]
    assert "canonical_event_json" not in stored

    receipt = stored["receipt"]
    assert receipt["event_id"] == stored["event_id"]
    assert receipt["event_hash"] == stored["event_hash"]
    assert receipt["created_at"] == stored["created_at"]
    assert receipt["algorithm"] == "HMAC-SHA256"
    assert len(receipt["signature"]) == 64
    assert verify_receipt(
        event_id=receipt["event_id"],
        event_hash=receipt["event_hash"],
        created_at=receipt["created_at"],
        signature=receipt["signature"],
        secret=TEST_RECEIPT_SECRET,
    )

    get_response = client.get("/audit/events/event-001")
    assert get_response.status_code == 200
    retrieved = get_response.json()
    assert retrieved["event_id"] == stored["event_id"]
    assert retrieved["event_hash"] == stored["event_hash"]
    assert retrieved["created_at"] == stored["created_at"]
    assert retrieved["canonical_event_json"]
    assert retrieved["verification_method"] == SAMPLE_VERIFICATION_METHOD
    assert retrieved["signature_algorithm"] == "Ed25519"


def test_store_duplicate_event_returns_409():
    api_key = register_test_agent(client)
    payload = sample_event_payload(event_id="event-dup")

    assert post_audit_event(client, payload=payload, api_key=api_key).status_code == 200
    assert post_audit_event(client, payload=payload, api_key=api_key).status_code == 409


def test_get_missing_event_returns_404():
    response = client.get("/audit/events/missing-event")

    assert response.status_code == 404


def test_verify_matching_event():
    api_key = register_test_agent(client)
    payload = sample_event_payload(event_id="event-verify-ok")
    post_audit_event(client, payload=payload, api_key=api_key)

    response = client.post("/audit/verify", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["computed_hash"] == body["stored_hash"]
    assert len(body["computed_hash"]) == 64


def test_verify_tampered_event():
    api_key = register_test_agent(client)
    payload = sample_event_payload(event_id="event-verify-fail")
    post_audit_event(client, payload=payload, api_key=api_key)

    tampered = sample_event_payload(
        event_id="event-verify-fail",
        output_hash="sha256:tampered-output",
    )
    response = client.post("/audit/verify", json=tampered)

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is False
    assert body["computed_hash"] != body["stored_hash"]

    original = AuditEvent.model_validate(payload)
    assert body["stored_hash"] == hash_event(original)


def test_verify_missing_event_returns_404():
    response = client.post("/audit/verify", json=sample_event_payload(event_id="missing"))

    assert response.status_code == 404
