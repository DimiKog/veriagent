# VeriAgent Python SDK (v1.0.0)

Minimal Python client for external agents to submit Ed25519-signed audit events to a VeriAgent API without hand-rolling canonicalization, signing, or auth headers.

Also includes a CLI for public registration (`veriagent register …`), event submit (`veriagent submit`), and an **independent verifier** (`veriagent verify`). See [docs/15-independent-verifier.md](../../docs/15-independent-verifier.md).

The SDK handles:

- Loading an Ed25519 private key from base64
- Deriving the public key, real Ed25519 `did:key`, and `verification_method`
- RFC 8785 / JCS canonicalization of the unsigned audit event
- Ed25519 signing over the canonical bytes
- `POST /audit/events` with `X-VeriAgent-API-Key`
- Public registration helpers: create request, prove ownership, claim credentials

## Install

From the repo root:

```bash
cd sdk/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Create a demo agent private key

Generate a fresh Ed25519 seed (32 raw bytes, base64-encoded):

```bash
python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; import base64; k=Ed25519PrivateKey.generate(); print(base64.b64encode(k.private_bytes_raw()).decode())"
```

Or reuse the repo demo key in `scripts/demo_agent.env`:

```bash
source scripts/demo_agent.env
echo "$VERIAGENT_DEMO_PRIVATE_KEY"
```

Derive the public key, DID, and verification method:

```python
from veriagent import derive_agent_identity

public_key, agent_did, verification_method = derive_agent_identity(
    "YOUR_PRIVATE_KEY_BASE64"
)
print(public_key)
print(agent_did)
print(verification_method)
```

Example output for the demo key in `scripts/demo_agent.env`:

| Field | Value |
| --- | --- |
| `public_key` | `B//IAHvaxhD+ChlhwU5fapc8DSLPN1yjmIWmXJTwOOk=` |
| `agent_did` | `did:key:z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN` |
| `verification_method` | `did:key:z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN#z6MkezV7YRFqjB8RH46omrmEyUDC6NfVsu38sPKbs2MqUQHN` |

You can also inspect a signed sample payload with the existing helper script:

```bash
source scripts/demo_agent.env
python scripts/sign_demo_event.py
```

## Public registration (CLI)

When `VERIAGENT_REGISTRATION_ENABLED` is on, create a request, prove key ownership, wait for admin approval, then claim the agent API key:

```bash
# Private key via --private-key-file, --private-key, or VERIAGENT_PRIVATE_KEY
veriagent register request \
  --api-base-url "$VERIAGENT_API_BASE" \
  --private-key-file ./agent.key \
  --agent-name "Demo Python Agent" \
  --agent-type "llm-agent" \
  --organization-name "Acme" \
  --contact-email "ops@example.com" \
  --use-case-summary "Pilot audit trail" \
  --output ./registration.json

veriagent register prove \
  --request-id <request_id> \
  --api-base-url "$VERIAGENT_API_BASE" \
  --private-key-file ./agent.key

# After approval:
veriagent register claim \
  --request-id <request_id> \
  --api-base-url "$VERIAGENT_API_BASE" \
  --private-key-file ./agent.key \
  --output-key-file ./agent.api_key
```

`register prove` fetches `proof_payload` from `GET /registration/requests/{id}` while the request is still pending and awaiting proof (or accept `--proof-payload` from the create response).

Python helpers: `create_registration_request`, `submit_registration_proof`, `claim_registration_credentials`.

Admin `POST /agents/register` remains available for operators; see [docs/03-api.md](../../docs/03-api.md).

## Submit signed events from Python

```python
from veriagent import VeriAgentClient

client = VeriAgentClient(
    api_base_url="https://veriagent.dimikog.org",
    agent_api_key="va_agent_...",  # from registration
    private_key_base64="YOUR_PRIVATE_KEY_BASE64",
)

# agent_did and verification_method are derived automatically
print(client.agent_did)
print(client.verification_method)

response = client.submit_event(
    event_id="event-sdk-001",
    task_id="task-001",
    model_name="demo-model",
    tool_calls=["search", "calculator"],
    input_hash="sha256:input123",
    output_hash="sha256:output456",
    policy_version="policy-v0.1",
    metadata={"purpose": "sdk-demo"},
)

print(response["event_id"])
print(response["event_hash"])
print(response["receipt"])
```

If `timestamp` is omitted, the SDK uses the current UTC ISO timestamp (matching backend JSON datetime encoding).

Or via CLI (event JSON and/or field flags):

```bash
veriagent submit \
  --api-base-url "$VERIAGENT_API_BASE" \
  --api-key "$VERIAGENT_API_KEY" \
  --private-key-file ./agent.key \
  --event ./event.json
```

### Signing boundary

The signature covers the RFC 8785 / JCS canonical JSON of the audit event **excluding** `signature` and `verification_method`. The backend Python `jcs` package remains the verification source of truth; this SDK uses the same `jcs` library.

## Run SDK tests

```bash
cd sdk/python
source .venv/bin/activate
python -m pytest -v
```

Tests cover DID derivation, signing, canonicalization stability (cross-checked against the backend hasher), signed payload construction, mocked HTTP submission with `X-VeriAgent-API-Key`, and offline verifier bundles (`tests/test_verifier.py`).

## Independent verifier CLI

After `pip install -e ".[dev]"`:

```bash
veriagent verify --event event.json --proof proof.json --anchor anchor.json
veriagent verify --event event.json --proof proof.json --anchor anchor.json --json
```

Optional public API fetch (verification still runs locally):

```bash
veriagent verify \
  --event event.json \
  --api-base-url https://veriagent.dimikog.org \
  --batch-id <uuid> \
  --event-id <event_id>
```

Full evidence bundle format and exit codes: [docs/15-independent-verifier.md](../../docs/15-independent-verifier.md).

## Package layout

```text
sdk/python/
  pyproject.toml
  README.md
  veriagent_cli.py
  veriagent/
    __init__.py
    client.py
    hashing.py
    identity.py
    merkle.py
    registration.py
    signing.py
    verifier.py
  tests/
```
