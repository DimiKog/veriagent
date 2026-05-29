# Development Log

## 2026-05-28

Initialized VeriAgent MVP.

Decisions:
- VeriAgent is framed as a verifiable audit commitment layer, not as a fully independent trust infrastructure.
- Phase 1 excludes blockchain, database, Merkle batching, DID/VC, ZKP, frontend, and authentication.
- Audit events are canonicalized using RFC 8785 / JCS before hashing.
- SHA-256 is used for event commitments in MVP.
- Threat model added early to avoid overclaiming.

Implemented:
- AuditEvent schema.
- RFC 8785 canonicalization.
- SHA-256 event hashing.
- FastAPI health endpoint.
- FastAPI audit hash endpoint.
- Pytest tests for hashing and API behavior.

## 2026-05-28 (Phase 2)

Decisions:
- Local SQLite persistence only; no blockchain, auth, or observability yet.
- Store canonical JCS JSON and committed hash for later verification.
- Verification recomputes hash from submitted event and compares to stored commitment.

Implemented:
- SQLite storage layer (`storage.py`) with `event_id`, `canonical_event_json`, `event_hash`, `created_at`.
- `POST /audit/events`, `GET /audit/events/{event_id}`, `POST /audit/verify`.
- Pytest coverage for storage and verification API flows.

## 2026-05-28

Completed VeriAgent Phase 2 local storage and verification.

Implemented:
- SQLite-backed audit event storage.
- `POST /audit/events` for storing canonicalized audit events.
- `GET /audit/events/{event_id}` for retrieving stored event commitments.
- `POST /audit/verify` for recomputing and comparing event hashes.
- Duplicate event detection using `event_id`.
- Isolated test database setup using `VERIAGENT_DB_PATH`.

Tested:
- Event storage.
- Event retrieval.
- Valid event verification.
- Tampered event detection.
- Duplicate event rejection.
- Missing event handling.

Current limitation:
- Events are stored in mutable SQLite before later Merkle anchoring.
- Integrity guarantees are local and post-storage only at this stage.

## 2026-05-28 (Phase 3)

Decisions:
- Ingestion receipts prove the service accepted a specific commitment at store time.
- HMAC-SHA256 with a server secret is sufficient for MVP; no asymmetric keys yet.
- `VERIAGENT_RECEIPT_SECRET` is required for non-development deployments.
- A clearly marked development fallback secret is used only when the env var is unset.

Implemented:
- `receipts.py` with receipt generation and `verify_receipt`.
- `POST /audit/events` returns `event_id`, `event_hash`, `created_at`, and signed `receipt`.
- Pytest coverage for receipt signing, verification, and API receipt responses.

Tested:
- Deterministic receipt signatures.
- Valid and tampered receipt verification.
- Secret mismatch rejection.
- Development fallback secret behavior.

## 2026-05-28 (Phase 4)

Decisions:
- Local Merkle batching only; no blockchain anchoring yet.
- Leaves are stored event hashes; internal nodes use SHA-256 over concatenated leaf bytes.
- Odd leaf counts duplicate the last leaf before pairing.
- Leaves are sorted lexicographically so batch roots are deterministic.
- Each batch includes only events not yet assigned to a prior batch.

Implemented:
- `merkle.py` with root computation, inclusion proof generation, and verification.
- SQLite tables `audit_batches` and `batch_events`.
- `POST /audit/batches`, `GET /audit/batches/{batch_id}`, `POST /audit/merkle/verify`.
- Pytest coverage for Merkle trees and batch API flows.

Tested:
- Single-leaf, two-leaf, and odd-leaf Merkle roots.
- Proof generation and verification.
- Tampered proof rejection.
- Batch creation, retrieval, and incremental batching of new events.

## 2026-05-29

Completed Phase 4 Merkle proof retrieval API.

Implemented:
- `GET /audit/batches/{batch_id}/proof/{event_id}` for API-generated inclusion proofs.
- Pytest coverage for included, missing, and not-in-batch proof cases.

Tested:
- Proof generation for events included in a batch.
- `404 Not Found` for missing batches and events.
- `400 Bad Request` when the event is not part of the batch.

