from fastapi.testclient import TestClient

from app.main import app
from app.merkle import merkle_proof, verify_inclusion_proof
from tests.test_api import sample_event_payload

client = TestClient(app)


def test_create_batch_with_no_events_returns_400():
    response = client.post("/audit/batches")

    assert response.status_code == 400


def test_create_and_get_batch():
    for event_id in ("event-batch-1", "event-batch-2", "event-batch-3"):
        response = client.post("/audit/events", json=sample_event_payload(event_id=event_id))
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
    client.post("/audit/events", json=sample_event_payload(event_id="event-new-1"))
    first_batch = client.post("/audit/batches").json()

    client.post("/audit/events", json=sample_event_payload(event_id="event-new-2"))
    second_batch = client.post("/audit/batches").json()

    assert first_batch["event_count"] == 1
    assert second_batch["event_count"] == 1
    assert first_batch["batch_id"] != second_batch["batch_id"]


def test_merkle_verify_endpoint_accepts_valid_proof():
    store_response = client.post(
        "/audit/events",
        json=sample_event_payload(event_id="event-merkle-api"),
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
    for event_id in ("event-merkle-tamper-1", "event-merkle-tamper-2"):
        client.post("/audit/events", json=sample_event_payload(event_id=event_id))

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
