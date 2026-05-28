import hashlib
import hmac
import json
import os

RECEIPT_SECRET_ENV = "VERIAGENT_RECEIPT_SECRET"
DEV_FALLBACK_SECRET = "VERIAGENT-DEV-ONLY-DO-NOT-USE-IN-PRODUCTION"

SIGNATURE_ALGORITHM = "HMAC-SHA256"


def get_receipt_secret() -> str:
    secret = os.environ.get(RECEIPT_SECRET_ENV)
    if secret:
        return secret
    return DEV_FALLBACK_SECRET


def is_using_dev_fallback_secret() -> bool:
    return RECEIPT_SECRET_ENV not in os.environ


def build_receipt_payload(event_id: str, event_hash: str, created_at: str) -> dict[str, str]:
    return {
        "event_id": event_id,
        "event_hash": event_hash,
        "created_at": created_at,
    }


def _canonical_payload_bytes(payload: dict[str, str]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_receipt_payload(payload: dict[str, str], secret: str | None = None) -> str:
    key = (secret if secret is not None else get_receipt_secret()).encode("utf-8")
    message = _canonical_payload_bytes(payload)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def generate_receipt(
    event_id: str,
    event_hash: str,
    created_at: str,
    secret: str | None = None,
) -> dict[str, str]:
    payload = build_receipt_payload(event_id, event_hash, created_at)
    signature = sign_receipt_payload(payload, secret=secret)
    return {
        **payload,
        "signature": signature,
        "algorithm": SIGNATURE_ALGORITHM,
    }


def verify_receipt(
    event_id: str,
    event_hash: str,
    created_at: str,
    signature: str,
    secret: str | None = None,
) -> bool:
    payload = build_receipt_payload(event_id, event_hash, created_at)
    expected = sign_receipt_payload(payload, secret=secret)
    return hmac.compare_digest(expected, signature)
