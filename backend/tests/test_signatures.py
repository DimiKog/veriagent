import base64

import pytest

from app.signatures import (
    demo_did_from_public_key,
    demo_verification_method,
    generate_ed25519_keypair,
    sign_bytes,
    verify_signature,
)


def test_generate_ed25519_keypair_returns_base64_strings():
    private_key_b64, public_key_b64 = generate_ed25519_keypair()

    assert isinstance(private_key_b64, str)
    assert isinstance(public_key_b64, str)

    private_raw = base64.b64decode(private_key_b64)
    public_raw = base64.b64decode(public_key_b64)

    assert len(private_raw) == 32
    assert len(public_raw) == 32


def test_sign_and_verify_succeeds():
    private_key_b64, public_key_b64 = generate_ed25519_keypair()
    payload = b"audit-event-payload"

    signature_b64 = sign_bytes(private_key_b64, payload)

    assert verify_signature(public_key_b64, payload, signature_b64)


def test_tampered_payload_fails_verification():
    private_key_b64, public_key_b64 = generate_ed25519_keypair()
    payload = b"original-payload"
    signature_b64 = sign_bytes(private_key_b64, payload)

    assert not verify_signature(public_key_b64, b"tampered-payload", signature_b64)


def test_wrong_public_key_fails_verification():
    private_key_b64, public_key_b64 = generate_ed25519_keypair()
    _, other_public_key_b64 = generate_ed25519_keypair()
    payload = b"audit-event-payload"
    signature_b64 = sign_bytes(private_key_b64, payload)

    assert verify_signature(public_key_b64, payload, signature_b64)
    assert not verify_signature(other_public_key_b64, payload, signature_b64)


@pytest.mark.parametrize(
    "malformed_signature",
    [
        "not-valid-base64!!!",
        base64.b64encode(b"too-short").decode("ascii"),
    ],
)
def test_malformed_signature_fails_cleanly(malformed_signature: str):
    _, public_key_b64 = generate_ed25519_keypair()

    assert verify_signature(public_key_b64, b"payload", malformed_signature) is False


def test_demo_did_is_deterministic():
    _, public_key_b64 = generate_ed25519_keypair()

    did_1 = demo_did_from_public_key(public_key_b64)
    did_2 = demo_did_from_public_key(public_key_b64)

    assert did_1 == did_2
    assert did_1.startswith("did:key:demo:")


def test_demo_verification_method_is_derived_correctly():
    agent_did = "did:key:demo:abc123"

    assert demo_verification_method(agent_did) == f"{agent_did}#keys-1"
