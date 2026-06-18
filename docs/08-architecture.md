# VeriAgent Architecture (v1.0-RC1)

VeriAgent is a **verifiable audit commitment layer for AI-agent actions**. It records structured audit events, binds them to registered agent identities, batches cryptographic commitments into Merkle trees, and anchors batch roots on a Besu blockchain. Third parties can verify inclusion proofs and on-chain anchors without trusting a single client implementation.

This document describes the system at **v1.0-RC1** (backend API `1.0-pre`). It is written for researchers, operators, and integrators evaluating the prototype.

---

## 1. Overview

An AI agent (or its middleware) produces an audit event describing an action: model, tool calls, input/output hashes, policy version, and metadata. The agent signs the event with Ed25519 and submits it to the VeriAgent API. The backend authenticates the agent, verifies the signature, stores the canonical event in SQLite, and returns an HMAC ingestion receipt.

Periodically—manually by an operator or automatically via a background scheduler—the backend groups unbatched events into a Merkle batch and submits the batch root to the `VeriAgentAnchor` smart contract on Besu. Observers can:

- Recompute event hashes and verify Merkle inclusion proofs.
- Confirm that a batch root was anchored on chain (via Blockscout or direct RPC reads).

VeriAgent does **not** prove that an agent's claimed action occurred in the physical world. It provides a **tamper-evident commitment trail** after ingestion and anchoring.

```text
Agent / SDK / Dashboard
        ↓ signed event
VeriAgent API
        ↓ verify + receipt
SQLite
        ↓ Merkle batch
Besu Anchor Contract
        ↓ tx/hash
Blockscout / Verifier
```

---

## 2. Design goals

- **Structured audit events** — A stable JSON schema for agent actions, suitable for hashing and batching.
- **Canonical commitments** — RFC 8785 / JCS canonicalization and SHA-256 hashes so independent parties reproduce the same commitment.
- **Agent binding** — Ed25519 `did:key` identities, per-agent API keys, and signature verification before storage.
- **Batch efficiency** — Merkle trees over event hashes; one on-chain transaction commits many events.
- **Public verifiability** — Open read endpoints for events, batches, proofs, and anchor records; block explorer links for transactions.
- **Operator control** — Admin-protected registration, batching, and anchoring; optional automatic scheduler for routine processing.
- **Operational visibility** — Public `GET /ops/status` for scheduler state without exposing secrets.
- **Research-friendly scope** — Clear trust boundaries; no overclaiming of legal or regulatory compliance.

---

## 3. Non-goals

VeriAgent v1.0-RC1 is **not**:

- A production EU AI Act compliance product.
- A decentralized trust network or public DID registry.
- Proof that submitted event *content* is truthful—only that a registered agent signed and the backend committed it.
- Protection against a malicious or compromised backend operator before anchoring.
- A complete agent identity platform (no VC-based onboarding, no network DID resolution).
- An off-chain blob store for raw inputs/outputs (only hashes are referenced in events).
- A standalone verifier CLI or TypeScript SDK (Python SDK covers event submission only).

---

## 4. System components

### Agent / Client

Any process that constructs audit events and calls the API: custom middleware, automation scripts, or `scripts/sign_demo_event.py`. Clients must hold the agent's Ed25519 private key (for signing) and `va_agent_...` API key (for authentication).

### Python SDK

Minimal library at `sdk/python/`. Handles `did:key` derivation, RFC 8785 / JCS canonicalization, Ed25519 signing, and `POST /audit/events` with `X-VeriAgent-API-Key`. Does not include admin registration or batch/anchor operations.

### Browser dashboard

Static React app on GitHub Pages (`https://dimikog.github.io/veriagent/`). Demonstrates the full workflow including **in-browser Ed25519 signing** for demo events. The demo private key lives in memory only. The dashboard no longer exposes batch creation or anchoring operations. Public users can submit signed audit events and inspect existing batch, proof, and anchor evidence. Batch creation and anchoring are performed either by operators through admin-protected API routes or automatically by the backend scheduler when auto-anchoring is enabled.

### FastAPI backend

Python 3.12+ service (`backend/app/main.py`). Exposes audit, batch, anchor, agent registry, health, and ops endpoints. Runs an optional **auto batch/anchor scheduler** inside the FastAPI lifespan when `VERIAGENT_AUTO_ANCHOR_ENABLED=true`.

