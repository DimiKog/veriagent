import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veriagent import VeriAgentClient
from veriagent.identity import (
    ed25519_public_key_to_did_key,
    public_key_from_base64,
    public_key_from_private_key_base64,
    verification_method_for_did_key,
)
from veriagent.signing import (
    build_signed_event_payload,
    build_unsigned_event_dict,
    canonicalize_unsigned_event,
    sign_unsigned_event,
)

DEMO_PRIVATE_KEY_B64 = "6RY+YrXELvYnMSdDKWmpDNsUG94gJrm/NGEnKw1+bWs="
DEMO_PUBLIC_KEY_B64 = "B//IAHvaxhD+ChlhwU5fapc8DSLPN1yjmIWmXJTwOOk="
DEMO_AGENT_DID = "did:key:z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN"
DEMO_VERIFICATION_METHOD = (
    "did:key:z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN"
    "#z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN"
)

BACKEND_CANONICAL_SAMPLE = (
    b'{"agent_id":"agent-001","event_id":"event-001","input_hash":"sha256:input123",'
    b'"metadata":{"purpose":"sdk-test"},"model_name":"demo-model","output_hash":"sha256:output456",'
    b'"policy_version":"policy-v0.1","task_id":"task-001","timestamp":"2026-05-26T18:00:00Z",'
    b'"tool_calls":["search","calculator"]}'
)


