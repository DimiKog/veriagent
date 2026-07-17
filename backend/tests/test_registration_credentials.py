import pytest
from fastapi.testclient import TestClient

from app.hashing import canonicalize_dict
from app.main import app
from app.registration import build_credentials_claim_payload
from app.signatures import sign_bytes
from tests.support import (
    SAMPLE_AGENT_DID,
    SAMPLE_VERIFICATION_METHOD,
    TEST_PRIVATE_KEY_B64,
    admin_request_headers,
    sample_agent_register_payload,
)

client = TestClient(app)


def sample_registration_request_payload():
    return {
        **sample_agent_register_payload(),
        "organization_name": "Acme Pilot Org",
        "contact_email": "ops@example.com",
        "use_case_summary": "Pilot audit trail integration",
    }


@pytest.fixture
def registration_enabled(monkeypatch):
    monkeypatch.setenv("VERIAGENT_REGISTRATION_ENABLED", "true")


def create_and_prove_registration_request():
    create_response = client.post(
        "/registration/requests",
        json=sample_registration_request_payload(),
    )
    assert create_response.status_code == 200
    body = create_response.json()
    proof_signature = sign_bytes(
        TEST_PRIVATE_KEY_B64,
        canonicalize_dict(body["proof_payload"]),
    )
    proof_response = client.post(
        f"/registration/requests/{body['request_id']}/proof",
        json={
            "proof_signature": proof_signature,
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
    )
    assert proof_response.status_code == 200
    return body["request_id"]


def approve_registration(request_id: str) -> dict:
    response = client.post(
        f"/registration/requests/{request_id}/approve",
        json={},
        headers=admin_request_headers(),
    )
    assert response.status_code == 200
    return response.json()


def sign_credentials_claim(request_id: str, agent_did: str = SAMPLE_AGENT_DID) -> str:
    payload = build_credentials_claim_payload(request_id, agent_did)
    return sign_bytes(TEST_PRIVATE_KEY_B64, canonicalize_dict(payload))


def test_approve_sets_credentials_available_on_status(registration_enabled):
    request_id = create_and_prove_registration_request()
    approve_body = approve_registration(request_id)

    assert "api_key" not in approve_body
    assert approve_body["retrieval_token"].startswith("vrt_")

    status_response = client.get(f"/registration/requests/{request_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "approved"
    assert status_body["credentials_available"] is True
    assert status_body["credentials_claimed"] is False
    assert status_body["credentials_claimed_at"] is None
    assert "api_key" not in status_body
    assert "retrieval_token" not in status_body


def test_claim_with_valid_signature_returns_api_key_once(registration_enabled):
    request_id = create_and_prove_registration_request()
    approve_registration(request_id)

    claim_response = client.post(
        f"/registration/requests/{request_id}/credentials",
        json={
            "proof_signature": sign_credentials_claim(request_id),
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
    )
    assert claim_response.status_code == 200
    claim_body = claim_response.json()
    assert claim_body["request_id"] == request_id
    assert claim_body["agent_did"] == SAMPLE_AGENT_DID
    assert claim_body["api_key"].startswith("va_agent_")
    assert claim_body["agent_status"] == "active"
    assert claim_body["verification_method"] == SAMPLE_VERIFICATION_METHOD

    status_response = client.get(f"/registration/requests/{request_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["credentials_available"] is False
    assert status_body["credentials_claimed"] is True
    assert status_body["credentials_claimed_at"] is not None


def test_second_claim_fails(registration_enabled):
    request_id = create_and_prove_registration_request()
    approve_registration(request_id)
    claim_payload = {
        "proof_signature": sign_credentials_claim(request_id),
        "verification_method": SAMPLE_VERIFICATION_METHOD,
    }

    first = client.post(
        f"/registration/requests/{request_id}/credentials",
        json=claim_payload,
    )
    assert first.status_code == 200

    second = client.post(
        f"/registration/requests/{request_id}/credentials",
        json=claim_payload,
    )
    assert second.status_code == 409
    assert "already claimed" in second.json()["detail"].lower()


def test_invalid_signature_returns_403(registration_enabled):
    request_id = create_and_prove_registration_request()
    approve_registration(request_id)

    response = client.post(
        f"/registration/requests/{request_id}/credentials",
        json={
            "proof_signature": "invalid-signature",
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
    )
    assert response.status_code == 403
    assert "Invalid proof signature" in response.json()["detail"]


def test_claim_with_matching_retrieval_token_succeeds(registration_enabled):
    request_id = create_and_prove_registration_request()
    approve_body = approve_registration(request_id)

    response = client.post(
        f"/registration/requests/{request_id}/credentials",
        json={
            "proof_signature": sign_credentials_claim(request_id),
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
        headers={
            "X-VeriAgent-Retrieval-Token": approve_body["retrieval_token"],
        },
    )
    assert response.status_code == 200
    assert response.json()["api_key"].startswith("va_agent_")
    assert "api_key" not in approve_body


def test_claim_with_invalid_retrieval_token_returns_403(registration_enabled):
    request_id = create_and_prove_registration_request()
    approve_registration(request_id)

    response = client.post(
        f"/registration/requests/{request_id}/credentials",
        json={
            "proof_signature": sign_credentials_claim(request_id),
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
        headers={"X-VeriAgent-Retrieval-Token": "vrt_invalid-token"},
    )
    assert response.status_code == 403
    assert "Invalid retrieval token" in response.json()["detail"]
