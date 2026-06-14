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

## 2026-05-29 (Phase 5E)

Decisions:
- Deploy `VeriAgentAnchor` to Hyperledger Besu Edu-Net before backend VM rollout.
- Compile with `evm_version = "paris"` for Besu compatibility.
- Enable the Solidity optimizer with `optimizer_runs = 200`.
- Submit deployment transactions in legacy mode at `1 gwei` gas price.
- Verify the contract on Blockscout using the same compiler settings as deployment.

Implemented:
- Besu Edu-Net deployment completed.
- Foundry `foundry.toml` configured with `evm_version = "paris"`, `optimizer = true`, and `optimizer_runs = 200`.
- Deployment via `forge script` with `--legacy` and `--with-gas-price 1000000000`.
- Blockscout contract verification succeeded.

Deployed on Besu Edu-Net:
- Contract address: `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`
- Deployment transaction: `0x4d093ffe3d81df50a9b19f11cfd5f7fe4c914e3643895b9b92423e0074a2cc59`
- Block explorer: `https://blockexplorer.dimikog.org/`

Current limitation (at time of Phase 5E):
- Backend VM deployment had not happened yet.
- Next validation step: backend local testing against Besu Edu-Net (`VERIAGENT_*` env vars pointed at Besu RPC and the deployed contract).

## 2026-05-30

Decisions:
- Keep Blockscout transaction links in the frontend only (no explorer URL in backend env).
- Hide the explorer link in the dashboard while `BLOCKSCOUT_TX_BASE` contains a placeholder hostname.

Implemented:
- Public dashboard UI refresh (design tokens, dark mode, numbered workflow steps, hash copy buttons).
- Live block explorer base: `https://blockexplorer.dimikog.org/tx/` in `frontend/src/api/client.ts`.
- README and deployment docs updated with explorer URLs and recorded contract address.
- API and dashboard display version bumped to `0.7.0` (public demo v0.7).

## 2026-05-30 (v0.7.0 / v0.7.1 — Public deployment)

Decisions:
- Treat the GitHub Pages dashboard + VM API + Besu anchoring as the public demo surface (v0.7).
- Keep Blockscout/explorer links in the frontend; anchoring keys and receipts stay server-side only.
- Use FastAPI CORS allowlist for `https://dimikog.github.io` rather than `allow_origins=["*"]`.
- Publish the frontend via GitHub Actions to the `gh-pages` branch (not `master` root).

Implemented:
- **Backend (production VM):** FastAPI under **systemd**; **Nginx** reverse proxy to uvicorn; **HTTPS** at `https://veriagent.dimikog.org` (health, Swagger `/docs`, audit API).
- **Frontend (GitHub Pages):** Dashboard deployed at `https://dimikog.github.io/veriagent/` (Vite `base` `/veriagent/`; workflow `.github/workflows/deploy-frontend.yml`).
- **CORS:** Fixed for GitHub Pages origin so the browser dashboard can call the production API.
- **Frontend redesign:** Completed (numbered workflow, workflow sidebar, hash copy, dark mode, explorer link when `tx_hash` is set).
- **Anchor metadata parsing:** Fixed so `anchored_at` and `anchored_by` are stored correctly in `batch_anchors` after on-chain anchor.
- **API version:** `0.7.0` on `/health` and OpenAPI metadata; dashboard badge aligned.
- **Documentation:** [docs/05-deployment.md](05-deployment.md) expanded with topology, release checklist, and Pages troubleshooting.

Public endpoints (verified):

| Resource | URL |
|----------|-----|
| API | `https://veriagent.dimikog.org` |
| API docs | `https://veriagent.dimikog.org/docs` |
| Dashboard | `https://dimikog.github.io/veriagent/` |
| Block explorer | `https://blockexplorer.dimikog.org/` |
| Contract | `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A` (Besu Edu-Net) |

Public end-to-end demo verified:

