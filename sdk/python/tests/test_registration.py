"""Tests for registration helpers and CLI register/submit commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from veriagent.identity import derive_agent_identity
from veriagent.registration import (
    RegistrationError,
    build_credentials_claim_payload,
    claim_registration_credentials,
    create_registration_request,
    get_registration_request_status,
    sign_payload,
    submit_registration_proof,
)
from veriagent.signing import canonicalize_unsigned_event
from veriagent_cli import main as cli_main

DEMO_PRIVATE_KEY_B64 = "6RY+YrXELvYnMSdDKWmpDNsUG94gJrm/NGEnKw1+bWs="
DEMO_PUBLIC_KEY_B64, DEMO_AGENT_DID, DEMO_VERIFICATION_METHOD = derive_agent_identity(
    DEMO_PRIVATE_KEY_B64
)

SAMPLE_PROOF_PAYLOAD = {
    "purpose": "veriagent-registration",
    "request_id": "req-001",
    "agent_did": DEMO_AGENT_DID,
    "nonce": "nonce-abc",
    "issued_at": "2026-07-17T12:00:00+00:00",
    "expires_at": "2026-07-17T12:15:00+00:00",
}


def test_sign_payload_is_jcs_ed25519():
    signature = sign_payload(DEMO_PRIVATE_KEY_B64, SAMPLE_PROOF_PAYLOAD)
    assert isinstance(signature, str)
    assert signature

    # Same bytes as canonicalize_unsigned_event / jcs
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    import base64

    public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(DEMO_PUBLIC_KEY_B64))
    public_key.verify(
        base64.b64decode(signature),
        canonicalize_unsigned_event(SAMPLE_PROOF_PAYLOAD),
    )


def test_build_credentials_claim_payload():
    payload = build_credentials_claim_payload("req-001", DEMO_AGENT_DID)
    assert payload == {
        "purpose": "veriagent-credentials-claim",
        "request_id": "req-001",
        "agent_did": DEMO_AGENT_DID,
    }


def test_create_registration_request_posts_identity(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "request_id": "req-001",
                "agent_did": DEMO_AGENT_DID,
                "challenge_nonce": "nonce",
                "challenge_expires_at": "2026-07-17T12:15:00+00:00",
                "proof_payload": SAMPLE_PROOF_PAYLOAD,
            }

    def fake_post(url: str, json: dict, timeout: float):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("veriagent.registration.httpx.post", fake_post)

    result = create_registration_request(
        "https://veriagent.example/",
        private_key_base64=DEMO_PRIVATE_KEY_B64,
        agent_name="Demo",
        agent_type="llm-agent",
        organization_name="Acme",
        contact_email="ops@example.com",
        use_case_summary="Pilot",
        description="desc",
    )

    assert result["request_id"] == "req-001"
    assert captured["url"] == "https://veriagent.example/registration/requests"
    assert captured["json"]["agent_did"] == DEMO_AGENT_DID
    assert captured["json"]["public_key"] == DEMO_PUBLIC_KEY_B64
    assert captured["json"]["verification_method"] == DEMO_VERIFICATION_METHOD
    assert captured["json"]["agent_name"] == "Demo"


def test_submit_registration_proof_fetches_payload_when_omitted(monkeypatch):
    posts: list[dict] = []

    class StatusResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "request_id": "req-001",
                "status": "pending",
                "agent_did": DEMO_AGENT_DID,
                "proof_payload": SAMPLE_PROOF_PAYLOAD,
            }

    class ProofResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "request_id": "req-001",
                "status": "pending",
                "proof_submitted_at": "2026-07-17T12:01:00+00:00",
            }

    def fake_get(url: str, timeout: float):
        assert url.endswith("/registration/requests/req-001")
        return StatusResponse()

    def fake_post(url: str, json: dict, timeout: float):
        posts.append({"url": url, "json": json})
        return ProofResponse()

    monkeypatch.setattr("veriagent.registration.httpx.get", fake_get)
    monkeypatch.setattr("veriagent.registration.httpx.post", fake_post)

    result = submit_registration_proof(
        "https://veriagent.example",
        request_id="req-001",
        private_key_base64=DEMO_PRIVATE_KEY_B64,
    )

    assert result["request_id"] == "req-001"
    assert len(posts) == 1
    assert posts[0]["url"].endswith("/registration/requests/req-001/proof")
    assert posts[0]["json"]["verification_method"] == DEMO_VERIFICATION_METHOD
    assert posts[0]["json"]["proof_signature"] == sign_payload(
        DEMO_PRIVATE_KEY_B64, SAMPLE_PROOF_PAYLOAD
    )


def test_submit_registration_proof_uses_provided_payload(monkeypatch):
    posts: list[dict] = []

    class ProofResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"request_id": "req-001", "status": "pending", "proof_submitted_at": "t"}

    def boom_get(*_args, **_kwargs):
        raise AssertionError("GET should not be called when proof_payload is provided")

    def fake_post(url: str, json: dict, timeout: float):
        posts.append(json)
        return ProofResponse()

    monkeypatch.setattr("veriagent.registration.httpx.get", boom_get)
    monkeypatch.setattr("veriagent.registration.httpx.post", fake_post)

    submit_registration_proof(
        "https://veriagent.example",
        request_id="req-001",
        private_key_base64=DEMO_PRIVATE_KEY_B64,
        proof_payload=SAMPLE_PROOF_PAYLOAD,
    )
    assert posts[0]["proof_signature"] == sign_payload(
        DEMO_PRIVATE_KEY_B64, SAMPLE_PROOF_PAYLOAD
    )


def test_submit_registration_proof_errors_when_payload_missing(monkeypatch):
    class StatusResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "request_id": "req-001",
                "status": "pending",
                "agent_did": DEMO_AGENT_DID,
                "proof_payload": None,
            }

    monkeypatch.setattr(
        "veriagent.registration.httpx.get",
        lambda *a, **k: StatusResponse(),
    )

    with pytest.raises(RegistrationError, match="proof_payload not available"):
        submit_registration_proof(
            "https://veriagent.example",
            request_id="req-001",
            private_key_base64=DEMO_PRIVATE_KEY_B64,
        )


def test_claim_registration_credentials(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "request_id": "req-001",
                "agent_did": DEMO_AGENT_DID,
                "api_key": "va_agent_secret",
                "agent_status": "active",
                "verification_method": DEMO_VERIFICATION_METHOD,
            }

    def fake_post(url: str, json: dict, headers: dict | None, timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("veriagent.registration.httpx.post", fake_post)

    result = claim_registration_credentials(
        "https://veriagent.example",
        request_id="req-001",
        private_key_base64=DEMO_PRIVATE_KEY_B64,
        retrieval_token="vrt_token",
    )

    assert result["api_key"] == "va_agent_secret"
    assert captured["url"].endswith("/registration/requests/req-001/credentials")
    assert captured["headers"]["X-VeriAgent-Retrieval-Token"] == "vrt_token"
    expected_sig = sign_payload(
        DEMO_PRIVATE_KEY_B64,
        build_credentials_claim_payload("req-001", DEMO_AGENT_DID),
    )
    assert captured["json"]["proof_signature"] == expected_sig
    assert captured["json"]["verification_method"] == DEMO_VERIFICATION_METHOD


def test_get_registration_request_status(monkeypatch):
    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"request_id": "req-001", "status": "pending"}

    monkeypatch.setattr(
        "veriagent.registration.httpx.get",
        lambda *a, **k: FakeResponse(),
    )
    assert get_registration_request_status("https://x.example", "req-001")["status"] == "pending"


def test_cli_register_prove(monkeypatch, tmp_path: Path, capsys):
    key_file = tmp_path / "key.txt"
    key_file.write_text(DEMO_PRIVATE_KEY_B64 + "\n", encoding="utf-8")

    def fake_submit(api_base_url, *, request_id, private_key_base64, proof_payload=None):
        assert api_base_url == "https://veriagent.example"
        assert request_id == "req-001"
        assert private_key_base64 == DEMO_PRIVATE_KEY_B64
        assert proof_payload is None
        return {
            "request_id": request_id,
            "status": "pending",
            "proof_submitted_at": "2026-07-17T12:01:00+00:00",
        }

    monkeypatch.setattr("veriagent_cli.submit_registration_proof", fake_submit)

    code = cli_main(
        [
            "register",
            "prove",
            "--request-id",
            "req-001",
            "--api-base-url",
            "https://veriagent.example",
            "--private-key-file",
            str(key_file),
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["request_id"] == "req-001"


def test_cli_register_claim_writes_key(monkeypatch, tmp_path: Path, capsys):
    key_file = tmp_path / "key.txt"
    key_file.write_text(DEMO_PRIVATE_KEY_B64, encoding="utf-8")
    out_key = tmp_path / "api.key"

    def fake_claim(api_base_url, *, request_id, private_key_base64, retrieval_token=None):
        return {
            "request_id": request_id,
            "agent_did": DEMO_AGENT_DID,
            "api_key": "va_agent_claimed",
            "agent_status": "active",
            "verification_method": DEMO_VERIFICATION_METHOD,
        }

    monkeypatch.setattr("veriagent_cli.claim_registration_credentials", fake_claim)

    code = cli_main(
        [
            "register",
            "claim",
            "--request-id",
            "req-001",
            "--api-base-url",
            "https://veriagent.example",
            "--private-key-file",
            str(key_file),
            "--output-key-file",
            str(out_key),
        ]
    )
    assert code == 0
    assert out_key.read_text(encoding="utf-8").strip() == "va_agent_claimed"
    assert json.loads(capsys.readouterr().out)["api_key"] == "va_agent_claimed"


def test_cli_submit_from_event_file(monkeypatch, tmp_path: Path, capsys):
    key_file = tmp_path / "key.txt"
    key_file.write_text(DEMO_PRIVATE_KEY_B64, encoding="utf-8")
    event_file = tmp_path / "event.json"
    event_file.write_text(
        json.dumps(
            {
                "event_id": "event-1",
                "task_id": "task-1",
                "model_name": "demo",
                "tool_calls": ["search"],
                "input_hash": "sha256:in",
                "output_hash": "sha256:out",
                "policy_version": "v1",
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self, api_base_url, agent_api_key, private_key_base64):
            assert api_base_url == "https://veriagent.example"
            assert agent_api_key == "va_agent_secret"
            assert private_key_base64 == DEMO_PRIVATE_KEY_B64

        def build_signed_payload(self, **kwargs):
            assert kwargs["event_id"] == "event-1"
            return {"event_id": "event-1", "signature": "sig", "verification_method": "vm"}

        def submit_signed_payload(self, payload):
            assert payload["event_id"] == "event-1"
            return {"event_id": "event-1", "event_hash": "abc"}

    monkeypatch.setattr("veriagent_cli.VeriAgentClient", FakeClient)

    code = cli_main(
        [
            "submit",
            "--api-base-url",
            "https://veriagent.example",
            "--api-key",
            "va_agent_secret",
            "--private-key-file",
            str(key_file),
            "--event",
            str(event_file),
            "--output-event",
            str(tmp_path / "signed-out.json"),
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["event_hash"] == "abc"
    signed_out = json.loads((tmp_path / "signed-out.json").read_text(encoding="utf-8"))
    assert signed_out["signature"] == "sig"


def test_cli_private_key_from_env(monkeypatch, capsys):
    monkeypatch.setenv("VERIAGENT_PRIVATE_KEY", DEMO_PRIVATE_KEY_B64)

    def fake_create(api_base_url, **kwargs):
        assert kwargs["private_key_base64"] == DEMO_PRIVATE_KEY_B64
        return {"request_id": "req-env", "agent_did": DEMO_AGENT_DID}

    monkeypatch.setattr("veriagent_cli.create_registration_request", fake_create)

    code = cli_main(
        [
            "register",
            "request",
            "--api-base-url",
            "https://veriagent.example",
            "--agent-name",
            "Demo",
            "--agent-type",
            "llm-agent",
            "--organization-name",
            "Acme",
            "--contact-email",
            "ops@example.com",
            "--use-case-summary",
            "Pilot",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["request_id"] == "req-env"
