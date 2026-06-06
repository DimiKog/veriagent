import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.signatures import (
    demo_did_from_public_key,
    demo_verification_method,
    did_key_to_ed25519_public_key,
    ed25519_public_key_to_did_key,
    generate_ed25519_keypair,
    sign_bytes,
    verification_method_for_did_key,
    verify_signature,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def test_ed25519_public_key_converts_to_did_key():
    _, public_key_b64 = generate_ed25519_keypair()

    did = ed25519_public_key_to_did_key(public_key_b64)

    assert did.startswith("did:key:z")
    assert not did.startswith("did:key:demo:")


def test_did_key_decodes_back_to_same_public_key():
    _, public_key_b64 = generate_ed25519_keypair()
    did = ed25519_public_key_to_did_key(public_key_b64)

    assert did_key_to_ed25519_public_key(did) == public_key_b64


def test_verification_method_for_did_key_is_correct():
    _, public_key_b64 = generate_ed25519_keypair()
    did = ed25519_public_key_to_did_key(public_key_b64)
    multibase_value = did.removeprefix("did:key:")

    assert verification_method_for_did_key(did) == f"{did}#{multibase_value}"


@pytest.mark.parametrize(
    "invalid_did",
    [
        "did:key:demo:abc123",
        "did:web:example.com",
        "not-a-did",
    ],
)
def test_invalid_did_key_prefix_rejected(invalid_did: str):
    with pytest.raises(ValueError, match="did:key must start with did:key:z"):
        did_key_to_ed25519_public_key(invalid_did)


def test_wrong_multicodec_prefix_rejected():
    _, public_key_b64 = generate_ed25519_keypair()
    raw = base64.b64decode(public_key_b64)
    wrong_prefixed = bytes((0x00, 0x01)) + raw
    import base58

    multibase_value = "z" + base58.b58encode(wrong_prefixed).decode("ascii")
    did = f"did:key:{multibase_value}"

    with pytest.raises(ValueError, match="invalid Ed25519 multicodec prefix"):
        did_key_to_ed25519_public_key(did)


def test_wrong_public_key_length_rejected():
    import base58

    wrong_length = bytes((0xED, 0x01)) + b"\x00" * 16
    multibase_value = "z" + base58.b58encode(wrong_length).decode("ascii")
    did = f"did:key:{multibase_value}"

    with pytest.raises(ValueError, match="invalid Ed25519 public key length"):
        did_key_to_ed25519_public_key(did)


def test_demo_did_is_deterministic():
    _, public_key_b64 = generate_ed25519_keypair()

    did_1 = demo_did_from_public_key(public_key_b64)
    did_2 = demo_did_from_public_key(public_key_b64)

    assert did_1 == did_2
    assert did_1.startswith("did:key:demo:")


def test_demo_verification_method_is_derived_correctly():
    agent_did = "did:key:demo:abc123"

    assert demo_verification_method(agent_did) == f"{agent_did}#keys-1"


def test_sign_demo_event_emits_real_did_key():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "sign_demo_event.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["agent_id"].startswith("did:key:z")
    assert not body["agent_id"].startswith("did:key:demo:")
    assert body["verification_method"].startswith(f"{body['agent_id']}#z")
