from fastapi.testclient import TestClient

from app.main import app
from app.hashing import hash_event
from app.models import AuditEvent

client = TestClient(app)


def sample_event_payload(event_id: str = "event-001", output_hash: str = "sha256:output456"):
    return {
        "event_id": event_id,
        "agent_id": "agent-001",
        "task_id": "task-001",
        "model_name": "demo-model",
        "tool_calls": ["search", "calculator"],
        "input_hash": "sha256:input123",
        "output_hash": output_hash,
        "policy_version": "policy-v0.1",
        "timestamp": "2026-05-26T18:00:00Z",
        "metadata": {"purpose": "api-test"},
    }


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.2.0"


def test_audit_hash_endpoint():
    response = client.post("/audit/hash", json=sample_event_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "event-001"
    assert len(body["event_hash"]) == 64
    assert body["canonicalization"] == "RFC8785-JCS"


def test_store_and_get_audit_event():
    payload = sample_event_payload()

    store_response = client.post("/audit/events", json=payload)
    assert store_response.status_code == 200
    stored = store_response.json()
    assert stored["event_id"] == "event-001"
    assert len(stored["event_hash"]) == 64
    assert stored["canonical_event_json"]
    assert stored["created_at"]

    get_response = client.get("/audit/events/event-001")
    assert get_response.status_code == 200
    retrieved = get_response.json()
    assert retrieved["event_id"] == stored["event_id"]
    assert retrieved["event_hash"] == stored["event_hash"]
    assert retrieved["canonical_event_json"] == stored["canonical_event_json"]
    assert retrieved["created_at"] == stored["created_at"]


def test_store_duplicate_event_returns_409():
    payload = sample_event_payload(event_id="event-dup")

    assert client.post("/audit/events", json=payload).status_code == 200
    assert client.post("/audit/events", json=payload).status_code == 409


def test_get_missing_event_returns_404():
    response = client.get("/audit/events/missing-event")

    assert response.status_code == 404


def test_verify_matching_event():
    payload = sample_event_payload(event_id="event-verify-ok")
    client.post("/audit/events", json=payload)

    response = client.post("/audit/verify", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["computed_hash"] == body["stored_hash"]
    assert len(body["computed_hash"]) == 64


def test_verify_tampered_event():
    payload = sample_event_payload(event_id="event-verify-fail")
    client.post("/audit/events", json=payload)

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