```text
audit event → ingestion receipt → Merkle batch → inclusion proof
  → Besu anchor (VeriAgentAnchor) → transaction visible on Blockscout
```

Operator flow exercised via the dashboard and API: store event, batch, proof/verify, anchor batch, confirm `tx_hash` on `https://blockexplorer.dimikog.org/tx/{hash}`.

## 2026-05-31 (Phase 6A)

Decisions:
- Agent registry only; no ingestion auth, event signatures, or DID resolution yet.
- Admin onboarding protected by `VERIAGENT_ADMIN_API_KEY` via `X-VeriAgent-Admin-Key`.
- Agent API keys use prefix `va_agent_`; only SHA-256 hashes are stored.
- `GET /agents/{agent_did}` is admin-protected for now (public lookup deferred).
- `POST /audit/events` remains unauthenticated in this phase.

Implemented:
- `backend/app/auth.py` with constant-time admin key verification and agent API key helpers.
- SQLite `agents` table and storage helpers (`register_agent`, `get_agent`).
- `POST /agents/register` and `GET /agents/{agent_did}`.
- Pytest coverage in `tests/test_agents_api.py`.

Tested:
- Successful registration returns raw API key once.
- Missing, invalid, and duplicate registration cases.
- Invalid `agent_did` and `verification_method` rejection.
- GET returns metadata without `api_key_hash`; missing agent returns `404`.

Current limitation:
- Registered agent DIDs are not yet enforced on audit event ingestion.
- No event signatures or DID resolution.

Next operational priorities:
- **Agent API key auth** for `POST /audit/events`.
- **Backup strategy** for production SQLite (`VERIAGENT_DB_PATH`) and recovery procedure on the VM.

## 2026-05-31 (v0.8.1 — Agent ingestion auth)

Decisions:
- Protect `POST /audit/events` with registered agent API keys only.
- Header: `X-VeriAgent-API-Key`; lookup by SHA-256 hash of the provided key.
- Enforce `event.agent_id == authenticated agent.agent_did`.
- Reject inactive agents with `403 Forbidden`.
- Keep public read/verify endpoints open (no auth on GET events, batches, proofs, anchor records, or `POST /audit/hash` / `POST /audit/verify` / `POST /audit/merkle/verify`).
- No event signatures or DID resolution in this release.

Implemented:
- `authenticate_agent` dependency in `backend/app/auth.py`.
- `get_agent_by_api_key_hash` in `backend/app/storage.py`.
- `POST /audit/events` agent auth and `agent_id` binding.
- Shared test helpers in `tests/support.py`.
- Pytest coverage in `tests/test_audit_event_auth.py`; existing API/batch tests updated for agent keys.

Tested:
- Missing or invalid agent API key returns `401`.
- Valid active agent stores events with receipts.
- `agent_id` mismatch and inactive agent return `403`.
- Public verification/read endpoints still work without agent key.

Current limitation:
- No cryptographic event signatures tied to agent DIDs.
- No DID resolution or `public_key` verification.
- Batch creation and anchoring endpoints remain unauthenticated.

Next operational priorities:
- **Event signatures** and stronger agent identity binding.
- **Backup strategy** for production SQLite (`VERIAGENT_DB_PATH`) and recovery procedure on the VM.

## 2026-05-31 (v0.9A — Ed25519 signing primitives)

Decisions:
- Add Ed25519 key generation, base64 encoding, sign, and verify helpers only.
- Use raw 32-byte Ed25519 keys encoded as base64 (no PEM).
- Provide temporary demo DID helpers until real `did:key` multibase encoding is implemented.
- Do not enforce event signatures on `POST /audit/events` in this release.

Implemented:
- `cryptography` dependency.
- `backend/app/signatures.py` with keypair generation, base64 key codecs, `sign_bytes`, `verify_signature`, `demo_did_from_public_key`, and `demo_verification_method`.
- Pytest coverage in `tests/test_signatures.py`.

