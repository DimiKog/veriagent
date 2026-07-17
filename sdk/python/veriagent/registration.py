"""HTTP helpers for VeriAgent public registration (request / prove / claim)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
import jcs

from veriagent.identity import derive_agent_identity
from veriagent.signing import sign_bytes

CREDENTIALS_CLAIM_PURPOSE = "veriagent-credentials-claim"
RETRIEVAL_TOKEN_HEADER = "X-VeriAgent-Retrieval-Token"


class RegistrationError(Exception):
    """Raised when a registration API call or local signing step fails."""


def _normalize_api_base_url(api_base_url: str) -> str:
    parsed = urlparse(api_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RegistrationError("api_base_url must be an absolute http(s) URL")
    return api_base_url.rstrip("/")


def canonicalize_dict(data: dict[str, Any]) -> bytes:
    return jcs.canonicalize(data)


def sign_payload(private_key_base64: str, payload: dict[str, Any]) -> str:
    return sign_bytes(private_key_base64, canonicalize_dict(payload))


def build_credentials_claim_payload(request_id: str, agent_did: str) -> dict[str, str]:
    return {
        "purpose": CREDENTIALS_CLAIM_PURPOSE,
        "request_id": request_id,
        "agent_did": agent_did,
    }


def _raise_for_response(response: httpx.Response, action: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = None
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail")
        except Exception:
            detail = None
        message = f"{action} failed ({response.status_code})"
        if detail:
            message = f"{message}: {detail}"
        raise RegistrationError(message) from exc


def create_registration_request(
    api_base_url: str,
    *,
    private_key_base64: str,
    agent_name: str,
    agent_type: str,
    organization_name: str,
    contact_email: str,
    use_case_summary: str,
    description: str | None = None,
) -> dict[str, Any]:
    """POST /registration/requests using identity derived from the private key."""
    base = _normalize_api_base_url(api_base_url)
    public_key, agent_did, verification_method = derive_agent_identity(private_key_base64)
    payload = {
        "agent_did": agent_did,
        "agent_name": agent_name,
        "agent_type": agent_type,
        "description": description,
        "verification_method": verification_method,
        "public_key": public_key,
        "organization_name": organization_name,
        "contact_email": contact_email,
        "use_case_summary": use_case_summary,
    }
    try:
        response = httpx.post(
            f"{base}/registration/requests",
            json=payload,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise RegistrationError(f"create registration request failed: {exc}") from exc
    _raise_for_response(response, "create registration request")
    data = response.json()
    if not isinstance(data, dict):
        raise RegistrationError("create registration response must be a JSON object")
    return data


def get_registration_request_status(
    api_base_url: str,
    request_id: str,
) -> dict[str, Any]:
    """GET /registration/requests/{request_id}."""
    base = _normalize_api_base_url(api_base_url)
    url = f"{base}/registration/requests/{request_id}"
    try:
        response = httpx.get(url, timeout=30.0)
    except httpx.HTTPError as exc:
        raise RegistrationError(f"get registration status failed: {exc}") from exc
    _raise_for_response(response, "get registration status")
    data = response.json()
    if not isinstance(data, dict):
        raise RegistrationError("registration status response must be a JSON object")
    return data


def submit_registration_proof(
    api_base_url: str,
    *,
    request_id: str,
    private_key_base64: str,
    proof_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sign proof_payload and POST /registration/requests/{id}/proof.

    If proof_payload is omitted, fetch status and use proof_payload while the
    request is still pending and awaiting proof.
    """
    base = _normalize_api_base_url(api_base_url)
    _, agent_did, verification_method = derive_agent_identity(private_key_base64)

    resolved_payload = proof_payload
    if resolved_payload is None:
        status = get_registration_request_status(api_base_url, request_id)
        resolved_payload = status.get("proof_payload")
        if not isinstance(resolved_payload, dict):
            raise RegistrationError(
                "proof_payload not available for this request "
                "(already proved, expired, or not pending)"
            )
        status_did = status.get("agent_did")
        if status_did is not None and status_did != agent_did:
            raise RegistrationError(
                "private key does not match registration request agent_did"
            )

    proof_signature = sign_payload(private_key_base64, resolved_payload)
    body = {
        "proof_signature": proof_signature,
        "verification_method": verification_method,
    }
    try:
        response = httpx.post(
            f"{base}/registration/requests/{request_id}/proof",
            json=body,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise RegistrationError(f"submit registration proof failed: {exc}") from exc
    _raise_for_response(response, "submit registration proof")
    data = response.json()
    if not isinstance(data, dict):
        raise RegistrationError("submit proof response must be a JSON object")
    return data


def claim_registration_credentials(
    api_base_url: str,
    *,
    request_id: str,
    private_key_base64: str,
    retrieval_token: str | None = None,
) -> dict[str, Any]:
    """Sign claim payload and POST /registration/requests/{id}/credentials."""
    base = _normalize_api_base_url(api_base_url)
    _, agent_did, verification_method = derive_agent_identity(private_key_base64)
    claim_payload = build_credentials_claim_payload(request_id, agent_did)
    proof_signature = sign_payload(private_key_base64, claim_payload)
    headers: dict[str, str] = {}
    if retrieval_token:
        headers[RETRIEVAL_TOKEN_HEADER] = retrieval_token

    try:
        response = httpx.post(
            f"{base}/registration/requests/{request_id}/credentials",
            json={
                "proof_signature": proof_signature,
                "verification_method": verification_method,
            },
            headers=headers or None,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise RegistrationError(f"claim registration credentials failed: {exc}") from exc
    _raise_for_response(response, "claim registration credentials")
    data = response.json()
    if not isinstance(data, dict):
        raise RegistrationError("claim credentials response must be a JSON object")
    return data
