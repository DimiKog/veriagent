from fastapi.testclient import TestClient

from app.auth import AGENT_API_KEY_PREFIX, hash_agent_api_key
from app.main import app
from tests.conftest import TEST_ADMIN_API_KEY

client = TestClient(app)

SAMPLE_AGENT_DID = "did:key:z6MkhaXgBZDv9FIm5N9EJ9R9Bz"
SAMPLE_VERIFICATION_METHOD = f"{SAMPLE_AGENT_DID}#z6MkhaXgBZDv9FIm5N9EJ9R9Bz"


def sample_agent_payload(
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


def register_agent_request(payload=None, admin_key=TEST_ADMIN_API_KEY):
    return client.post(
        "/agents/register",
        json=payload or sample_agent_payload(),
        headers={"X-VeriAgent-Admin-Key": admin_key},
    )


def test_register_agent_success():
    response = register_agent_request()

    assert response.status_code == 200
    body = response.json()
    assert body["agent_did"] == SAMPLE_AGENT_DID
    assert body["agent_name"] == "Test Agent"
    assert body["agent_type"] == "llm-agent"
    assert body["description"] == "A test agent"
    assert body["verification_method"] == SAMPLE_VERIFICATION_METHOD
    assert body["public_key"] == "z6MkhaXgBZDv9FIm5N9EJ9R9Bz"
    assert body["status"] == "active"
    assert body["created_at"]
    assert body["api_key"].startswith(AGENT_API_KEY_PREFIX)
    assert "api_key_hash" not in body


def test_register_agent_missing_admin_key_rejected():
    response = client.post("/agents/register", json=sample_agent_payload())

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing admin API key"


def test_register_agent_invalid_admin_key_rejected():
    response = register_agent_request(admin_key="wrong-admin-key")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing admin API key"


def test_register_agent_duplicate_did_rejected():
    first = register_agent_request()
    assert first.status_code == 200

    second = register_agent_request()
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"]


def test_register_agent_invalid_did_rejected():
    response = register_agent_request(
        payload=sample_agent_payload(agent_did="not-a-did")
    )

    assert response.status_code == 400
    assert "did:key:" in response.json()["detail"]


def test_register_agent_invalid_verification_method_rejected():
    response = register_agent_request(
        payload=sample_agent_payload(
            verification_method="did:key:other#fragment"
        )
    )

    assert response.status_code == 400
    assert "verification_method" in response.json()["detail"]


def test_get_agent_returns_metadata_without_api_key_hash():
    register_response = register_agent_request()
    assert register_response.status_code == 200

    get_response = client.get(
        f"/agents/{SAMPLE_AGENT_DID}",
        headers={"X-VeriAgent-Admin-Key": TEST_ADMIN_API_KEY},
    )

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["agent_did"] == SAMPLE_AGENT_DID
    assert body["agent_name"] == "Test Agent"
    assert body["status"] == "active"
    assert "api_key" not in body
    assert "api_key_hash" not in body


def test_get_missing_agent_returns_404():
    response = client.get(
        "/agents/did:key:missing-agent",
        headers={"X-VeriAgent-Admin-Key": TEST_ADMIN_API_KEY},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_register_agent_stores_api_key_hash_not_raw_key():
    response = register_agent_request()
    assert response.status_code == 200

    api_key = response.json()["api_key"]
    from app.storage import get_agent

    stored = get_agent(SAMPLE_AGENT_DID)
    assert stored is not None
    assert stored.api_key_hash == hash_agent_api_key(api_key)
    assert stored.api_key_hash != api_key
