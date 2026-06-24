import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.hashing import canonicalize_dict
from app.signatures import validate_ed25519_did_key_agent, verify_signature
from app.storage import (
    AgentAlreadyExistsError,
    DuplicatePendingRegistrationError,
    RegistrationRequestNotFoundError,
    RegistrationRequestNotPendingError,
    StoredRegistrationRequest,
    create_registration_request,
    expire_stale_requests,
    get_agent,
    get_registration_request,
    mark_registration_request_expired,
    submit_registration_proof,
)

REGISTRATION_ENABLED_ENV = "VERIAGENT_REGISTRATION_ENABLED"
CHALLENGE_TTL_MINUTES_ENV = "VERIAGENT_REGISTRATION_CHALLENGE_TTL_MINUTES"
DEFAULT_CHALLENGE_TTL_MINUTES = 15
PROOF_PURPOSE = "veriagent-registration"


class RegistrationDisabledError(Exception):
    pass


class RegistrationChallengeExpiredError(Exception):
    pass


class RegistrationProofInvalidError(Exception):
    pass


def is_registration_enabled() -> bool:
    value = os.environ.get(REGISTRATION_ENABLED_ENV, "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_challenge_ttl_minutes() -> int:
    raw = os.environ.get(
        CHALLENGE_TTL_MINUTES_ENV,
        str(DEFAULT_CHALLENGE_TTL_MINUTES),
    ).strip()
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{CHALLENGE_TTL_MINUTES_ENV} must be a positive integer"
        ) from exc
    if minutes <= 0:
        raise ValueError(f"{CHALLENGE_TTL_MINUTES_ENV} must be a positive integer")
    return minutes


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _is_challenge_expired(challenge_expires_at: str, now: datetime | None = None) -> bool:
    current = now or _utc_now()
    return current >= _parse_iso_timestamp(challenge_expires_at)


def hash_client_ip(client_ip: str | None) -> str | None:
    if not client_ip:
        return None
    return hashlib.sha256(client_ip.encode("utf-8")).hexdigest()


def build_proof_payload(
    request_id: str,
    agent_did: str,
    challenge_nonce: str,
    issued_at: str,
    challenge_expires_at: str,
) -> dict[str, str]:
    return {
        "purpose": PROOF_PURPOSE,
        "request_id": request_id,
        "agent_did": agent_did,
        "nonce": challenge_nonce,
        "issued_at": issued_at,
        "expires_at": challenge_expires_at,
    }


def create_registration_request_with_challenge(
    *,
    agent_did: str,
    agent_name: str,
    agent_type: str,
    description: str | None,
    organization_name: str,
    contact_email: str,
    use_case_summary: str,
    verification_method: str,
    public_key: str,
    client_ip_hash: str | None = None,
) -> tuple[StoredRegistrationRequest, dict[str, str]]:
    if not is_registration_enabled():
        raise RegistrationDisabledError()

    validate_ed25519_did_key_agent(agent_did, public_key, verification_method)

    if get_agent(agent_did) is not None:
        raise AgentAlreadyExistsError(agent_did)

    request_id = str(uuid.uuid4())
    challenge_nonce = secrets.token_urlsafe(32)
    issued_at_dt = _utc_now()
    challenge_expires_at_dt = issued_at_dt + timedelta(
        minutes=get_challenge_ttl_minutes()
    )
    issued_at = _isoformat(issued_at_dt)
    challenge_expires_at = _isoformat(challenge_expires_at_dt)

    proof_payload = build_proof_payload(
        request_id=request_id,
        agent_did=agent_did,
        challenge_nonce=challenge_nonce,
        issued_at=issued_at,
        challenge_expires_at=challenge_expires_at,
    )
    proof_payload_json = json.dumps(proof_payload, separators=(",", ":"), sort_keys=True)

    try:
        stored = create_registration_request(
            request_id=request_id,
            agent_did=agent_did,
            agent_name=agent_name,
            agent_type=agent_type,
            description=description,
            organization_name=organization_name,
            contact_email=contact_email,
            use_case_summary=use_case_summary,
            verification_method=verification_method,
            public_key=public_key,
            challenge_nonce=challenge_nonce,
            challenge_expires_at=challenge_expires_at,
            proof_payload_json=proof_payload_json,
            client_ip_hash=client_ip_hash,
        )
    except DuplicatePendingRegistrationError:
        raise

    return stored, proof_payload


def submit_registration_request_proof(
    request_id: str,
    proof_signature: str,
    verification_method: str,
) -> StoredRegistrationRequest:
    if not is_registration_enabled():
        raise RegistrationDisabledError()

    expire_stale_requests()

    stored = get_registration_request(request_id)
    if stored is None:
        raise RegistrationRequestNotFoundError(request_id)

    if stored.status == "expired":
        raise RegistrationChallengeExpiredError(request_id)

    if stored.status != "pending":
        raise RegistrationRequestNotPendingError(request_id)

    if _is_challenge_expired(stored.challenge_expires_at):
        mark_registration_request_expired(request_id)
        raise RegistrationChallengeExpiredError(request_id)

    if not hmac_compare(verification_method, stored.verification_method):
        raise RegistrationProofInvalidError("verification_method does not match request")

    try:
        proof_payload = json.loads(stored.proof_payload_json)
    except json.JSONDecodeError as exc:
        raise RegistrationProofInvalidError("stored proof payload is invalid") from exc

    canonical_bytes = canonicalize_dict(proof_payload)
    if not verify_signature(stored.public_key, canonical_bytes, proof_signature):
        raise RegistrationProofInvalidError("Invalid proof signature")

    return submit_registration_proof(request_id, proof_signature)


def get_registration_request_status(
    request_id: str,
) -> StoredRegistrationRequest:
    if not is_registration_enabled():
        raise RegistrationDisabledError()

    expire_stale_requests()

    stored = get_registration_request(request_id)
    if stored is None:
        raise RegistrationRequestNotFoundError(request_id)

    return stored


def hmac_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
