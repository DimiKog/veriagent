from app.hashing import canonicalize_event, hash_event
from app.models import AuditEvent


def make_event(event_id: str = "event-001", output_hash: str = "sha256:output456") -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        agent_id="agent-001",
        task_id="task-001",
        model_name="demo-model",
        tool_calls=["search", "calculator"],
        input_hash="sha256:input123",
        output_hash=output_hash,
        policy_version="policy-v0.1",
        timestamp="2026-05-26T18:00:00Z",
        metadata={"purpose": "mvp-test"},
    )


def test_same_event_produces_same_hash():
    event = make_event()

    hash_1 = hash_event(event)
    hash_2 = hash_event(event)

    assert hash_1 == hash_2
    assert len(hash_1) == 64


def test_different_events_produce_different_hashes():
    event_1 = make_event()
    event_2 = make_event(event_id="event-002")

    assert hash_event(event_1) != hash_event(event_2)


def test_changed_output_changes_hash():
    event_1 = make_event()
    event_2 = make_event(output_hash="sha256:changed-output")

    assert hash_event(event_1) != hash_event(event_2)


def test_canonicalization_is_stable():
    event = make_event()

    canonical_1 = canonicalize_event(event)
    canonical_2 = canonicalize_event(event)

    assert canonical_1 == canonical_2
    assert isinstance(canonical_1, bytes)