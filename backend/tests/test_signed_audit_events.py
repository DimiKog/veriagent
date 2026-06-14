import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.receipts import verify_receipt
from app.signatures import (
    SIGNATURE_ALGORITHM,
    ed25519_public_key_to_did_key,
    generate_ed25519_keypair,
    sign_bytes,
    verification_method_for_did_key,
)
from app.storage import get_audit_event
from tests.conftest import TEST_RECEIPT_SECRET
from tests.support import (
    SAMPLE_AGENT_DID,
    SAMPLE_VERIFICATION_METHOD,
    TEST_PRIVATE_KEY_B64,
    TEST_PUBLIC_KEY_B64,
    post_audit_batch,
    post_audit_event,
    register_test_agent,
    sample_event_payload,
    sign_event_payload,
)

client = TestClient(app)


def test_valid_signature_accepted():
    api_key = register_test_agent(client)
    payload = sign_event_payload(sample_event_payload(event_id="event-signed-ok"))

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "event-signed-ok"
    assert verify_receipt(
        event_id=body["receipt"]["event_id"],
        event_hash=body["receipt"]["event_hash"],
        created_at=body["receipt"]["created_at"],
        signature=body["receipt"]["signature"],
        secret=TEST_RECEIPT_SECRET,
    )


def test_tampered_event_rejected():
    api_key = register_test_agent(client)
    payload = sign_event_payload(sample_event_payload(event_id="event-tampered"))
    payload["output_hash"] = "sha256:tampered-output"

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid event signature"


def test_wrong_signature_rejected():
    api_key = register_test_agent(client)
    payload = sign_event_payload(sample_event_payload(event_id="event-wrong-sig"))
    payload["signature"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid event signature"


def test_wrong_public_key_rejected():
    _, other_public_key = generate_ed25519_keypair()
    other_agent_did = ed25519_public_key_to_did_key(other_public_key)
    other_verification_method = verification_method_for_did_key(other_agent_did)
    api_key = register_test_agent(
        client,
        agent_did=other_agent_did,
        public_key=other_public_key,
        verification_method=other_verification_method,
    )
    payload = sign_event_payload(
        sample_event_payload(
            event_id="event-wrong-key",
            agent_id=other_agent_did,
        ),
        private_key_b64=TEST_PRIVATE_KEY_B64,
        verification_method=other_verification_method,
    )

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid event signature"


def test_wrong_verification_method_rejected():
    api_key = register_test_agent(client)
    payload = sign_event_payload(
        sample_event_payload(event_id="event-wrong-vm"),
        verification_method=f"{SAMPLE_AGENT_DID}#wrong-key",
    )

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 403
    assert "verification_method" in response.json()["detail"]


def test_missing_signature_rejected():
    api_key = register_test_agent(client)
    payload = sample_event_payload(event_id="event-no-signature")

    response = client.post(
        "/audit/events",
        json=payload,
        headers={"X-VeriAgent-API-Key": api_key},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "signature is required"


def test_missing_verification_method_rejected():
    api_key = register_test_agent(client)
    payload = sign_event_payload(sample_event_payload(event_id="event-no-vm"))
    del payload["verification_method"]

    response = client.post(
        "/audit/events",
        json=payload,
        headers={"X-VeriAgent-API-Key": api_key},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "verification_method is required"


def test_stored_event_exposes_signature_metadata():
    api_key = register_test_agent(client)
    payload = sign_event_payload(sample_event_payload(event_id="event-metadata"))

    store_response = post_audit_event(client, payload=payload, api_key=api_key)
    assert store_response.status_code == 200

    stored = get_audit_event("event-metadata")
    assert stored is not None
    assert stored.signature == payload["signature"]
    assert stored.verification_method == SAMPLE_VERIFICATION_METHOD
    assert stored.signature_algorithm == SIGNATURE_ALGORITHM

    get_response = client.get("/audit/events/event-metadata")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["verification_method"] == SAMPLE_VERIFICATION_METHOD
    assert body["signature_algorithm"] == SIGNATURE_ALGORITHM
    assert "signature" not in body
    assert "public_key" not in body


def test_receipt_generation_still_works():
    api_key = register_test_agent(client)
    payload = sign_event_payload(sample_event_payload(event_id="event-receipt"))

    response = post_audit_event(client, payload=payload, api_key=api_key)

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["algorithm"] == "HMAC-SHA256"
    assert verify_receipt(
        event_id=receipt["event_id"],
        event_hash=receipt["event_hash"],
        created_at=receipt["created_at"],
        signature=receipt["signature"],
        secret=TEST_RECEIPT_SECRET,
    )


def test_batching_still_works():
    api_key = register_test_agent(client)
    payload = sign_event_payload(sample_event_payload(event_id="event-batch-signed"))

    store_response = post_audit_event(client, payload=payload, api_key=api_key)
    assert store_response.status_code == 200

    batch_response = post_audit_batch(client)
    assert batch_response.status_code == 200
    batch = batch_response.json()
    assert store_response.json()["event_hash"] in batch["event_hashes"]

    proof_response = client.get(
        f"/audit/batches/{batch['batch_id']}/proof/event-batch-signed"
    )
    assert proof_response.status_code == 200