### SQLite storage

Single-file database (default `backend/data/veriagent.db`, overridable via `VERIAGENT_DB_PATH`). Tables include audit events, agent registry, Merkle batches, batch membership, and anchor records. Hot backup via `scripts/backup_sqlite.sh` (see [07-backup-restore.md](07-backup-restore.md)).

### Agent registry

Admin-protected `POST /agents/register`. Stores agent DID, metadata, Ed25519 public key, verification method, and SHA-256 hash of the issued API key (never the raw key at rest). `POST /audit/events` requires a valid key and matching `agent_id`.

### Merkle batching

Unbatched events are collected in stable order; leaf hashes are sorted lexicographically; a SHA-256 Merkle root is computed (odd leaf count duplicates the last leaf). Batch metadata and membership are stored in SQLite. Inclusion proofs are served via `GET /audit/batches/{batch_id}/proof/{event_id}`.

### Besu anchor contract

`VeriAgentAnchor` (Solidity) on Besu Edu-Net (chain ID `424242`). Production deployment: `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`. The backend calls `anchorBatch` with batch ID, Merkle root, event count, and a metadata hash; anchor metadata is persisted in SQLite.

### Blockscout / verifier

[Blockscout](https://blockexplorer.dimikog.org/) indexes Besu transactions for human review. Independent verification today combines:

- Public API reads (`GET /audit/events/{id}`, batch, proof, anchor record).
- `POST /audit/verify` and `POST /audit/merkle/verify`.
- On-chain `getBatch` reads (via RPC or explorer).

There is no bundled verifier CLI yet.

---

## 5. Agent lifecycle

1. **Key generation** — Operator or agent generates a 32-byte Ed25519 seed; public key derived from the seed.
2. **`did:key` derivation** — Public key encoded as multibase; agent DID is `did:key:z...` (Ed25519 method).
3. **Registration** — Admin calls `POST /agents/register` with `X-VeriAgent-Admin-Key`, supplying DID, name, type, `public_key`, and `verification_method` (`{did}#{multibase}`). Backend validates key/DID binding.
4. **API key issuance** — Backend generates `va_agent_...`, stores SHA-256 hash only, returns raw key **once** in the registration response.
5. **Event signing** — Agent canonicalizes the unsigned event (JCS), signs with Ed25519, attaches `signature` and `verification_method`, and submits with `X-VeriAgent-API-Key`.

Revocation and status are managed in VeriAgent's internal registry; `did:key` does not support key rotation by itself.

---

## 6. Event lifecycle

| Stage | Description |
| --- | --- |
| **Event creation** | Client builds JSON with `event_id`, `agent_id`, `task_id`, `model_name`, `tool_calls`, hashes, `policy_version`, `timestamp`, `metadata`. |
| **Canonicalization** | RFC 8785 / JCS over the unsigned payload (excludes `signature`, `verification_method`). |
| **Ed25519 signing** | Signature over canonical bytes using the agent's private key. |
| **API authentication** | `X-VeriAgent-API-Key` header; backend hashes key and looks up active agent. |
| **Signature verification** | Backend verifies signature against registered `public_key`; checks `agent_id` and `verification_method` match. |
| **Receipt generation** | HMAC-SHA256 receipt over `event_id`, `event_hash`, `created_at` using `VERIAGENT_RECEIPT_SECRET`. |
| **Storage** | Unsigned canonical JSON, hash, signature metadata written to SQLite. |
| **Batching** | Admin or auto scheduler calls `create_batch_from_unbatched()`; Merkle root stored with batch membership. |
| **Anchoring** | `perform_batch_anchor()` submits on-chain transaction; SQLite `batch_anchors` row records `tx_hash`, block, timestamps. |
| **Proof verification** | Client fetches Merkle proof; `POST /audit/merkle/verify` or local recomputation confirms inclusion under the anchored root. |

The Merkle leaf is the **unsigned** event hash. The Ed25519 signature is stored separately and verified at ingestion time.

---

## 7. Trust model

**Trusted during operation:**

- The **backend operator** controls SQLite, receipt signing, batch creation, and anchor submission.
- **Besu Edu-Net** in the public demo is prototype infrastructure; governance and finality assumptions are operator-defined.

**Cryptographic assurances (after anchoring):**

- A committed event hash cannot be altered without breaking Merkle proofs and disagreeing with the on-chain root.
- A registered agent's signature at ingestion time binds the event payload to that agent's key (assuming the private key was not compromised).

**Not assured:**

- Truthfulness of `input_hash`, `output_hash`, or metadata.
- Immutability of SQLite **before** anchoring.
- Secrecy of leaked agent API keys or Ed25519 private keys.

See [06-threat-model.md](06-threat-model.md) for detail.

---

## 8. Threat model summary

**Mitigates:**

- Post-commitment tampering (Merkle + on-chain root).
- Forged events without the agent's private key (Ed25519 verification before storage).
- Unauthorized ingestion from unregistered agents (API key + DID binding).
- Unauthorized batch/anchor mutations (admin API key on `POST /audit/batches` and `POST .../anchor`).

**Does not mitigate:**

- Missing or false agent submissions.
- Operator modification of SQLite before anchoring.
- Stolen API keys or compromised signing keys.
- Regulatory compliance or legal admissibility claims.

---

## 9. Operator model

### Admin key

`VERIAGENT_ADMIN_API_KEY` / header `X-VeriAgent-Admin-Key`. Required for agent registration, manual batch creation, and manual anchoring. Never exposed via public endpoints or the dashboard.

### Automatic batching/anchoring

When `VERIAGENT_AUTO_ANCHOR_ENABLED=true`, a background scheduler runs inside the API process:

- Every `VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS` (default 300), counts unbatched events.
- If count ≥ `VERIAGENT_AUTO_ANCHOR_MIN_EVENTS` (default 1), creates a batch and anchors it.
- On anchor failure, the batch remains in SQLite; the next cycle continues.
- Requires the same Besu anchoring env vars as manual anchoring.

### Backup/restore

Operator scripts `scripts/backup_sqlite.sh` and `scripts/restore_sqlite.sh` use SQLite `.backup` for consistent snapshots. Documented in [07-backup-restore.md](07-backup-restore.md).

### Ops status

Public `GET /ops/status` returns scheduler configuration and last cycle metadata (`last_status`, `last_batch_id`, `last_anchor_tx`, `last_error`). No secrets, RPC URL, or private keys.

---

## 10. Current limitations

- **SQLite is local** — Single-node storage; no built-in replication or multi-region HA.
- **Registry is centralized** — Agent records live in operator-controlled SQLite, not on a public DID network.
- **Admin registration is manual** — No self-service or VC-based onboarding flow.
- **No VC-based onboarding yet** — W3C Verifiable Credentials are not used for agent identity.
- **No independent verifier CLI yet** — Verification requires API calls, custom scripts, or manual Blockscout/RPC checks.
- **No off-chain object storage yet** — Events reference content via hashes only; raw inputs/outputs are not stored by VeriAgent.
- **Dashboard lag** — UI does not reflect auto-anchoring or admin-protected batch steps without operator tooling.
- **Python SDK scope** — Event submission only; no admin helpers, async client, or TypeScript SDK.

---

## 11. Roadmap to v1.0 and beyond

**Toward v1.0 (RC → stable):**

- Deploy v1.0-RC1 to production; validate `/health`, `/ops/status`, and end-to-end auto-anchoring on Besu Edu-Net.
- Rehearse SQLite backup/restore on a staging copy.
- Optional dashboard update for admin key or auto-anchor status display.
- Documented operator runbooks and monitoring alerts on `last_status` / `last_error`.

**Beyond v1.0 (research directions):**

- Independent verifier CLI (local proof + anchor validation without trusting the API for reads).
- TypeScript SDK and SDK admin registration helper.
- VC-based or federated agent onboarding.
- Off-chain object storage with hash-linked references in events.
- Shorter anchoring intervals, public-chain anchoring, or external witnesses.
- Middleware-based capture outside the agent process.
- Threat-model hardening for stolen keys (rotation, revocation workflows, HSM integration).

For phase-by-phase implementation history, see [02-devlog.md](02-devlog.md). For API and deployment details, see [03-api.md](03-api.md) and [05-deployment.md](05-deployment.md).
