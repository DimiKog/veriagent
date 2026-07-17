"""Ed25519 signature verification helpers."""

from __future__ import annotations

import base64

import base58
from cryptography.exceptions import InvalidSignature

from veriagent.identity import (
    DID_KEY_PREFIX,
    ED25519_DID_KEY_PREFIX,
    ED25519_MULTICODEC_PREFIX,
    ED25519_PUBLIC_KEY_LENGTH,
    public_key_from_base64,
)


def did_key_to_ed25519_public_key(did: str) -> str:
    """Decode an Ed25519 public key from a did:key:z... identifier."""
    if not did.startswith(ED25519_DID_KEY_PREFIX):
        raise ValueError("agent_id must be a valid Ed25519 did:key (did:key:z...)")

    multibase_value = did[len(DID_KEY_PREFIX) :]
    if not multibase_value.startswith("z"):
        raise ValueError("agent_id must be a valid Ed25519 did:key (did:key:z...)")

    try:
        prefixed = base58.b58decode(multibase_value[1:])
    except ValueError as exc:
        raise ValueError("invalid did:key multibase encoding") from exc

    if len(prefixed) < len(ED25519_MULTICODEC_PREFIX):
        raise ValueError("invalid Ed25519 multicodec prefix")

    if prefixed[: len(ED25519_MULTICODEC_PREFIX)] != ED25519_MULTICODEC_PREFIX:
        raise ValueError("invalid Ed25519 multicodec prefix")

    raw = prefixed[len(ED25519_MULTICODEC_PREFIX) :]
    if len(raw) != ED25519_PUBLIC_KEY_LENGTH:
        raise ValueError("invalid Ed25519 public key length")

    return base64.b64encode(raw).decode("ascii")


def extract_signature(event_payload: dict) -> str:
    value = event_payload.get("signature")
    if value is None:
        raise ValueError("event.signature is required for verification")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("event.signature must be a non-empty base64 string")
    return value


def verify_signature(
    public_key_base64: str,
    payload_bytes: bytes,
    signature_base64: str,
) -> bool:
    try:
        public_key = public_key_from_base64(public_key_base64)
        signature = base64.b64decode(signature_base64, validate=True)
    except (ValueError, TypeError):
        return False

    try:
        public_key.verify(signature, payload_bytes)
    except InvalidSignature:
        return False

    return True


def verify_event_signature(unsigned_event: dict, event_payload: dict) -> tuple[bool, str]:
    agent_did = unsigned_event.get("agent_id") or unsigned_event.get("agent_did")
    if not isinstance(agent_did, str) or not agent_did.strip():
        return False, "event.agent_id (or event.agent_did) must be a non-empty string"

    try:
        public_key_b64 = did_key_to_ed25519_public_key(agent_did)
        signature_b64 = extract_signature(event_payload)
    except ValueError as exc:
        return False, str(exc)

    from veriagent.hashing import canonicalize_unsigned_event

    canonical_bytes = canonicalize_unsigned_event(unsigned_event)
    if verify_signature(public_key_b64, canonical_bytes, signature_b64):
        return True, "Ed25519 signature verified against did:key-derived public key"

    return False, "Ed25519 signature is invalid for event.agent_id"
