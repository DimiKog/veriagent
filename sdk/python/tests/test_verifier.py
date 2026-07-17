import json
from pathlib import Path

import pytest

from veriagent.hashing import hash_event_payload
from veriagent.merkle import merkle_proof, merkle_root, verify_inclusion_proof
from veriagent.signing import sign_unsigned_event
from veriagent.verifier import (
    VerificationInputError,
    load_json_file,
    verify_audit_evidence,
)

DEMO_PRIVATE_KEY_B64 = "6RY+YrXELvYnMSdDKWmpDNsUG94gJrm/NGEnKw1+bWs="
DEMO_VERIFICATION_METHOD = (
    "did:key:z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN"
    "#z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN"
)

SAMPLE_UNSIGNED_EVENT = {
    "event_id": "event-proof-1",
    "agent_id": "did:key:z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN",
    "task_id": "task-001",
    "model_name": "demo-model",
    "tool_calls": ["search", "calculator"],
    "input_hash": "sha256:input123",
    "output_hash": "sha256:output456",
    "policy_version": "policy-v0.1",
    "timestamp": "2026-05-26T18:00:00Z",
    "metadata": {"purpose": "verifier-test"},
}

SECOND_EVENT_HASH = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _event_hash_for(event: dict) -> str:
    return hash_event_payload(event)


def build_valid_evidence() -> tuple[dict, dict, dict]:
    unsigned_event = dict(SAMPLE_UNSIGNED_EVENT)
    signature = sign_unsigned_event(DEMO_PRIVATE_KEY_B64, unsigned_event)
    event = {
        **unsigned_event,
        "verification_method": DEMO_VERIFICATION_METHOD,
        "signature": signature,
    }
    event_hash = _event_hash_for(unsigned_event)
    leaves = [event_hash, SECOND_EVENT_HASH]
    root = merkle_root(leaves)
    proof_steps = merkle_proof(leaves, event_hash)

    proof = {
        "batch_id": "550e8400-e29b-41d4-a716-446655440000",
        "event_id": event["event_id"],
        "event_hash": event_hash,
        "merkle_root": root,
        "proof": [{"sibling": sibling, "side": side} for sibling, side in proof_steps],
    }
    anchor = {
        "batch_id": proof["batch_id"],
        "merkle_root": root,
        "anchor_address": "0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A",
        "tx_hash": "0x" + ("ab" * 32),
        "block_number": 42,
        "anchored_at": 1700000000,
        "anchored_by": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "chain_id": 424242,
    }
    return event, proof, anchor


def test_valid_event_proof_anchor_passes():
    event, proof, anchor = build_valid_evidence()

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is True
    assert result.status == "PASS"
    assert all(step.passed for step in result.steps)
    assert result.event_hash == proof["event_hash"]
    assert result.merkle_root == proof["merkle_root"]
    assert result.anchor_tx_hash == anchor["tx_hash"]


def test_signed_event_payload_still_verifies():
    event, proof, anchor = build_valid_evidence()

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is True
    assert any(step.step == "ed25519_signature" and step.passed for step in result.steps)


def test_invalid_signature_fails():
    event, proof, anchor = build_valid_evidence()
    event["signature"] = "aGVsbG8="

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is False
    assert any(step.step == "ed25519_signature" and not step.passed for step in result.steps)


def test_missing_signature_fails():
    event, proof, anchor = build_valid_evidence()
    del event["signature"]

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is False
    assert any(
        step.step == "ed25519_signature" and not step.passed and "required" in step.detail
        for step in result.steps
    )


def test_tampered_event_fails():
    event, proof, anchor = build_valid_evidence()
    event["output_hash"] = "sha256:tampered"

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is False
    assert result.status == "FAIL"
    failed_steps = [step for step in result.steps if not step.passed]
    assert failed_steps[-1].step in {"ed25519_signature", "proof_event_hash_match"}


def test_wrong_proof_fails():
    event, proof, anchor = build_valid_evidence()
    proof["proof"][0]["sibling"] = "f" * 64

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is False
    assert any(step.step == "merkle_inclusion_proof" and not step.passed for step in result.steps)


def test_wrong_merkle_root_fails():
    event, proof, anchor = build_valid_evidence()
    anchor["merkle_root"] = "c" * 64

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is False
    assert any(step.step == "anchor_merkle_root_match" and not step.passed for step in result.steps)


def test_malformed_proof_file_fails_cleanly():
    event, proof, anchor = build_valid_evidence()
    proof["proof"] = [{"sibling": "not-hex", "side": "left"}]

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is False
    assert result.steps[-1].step == "input_validation"
    assert "64-character" in result.steps[-1].detail


def test_missing_anchor_merkle_root_fails_cleanly():
    event, proof, anchor = build_valid_evidence()
    del anchor["merkle_root"]

    result = verify_audit_evidence(event, proof, anchor)

    assert result.verified is False
    assert result.steps[-1].step == "input_validation"
    assert "anchor.merkle_root is required" in result.steps[-1].detail


def test_load_json_file_rejects_invalid_json(tmp_path: Path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not-json", encoding="utf-8")

    with pytest.raises(VerificationInputError, match="Invalid JSON"):
        load_json_file(bad_file)


def test_merkle_proof_round_trip_matches_backend_rules():
    event_hash = _event_hash_for(SAMPLE_UNSIGNED_EVENT)
    leaves = [event_hash, SECOND_EVENT_HASH]
    root = merkle_root(leaves)
    proof = merkle_proof(leaves, event_hash)

    assert verify_inclusion_proof(event_hash, root, proof)


def test_structured_json_output_shape():
    event, proof, anchor = build_valid_evidence()
    result = verify_audit_evidence(event, proof, anchor)
    payload = result.to_dict()

    assert payload["status"] == "PASS"
    assert payload["verified"] is True
    assert isinstance(payload["steps"], list)
    assert json.dumps(payload)
