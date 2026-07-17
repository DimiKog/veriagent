"""Minimal Python SDK for submitting signed VeriAgent audit events."""

from veriagent.client import VeriAgentClient
from veriagent.hashing import hash_event_payload, hash_unsigned_event
from veriagent.identity import (
    derive_agent_identity,
    ed25519_public_key_to_did_key,
    public_key_from_private_key_base64,
    verification_method_for_did_key,
)
from veriagent.merkle import merkle_proof, merkle_root, verify_inclusion_proof
from veriagent.registration import (
    RegistrationError,
    build_credentials_claim_payload,
    claim_registration_credentials,
    create_registration_request,
    get_registration_request_status,
    sign_payload,
    submit_registration_proof,
)
from veriagent.signing import (
    build_signed_event_payload,
    build_unsigned_event_dict,
    canonicalize_unsigned_event,
    format_timestamp,
    sign_unsigned_event,
    utc_now_timestamp,
)
from veriagent.verifier import VerificationResult, verify_audit_evidence

__all__ = [
    "RegistrationError",
    "VeriAgentClient",
    "VerificationResult",
    "build_credentials_claim_payload",
    "build_signed_event_payload",
    "build_unsigned_event_dict",
    "canonicalize_unsigned_event",
    "claim_registration_credentials",
    "create_registration_request",
    "derive_agent_identity",
    "ed25519_public_key_to_did_key",
    "format_timestamp",
    "get_registration_request_status",
    "hash_event_payload",
    "hash_unsigned_event",
    "merkle_proof",
    "merkle_root",
    "public_key_from_private_key_base64",
    "sign_payload",
    "sign_unsigned_event",
    "submit_registration_proof",
    "utc_now_timestamp",
    "verification_method_for_did_key",
    "verify_audit_evidence",
    "verify_inclusion_proof",
]

__version__ = "1.0.0-rc.1"