## 2026-05-29 (Phase 5A)

Decisions:
- Solidity anchor contract only; no backend `web3.py` integration, Besu deployment, frontend changes, or blockchain API endpoints yet.
- Foundry project lives under `contracts/` with Solc `0.8.20`.
- On-chain anchors are keyed by `batchId` and store `Merkle root`, `event count`, `metadata hash`, `timestamp`, and `anchoring address`.
- Owner-gated `anchorBatch`; custom errors instead of string reverts.
- Duplicate batch IDs rejected when `anchoredAt` is already set.

Implemented:
- Foundry layout: `foundry.toml`, `src/VeriAgentAnchor.sol`, `test/VeriAgentAnchor.t.sol`.
- `forge-std` dependency under `contracts/lib/forge-std`.
- `VeriAgentAnchor` with `BatchAnchor` struct, `mapping(bytes32 => BatchAnchor)`, and `anchorBatch` / `getBatch` / `isAnchored`.
- `onlyOwner`, `transferOwnership`, and `OwnershipTransferred` / `BatchAnchored` events.
- `.gitignore` entries for `contracts/out/`, `contracts/cache/`, and `contracts/broadcast/`.

Tested (Foundry, 14 tests):
- Deployer is initial owner.
- Owner can anchor; non-owner cannot.
- Rejection of zero `batchId`, Merkle root, metadata hash, and event count.
- Duplicate batch rejection.
- `getBatch` returns stored anchor fields.
- `isAnchored` false before anchor and true after.
- Ownership transfer to a new owner; old owner cannot anchor; new owner can.
- `transferOwnership` rejects zero address.

Current limitation:
- Anchors exist only in the local Foundry project; no chain deployment or backend anchoring flow yet.

## 2026-05-29 (Phase 5B)

Decisions:
- Local Anvil deployment script only; no Besu deployment, backend `web3.py` integration, or frontend changes yet.
- Deployment uses Foundry `vm.startBroadcast()` / `vm.stopBroadcast()`; signing keys come from the CLI or unlocked Anvil accounts, not from source code.

Implemented:
- `contracts/script/DeployVeriAgentAnchor.s.sol` deploys `VeriAgentAnchor` and logs the contract address and owner.
- `foundry.toml` `script` path set to `script/`.

Current limitation:
- Contract can be deployed to a local Anvil node only; no Besu deployment yet.
- No backend anchoring flow yet.

## 2026-05-29 (Phase 5C)

Decisions:
- Backend `web3.py` anchoring module only; no FastAPI endpoints, SQLite schema changes, Besu deployment, or frontend changes yet.
- Configuration from environment variables only; no hardcoded private keys.
- Backend `batch_id` strings map to on-chain `bytes32` via keccak256 of UTF-8.
- Batch metadata committed with RFC 8785 / JCS + SHA-256 before anchoring.
- Committed ABI at `backend/app/abi/VeriAgentAnchor.json` (no `contracts/out/` at runtime).

Implemented:
- `backend/app/anchoring.py` with `anchor_batch`, `get_onchain_batch`, `is_batch_anchored`, and helpers.
- `tests/test_anchoring.py`.

## 2026-05-29 (Phase 5D)

Decisions:
- Anchoring exposed via FastAPI only; no Besu deployment, VM rollout, frontend, auth, or observability yet.
- SQLite `batch_anchors` stores transaction metadata; on-chain state remains source of truth for anchor fields.
- `app.batch_anchoring` orchestrates anchoring so tests can monkeypatch `app.anchoring` without Anvil.

Implemented:
- `batch_anchors` table and `store_batch_anchor` / `get_batch_anchor`.
- `POST /audit/batches/{batch_id}/anchor` (idempotent) and `GET /audit/batches/{batch_id}/anchor`.
- `wait_for_transaction_receipt()` in `anchoring.py`.
- `tests/test_batch_anchor_api.py`.
- API version `0.5.0`.

Current limitation:
- Anchoring requires a reachable RPC and configured env vars; Besu and production VM deployment are not documented as supported yet.