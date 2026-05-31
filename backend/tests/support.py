from app.hashing import canonicalize_event
from app.models import AuditEvent
from app.signatures import (
    demo_did_from_public_key,
    demo_verification_method,
    generate_ed25519_keypair,
    sign_bytes,
)
from tests.conftest import TEST_ADMIN_API_KEY

TEST_PRIVATE_KEY_B64, TEST_PUBLIC_KEY_B64 = generate_ed25519_keypair()
SAMPLE_AGENT_DID = demo_did_from_public_key(TEST_PUBLIC_KEY_B64)
SAMPLE_VERIFICATION_METHOD = demo_verification_method(SAMPLE_AGENT_DID)


def sample_agent_register_payload(
    agent_did: str = SAMPLE_AGENT_DID,
    verification_method: str = SAMPLE_VERIFICATION_METHOD,
    public_key: str = TEST_PUBLIC_KEY_B64,
):
    return {
        "agent_did": agent_did,
        "agent_name": "Test Agent",
        "agent_type": "llm-agent",
        "description": "A test agent",
        "verification_method": verification_method,
        "public_key": public_key,
    }


def register_test_agent(
    client,
    agent_did: str = SAMPLE_AGENT_DID,
    public_key: str = TEST_PUBLIC_KEY_B64,
    verification_method: str = SAMPLE_VERIFICATION_METHOD,
) -> str:
    response = client.post(
        "/agents/register",
        json=sample_agent_register_payload(
            agent_did=agent_did,
            verification_method=verification_method,
            public_key=public_key,
        ),
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


def sign_event_payload(
    payload: dict,
    private_key_b64: str = TEST_PRIVATE_KEY_B64,
    verification_method: str = SAMPLE_VERIFICATION_METHOD,
) -> dict:
    event = AuditEvent.model_validate(payload)
    signature = sign_bytes(private_key_b64, canonicalize_event(event))
    return {
        **payload,
        "verification_method": verification_method,
        "signature": signature,
    }


def post_audit_event(client, payload=None, api_key: str | None = None, **payload_kwargs):
    if api_key is None:
        api_key = register_test_agent(client)
    if payload is None:
        payload = sign_event_payload(sample_event_payload(**payload_kwargs))
    elif "signature" not in payload or "verification_method" not in payload:
        payload = sign_event_payload(payload)
    return client.post(
        "/audit/events",
        json=payload,
        headers={"X-VeriAgent-API-Key": api_key},
    )
