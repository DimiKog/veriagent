import base64
import hashlib

import base58
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SIGNATURE_ALGORITHM = "Ed25519"

ED25519_MULTICODEC_PREFIX = bytes((0xED, 0x01))
ED25519_PUBLIC_KEY_LENGTH = 32
DID_KEY_PREFIX = "did:key:"
ED25519_DID_KEY_PREFIX = "did:key:z"


def generate_ed25519_keypair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key_to_base64(private_key), public_key_to_base64(public_key)


def public_key_to_base64(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def private_key_to_base64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(raw).decode("ascii")


def public_key_from_base64(value: str) -> Ed25519PublicKey:
    raw = base64.b64decode(value)
    return Ed25519PublicKey.from_public_bytes(raw)


def private_key_from_base64(value: str) -> Ed25519PrivateKey:
    raw = base64.b64decode(value)
    return Ed25519PrivateKey.from_private_bytes(raw)


def sign_bytes(private_key_base64: str, payload_bytes: bytes) -> str:
    private_key = private_key_from_base64(private_key_base64)
    signature = private_key.sign(payload_bytes)
    return base64.b64encode(signature).decode("ascii")


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


def ed25519_public_key_to_did_key(public_key_base64: str) -> str:
    raw = base64.b64decode(public_key_base64)
    prefixed = ED25519_MULTICODEC_PREFIX + raw
    multibase_value = "z" + base58.b58encode(prefixed).decode("ascii")
    return f"{DID_KEY_PREFIX}{multibase_value}"


def did_key_to_ed25519_public_key(did: str) -> str:
    if not did.startswith(ED25519_DID_KEY_PREFIX):
        raise ValueError("did:key must start with did:key:z")

    multibase_value = did[len(DID_KEY_PREFIX) :]
    if not multibase_value.startswith("z"):
        raise ValueError("did:key must start with did:key:z")

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


def verification_method_for_did_key(did: str) -> str:
    if not did.startswith(DID_KEY_PREFIX):
        raise ValueError("did must start with did:key:")

    multibase_value = did[len(DID_KEY_PREFIX) :]
    return f"{did}#{multibase_value}"


def validate_ed25519_did_key_agent(
    agent_did: str,
    public_key_base64: str,
    verification_method: str,
) -> None:
    try:
        did_public_key = did_key_to_ed25519_public_key(agent_did)
    except ValueError as exc:
        raise ValueError(
            "agent_did must be a valid Ed25519 did:key (did:key:z...)"
        ) from exc

    if did_public_key != public_key_base64:
        raise ValueError("public_key does not match agent_did")

    expected_verification_method = verification_method_for_did_key(agent_did)
    if verification_method != expected_verification_method:
        raise ValueError(
            "verification_method must equal the did:key verification method fragment"
        )


def demo_did_from_public_key(public_key_base64: str) -> str:
    """Deprecated: temporary did:key:demo identifier; use ed25519_public_key_to_did_key."""
    raw = base64.b64decode(public_key_base64)
    digest = hashlib.sha256(raw).hexdigest()
    return f"did:key:demo:{digest}"


def demo_verification_method(agent_did: str) -> str:
    """Deprecated: use verification_method_for_did_key for real did:key agents."""
    return f"{agent_did}#keys-1"
