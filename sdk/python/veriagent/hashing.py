"""RFC 8785 / JCS canonicalization and SHA-256 hashing for audit events."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import jcs

UNSIGNED_EVENT_EXCLUDE_FIELDS = frozenset({"signature", "verification_method"})


def unsigned_event_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip signing fields from a signed or unsigned audit event payload."""
    return {
        key: value
        for key, value in payload.items()
        if key not in UNSIGNED_EVENT_EXCLUDE_FIELDS
    }


def canonicalize_unsigned_event(unsigned_event: dict[str, Any]) -> bytes:
    return jcs.canonicalize(unsigned_event)


def hash_unsigned_event(unsigned_event: dict[str, Any]) -> str:
    canonical_bytes = canonicalize_unsigned_event(unsigned_event)
    return hashlib.sha256(canonical_bytes).hexdigest()


def hash_event_payload(payload: dict[str, Any]) -> str:
    return hash_unsigned_event(unsigned_event_from_payload(payload))


def hash_canonical_event_json(canonical_event_json: str) -> str:
    try:
        event_dict = json.loads(canonical_event_json)
    except json.JSONDecodeError as exc:
        raise ValueError("canonical_event_json is not valid JSON") from exc
    if not isinstance(event_dict, dict):
        raise ValueError("canonical_event_json must decode to a JSON object")
    return hash_unsigned_event(event_dict)
