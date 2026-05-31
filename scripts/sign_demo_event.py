#!/usr/bin/env python3
"""Sign a sample audit event for manual POST /audit/events testing."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.hashing import canonicalize_event  # noqa: E402
from app.models import AuditEvent  # noqa: E402
from app.signatures import (  # noqa: E402
    demo_did_from_public_key,
    demo_verification_method,
    generate_ed25519_keypair,
    public_key_to_base64,
    sign_bytes,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402


def load_private_key_base64() -> tuple[str, str]:
    env_private_key = os.environ.get("VERIAGENT_DEMO_PRIVATE_KEY")
    if env_private_key:
        private_key = Ed25519PrivateKey.from_private_bytes(
            __import__("base64").b64decode(env_private_key)
        )
        public_key_b64 = public_key_to_base64(private_key.public_key())
        return env_private_key, public_key_b64

    private_key_b64, public_key_b64 = generate_ed25519_keypair()
    print(
        "Generated demo Ed25519 keypair. Set VERIAGENT_DEMO_PRIVATE_KEY to reuse it:",
        file=sys.stderr,
    )
    print(f"export VERIAGENT_DEMO_PRIVATE_KEY='{private_key_b64}'", file=sys.stderr)
    return private_key_b64, public_key_b64


def main() -> int:
    private_key_b64, public_key_b64 = load_private_key_base64()
    agent_did = demo_did_from_public_key(public_key_b64)
    verification_method = demo_verification_method(agent_did)

    event = AuditEvent(
        event_id="demo-event-001",
        agent_id=agent_did,
        task_id="task-demo-001",
        model_name="demo-model",
        tool_calls=["search"],
        input_hash="sha256:demo-input",
        output_hash="sha256:demo-output",
        policy_version="policy-v0.1",
        timestamp="2026-05-31T12:00:00Z",
        metadata={"purpose": "sign-demo-event"},
    )

    signature = sign_bytes(private_key_b64, canonicalize_event(event))
    request_body = {
        **event.model_dump(mode="json"),
        "verification_method": verification_method,
        "signature": signature,
    }

    print(json.dumps(request_body, indent=2))
    print(
        "\nRegister the agent with this public_key and verification_method, then POST the JSON above to /audit/events with X-VeriAgent-API-Key.",
        file=sys.stderr,
    )
    print(f"agent_did: {agent_did}", file=sys.stderr)
    print(f"verification_method: {verification_method}", file=sys.stderr)
    print(f"public_key: {public_key_b64}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
