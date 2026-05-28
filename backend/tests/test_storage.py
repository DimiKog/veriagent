import pytest

from app.storage import (
    EventAlreadyExistsError,
    get_audit_event,
    init_db,
    store_audit_event,
)


def test_init_db_creates_table(tmp_path):
    db_path = tmp_path / "init.db"
    init_db(db_path)

    stored = store_audit_event(
        event_id="event-001",
        canonical_event_json='{"event_id":"event-001"}',
        event_hash="abc123",
        db_path=db_path,
    )

    assert stored.event_id == "event-001"
    assert stored.event_hash == "abc123"
    assert stored.canonical_event_json == '{"event_id":"event-001"}'
    assert stored.created_at.endswith("+00:00")


def test_store_and_get_audit_event(tmp_path):
    db_path = tmp_path / "store.db"
    init_db(db_path)

    store_audit_event(
        event_id="event-002",
        canonical_event_json='{"event_id":"event-002"}',
        event_hash="hash-002",
        db_path=db_path,
    )

    retrieved = get_audit_event("event-002", db_path=db_path)

    assert retrieved is not None
    assert retrieved.event_id == "event-002"
    assert retrieved.event_hash == "hash-002"
    assert retrieved.canonical_event_json == '{"event_id":"event-002"}'


def test_get_missing_event_returns_none(tmp_path):
    db_path = tmp_path / "missing.db"
    init_db(db_path)

    assert get_audit_event("does-not-exist", db_path=db_path) is None


def test_duplicate_event_id_raises(tmp_path):
    db_path = tmp_path / "dup.db"
    init_db(db_path)

    store_audit_event(
        event_id="event-dup",
        canonical_event_json="{}",
        event_hash="hash-a",
        db_path=db_path,
    )

    with pytest.raises(EventAlreadyExistsError):
        store_audit_event(
            event_id="event-dup",
            canonical_event_json="{}",
            event_hash="hash-b",
            db_path=db_path,
        )
