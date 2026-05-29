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

## Isolation

Tests use isolated resources via environment variables set in `tests/conftest.py`:

- `VERIAGENT_DB_PATH` — temporary SQLite database per test
- `VERIAGENT_RECEIPT_SECRET` — fixed secret for deterministic receipt tests

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

## Manual API checks

With the server running (`uvicorn app.main:app --reload`):

1. `POST /audit/events` with a sample audit event.
2. Confirm the response includes `event_id`, `event_hash`, `created_at`, and `receipt.signature`.
3. Recompute verification locally using the same secret, or call application code that uses `verify_receipt`.

For production-like runs, set a strong secret:

```bash
export VERIAGENT_RECEIPT_SECRET="replace-with-a-long-random-secret"
```
