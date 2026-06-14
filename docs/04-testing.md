# Testing Guide

## Run tests

### Backend

From the project root:

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

### Frontend (v0.9.3+)

From `frontend/`:

```bash
npm run build   # TypeScript check + production bundle
npm run lint
```

Browser signing utilities live under `frontend/src/utils/` (`didKey.ts`, `canonicalize.ts`, `signEvent.ts`, `credentials.ts`). JCS output should match backend `jcs.canonicalize` for the same unsigned event object.

### Python SDK (v0.9.4+)

From `sdk/python/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -v
```

SDK tests cover DID derivation, Ed25519 signing, canonicalization stability (cross-checked against a backend canonical vector), signed payload construction, and mocked HTTP submission with `X-VeriAgent-API-Key`. See [sdk/python/README.md](../sdk/python/README.md) for install and usage.

Verbose output:

```bash
python -m pytest -v
```

## Test layout

| File | Coverage |
|------|----------|
| `tests/test_hashing.py` | RFC 8785 / JCS canonicalization and SHA-256 commitments |
| `tests/test_storage.py` | SQLite storage, duplicate detection, retrieval |
| `tests/test_receipts.py` | HMAC-SHA256 ingestion receipt signing and verification |
| `tests/test_merkle.py` | Merkle root, inclusion proof generation, and verification |
| `tests/test_batches.py` | Batch creation, retrieval, proof API, and Merkle verify API |
| `tests/test_api.py` | FastAPI endpoints including receipt responses |
| `tests/test_anchoring.py` | On-chain anchor helpers (batch id, metadata hash, ABI loading, config) |
| `tests/test_batch_anchor_api.py` | Batch anchor API with monkeypatched web3 calls (no Anvil required) |
| `tests/test_agents_api.py` | Agent registry registration, Ed25519 `did:key` binding validation, and lookup with admin key auth |
| `tests/test_audit_event_auth.py` | Agent API key auth for `POST /audit/events` and public endpoint regression |
| `tests/test_signatures.py` | Ed25519 key generation, signing, verification, real `did:key` encoding/decoding, and deprecated demo DID helpers |
| `tests/test_signed_audit_events.py` | Ed25519 event signature enforcement on ingestion and stored metadata |
| `sdk/python/tests/test_sdk.py` | Python SDK: DID derivation, signing, JCS canonicalization, client payload, mocked HTTP |

## Isolation

Tests use isolated resources via environment variables set in `tests/conftest.py`:

- `VERIAGENT_DB_PATH` — temporary SQLite database per test
- `VERIAGENT_RECEIPT_SECRET` — fixed secret for deterministic receipt tests
- `VERIAGENT_ADMIN_API_KEY` — fixed admin key for agent registry tests

## Receipt tests

Receipt unit tests cover:

- Stable payload construction (`event_id`, `event_hash`, `created_at`)
- Deterministic HMAC-SHA256 signatures
- Valid signature verification
- Rejection of tampered payload fields
- Rejection of signatures produced with a different secret
- Development fallback secret when `VERIAGENT_RECEIPT_SECRET` is unset

API tests assert that `POST /audit/events` returns a verifiable receipt and that `GET /audit/events/{event_id}` still returns stored metadata including `canonical_event_json`, `verification_method`, and `signature_algorithm`.

## Merkle batch tests

Merkle unit tests cover:

- Single-leaf root equals the leaf hash
- Two-leaf root and proofs
- Odd leaf count with last-leaf duplication
- Deterministic roots regardless of input order
- Valid and tampered inclusion proof verification

Batch API tests cover:

- Rejecting batch creation when no events exist (with valid admin key)
- Creating and retrieving batches (admin key on `POST`, public `GET`)
- Batching only newly stored events on subsequent runs
- `POST /audit/merkle/verify` with valid and tampered proofs
- `GET /audit/batches/{batch_id}/proof/{event_id}` for included, missing, and not-in-batch cases
- Proof responses verifying successfully via `POST /audit/merkle/verify`

## Batch and anchor admin auth tests

`tests/test_batch_admin_auth.py` covers:

- `POST /audit/batches` without admin key returns `401`
- Invalid admin key on batch creation returns `401`
- Valid admin key creates a batch successfully
- `POST /audit/batches/{batch_id}/anchor` without admin key returns `401`
- Invalid admin key on anchoring returns `401`
- Valid admin key anchors successfully (with mocked on-chain calls)

Shared helpers in `tests/support.py` attach `X-VeriAgent-Admin-Key` via `post_audit_batch()` and `post_batch_anchor()`.

## Anchoring tests

