from tests.conftest import TEST_ADMIN_API_KEY

SAMPLE_AGENT_DID = "did:key:z6MkhaXgBZDv9FIm5N9EJ9R9Bz"
SAMPLE_VERIFICATION_METHOD = f"{SAMPLE_AGENT_DID}#z6MkhaXgBZDv9FIm5N9EJ9R9Bz"


def sample_agent_register_payload(
    agent_did: str = SAMPLE_AGENT_DID,
    verification_method: str = SAMPLE_VERIFICATION_METHOD,
):
    return {
        "agent_did": agent_did,
        "agent_name": "Test Agent",
        "agent_type": "llm-agent",
        "description": "A test agent",
        "verification_method": verification_method,
        "public_key": "z6MkhaXgBZDv9FIm5N9EJ9R9Bz",
    }


def register_test_agent(client, agent_did: str = SAMPLE_AGENT_DID) -> str:
    response = client.post(
        "/agents/register",
        json=sample_agent_register_payload(agent_did=agent_did),
        headers={"X-VeriAgent-Admin-Key": TEST_ADMIN_API_KEY},
    )
    assert response.status_code == 200, response.text
    return response.json()["api_key"]


def sample_event_payload(
    event_id: str = "event-001",
    agent_id: str = SAMPLE_AGENT_DID,
    output_hash: str = "sha256:output456",
):
    return {
        "event_id": event_id,
        "agent_id": agent_id,
        "task_id": "task-001",
        "model_name": "demo-model",
        "tool_calls": ["search", "calculator"],
        "input_hash": "sha256:input123",
        "output_hash": output_hash,
        "policy_version": "policy-v0.1",
        "timestamp": "2026-05-26T18:00:00Z",
        "metadata": {"purpose": "api-test"},
    }


def post_audit_event(client, payload=None, api_key: str | None = None, **payload_kwargs):
    if api_key is None:
        api_key = register_test_agent(client)
    if payload is None:
        payload = sample_event_payload(**payload_kwargs)
    return client.post(
        "/audit/events",
        json=payload,
        headers={"X-VeriAgent-API-Key": api_key},
    )
