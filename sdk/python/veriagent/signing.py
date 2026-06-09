"""RFC 8785 / JCS canonicalization and Ed25519 signing for audit events."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import jcs

from veriagent.identity import private_key_from_base64


def format_timestamp(dt: datetime) -> str:
    """Format a datetime the same way Pydantic JSON mode does for UTC timestamps."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="microseconds").replace("+00:00", "Z")


def utc_now_timestamp() -> str:
    return format_timestamp(datetime.now(timezone.utc))


def build_unsigned_event_dict(
    *,
    event_id: str,
    agent_id: str,
    task_id: str,
    model_name: str,
    tool_calls: list[str],
    input_hash: str,
    output_hash: str,
    policy_version: str,
    timestamp: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "model_name": model_name,
        "tool_calls": tool_calls,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "policy_version": policy_version,
        "timestamp": timestamp,
        "metadata": metadata,
    }


def canonicalize_unsigned_event(unsigned_event: dict[str, Any]) -> bytes:
    return jcs.canonicalize(unsigned_event)


def sign_bytes(private_key_base64: str, payload_bytes: bytes) -> str:
    private_key = private_key_from_base64(private_key_base64)
    signature = private_key.sign(payload_bytes)
    return base64.b64encode(signature).decode("ascii")


def sign_unsigned_event(private_key_base64: str, unsigned_event: dict[str, Any]) -> str:
    payload = canonicalize_unsigned_event(unsigned_event)
    return sign_bytes(private_key_base64, payload)


def build_signed_event_payload(
    *,
    private_key_base64: str,
    verification_method: str,
    event_id: str,
    agent_id: str,
    task_id: str,
    model_name: str,
    tool_calls: list[str],
    input_hash: str,
    output_hash: str,
    policy_version: str,
    timestamp: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unsigned_event = build_unsigned_event_dict(
        event_id=event_id,
        agent_id=agent_id,
        task_id=task_id,
        model_name=model_name,
        tool_calls=tool_calls,
        input_hash=input_hash,
        output_hash=output_hash,
        policy_version=policy_version,
        timestamp=timestamp,
        metadata=metadata,
    )
    signature = sign_unsigned_event(private_key_base64, unsigned_event)
    return {
        **unsigned_event,
        "verification_method": verification_method,
        "signature": signature,
    }
