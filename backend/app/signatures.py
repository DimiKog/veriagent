import base64
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SIGNATURE_ALGORITHM = "Ed25519"


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


def demo_did_from_public_key(public_key_base64: str) -> str:
    raw = base64.b64decode(public_key_base64)
    digest = hashlib.sha256(raw).hexdigest()
    return f"did:key:demo:{digest}"


def demo_verification_method(agent_did: str) -> str:
    return f"{agent_did}#keys-1"
