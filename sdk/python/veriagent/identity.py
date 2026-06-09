"""Ed25519 identity helpers for VeriAgent agents."""

from __future__ import annotations

import base64

import base58
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ED25519_MULTICODEC_PREFIX = bytes((0xED, 0x01))
ED25519_PUBLIC_KEY_LENGTH = 32
DID_KEY_PREFIX = "did:key:"
ED25519_DID_KEY_PREFIX = "did:key:z"


def private_key_from_base64(value: str) -> Ed25519PrivateKey:
    raw = base64.b64decode(value)
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_key_from_base64(value: str) -> Ed25519PublicKey:
    raw = base64.b64decode(value)
    return Ed25519PublicKey.from_public_bytes(raw)


def public_key_to_base64(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def public_key_from_private_key_base64(private_key_base64: str) -> str:
    private_key = private_key_from_base64(private_key_base64)
    return public_key_to_base64(private_key.public_key())


def ed25519_public_key_to_did_key(public_key_base64: str) -> str:
    raw = base64.b64decode(public_key_base64)
    prefixed = ED25519_MULTICODEC_PREFIX + raw
    multibase_value = "z" + base58.b58encode(prefixed).decode("ascii")
    return f"{DID_KEY_PREFIX}{multibase_value}"


def verification_method_for_did_key(did: str) -> str:
    if not did.startswith(DID_KEY_PREFIX):
        raise ValueError("did must start with did:key:")

    multibase_value = did[len(DID_KEY_PREFIX) :]
    return f"{did}#{multibase_value}"


def derive_agent_identity(private_key_base64: str) -> tuple[str, str, str]:
    """Return (public_key_base64, agent_did, verification_method)."""
    public_key_base64 = public_key_from_private_key_base64(private_key_base64)
    agent_did = ed25519_public_key_to_did_key(public_key_base64)
    verification_method = verification_method_for_did_key(agent_did)
    return public_key_base64, agent_did, verification_method