Tested:
- Key generation returns valid base64-encoded raw keys.
- Sign and verify round-trip succeeds.
- Tampered payload, wrong public key, and malformed signature are rejected cleanly.
- Demo DID is deterministic; verification method derives as `{agent_did}#keys-1`.

Current limitation:
- `demo_did_from_public_key` is explicitly temporary (`did:key:demo:<sha256>`), not spec-compliant `did:key`.
- No event signature enforcement or signed event API yet.
- Agent registry and ingestion auth unchanged from v0.8.1.

Next operational priorities:
- **Signed audit events** with verification against registered agent public keys.
- **Backup strategy** for production SQLite (`VERIAGENT_DB_PATH`) and recovery procedure on the VM.

## 2026-05-31 (v0.9B — Signed audit event verification)

Decisions:
- Require Ed25519 signatures on `POST /audit/events` before storage.
- Sign the RFC8785/JCS canonical unsigned event (exclude `signature` and `verification_method`).
- Verify `verification_method` against the registered agent record.
- Keep Merkle hashing on the unsigned canonical payload unchanged.
- Store signature metadata separately (`signature`, `verification_method`, `signature_algorithm`).
- Do not implement real `did:key` derivation, DID resolution, or frontend signing in this release.

Implemented:
- `SignedAuditEventRequest` model with required `verification_method` and `signature`.
- Signature verification in `POST /audit/events` after agent API key auth and DID binding.
- SQLite columns for event signature metadata with migration for existing databases.
- `GET /audit/events/{event_id}` returns `verification_method` and `signature_algorithm` (not raw signature or public keys).
- Pytest coverage in `tests/test_signed_audit_events.py`; shared helpers sign events in `tests/support.py`.
- Demo script `scripts/sign_demo_event.py` for manual signed POST bodies.

Tested:
- Valid signatures accepted; tampered payload, wrong signature, wrong public key, and wrong verification method rejected with `403`.
- Missing `signature` or `verification_method` rejected with `400`.
- Stored events expose signature metadata; receipts and batching unchanged.

Current limitation:
- Demo DID helpers from v0.9A remain temporary; no DID resolution.
- Frontend does not yet sign events.
- Batch creation and anchoring endpoints remain unauthenticated.

Next operational priorities:
- **Frontend / agent SDK signing** for production ingestion flows.
- **Backup strategy** for production SQLite (`VERIAGENT_DB_PATH`) and recovery procedure on the VM.

## 2026-06-06 (v0.9.0 — End-to-End Verifiable Audit Chain)

Release tag: `v0.9.0`

### Changelog

**v0.9.0 – End-to-End Verifiable Audit Chain**

- Agent Registry
- API Key Authentication
- Signed Audit Events (Ed25519)
- Signature Verification
- HMAC Receipts
- Merkle Batching
- Merkle Proof Generation
- Merkle Proof Verification
- Besu Smart Contract Anchoring
- Frontend Dashboard
- Production Deployment (`https://veriagent.dimikog.org`)

**Status:** End-to-end trust chain validated on Besu chain `424242`.

### Decisions

- Treat v0.9.0 as the first release where the full audit pipeline is wired together: registered agent identity, signed ingestion, Merkle batching, and Besu anchoring.
- Agent onboarding remains admin-protected (`VERIAGENT_ADMIN_API_KEY`); ingestion uses per-agent API keys (`X-VeriAgent-API-Key`).
- Event signatures use Ed25519 over the unsigned RFC8785/JCS canonical payload; Merkle leaves and `event_hash` remain on the unsigned payload only.
- Public read, verify, batch, proof, and anchor lookup endpoints stay open; only `POST /audit/events` and agent registration require credentials.
- Production demo surface unchanged: GitHub Pages dashboard + VM API + Besu Edu-Net `VeriAgentAnchor`.

### Implemented (cumulative through v0.9.0)

