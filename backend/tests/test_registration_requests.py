import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.hashing import canonicalize_dict
from app.main import app
from app.signatures import sign_bytes
from app.storage import expire_stale_requests, resolve_db_path
from tests.conftest import TEST_ADMIN_API_KEY
from tests.support import (
    SAMPLE_AGENT_DID,
    SAMPLE_VERIFICATION_METHOD,
    TEST_PRIVATE_KEY_B64,
    TEST_PUBLIC_KEY_B64,
    sample_agent_register_payload,
)

client = TestClient(app)


def sample_registration_request_payload(
    agent_did: str = SAMPLE_AGENT_DID,
    verification_method: str = SAMPLE_VERIFICATION_METHOD,
    public_key: str = TEST_PUBLIC_KEY_B64,
):
    return {
        **sample_agent_register_payload(
            agent_did=agent_did,
            verification_method=verification_method,
            public_key=public_key,
        ),
        "organization_name": "Acme Pilot Org",
        "contact_email": "ops@example.com",
        "use_case_summary": "Pilot audit trail integration",
    }


@pytest.fixture
def registration_enabled(monkeypatch):
    monkeypatch.setenv("VERIAGENT_REGISTRATION_ENABLED", "true")


def post_registration_request(payload=None):
    return client.post(
        "/registration/requests",
        json=payload or sample_registration_request_payload(),
    )


def sign_proof_payload(proof_payload: dict, private_key_b64: str = TEST_PRIVATE_KEY_B64) -> str:
    return sign_bytes(private_key_b64, canonicalize_dict(proof_payload))


def test_registration_disabled_by_default():
    response = post_registration_request()

    assert response.status_code == 404
    assert response.json()["detail"] == "Registration is not enabled"


def test_create_registration_request(registration_enabled):
    response = post_registration_request()

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["agent_did"] == SAMPLE_AGENT_DID
    assert body["challenge_nonce"]
    assert body["challenge_expires_at"]
    assert body["proof_payload"]["purpose"] == "veriagent-registration"
    assert body["proof_payload"]["request_id"] == body["request_id"]
    assert body["proof_payload"]["agent_did"] == SAMPLE_AGENT_DID
    assert body["proof_payload"]["nonce"] == body["challenge_nonce"]
    assert "api_key" not in body


def test_duplicate_pending_did_rejected(registration_enabled):
    first = post_registration_request()
    assert first.status_code == 200

    second = post_registration_request()
    assert second.status_code == 409
    assert "cannot be created" in second.json()["detail"]


def test_invalid_did_rejected(registration_enabled):
    response = post_registration_request(
        payload=sample_registration_request_payload(agent_did="not-a-did")
    )

    assert response.status_code == 400
    assert "did:key" in response.json()["detail"]


def test_valid_proof_submission(registration_enabled):
    create_response = post_registration_request()
    assert create_response.status_code == 200
    body = create_response.json()

    proof_signature = sign_proof_payload(body["proof_payload"])
    proof_response = client.post(
        f"/registration/requests/{body['request_id']}/proof",
        json={
            "proof_signature": proof_signature,
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
    )

    assert proof_response.status_code == 200
    proof_body = proof_response.json()
    assert proof_body["request_id"] == body["request_id"]
    assert proof_body["status"] == "pending"
    assert proof_body["proof_submitted_at"]


def test_invalid_proof_rejected(registration_enabled):
    create_response = post_registration_request()
    assert create_response.status_code == 200
    request_id = create_response.json()["request_id"]

    proof_response = client.post(
        f"/registration/requests/{request_id}/proof",
        json={
            "proof_signature": "invalid-signature",
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
    )

    assert proof_response.status_code == 403
    assert "Invalid proof signature" in proof_response.json()["detail"]


def test_expired_challenge_rejected(registration_enabled, isolated_db):
    create_response = post_registration_request()
    assert create_response.status_code == 200
    body = create_response.json()

    db_path = resolve_db_path(isolated_db)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE registration_requests
            SET challenge_expires_at = '2020-01-01T00:00:00+00:00'
            WHERE request_id = ?
            """,
            (body["request_id"],),
        )
        conn.commit()

    proof_signature = sign_proof_payload(body["proof_payload"])
    proof_response = client.post(
        f"/registration/requests/{body['request_id']}/proof",
        json={
            "proof_signature": proof_signature,
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
    )

    assert proof_response.status_code == 410
    assert "expired" in proof_response.json()["detail"].lower()

    status_response = client.get(f"/registration/requests/{body['request_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "expired"


def test_registration_status_polling(registration_enabled):
    create_response = post_registration_request()
    assert create_response.status_code == 200
    body = create_response.json()

    pending_status = client.get(f"/registration/requests/{body['request_id']}")
    assert pending_status.status_code == 200
    pending_body = pending_status.json()
    assert pending_body["status"] == "pending"
    assert pending_body["request_id"] == body["request_id"]
    assert pending_body["agent_did"] == SAMPLE_AGENT_DID
    assert pending_body["challenge_expires_at"]
    assert pending_body["proof_submitted_at"] is None
    assert "api_key" not in pending_body
    assert "challenge_nonce" not in pending_body
    assert "proof_payload" not in pending_body

    proof_signature = sign_proof_payload(body["proof_payload"])
    proof_response = client.post(
        f"/registration/requests/{body['request_id']}/proof",
        json={
            "proof_signature": proof_signature,
            "verification_method": SAMPLE_VERIFICATION_METHOD,
        },
    )
    assert proof_response.status_code == 200

    proved_status = client.get(f"/registration/requests/{body['request_id']}")
    assert proved_status.status_code == 200
    proved_body = proved_status.json()
    assert proved_body["status"] == "pending"
    assert proved_body["proof_submitted_at"]
    assert "api_key" not in proved_body


def test_expire_stale_requests_marks_pending_requests(isolated_db, registration_enabled):
    create_response = post_registration_request()
    assert create_response.status_code == 200
    request_id = create_response.json()["request_id"]

    db_path = resolve_db_path(isolated_db)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE registration_requests
            SET challenge_expires_at = '2020-01-01T00:00:00+00:00'
            WHERE request_id = ?
            """,
            (request_id,),
        )
        conn.commit()

    expired_count = expire_stale_requests(db_path=db_path)
    assert expired_count == 1

    status_response = client.get(f"/registration/requests/{request_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "expired"


def test_create_request_rejects_already_registered_agent(registration_enabled):
    admin_response = client.post(
        "/agents/register",
        json=sample_agent_register_payload(),
        headers={"X-VeriAgent-Admin-Key": TEST_ADMIN_API_KEY},
    )
    assert admin_response.status_code == 200

    response = post_registration_request()
    assert response.status_code == 409


def test_invalid_verification_method_on_proof(registration_enabled):
    create_response = post_registration_request()
    assert create_response.status_code == 200
    body = create_response.json()

    proof_signature = sign_proof_payload(body["proof_payload"])
    proof_response = client.post(
        f"/registration/requests/{body['request_id']}/proof",
        json={
            "proof_signature": proof_signature,
            "verification_method": f"{SAMPLE_AGENT_DID}#wrong-fragment",
        },
    )

    assert proof_response.status_code == 403
    assert "verification_method" in proof_response.json()["detail"]