Anchoring unit tests cover:

- Deterministic `batch_id` and batch metadata hashing
- Loading `VeriAgentAnchor` ABI from `backend/app/abi/VeriAgentAnchor.json` (committed JSON array)
- Optional Foundry-style artifact compatibility (`{"abi": [...]}`)
- Missing or invalid anchoring environment variables

The backend test suite does not require `contracts/out/` or a local Foundry build. Refresh `backend/app/abi/VeriAgentAnchor.json` when the Solidity contract ABI changes.

## Batch anchor API tests

Batch anchor API tests use `monkeypatch` on `app.batch_anchoring.anchoring` (and config loading). They do not require a running Anvil node.

Coverage includes:

- `GET /audit/batches/{batch_id}/anchor` returns `404` before anchoring
- `POST /audit/batches/{batch_id}/anchor` returns `404` for a missing batch
- Successful anchor stores a `batch_anchors` row when mocks succeed
- Second `POST` is idempotent (`already_anchored: true`, no second `anchor_batch` call)
- `GET` returns the stored record after anchoring

## Agent registry tests

Agent registry API tests cover:

- Successful registration with admin key; response includes raw `api_key` with `va_agent_` prefix
- `401 Unauthorized` when admin key is missing or invalid
- `409 Conflict` for duplicate `agent_did`
- `400 Bad Request` for invalid `agent_did`, deprecated `did:key:demo:...`, mismatched `public_key`, or wrong `verification_method`
- `GET /agents/{agent_did}` returns metadata without `api_key_hash` or raw `api_key`
- `404 Not Found` for unregistered agents
- Stored row contains SHA-256 hash of the issued API key, not the raw key

## Audit event auth tests

Audit ingestion auth tests cover:

- `POST /audit/events` without `X-VeriAgent-API-Key` returns `401`
- Invalid agent API key returns `401`
- Valid active agent key stores an event with a verifiable receipt
- `event.agent_id` mismatch with authenticated agent returns `403`
- Inactive agent key returns `403`
- Public endpoints still work without agent key: `GET /health`, `POST /audit/hash`, `GET /audit/events/{event_id}`, `POST /audit/verify`, batch GET/proof, and `POST /audit/merkle/verify`
- Batch creation and anchoring require admin key: see `tests/test_batch_admin_auth.py`

Shared helpers in `tests/support.py` register a test agent, sign the unsigned canonical event payload, attach `X-VeriAgent-API-Key` to event submission, and attach `X-VeriAgent-Admin-Key` for batch create/anchor via `post_audit_batch()` and `post_batch_anchor()`.

## Signed audit event tests

Signed event tests cover:

- Valid Ed25519 signature accepted for a registered agent
- Tampered unsigned payload rejected (`403`)
- Wrong signature, wrong public key, and wrong `verification_method` rejected (`403`)
- Missing `signature` or `verification_method` rejected (`400`)
- Stored events retain signature metadata in SQLite; GET exposes `verification_method` and `signature_algorithm`
- HMAC ingestion receipts still verify after signed ingestion
- Merkle batching still works for signed events

Signing boundary under test: RFC8785/JCS bytes of the audit event **without** `signature` or `verification_method`. The event hash and Merkle leaves use that same unsigned canonical payload.

Manual signing helpers:

```bash
# One-off signed JSON payload (stdout)
python scripts/sign_demo_event.py

# Python SDK (recommended for external agents)
cd sdk/python && pip install -e . && python -c "
from veriagent import VeriAgentClient
client = VeriAgentClient('http://127.0.0.1:8000', 'va_agent_...', 'YOUR_PRIVATE_KEY_B64')
print(client.agent_did)
"
```

See [sdk/python/README.md](../sdk/python/README.md) for full `submit_event` examples.

Each run generates unique `event_id` and `task_id` values by default (format: `demo-event-<UTC timestamp>-<short uuid>` and `task-demo-<UTC timestamp>-<short uuid>`), so repeated manual POST tests do not hit duplicate `event_id` conflicts.

Set `VERIAGENT_DEMO_PRIVATE_KEY` to reuse the same agent identity (`agent_did` as `did:key:z...`, `verification_method`, and `public_key`) across runs while still emitting fresh event and task IDs.

`sign_demo_event.py` emits real Ed25519 `did:key` identifiers (`did:key:z...`), not deprecated `did:key:demo:...` values.

## Python SDK tests (v0.9.4)

The minimal Python SDK lives at `sdk/python/`. Tests are independent of the backend test suite (no FastAPI or SQLite required).

```bash
cd sdk/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -v
```

