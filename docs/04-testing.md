# Testing Guide

## Run tests

From the project root:

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

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
| `tests/test_agents_api.py` | Agent registry registration and lookup with admin key auth |
| `tests/test_audit_event_auth.py` | Agent API key auth for `POST /audit/events` and public endpoint regression |

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

API tests assert that `POST /audit/events` returns a verifiable receipt and that `GET /audit/events/{event_id}` still returns stored metadata including `canonical_event_json`.

## Merkle batch tests

Merkle unit tests cover:

- Single-leaf root equals the leaf hash
- Two-leaf root and proofs
- Odd leaf count with last-leaf duplication
- Deterministic roots regardless of input order
- Valid and tampered inclusion proof verification

Batch API tests cover:

- Rejecting batch creation when no events exist
- Creating and retrieving batches
- Batching only newly stored events on subsequent runs
- `POST /audit/merkle/verify` with valid and tampered proofs
- `GET /audit/batches/{batch_id}/proof/{event_id}` for included, missing, and not-in-batch cases
- Proof responses verifying successfully via `POST /audit/merkle/verify`

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
- `400 Bad Request` for invalid `agent_did` or `verification_method`
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

Shared helpers in `tests/support.py` register a test agent and attach `X-VeriAgent-API-Key` to event submission in API and batch tests.

## Manual API checks

With the server running (`uvicorn app.main:app --reload`):

1. Register an agent via `POST /agents/register` (admin key required) and save the returned `api_key`.
2. `POST /audit/events` with a sample audit event and header `X-VeriAgent-API-Key: {api_key}`; set `agent_id` to the registered `agent_did`.
3. Confirm the response includes `event_id`, `event_hash`, `created_at`, and `receipt.signature`.
4. Recompute verification locally using the same secret, or call application code that uses `verify_receipt`.

For production-like runs, set a strong secret:

```bash
export VERIAGENT_RECEIPT_SECRET="replace-with-a-long-random-secret"
export VERIAGENT_ADMIN_API_KEY="replace-with-a-long-random-admin-key"
```

## Dashboard end-to-end check

With the [public dashboard](https://dimikog.github.io/veriagent/) and API at `https://veriagent.dimikog.org`:

1. **API health check** — expect a healthy response with API version.
2. **Create audit event** — confirm `event_id` and `event_hash` appear in the workflow sidebar.
3. **Create Merkle batch** — confirm `batch_id` and `merkle_root`.
4. **Retrieve Merkle proof** — confirm verification succeeds in the status panel.
5. **Anchor batch** — requires production backend Besu anchoring env vars; confirm `tx_hash` in the sidebar.
6. **Show anchor result** — confirm stored anchor metadata matches step 5.
7. After anchoring, open **View on Blockscout** (links to `https://blockexplorer.dimikog.org/tx/{hash}`).

Local dashboard dev: [frontend/README.md](../frontend/README.md).
