from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_audit_hash_endpoint():
    payload = {
        "event_id": "event-001",
        "agent_id": "agent-001",
        "task_id": "task-001",
        "model_name": "demo-model",
        "tool_calls": ["search", "calculator"],
        "input_hash": "sha256:input123",
        "output_hash": "sha256:output456",
        "policy_version": "policy-v0.1",
        "timestamp": "2026-05-26T18:00:00Z",
        "metadata": {"purpose": "api-test"},
    }

    response = client.post("/audit/hash", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "event-001"
    assert len(body["event_hash"]) == 64
    assert body["canonicalization"] == "RFC8785-JCS"