- **Agent registry** — `POST /agents/register`, `GET /agents/{agent_did}`; SHA-256 hashed API keys; admin key auth.
- **API key authentication** — `POST /audit/events` requires valid active agent key and `agent_id` binding.
- **Signed audit events** — Ed25519 primitives (`signatures.py`), required `signature` + `verification_method` on ingestion, SQLite signature metadata.
- **HMAC receipts** — ingestion receipts on successful store (`receipts.py`).
- **Merkle batching** — incremental batches, sorted leaves, odd-leaf duplication (`merkle.py`).
- **Merkle proofs** — `GET /audit/batches/{batch_id}/proof/{event_id}` and `POST /audit/merkle/verify`.
- **Besu anchoring** — `VeriAgentAnchor` on Besu Edu-Net; `POST /audit/batches/{batch_id}/anchor` via `web3.py`.
- **Frontend dashboard** — workflow UI at `https://dimikog.github.io/veriagent/` (agent credential step for ingestion).
- **Production deployment** — API at `https://veriagent.dimikog.org` (Nginx, systemd, HTTPS).

### Tested

- Full pytest suite (hashing, storage, receipts, Merkle, batches, anchoring mocks, agent registry, ingestion auth, Ed25519 primitives, signed event enforcement).
- Manual signed ingestion via `scripts/sign_demo_event.py`.
- Production end-to-end flow on Besu chain ID `424242`:

```text
register agent → signed audit event → HMAC receipt → Merkle batch
  → inclusion proof → Besu anchor (VeriAgentAnchor) → Blockscout tx
```

### Public endpoints (v0.9.0)

| Resource | URL |
|----------|-----|
| API | `https://veriagent.dimikog.org` |
| API docs | `https://veriagent.dimikog.org/docs` |
| Dashboard | `https://dimikog.github.io/veriagent/` |
| Block explorer | `https://blockexplorer.dimikog.org/` |
| Contract | `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A` (Besu Edu-Net, chain `424242`) |

### Current limitation

- Dashboard stores events with agent API key only; client-side Ed25519 signing for the dashboard workflow is not implemented yet — use the admin API + `scripts/sign_demo_event.py` (or an agent SDK) for signed ingestion.
- Batch creation and anchoring endpoints remain unauthenticated.
- No DID resolution over the network; `did:key` does not support key rotation by itself — revocation and status remain in VeriAgent's internal agent registry.

### Next operational priorities

- **Frontend / agent SDK signing** for dashboard and production agent ingestion.
- **Backup strategy** for production SQLite (`VERIAGENT_DB_PATH`) and recovery procedure on the VM.

## 2026-06-06 (v0.9.2 — Real Ed25519 did:key)

Decisions:
- Replace temporary `did:key:demo:<sha256>` identifiers with spec-compliant Ed25519 `did:key` (`did:key:z...`).
- Encode Ed25519 public keys with multicodec prefix `0xed 0x01` and base58btc multibase (`z`).
- Derive verification method as `{did}#{multibase_value}`.
- Validate `public_key` and `verification_method` against `agent_did` at registration.
- Keep deprecated demo helpers only for backward-compat unit tests; do not use in `sign_demo_event.py`.
- Do not implement DID resolution over the network or blockchain anchoring changes.

Implemented:
- `base58` dependency.
- `ed25519_public_key_to_did_key`, `did_key_to_ed25519_public_key`, `verification_method_for_did_key`, and `validate_ed25519_did_key_agent` in `backend/app/signatures.py`.
- Registration validation in `POST /agents/register`.
- `scripts/sign_demo_event.py` emits real `did:key:z...` values.
- Pytest coverage for encoding round-trip, invalid DID rejection, registration binding, and demo script output.

Tested:
- Ed25519 public key converts to `did:key` and decodes back.
- Verification method `{did}#{multibase_value}` is correct.
- Invalid prefix, multicodec, and key length rejected.
- Registration rejects mismatched `public_key` and wrong `verification_method`.
- `sign_demo_event.py` emits `did:key:z...` not `did:key:demo:...`.

