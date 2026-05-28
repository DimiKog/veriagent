import pytest

from app.receipts import (
    DEV_FALLBACK_SECRET,
    build_receipt_payload,
    generate_receipt,
    get_receipt_secret,
    is_using_dev_fallback_secret,
    sign_receipt_payload,
    verify_receipt,
)


def test_build_receipt_payload():
    payload = build_receipt_payload("event-001", "abc123", "2026-05-28T12:00:00+00:00")

    assert payload == {
        "event_id": "event-001",
        "event_hash": "abc123",
        "created_at": "2026-05-28T12:00:00+00:00",
    }


def test_sign_receipt_payload_is_deterministic():
    payload = build_receipt_payload("event-001", "abc123", "2026-05-28T12:00:00+00:00")

    sig_1 = sign_receipt_payload(payload, secret="fixed-secret")
    sig_2 = sign_receipt_payload(payload, secret="fixed-secret")

    assert sig_1 == sig_2
    assert len(sig_1) == 64


def test_generate_receipt_includes_payload_and_signature():
    receipt = generate_receipt(
        event_id="event-001",
        event_hash="hash-001",
        created_at="2026-05-28T12:00:00+00:00",
        secret="fixed-secret",
    )

    assert receipt["event_id"] == "event-001"
    assert receipt["event_hash"] == "hash-001"
    assert receipt["created_at"] == "2026-05-28T12:00:00+00:00"
    assert receipt["algorithm"] == "HMAC-SHA256"
    assert len(receipt["signature"]) == 64


def test_verify_receipt_accepts_valid_signature():
    receipt = generate_receipt(
        event_id="event-001",
        event_hash="hash-001",
        created_at="2026-05-28T12:00:00+00:00",
        secret="fixed-secret",
    )

    assert verify_receipt(
        event_id=receipt["event_id"],
        event_hash=receipt["event_hash"],
        created_at=receipt["created_at"],
        signature=receipt["signature"],
        secret="fixed-secret",
    )


def test_verify_receipt_rejects_tampered_payload():
    receipt = generate_receipt(
        event_id="event-001",
        event_hash="hash-001",
        created_at="2026-05-28T12:00:00+00:00",
        secret="fixed-secret",
    )

    assert not verify_receipt(
        event_id=receipt["event_id"],
        event_hash="tampered-hash",
        created_at=receipt["created_at"],
        signature=receipt["signature"],
        secret="fixed-secret",
    )


def test_verify_receipt_rejects_wrong_secret():
    receipt = generate_receipt(
        event_id="event-001",
        event_hash="hash-001",
        created_at="2026-05-28T12:00:00+00:00",
        secret="secret-a",
    )

    assert not verify_receipt(
        event_id=receipt["event_id"],
        event_hash=receipt["event_hash"],
        created_at=receipt["created_at"],
        signature=receipt["signature"],
        secret="secret-b",
    )


def test_dev_fallback_secret_when_env_missing(monkeypatch):
    monkeypatch.delenv("VERIAGENT_RECEIPT_SECRET", raising=False)

    assert get_receipt_secret() == DEV_FALLBACK_SECRET
    assert is_using_dev_fallback_secret() is True


def test_env_secret_overrides_dev_fallback(monkeypatch):
    monkeypatch.setenv("VERIAGENT_RECEIPT_SECRET", "production-secret")

    assert get_receipt_secret() == "production-secret"
    assert is_using_dev_fallback_secret() is False
