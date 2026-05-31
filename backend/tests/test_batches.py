from fastapi.testclient import TestClient

from app.main import app
from app.merkle import merkle_proof, verify_inclusion_proof
from tests.support import post_audit_event, register_test_agent, sample_event_payload

client = TestClient(app)


def test_create_batch_with_no_events_returns_400():
    response = client.post("/audit/batches")

    assert response.status_code == 400


def test_create_and_get_batch():
    api_key = register_test_agent(client)
    for event_id in ("event-batch-1", "event-batch-2", "event-batch-3"):
        response = post_audit_event(
            client,
            payload=sample_event_payload(event_id=event_id),
            api_key=api_key,
        )
        assert response.status_code == 200

    create_response = client.post("/audit/batches")
    assert create_response.status_code == 200
    batch = create_response.json()
    assert batch["event_count"] == 3
    assert len(batch["merkle_root"]) == 64
    assert len(batch["event_hashes"]) == 3

    get_response = client.get(f"/audit/batches/{batch['batch_id']}")
    assert get_response.status_code == 200
    retrieved = get_response.json()
    assert retrieved == batch


def test_second_batch_only_includes_new_events():
    api_key = register_test_agent(client)
    post_audit_event(
        client,
        payload=sample_event_payload(event_id="event-new-1"),
        api_key=api_key,
    )
    first_batch = client.post("/audit/batches").json()

    post_audit_event(
        client,
        payload=sample_event_payload(event_id="event-new-2"),
        api_key=api_key,
    )
    second_batch = client.post("/audit/batches").json()

    assert first_batch["event_count"] == 1
    assert second_batch["event_count"] == 1
    assert first_batch["batch_id"] != second_batch["batch_id"]


def test_merkle_verify_endpoint_accepts_valid_proof():
    api_key = register_test_agent(client)
    store_response = post_audit_event(
        client,
        payload=sample_event_payload(event_id="event-merkle-api"),
        api_key=api_key,
    )
    event_hash = store_response.json()["event_hash"]

    batch = client.post("/audit/batches").json()
    proof = merkle_proof(batch["event_hashes"], event_hash)
    proof_payload = [{"sibling": sibling, "side": side} for sibling, side in proof]

    verify_response = client.post(
        "/audit/merkle/verify",
        json={
            "event_hash": event_hash,
            "merkle_root": batch["merkle_root"],
            "proof": proof_payload,
        },
    )

    assert verify_response.status_code == 200
    assert verify_response.json()["verified"] is True
    assert verify_inclusion_proof(event_hash, batch["merkle_root"], proof)


def test_merkle_verify_endpoint_rejects_tampered_proof():
    api_key = register_test_agent(client)
    for event_id in ("event-merkle-tamper-1", "event-merkle-tamper-2"):
        post_audit_event(
            client,
            payload=sample_event_payload(event_id=event_id),
            api_key=api_key,
        )

    event_hash = client.get("/audit/events/event-merkle-tamper-1").json()["event_hash"]
    batch = client.post("/audit/batches").json()
    proof = merkle_proof(batch["event_hashes"], event_hash)
    proof_payload = [{"sibling": "f" * 64, "side": proof[0][1]}]

    verify_response = client.post(
        "/audit/merkle/verify",
        json={
            "event_hash": event_hash,
            "merkle_root": batch["merkle_root"],
            "proof": proof_payload,
        },
    )

    assert verify_response.status_code == 200
    assert verify_response.json()["verified"] is False


def test_get_missing_batch_returns_404():
    response = client.get("/audit/batches/does-not-exist")

    assert response.status_code == 404


def _store_and_batch(event_ids: list[str], api_key: str) -> tuple[dict, str]:
    for event_id in event_ids:
        response = post_audit_event(
            client,
            payload=sample_event_payload(event_id=event_id),
            api_key=api_key,
        )
        assert response.status_code == 200

    batch = client.post("/audit/batches").json()
    return batch, event_ids[0]


def test_proof_endpoint_returns_valid_proof_for_included_event():
    api_key = register_test_agent(client)
    batch, event_id = _store_and_batch(["event-proof-1", "event-proof-2"], api_key)

    response = client.get(f"/audit/batches/{batch['batch_id']}/proof/{event_id}")
    assert response.status_code == 200
    body = response.json()

    assert body["batch_id"] == batch["batch_id"]
    assert body["event_id"] == event_id
    assert body["event_hash"] in batch["event_hashes"]
    assert body["merkle_root"] == batch["merkle_root"]
    assert isinstance(body["proof"], list)

    proof_tuples = [(step["sibling"], step["side"]) for step in body["proof"]]
    assert verify_inclusion_proof(body["event_hash"], body["merkle_root"], proof_tuples)


def test_proof_endpoint_proof_verifies_with_merkle_verify():
    api_key = register_test_agent(client)
    batch, event_id = _store_and_batch(
        ["event-proof-verify-1", "event-proof-verify-2"],
        api_key,
    )

    proof_response = client.get(f"/audit/batches/{batch['batch_id']}/proof/{event_id}")
    body = proof_response.json()

    verify_response = client.post(
        "/audit/merkle/verify",
        json={
            "event_hash": body["event_hash"],
            "merkle_root": body["merkle_root"],
            "proof": body["proof"],
        },
    )

    assert verify_response.status_code == 200
    assert verify_response.json()["verified"] is True


def test_proof_endpoint_returns_404_when_event_not_in_batch():
    api_key = register_test_agent(client)
    post_audit_event(
        client,
        payload=sample_event_payload(event_id="event-in-batch"),
        api_key=api_key,
    )
    batch = client.post("/audit/batches").json()

    post_audit_event(
        client,
        payload=sample_event_payload(event_id="event-not-in-batch"),
        api_key=api_key,
    )

    response = client.get(
        f"/audit/batches/{batch['batch_id']}/proof/event-not-in-batch",
    )

    assert response.status_code == 404


def test_proof_endpoint_returns_404_for_missing_batch():
    response = client.get("/audit/batches/missing-batch-id/proof/event-001")

    assert response.status_code == 404


def test_proof_endpoint_returns_404_for_missing_event():
    api_key = register_test_agent(client)
    batch, _ = _store_and_batch(["event-proof-only"], api_key)

    response = client.get(
        f"/audit/batches/{batch['batch_id']}/proof/missing-event-id",
    )

    assert response.status_code == 404
