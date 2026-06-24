import hashlib
from typing import Any

import jcs

from app.models import AuditEvent


def canonicalize_event(event: AuditEvent) -> bytes:
    event_dict: dict[str, Any] = event.model_dump(mode="json", exclude_none=False)
    return jcs.canonicalize(event_dict)


def hash_event(event: AuditEvent) -> str:
    canonical_bytes = canonicalize_event(event)
    return hashlib.sha256(canonical_bytes).hexdigest()


def canonicalize_dict(data: dict[str, Any]) -> bytes:
    return jcs.canonicalize(data)