Coverage in `sdk/python/tests/test_sdk.py`:

- Public key, `did:key`, and `verification_method` derivation (including demo key from `scripts/demo_agent.env`)
- Ed25519 signing over canonical bytes
- Canonicalization stability and byte match against a backend JCS vector
- `VeriAgentClient.build_signed_payload` structure and signature validity
- Mocked `submit_event` sends `X-VeriAgent-API-Key` and POSTs to `/audit/events`

Cross-check (optional, from repo root with backend venv active): SDK signatures match `backend/tests/support.py` `sign_event_payload` for the same unsigned event.

Install and usage: [sdk/python/README.md](../sdk/python/README.md).

## Manual API checks

With the server running (`uvicorn app.main:app --reload`):

1. Register an agent via `POST /agents/register` (admin key required) and save the returned `api_key`, `agent_did`, `verification_method`, and `public_key`.
2. Build a signed request body (unsigned event fields + `verification_method` + Ed25519 `signature` over the unsigned RFC8785/JCS canonical bytes). Use the [Python SDK](../sdk/python/README.md) (`VeriAgentClient.submit_event`), `python scripts/sign_demo_event.py` for a sample payload, or sign in the browser via the [public dashboard](https://dimikog.github.io/veriagent/) (v0.9.3 demo flow).
3. `POST /audit/events` with the signed audit event and header `X-VeriAgent-API-Key: {api_key}`; set `agent_id` to the registered `agent_did`.
4. Confirm the response includes `event_id`, `event_hash`, `created_at`, and `receipt.signature`.
5. `GET /audit/events/{event_id}` should include `verification_method` and `signature_algorithm`.
6. Recompute receipt verification locally using the same secret, or call application code that uses `verify_receipt`.

For production-like runs, set a strong secret:

```bash
export VERIAGENT_RECEIPT_SECRET="replace-with-a-long-random-secret"
export VERIAGENT_ADMIN_API_KEY="replace-with-a-long-random-admin-key"
```

## Production end-to-end check (v0.9.3)

Full trust-chain validation requires **signed** event ingestion. Options: the [Python SDK](../sdk/python/README.md) (`VeriAgentClient`), the dashboard browser demo (step 2 credentials + step 3), [manual API checks](#manual-api-checks), or `scripts/sign_demo_event.py`.

### Signed ingestion + chain validation

1. Register an agent via `POST /agents/register` with `X-VeriAgent-Admin-Key`; save `api_key`, `agent_did`, `verification_method`, and `public_key`.
2. Submit a signed event with the [Python SDK](../sdk/python/README.md) or build a signed body with `python scripts/sign_demo_event.py` (set `VERIAGENT_DEMO_PRIVATE_KEY` to reuse the same agent identity across runs).
3. `POST /audit/events` with `X-VeriAgent-API-Key` and the signed payload; confirm `receipt.signature` verifies.
4. `POST /audit/batches` — note `batch_id` and `merkle_root` (requires `X-VeriAgent-Admin-Key`).
5. `GET /audit/batches/{batch_id}/proof/{event_id}` — confirm proof verifies via `POST /audit/merkle/verify`.
6. `POST /audit/batches/{batch_id}/anchor` — requires admin key and Besu anchoring env on the API host (`VERIAGENT_CHAIN_ID=424242` for Besu Edu-Net); confirm `tx_hash`.
7. Open `https://blockexplorer.dimikog.org/tx/{tx_hash}` and confirm the anchor transaction on chain `424242`.

### Dashboard end-to-end check

With the [public dashboard](https://dimikog.github.io/veriagent/) and API at `https://veriagent.dimikog.org`:

1. **API health check** — expect a healthy response with API version `0.9.3`.
2. **Agent credentials** — enter registered Agent DID, `va_agent_...` API key, and base64 Ed25519 private key (demo mode); click **Use agent credentials** and confirm **Ready**.
3. **Create signed audit event** — submit a signed event from the browser; confirm `event_id` and `event_hash` in the workflow sidebar.
4. **Create Merkle batch** — confirm `batch_id` and `merkle_root`.
5. **Retrieve Merkle proof** — confirm verification succeeds in the status panel.
6. **Anchor batch** — requires production backend Besu anchoring env vars (`VERIAGENT_CHAIN_ID=424242`); confirm `tx_hash` in the sidebar.
7. **Show anchor result** — confirm stored anchor metadata matches step 6.
8. After anchoring, open **View on Blockscout** (links to `https://blockexplorer.dimikog.org/tx/{hash}`).

Local dashboard dev: [frontend/README.md](../frontend/README.md).
