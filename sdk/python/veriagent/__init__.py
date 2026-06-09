"""Minimal Python SDK for submitting signed VeriAgent audit events."""

from veriagent.client import VeriAgentClient
from veriagent.identity import (
    derive_agent_identity,
    ed25519_public_key_to_did_key,
    public_key_from_private_key_base64,
    verification_method_for_did_key,
)
from veriagent.signing import (
    build_signed_event_payload,
    build_unsigned_event_dict,
    canonicalize_unsigned_event,
    format_timestamp,
    sign_unsigned_event,
    utc_now_timestamp,
)

__all__ = [
    "VeriAgentClient",
    "build_signed_event_payload",
    "build_unsigned_event_dict",
    "canonicalize_unsigned_event",
    "derive_agent_identity",
    "ed25519_public_key_to_did_key",
    "format_timestamp",
    "public_key_from_private_key_base64",
    "sign_unsigned_event",
    "utc_now_timestamp",
    "verification_method_for_did_key",
]

__version__ = "0.9.4"
