"""Offline verification of VeriAgent audit evidence bundles."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from veriagent.hashing import hash_event_payload, unsigned_event_from_payload
from veriagent.merkle import verify_inclusion_proof
from veriagent.signatures import verify_event_signature

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

VerificationStatus = Literal["PASS", "FAIL"]


class VerificationInputError(ValueError):
    """Raised when input files or payloads are malformed."""


@dataclass(frozen=True)
class VerificationStepResult:
    step: str
    passed: bool
    detail: str


@dataclass
class VerificationResult:
    status: VerificationStatus
    verified: bool
    steps: list[VerificationStepResult] = field(default_factory=list)
    event_hash: str | None = None
    merkle_root: str | None = None
    batch_id: str | None = None
    anchor_tx_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [asdict(step) for step in self.steps]
        return payload


def load_json_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationInputError(f"Unable to read file: {file_path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VerificationInputError(f"Invalid JSON in {file_path}") from exc

    if not isinstance(data, dict):
        raise VerificationInputError(f"Expected a JSON object in {file_path}")
    return data


def _require_hex64(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
        raise VerificationInputError(f"{field_name} must be a 64-character lowercase hex string")
    return value


def _parse_proof_steps(proof_payload: dict[str, Any]) -> list[tuple[str, str]]:
    proof_steps = proof_payload.get("proof")
    if not isinstance(proof_steps, list):
        raise VerificationInputError("proof.proof must be a list")

    parsed: list[tuple[str, str]] = []
    for index, step in enumerate(proof_steps):
        if not isinstance(step, dict):
            raise VerificationInputError(f"proof.proof[{index}] must be an object")
        sibling = step.get("sibling")
        side = step.get("side")
        if side not in {"left", "right"}:
            raise VerificationInputError(f"proof.proof[{index}].side must be 'left' or 'right'")
        parsed.append((_require_hex64(sibling, f"proof.proof[{index}].sibling"), side))
    return parsed


def _validate_anchor_metadata(anchor_payload: dict[str, Any]) -> dict[str, Any]:
    batch_id = anchor_payload.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise VerificationInputError("anchor.batch_id must be a non-empty string")

    merkle_root = anchor_payload.get("merkle_root")
    if merkle_root is not None:
        merkle_root = _require_hex64(merkle_root, "anchor.merkle_root")

    tx_hash = anchor_payload.get("tx_hash")
    if not isinstance(tx_hash, str) or not TX_HASH_RE.fullmatch(tx_hash):
        raise VerificationInputError("anchor.tx_hash must be a 0x-prefixed 32-byte hex string")

    block_number = anchor_payload.get("block_number")
    if not isinstance(block_number, int) or block_number < 0:
        raise VerificationInputError("anchor.block_number must be a non-negative integer")

    chain_id = anchor_payload.get("chain_id")
    if not isinstance(chain_id, int) or chain_id <= 0:
        raise VerificationInputError("anchor.chain_id must be a positive integer")

    anchored_at = anchor_payload.get("anchored_at")
    if not isinstance(anchored_at, int) or anchored_at <= 0:
        raise VerificationInputError("anchor.anchored_at must be a positive Unix timestamp")

    return {
        "batch_id": batch_id,
        "merkle_root": merkle_root,
        "tx_hash": tx_hash,
        "block_number": block_number,
        "chain_id": chain_id,
        "anchored_at": anchored_at,
    }


def verify_audit_evidence(
    event_payload: dict[str, Any],
    proof_payload: dict[str, Any],
    anchor_payload: dict[str, Any],
) -> VerificationResult:
    """Verify hash, Merkle inclusion, and anchor metadata without trusting the API."""
    result = VerificationResult(status="FAIL", verified=False)
    steps: list[VerificationStepResult] = []

    try:
        unsigned_event = unsigned_event_from_payload(event_payload)
        if not unsigned_event:
            raise VerificationInputError("event payload is empty after removing signing fields")

        computed_hash = hash_event_payload(event_payload)
        result.event_hash = computed_hash
        steps.append(
            VerificationStepResult(
                step="event_canonical_hash",
                passed=True,
                detail="Computed SHA-256 over RFC8785/JCS canonical unsigned event",
            )
        )

        proof_event_hash = _require_hex64(proof_payload.get("event_hash"), "proof.event_hash")
        proof_merkle_root = _require_hex64(proof_payload.get("merkle_root"), "proof.merkle_root")
        proof_batch_id = proof_payload.get("batch_id")
        if not isinstance(proof_batch_id, str) or not proof_batch_id.strip():
            raise VerificationInputError("proof.batch_id must be a non-empty string")

        hash_matches = computed_hash == proof_event_hash
        steps.append(
            VerificationStepResult(
                step="proof_event_hash_match",
                passed=hash_matches,
                detail=(
                    "Computed event hash matches proof.event_hash"
                    if hash_matches
                    else (
                        f"Hash mismatch: computed {computed_hash}, "
                        f"proof.event_hash {proof_event_hash}"
                    )
                ),
            )
        )
        if not hash_matches:
            result.steps = steps
            return result

        signature_verified, signature_detail = verify_event_signature(
            unsigned_event,
            event_payload,
        )
        steps.append(
            VerificationStepResult(
                step="ed25519_signature",
                passed=signature_verified,
                detail=signature_detail,
            )
        )
        if not signature_verified:
            result.steps = steps
            return result

        proof_steps = _parse_proof_steps(proof_payload)
        merkle_verified = verify_inclusion_proof(
            proof_event_hash,
            proof_merkle_root,
            proof_steps,
        )
        result.merkle_root = proof_merkle_root
        result.batch_id = proof_batch_id
        steps.append(
            VerificationStepResult(
                step="merkle_inclusion_proof",
                passed=merkle_verified,
                detail=(
                    "Merkle proof reconstructs proof.merkle_root"
                    if merkle_verified
                    else "Merkle proof does not reconstruct proof.merkle_root"
                ),
            )
        )
        if not merkle_verified:
            result.steps = steps
            return result

        anchor = _validate_anchor_metadata(anchor_payload)
        anchor_merkle_root = anchor["merkle_root"]
        if anchor_merkle_root is None:
            raise VerificationInputError(
                "anchor.merkle_root is required for offline verification"
            )

        root_matches = proof_merkle_root == anchor_merkle_root
        steps.append(
            VerificationStepResult(
                step="anchor_merkle_root_match",
                passed=root_matches,
                detail=(
                    "proof.merkle_root matches anchor.merkle_root"
                    if root_matches
                    else (
                        f"Root mismatch: proof.merkle_root {proof_merkle_root}, "
                        f"anchor.merkle_root {anchor_merkle_root}"
                    )
                ),
            )
        )
        if not root_matches:
            result.steps = steps
            return result

        batch_matches = proof_batch_id == anchor["batch_id"]
        steps.append(
            VerificationStepResult(
                step="batch_id_match",
                passed=batch_matches,
                detail=(
                    "proof.batch_id matches anchor.batch_id"
                    if batch_matches
                    else (
                        f"Batch mismatch: proof.batch_id {proof_batch_id}, "
                        f"anchor.batch_id {anchor['batch_id']}"
                    )
                ),
            )
        )
        if not batch_matches:
            result.steps = steps
            return result

        steps.append(
            VerificationStepResult(
                step="anchor_metadata_present",
                passed=True,
                detail=(
                    "Anchor metadata present: tx_hash, block_number, chain_id, anchored_at"
                ),
            )
        )

        result.anchor_tx_hash = anchor["tx_hash"]
        result.status = "PASS"
        result.verified = True
        result.steps = steps
        return result
    except VerificationInputError as exc:
        steps.append(
            VerificationStepResult(
                step="input_validation",
                passed=False,
                detail=str(exc),
            )
        )
        result.steps = steps
        return result


def _normalize_api_base_url(api_base_url: str) -> str:
    parsed = urlparse(api_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VerificationInputError("api-base-url must be an absolute http(s) URL")
    return api_base_url.rstrip("/")


def fetch_proof_payload(api_base_url: str, batch_id: str, event_id: str) -> dict[str, Any]:
    base = _normalize_api_base_url(api_base_url)
    url = f"{base}/audit/batches/{batch_id}/proof/{event_id}"
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise VerificationInputError(f"Failed to fetch proof from {url}: {exc}") from exc
    data = response.json()
    if not isinstance(data, dict):
        raise VerificationInputError("Proof API response must be a JSON object")
    return data


def fetch_anchor_payload(api_base_url: str, batch_id: str) -> dict[str, Any]:
    base = _normalize_api_base_url(api_base_url)
    url = f"{base}/audit/batches/{batch_id}/anchor"
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise VerificationInputError(f"Failed to fetch anchor from {url}: {exc}") from exc
    data = response.json()
    if not isinstance(data, dict):
        raise VerificationInputError("Anchor API response must be a JSON object")
    return data


def fetch_event_payload(api_base_url: str, event_id: str) -> dict[str, Any]:
    base = _normalize_api_base_url(api_base_url)
    url = f"{base}/audit/events/{event_id}"
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise VerificationInputError(f"Failed to fetch event from {url}: {exc}") from exc
    data = response.json()
    if not isinstance(data, dict):
        raise VerificationInputError("Event API response must be a JSON object")

    canonical_event_json = data.get("canonical_event_json")
    if not isinstance(canonical_event_json, str):
        raise VerificationInputError("Event API response missing canonical_event_json")

    try:
        event_payload = json.loads(canonical_event_json)
    except json.JSONDecodeError as exc:
        raise VerificationInputError("canonical_event_json is not valid JSON") from exc
    if not isinstance(event_payload, dict):
        raise VerificationInputError("canonical_event_json must decode to a JSON object")
    return event_payload


def enrich_anchor_with_merkle_root(
    anchor_payload: dict[str, Any],
    proof_payload: dict[str, Any],
) -> dict[str, Any]:
    """Add merkle_root from proof when older API anchor records omit it."""
    enriched = dict(anchor_payload)
    if enriched.get("merkle_root") is None:
        enriched["merkle_root"] = proof_payload.get("merkle_root")
    return enriched