Current limitation:
- `did:key:demo:...` is deprecated and rejected at registration.
- `did:key` does not support key rotation by itself; agent revocation/status is internal to VeriAgent.
- No DID resolution over the network.
- Dashboard browser signing shipped in v0.9.3; Python agent SDK shipped in v0.9.4 (`sdk/python/`).

Next operational priorities:
- **Backup strategy** for production SQLite (`VERIAGENT_DB_PATH`) and recovery procedure on the VM.

## 2026-06-09 (v0.9.3 — Frontend browser signing)

Decisions:
- Add browser-side Ed25519 signing to the dashboard for **demo purposes only**; production agents should sign outside the browser or via an SDK.
- Use `@noble/ed25519` and `bs58` in the frontend — no Node-only `crypto` APIs.
- Mirror backend `did:key` behavior: multicodec prefix `0xed 0x01`, base58btc multibase (`z`), `verification_method` = `{did}#{multibase_value}`.
- Canonicalize unsigned events with RFC 8785 / JCS (`canonicalize` npm package); backend Python `jcs` remains the source of truth.
- Sign only the unsigned canonical payload (`signature` and `verification_method` excluded).
- Store the demo private key in React state only — never `localStorage` or `sessionStorage`.
- Do not expose admin registration or `VERIAGENT_ADMIN_API_KEY` in the frontend.
- Bump backend `/health` and OpenAPI version to `0.9.3` to align with the dashboard release.

Implemented:
- **Frontend utilities** — `src/utils/didKey.ts`, `canonicalize.ts`, `signEvent.ts`, `credentials.ts`, `nobleEd25519.ts`.
- **Agent credentials (step 2)** — Agent DID, Agent API Key, and Agent Private Key (base64, `type="password"`); **Use agent credentials** derives the public key, verifies DID match, and computes `verification_method` before marking **Ready**.
- **Signed audit event (step 3)** — build unsigned payload → JCS canonicalize → Ed25519 sign → submit `POST /audit/events` with `X-VeriAgent-API-Key`, `verification_method`, and base64 `signature`.
- **Error handling** — clear messages for invalid private key, DID mismatch, and backend `403 Invalid event signature`.
- **UI copy** — step 3 renamed to **Create signed audit event**; step 6 clarifies blockchain keys stay server-side.
- **Dependencies** — `@noble/ed25519`, `@noble/hashes`, `bs58`, `canonicalize`.
- **Backend** — `API_VERSION = "0.9.3"` in `backend/app/main.py` for `/health` and FastAPI metadata.
- **Docs** — `frontend/README.md` updated with signed-event demo flow.

Tested:
- `npm run build` and `npm run lint` pass.
- Frontend JCS output cross-checked against backend canonical form for a sample event (byte-identical).
- Credential validation rejects invalid base64, wrong key length, and DID/private-key mismatch.

Current limitation:
- Browser signing is demo-mode only; users must not paste production private keys into the dashboard.
- Batch creation and anchoring endpoints remain unauthenticated.

Deployed:
- Production VM updated; `https://veriagent.dimikog.org/health` returns `version: "0.9.3"`.

Next operational priorities:
- **Backup strategy** for production SQLite (`VERIAGENT_DB_PATH`) and recovery procedure on the VM.

## 2026-06-09 (v0.9.4 — Python Agent SDK)

Decisions:
- Ship a **minimal Python SDK** for external agents to submit signed audit events without hand-rolling canonicalization, signing, or HTTP headers.
- Keep the SDK small: identity derivation, JCS canonicalization, Ed25519 signing, and `POST /audit/events` only — **no admin registration wrapper** yet.
- Reuse the same libraries and rules as the backend: Python `jcs`, Ed25519 `did:key` multicodec encoding, unsigned canonical signing boundary.
- Package lives at `sdk/python/veriagent/` with its own `pyproject.toml` and tests; backend and frontend behavior unchanged.

