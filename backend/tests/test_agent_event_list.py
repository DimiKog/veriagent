from fastapi.testclient import TestClient

from app.main import app
from app.signatures import (
    ed25519_public_key_to_did_key,
    generate_ed25519_keypair,
    verification_method_for_did_key,
)
from tests.support import (
    post_audit_batch,
    post_audit_event,
    register_test_agent,
    sample_event_payload,
    sign_event_payload,
)

client = TestClient(app)


def test_list_audit_events_requires_auth():
    response = client.get("/audit/events")
    assert response.status_code == 401


def test_list_audit_events_returns_only_authenticated_agent_events():
    api_key = register_test_agent(client)
    other_private_key, other_public_key = generate_ed25519_keypair()
    other_did = ed25519_public_key_to_did_key(other_public_key)
    other_vm = verification_method_for_did_key(other_did)
    other_api_key = register_test_agent(
        client,
        agent_did=other_did,
        public_key=other_public_key,
        verification_method=other_vm,
    )

    own_response = post_audit_event(
        client,
        payload=sample_event_payload(event_id="own-event-1"),
        api_key=api_key,
    )
    assert own_response.status_code == 200

    other_payload = sample_event_payload(event_id="other-event-1", agent_id=other_did)
    other_response = post_audit_event(
        client,
        payload=sign_event_payload(
            other_payload,
            private_key_b64=other_private_key,
            verification_method=other_vm,
        ),
        api_key=other_api_key,
    )
    assert other_response.status_code == 200

    list_response = client.get(
        "/audit/events",
        headers={"X-VeriAgent-API-Key": api_key},
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert event["event_id"] == "own-event-1"
    assert event["event_hash"] == own_response.json()["event_hash"]
    assert event["created_at"]
    assert event["batched"] is False
    assert event["anchored"] is False
    assert "canonical_event_json" not in event
    assert "signature" not in event


def test_list_audit_events_respects_limit_and_offset():
    api_key = register_test_agent(client)
    for index in range(3):
        response = post_audit_event(
            client,
            payload=sample_event_payload(event_id=f"paged-event-{index}"),
            api_key=api_key,
        )
        assert response.status_code == 200

    page = client.get(
        "/audit/events",
        params={"limit": 2, "offset": 0},
        headers={"X-VeriAgent-API-Key": api_key},
    )
    assert page.status_code == 200
    page_body = page.json()
    assert len(page_body["events"]) == 2

    next_page = client.get(
        "/audit/events",
        params={"limit": 2, "offset": 2},
        headers={"X-VeriAgent-API-Key": api_key},
    )
    assert next_page.status_code == 200
    next_body = next_page.json()
    assert len(next_body["events"]) == 1

    all_ids = {event["event_id"] for event in page_body["events"] + next_body["events"]}
    assert all_ids == {"paged-event-0", "paged-event-1", "paged-event-2"}


def test_list_audit_events_includes_batched_flag():
    api_key = register_test_agent(client)
    store_response = post_audit_event(
        client,
        payload=sample_event_payload(event_id="batched-list-event"),
        api_key=api_key,
    )
    assert store_response.status_code == 200

    batch_response = post_audit_batch(client)
    assert batch_response.status_code == 200

    list_response = client.get(
        "/audit/events",
        headers={"X-VeriAgent-API-Key": api_key},
    )
    assert list_response.status_code == 200
    event = list_response.json()["events"][0]
    assert event["event_id"] == "batched-list-event"
    assert event["batched"] is True
    assert event["anchored"] is False
