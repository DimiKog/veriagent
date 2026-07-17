#!/usr/bin/env python3
"""VeriAgent command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from veriagent.client import VeriAgentClient
from veriagent.registration import (
    RegistrationError,
    claim_registration_credentials,
    create_registration_request,
    submit_registration_proof,
)
from veriagent.verifier import (
    VerificationInputError,
    enrich_anchor_with_merkle_root,
    fetch_anchor_payload,
    fetch_event_payload,
    fetch_proof_payload,
    load_json_file,
    verify_audit_evidence,
)

PRIVATE_KEY_ENV = "VERIAGENT_PRIVATE_KEY"
API_KEY_ENV = "VERIAGENT_API_KEY"


def _load_private_key(
    *,
    private_key: str | None = None,
    private_key_file: str | None = None,
) -> str:
    if private_key and private_key_file:
        raise ValueError("Pass only one of --private-key or --private-key-file")
    if private_key:
        return private_key.strip()
    if private_key_file:
        return Path(private_key_file).read_text(encoding="utf-8").strip()
    env_value = os.environ.get(PRIVATE_KEY_ENV, "").strip()
    if env_value:
        return env_value
    raise ValueError(
        f"Private key required via --private-key, --private-key-file, or {PRIVATE_KEY_ENV}"
    )


def _add_private_key_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--private-key",
        help="Ed25519 private key (base64). Prefer --private-key-file or env.",
    )
    parser.add_argument(
        "--private-key-file",
        help=f"Path to file containing base64 private key (or set {PRIVATE_KEY_ENV})",
    )


def _add_api_base_url_arg(parser: argparse.ArgumentParser, *, required: bool = True) -> None:
    parser.add_argument(
        "--api-base-url",
        required=required,
        help="VeriAgent API base URL (e.g. https://veriagent.example)",
    )


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _write_json_file(path: str, data: Any) -> None:
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_verify_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "verify",
        help="Verify audit evidence offline from JSON files",
    )
    parser.add_argument(
        "--event",
        required=True,
        help="Path to unsigned or signed audit event JSON",
    )
    parser.add_argument(
        "--proof",
        help="Path to Merkle proof JSON (BatchProofResponse shape)",
    )
    parser.add_argument(
        "--anchor",
        help="Path to anchor metadata JSON (must include merkle_root for offline verify)",
    )
    parser.add_argument(
        "--api-base-url",
        help="Optional API base URL to fetch missing proof/anchor/event payloads",
    )
    parser.add_argument(
        "--batch-id",
        help="Batch ID used when fetching proof/anchor from the API",
    )
    parser.add_argument(
        "--event-id",
        help="Event ID used when fetching proof/event from the API",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output",
    )


def _build_register_parser(subparsers: argparse._SubParsersAction) -> None:
    register = subparsers.add_parser(
        "register",
        help="Public registration: request, prove ownership, claim credentials",
    )
    register_sub = register.add_subparsers(dest="register_command", required=True)

    request_parser = register_sub.add_parser(
        "request",
        help="Create a registration request (returns challenge + proof_payload)",
    )
    _add_api_base_url_arg(request_parser)
    _add_private_key_args(request_parser)
    request_parser.add_argument("--agent-name", required=True)
    request_parser.add_argument("--agent-type", required=True)
    request_parser.add_argument("--organization-name", required=True)
    request_parser.add_argument("--contact-email", required=True)
    request_parser.add_argument("--use-case-summary", required=True)
    request_parser.add_argument("--description", default=None)
    request_parser.add_argument(
        "--output",
        help="Optional path to save the create response JSON (includes proof_payload)",
    )

    prove_parser = register_sub.add_parser(
        "prove",
        help="Sign and submit registration proof for a pending request",
    )
    _add_api_base_url_arg(prove_parser)
    _add_private_key_args(prove_parser)
    prove_parser.add_argument("--request-id", required=True)
    prove_parser.add_argument(
        "--proof-payload",
        help="Optional JSON file with proof_payload; otherwise fetched from pending status",
    )

    claim_parser = register_sub.add_parser(
        "claim",
        help="Claim agent API key after approval",
    )
    _add_api_base_url_arg(claim_parser)
    _add_private_key_args(claim_parser)
    claim_parser.add_argument("--request-id", required=True)
    claim_parser.add_argument(
        "--retrieval-token",
        help="Optional X-VeriAgent-Retrieval-Token from approval",
    )
    claim_parser.add_argument(
        "--output-key-file",
        help="Optional path to write the claimed api_key (plaintext)",
    )


def _build_submit_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "submit",
        help="Sign and submit an audit event",
    )
    _add_api_base_url_arg(parser)
    _add_private_key_args(parser)
    parser.add_argument(
        "--api-key",
        help=f"Agent API key (or set {API_KEY_ENV})",
    )
    parser.add_argument(
        "--event",
        help="Path to event JSON with fields for VeriAgentClient.submit_event",
    )
    parser.add_argument("--event-id")
    parser.add_argument("--task-id")
    parser.add_argument("--model-name")
    parser.add_argument(
        "--tool-calls",
        help="Comma-separated tool call names",
    )
    parser.add_argument("--input-hash")
    parser.add_argument("--output-hash")
    parser.add_argument("--policy-version")
    parser.add_argument("--timestamp", default=None)
    parser.add_argument(
        "--metadata-json",
        help="Optional metadata as a JSON object string",
    )
    parser.add_argument(
        "--output-event",
        help="Optional path to write the signed event JSON (for veriagent verify)",
    )


def _resolve_verify_inputs(args: argparse.Namespace) -> tuple[dict, dict, dict]:
    event_payload = load_json_file(args.event)

    proof_payload: dict | None = None
    anchor_payload: dict | None = None

    if args.proof:
        proof_payload = load_json_file(args.proof)
    if args.anchor:
        anchor_payload = load_json_file(args.anchor)

    if args.api_base_url:
        batch_id = args.batch_id or (proof_payload or {}).get("batch_id")
        event_id = args.event_id or (proof_payload or {}).get("event_id")
        if event_id is None:
            unsigned = {
                key: value
                for key, value in event_payload.items()
                if key not in {"signature", "verification_method"}
            }
            event_id = unsigned.get("event_id")

        if proof_payload is None:
            if not batch_id or not event_id:
                raise VerificationInputError(
                    "Fetching proof requires --batch-id and --event-id "
                    "(or proof.batch_id / proof.event_id in files)"
                )
            proof_payload = fetch_proof_payload(args.api_base_url, batch_id, event_id)

        if anchor_payload is None:
            batch_id = batch_id or proof_payload.get("batch_id")
            if not batch_id:
                raise VerificationInputError(
                    "Fetching anchor requires --batch-id or proof.batch_id"
                )
            anchor_payload = fetch_anchor_payload(args.api_base_url, batch_id)
            anchor_payload = enrich_anchor_with_merkle_root(anchor_payload, proof_payload)

        if event_payload.get("canonical_event_json"):
            if not event_id:
                raise VerificationInputError(
                    "Fetching event requires --event-id when --event is a stored-event wrapper"
                )
            event_payload = fetch_event_payload(args.api_base_url, event_id)

    if proof_payload is None or anchor_payload is None:
        raise VerificationInputError("Both --proof and --anchor are required unless using --api-base-url")

    return event_payload, proof_payload, anchor_payload


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        event_payload, proof_payload, anchor_payload = _resolve_verify_inputs(args)
        result = verify_audit_evidence(event_payload, proof_payload, anchor_payload)
    except VerificationInputError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "FAIL",
                        "verified": False,
                        "error": str(exc),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(result.status)
        for step in result.steps:
            marker = "ok" if step.passed else "fail"
            print(f"  [{marker}] {step.step}: {step.detail}")
        if result.verified:
            print(f"event_hash={result.event_hash}")
            print(f"merkle_root={result.merkle_root}")
            print(f"batch_id={result.batch_id}")
            if result.anchor_tx_hash:
                print(f"anchor_tx_hash={result.anchor_tx_hash}")

    return 0 if result.verified else 1


def _cmd_register_request(args: argparse.Namespace) -> int:
    try:
        private_key = _load_private_key(
            private_key=args.private_key,
            private_key_file=args.private_key_file,
        )
        result = create_registration_request(
            args.api_base_url,
            private_key_base64=private_key,
            agent_name=args.agent_name,
            agent_type=args.agent_type,
            organization_name=args.organization_name,
            contact_email=args.contact_email,
            use_case_summary=args.use_case_summary,
            description=args.description,
        )
    except (ValueError, RegistrationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output:
        try:
            _write_json_file(args.output, result)
        except OSError as exc:
            print(f"ERROR: failed to write --output: {exc}", file=sys.stderr)
            return 1

    _print_json(result)
    return 0


def _cmd_register_prove(args: argparse.Namespace) -> int:
    try:
        private_key = _load_private_key(
            private_key=args.private_key,
            private_key_file=args.private_key_file,
        )
        proof_payload = None
        if args.proof_payload:
            loaded = load_json_file(args.proof_payload)
            if "proof_payload" in loaded and isinstance(loaded["proof_payload"], dict):
                proof_payload = loaded["proof_payload"]
            else:
                proof_payload = loaded
        result = submit_registration_proof(
            args.api_base_url,
            request_id=args.request_id,
            private_key_base64=private_key,
            proof_payload=proof_payload,
        )
    except (ValueError, RegistrationError, VerificationInputError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_json(result)
    return 0


def _cmd_register_claim(args: argparse.Namespace) -> int:
    try:
        private_key = _load_private_key(
            private_key=args.private_key,
            private_key_file=args.private_key_file,
        )
        result = claim_registration_credentials(
            args.api_base_url,
            request_id=args.request_id,
            private_key_base64=private_key,
            retrieval_token=args.retrieval_token,
        )
    except (ValueError, RegistrationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    api_key = result.get("api_key")
    if args.output_key_file and isinstance(api_key, str):
        try:
            Path(args.output_key_file).write_text(api_key + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: failed to write --output-key-file: {exc}", file=sys.stderr)
            return 1

    _print_json(result)
    return 0


def _resolve_submit_fields(args: argparse.Namespace) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if args.event:
        fields.update(load_json_file(args.event))

    overrides = {
        "event_id": args.event_id,
        "task_id": args.task_id,
        "model_name": args.model_name,
        "input_hash": args.input_hash,
        "output_hash": args.output_hash,
        "policy_version": args.policy_version,
        "timestamp": args.timestamp,
    }
    for key, value in overrides.items():
        if value is not None:
            fields[key] = value

    if args.tool_calls is not None:
        fields["tool_calls"] = [part.strip() for part in args.tool_calls.split(",") if part.strip()]

    if args.metadata_json is not None:
        metadata = json.loads(args.metadata_json)
        if not isinstance(metadata, dict):
            raise ValueError("--metadata-json must be a JSON object")
        fields["metadata"] = metadata

    required = (
        "event_id",
        "task_id",
        "model_name",
        "tool_calls",
        "input_hash",
        "output_hash",
        "policy_version",
    )
    missing = [name for name in required if name not in fields or fields[name] is None]
    if missing:
        raise ValueError(
            "Missing event fields: "
            + ", ".join(missing)
            + " (provide via --event FILE and/or flags)"
        )
    if not isinstance(fields["tool_calls"], list):
        raise ValueError("tool_calls must be a list")
    return fields


def _cmd_submit(args: argparse.Namespace) -> int:
    try:
        private_key = _load_private_key(
            private_key=args.private_key,
            private_key_file=args.private_key_file,
        )
        api_key = (args.api_key or os.environ.get(API_KEY_ENV, "")).strip()
        if not api_key:
            raise ValueError(f"API key required via --api-key or {API_KEY_ENV}")
        fields = _resolve_submit_fields(args)
        client = VeriAgentClient(
            api_base_url=args.api_base_url,
            agent_api_key=api_key,
            private_key_base64=private_key,
        )
        signed_event = client.build_signed_payload(
            event_id=fields["event_id"],
            task_id=fields["task_id"],
            model_name=fields["model_name"],
            tool_calls=fields["tool_calls"],
            input_hash=fields["input_hash"],
            output_hash=fields["output_hash"],
            policy_version=fields["policy_version"],
            timestamp=fields.get("timestamp"),
            metadata=fields.get("metadata"),
        )
        result = client.submit_signed_payload(signed_event)
        if args.output_event:
            Path(args.output_event).write_text(
                json.dumps(signed_event, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (ValueError, RegistrationError, VerificationInputError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # httpx / network errors from VeriAgentClient
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_json(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="veriagent",
        description="VeriAgent registration, event submit, and offline verifier tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_verify_parser(subparsers)
    _build_register_parser(subparsers)
    _build_submit_parser(subparsers)
    args = parser.parse_args(argv)

    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "register":
        if args.register_command == "request":
            return _cmd_register_request(args)
        if args.register_command == "prove":
            return _cmd_register_prove(args)
        if args.register_command == "claim":
            return _cmd_register_claim(args)
        parser.error(f"Unknown register command: {args.register_command}")
        return 2
    if args.command == "submit":
        return _cmd_submit(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