Implemented:
- **`veriagent.identity`** — load Ed25519 private key from base64; derive public key, real `did:key:z...`, and `verification_method`.
- **`veriagent.signing`** — build unsigned event dict, RFC 8785 / JCS canonicalize, sign canonical bytes.
- **`veriagent.client.VeriAgentClient`** — `api_base_url`, `agent_api_key`, `private_key_base64`; auto-derived `agent_did` and `verification_method`; `submit_event(...)` POSTs with `X-VeriAgent-API-Key` and returns backend JSON.
- **`sdk/python/README.md`** — demo key creation, manual agent registration, Python submit example.
- **Tests** — DID derivation, signing, canonicalization stability (backend vector), signed payload construction, mocked HTTP header check (`sdk/python/tests/test_sdk.py`).

Tested:
- `cd sdk/python && pip install -e ".[dev]" && python -m pytest -v` — 10 tests pass.
- SDK signatures cross-checked against `backend/tests/support.py` for the same unsigned event payload (byte-identical signatures).

Current limitation:
- Admin `POST /agents/register` is not wrapped by the SDK; agents must register manually (curl, dashboard operator flow, or direct API).
- SDK version is `0.9.4`; backend `/health` remains `0.9.3` until a separate API release bump.

Next operational priorities:
- Optional SDK extensions: agent registration helper, async client, TypeScript SDK.

## 2026-06-14 (SQLite backup and restore)

Decisions:
- Add **operator-safe VM tooling** before v1.0: hot backup with `sqlite3 ".backup"` (not raw `cp` while the service runs), gzip artifacts, 14-backup retention on disk.
- Restore is **explicit and destructive**: require a backup file path, stop `veriagent`, copy current DB to an emergency file, then restore and restart.
- Resolve `VERIAGENT_DB_PATH` from `backend/.env` when present; default production path `/opt/veriagent/backend/data/veriagent.db`.
- No backend API or frontend changes for this milestone.

Implemented:
- **`scripts/backup_sqlite.sh`** — timestamped gzip backups under `/opt/veriagent/backups/sqlite/`.
- **`scripts/restore_sqlite.sh`** — systemd stop/start, emergency copy, restore from `.db.gz`.
- **`docs/07-backup-restore.md`** — manual backup, cron example, restore and rollback steps.

Tested:
- Script review against production VM paths and env resolution; operator verification steps documented for live VM use.

Next operational priorities:
- Schedule cron on the production VM and rehearse restore on a staging copy.
- Optional SDK extensions: agent registration helper, async client, TypeScript SDK.

## 2026-06-14 (v0.9.6 — Admin-protected batch and anchor)

Decisions:
- Restrict **operator mutations** on Merkle batching and on-chain anchoring to holders of `VERIAGENT_ADMIN_API_KEY` (`X-VeriAgent-Admin-Key`), matching agent registration auth.
- Leave **read-only** batch endpoints public: `GET /audit/batches/{batch_id}`, proof, and anchor record routes unchanged.
- Bump backend `API_VERSION` to `0.9.6`; no frontend or Python SDK changes in this release.

Implemented:
- **`require_admin_api_key`** dependency on `POST /audit/batches` and `POST /audit/batches/{batch_id}/anchor` in `backend/app/main.py`.
- **`tests/test_batch_admin_auth.py`** — missing/invalid/valid admin key cases for batch create and anchor.
- **`tests/support.py`** — `post_audit_batch()` and `post_batch_anchor()` helpers for existing batch tests.
- **Docs** — API auth requirements, threat model, testing guide, README security note.

Tested:
- `cd backend && python -m pytest` — full suite including six new admin auth tests.

Current limitation:
- Public dashboard still calls batch create/anchor without admin key; operator must use curl or automation with `X-VeriAgent-Admin-Key` until a frontend update.

Next operational priorities:
- Update dashboard batch/anchor steps to accept admin key (or move those steps to operator-only tooling).
- Deploy v0.9.6 to production VM and verify `/health` reports `0.9.6`.