def generate_ed25519_keypair() -> tuple[str, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_b64 = base64.b64encode(private_key.private_bytes_raw()).decode("ascii")
    public_b64 = base64.b64encode(
        public_key.public_bytes_raw()
    ).decode("ascii")
    return private_b64, public_b64


def verify_signature(public_key_b64: str, payload_bytes: bytes, signature_b64: str) -> bool:
    try:
        public_key = public_key_from_base64(public_key_b64)
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(signature, payload_bytes)
    except (ValueError, TypeError, InvalidSignature):
        return False
    return True


def sample_unsigned_event(agent_id: str = DEMO_AGENT_DID) -> dict:
    return build_unsigned_event_dict(
        event_id="event-001",
        agent_id=agent_id,
        task_id="task-001",
        model_name="demo-model",
        tool_calls=["search", "calculator"],
        input_hash="sha256:input123",
        output_hash="sha256:output456",
        policy_version="policy-v0.1",
        timestamp="2026-05-26T18:00:00Z",
        metadata={"purpose": "sdk-test"},
    )


def test_public_key_derived_from_private_key():
    public_key = public_key_from_private_key_base64(DEMO_PRIVATE_KEY_B64)

    assert public_key == DEMO_PUBLIC_KEY_B64


def test_demo_agent_did_derivation():
    did = ed25519_public_key_to_did_key(DEMO_PUBLIC_KEY_B64)

    assert did == DEMO_AGENT_DID
    assert did.startswith("did:key:z")
    assert not did.startswith("did:key:demo:")


def test_demo_verification_method_derivation():
    verification_method = verification_method_for_did_key(DEMO_AGENT_DID)

    assert verification_method == DEMO_VERIFICATION_METHOD


def test_generated_keypair_produces_valid_did():
    _, public_key_b64 = generate_ed25519_keypair()
    did = ed25519_public_key_to_did_key(public_key_b64)

    assert did.startswith("did:key:z")
    assert verification_method_for_did_key(did) == f"{did}#{did.removeprefix('did:key:')}"


def test_event_signing_verifies_locally():
    private_key_b64, public_key_b64 = generate_ed25519_keypair()
    unsigned_event = sample_unsigned_event(
        agent_id=ed25519_public_key_to_did_key(public_key_b64)
    )

    signature = sign_unsigned_event(private_key_b64, unsigned_event)
    payload = canonicalize_unsigned_event(unsigned_event)

    assert verify_signature(public_key_b64, payload, signature)


def test_canonicalization_is_stable():
    unsigned_event = sample_unsigned_event()

    canonical_1 = canonicalize_unsigned_event(unsigned_event)
    canonical_2 = canonicalize_unsigned_event(unsigned_event)

    assert canonical_1 == canonical_2
    assert isinstance(canonical_1, bytes)


def test_canonicalization_matches_backend_vector():
    unsigned_event = sample_unsigned_event(agent_id="agent-001")

    assert canonicalize_unsigned_event(unsigned_event) == BACKEND_CANONICAL_SAMPLE


def test_client_builds_signed_payload_correctly():
    client = VeriAgentClient(
        api_base_url="http://example.test",
        agent_api_key="va_agent_test",
        private_key_base64=DEMO_PRIVATE_KEY_B64,
    )

    payload = client.build_signed_payload(
        event_id="event-sdk-001",
        task_id="task-001",
        model_name="demo-model",
        tool_calls=["search"],
        input_hash="sha256:input123",
        output_hash="sha256:output456",
        policy_version="policy-v0.1",
        timestamp="2026-05-26T18:00:00Z",
        metadata={"purpose": "sdk-test"},
    )

    assert payload["agent_id"] == DEMO_AGENT_DID
    assert payload["verification_method"] == DEMO_VERIFICATION_METHOD
    assert isinstance(payload["signature"], str)
    assert payload["signature"]

    unsigned = {key: value for key, value in payload.items() if key not in {"signature", "verification_method"}}
    assert verify_signature(
        DEMO_PUBLIC_KEY_B64,
        canonicalize_unsigned_event(unsigned),
        payload["signature"],
    )


def test_build_signed_event_payload_matches_client():
    client = VeriAgentClient(
        api_base_url="http://example.test",
        agent_api_key="va_agent_test",
        private_key_base64=DEMO_PRIVATE_KEY_B64,
    )

    direct = build_signed_event_payload(
        private_key_base64=DEMO_PRIVATE_KEY_B64,
        verification_method=DEMO_VERIFICATION_METHOD,
        event_id="event-sdk-002",
        agent_id=DEMO_AGENT_DID,
        task_id="task-002",
        model_name="demo-model",
        tool_calls=["search"],
        input_hash="sha256:input123",
        output_hash="sha256:output456",
        policy_version="policy-v0.1",
        timestamp="2026-05-26T18:00:00Z",
        metadata=None,
    )
    via_client = client.build_signed_payload(
        event_id="event-sdk-002",
        task_id="task-002",
        model_name="demo-model",
        tool_calls=["search"],
        input_hash="sha256:input123",
        output_hash="sha256:output456",
        policy_version="policy-v0.1",
        timestamp="2026-05-26T18:00:00Z",
        metadata=None,
    )

    assert direct == via_client


def test_submit_event_sends_api_key_header(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "event_id": "event-sdk-http",
                "event_hash": "abc123",
                "created_at": "2026-05-26T18:00:00Z",
                "receipt": {},
            }

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("veriagent.client.httpx.post", fake_post)

    client = VeriAgentClient(
        api_base_url="https://veriagent.example/",
        agent_api_key="va_agent_secret",
        private_key_base64=DEMO_PRIVATE_KEY_B64,
    )

    response = client.submit_event(
        event_id="event-sdk-http",
        task_id="task-http",
        model_name="demo-model",
        tool_calls=["search"],
        input_hash="sha256:input123",
        output_hash="sha256:output456",
        policy_version="policy-v0.1",
        timestamp="2026-05-26T18:00:00Z",
    )

    assert response["event_id"] == "event-sdk-http"
    assert captured["url"] == "https://veriagent.example/audit/events"
    assert captured["headers"]["X-VeriAgent-API-Key"] == "va_agent_secret"
    assert captured["json"]["agent_id"] == DEMO_AGENT_DID
    assert captured["json"]["signature"]
    assert captured["json"]["verification_method"] == DEMO_VERIFICATION_METHOD
