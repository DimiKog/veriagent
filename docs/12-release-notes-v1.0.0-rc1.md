# VeriAgent v1.0.0-RC1 Release Notes

**Release:** v1.0.0-RC1  
**Status:** Stable research-grade release candidate  
**Backend API version:** `1.0-pre` (target stable tag: `v1.0.0`)  
**Date:** June 2026

**Related:** [10-v1-release-checklist.md](10-v1-release-checklist.md) · [08-architecture.md](08-architecture.md) · [13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md)

---

## What VeriAgent is

VeriAgent is a **verifiable audit commitment layer** for AI-agent actions. It records structured audit events from autonomous agents, binds them to registered identities, batches cryptographic commitments into Merkle trees, and anchors batch roots on a Besu blockchain. Third parties can verify inclusion proofs and on-chain anchors without trusting a single client implementation.

VeriAgent does **not** prove that an agent's claimed action occurred in the physical world. It provides a **tamper-evident commitment trail** after ingestion and anchoring.

---

## What changed since early versions

Early releases established hashing, SQLite storage, and Merkle batching. Subsequent phases added agent registry, ingestion authentication, Ed25519 event signatures, real `did:key` identities, browser demo signing, admin-protected batch/anchor operations, the Python SDK, SQLite backup/restore tooling, and finally **automatic batching and anchoring** with public ops visibility.

| Era | Highlights |
| --- | --- |
| MVP–Phase 4 | Structured events, JCS canonicalization, receipts, Merkle batches and proofs |
| Phase 5 | `VeriAgentAnchor` on Besu; backend anchoring via `web3.py` |
| v0.8–v0.9 | Agent API keys, Ed25519 signatures, real `did:key`, dashboard signing, Python SDK |
| v0.9.5–v0.9.6 | Backup/restore scripts; admin-only batch and anchor mutations |
| v1.0-pre | Background auto batch/anchor scheduler; `GET /ops/status` |

The v1.0.0-RC1 candidate consolidates these into one deployable, publicly demonstrable pipeline suitable for research evaluation, partner demos, and proposal evidence.

---

## Core capabilities

| Capability | Description |
| --- | --- |
| **Ed25519 `did:key` agent identities** | Spec-compliant multibase encoding; registration-time DID/key binding validation |
| **Agent API key authentication** | Per-agent `va_agent_...` keys; SHA-256 hash at rest; `X-VeriAgent-API-Key` on ingestion |
| **Signed audit events** | Ed25519 signature over unsigned canonical payload; verified before storage |
| **RFC 8785 / JCS canonicalization** | Deterministic JSON bytes for independent hash recomputation |
| **SHA-256 event commitments** | Stable `event_hash` over unsigned canonical event |
| **HMAC ingestion receipts** | Server-signed receipt at ingestion (`VERIAGENT_RECEIPT_SECRET`) |
| **SQLite storage** | Events, agent registry, batches, membership, anchor records |
| **Merkle batching** | Sorted leaves; odd-leaf duplication; incremental batches from unbatched events |
| **Merkle proof generation and verification** | `GET .../proof/{event_id}`; `POST /audit/merkle/verify` |
| **Besu anchoring** | `VeriAgentAnchor` contract; `anchorBatch` with batch ID, root, count, metadata hash |
| **Automatic batching and anchoring** | FastAPI lifespan scheduler; configurable interval and minimum event threshold |
| **`GET /ops/status`** | Public scheduler config and last-cycle metadata (no secrets) |
| **Browser signing dashboard** | In-browser Ed25519 + JCS for demo workflows; keys in memory only |
| **Python Agent SDK** | `sdk/python/` — identity, signing, `POST /audit/events` |
| **SQLite backup/restore** | `scripts/backup_sqlite.sh`, `scripts/restore_sqlite.sh`; operator guide |

**Public read endpoints** (no auth): event retrieval, verify, batch metadata, Merkle proof, anchor record, `POST /audit/hash`, `POST /audit/merkle/verify`, `/health`, `/ops/status`.

---

## Public deployment

| Resource | URL |
| --- | --- |
| Dashboard | https://dimikog.github.io/veriagent/ |
| API | https://veriagent.dimikog.org |
| API docs | https://veriagent.dimikog.org/docs |
| Health | https://veriagent.dimikog.org/health |
| Ops status | https://veriagent.dimikog.org/ops/status |
| Blockscout | https://blockexplorer.dimikog.org/ |

**Anchor contract:** `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A` on Besu Edu-Net (chain ID `424242`).

Production auto-anchor is enabled with a 300-second interval and `min_events=5` (at least five unbatched events before a batch is created).

---

## Security model

VeriAgent v1.0.0-RC1 is a **research prototype** with explicit trust boundaries. See [06-threat-model.md](06-threat-model.md).

| Operation | Credential |
| --- | --- |
| Agent registration | `X-VeriAgent-Admin-Key` |
| Event ingestion | `X-VeriAgent-API-Key` + Ed25519-signed body |
| Manual batch / anchor | `X-VeriAgent-Admin-Key` |
| Public reads, verify, ops status | None |

**Mitigates:** post-commitment tampering (Merkle + on-chain root); forged events without the agent's private key; unauthorized ingestion from unregistered agents; unauthorized batch/anchor without the admin key.

**Does not mitigate:** missing or false submissions; operator modification of SQLite before anchoring; stolen API keys or compromised signing keys; legal or regulatory compliance claims.

The frontend never holds admin keys, anchor private keys, or receipt secrets. Demo agent private keys live in browser memory only.

---

## Intended use cases

VeriAgent v1.0.0-RC1 is intended for scenarios where actors need a verifiable commitment trail for AI-agent activity, including:

- Auditable AI-agent workflows
- Research and academic experiments
- Multi-agent systems
- Agent governance and accountability research
- Evidence preservation for AI-assisted processes
- Educational and training environments

VeriAgent is not intended to evaluate model quality, detect hallucinations, or determine whether an agent's actions were correct. It provides verifiable evidence that specific audit records existed, were signed by registered agents, and were anchored at a particular point in time.

## Current limitations

| Limitation | Notes |
| --- | --- |
| **Single-tenant** | One operator-controlled deployment; no organization or tenant isolation |
| **SQLite local storage** | Single-node; no built-in replication or HA |
| **Admin-managed registration** | `POST /agents/register` requires admin key; no self-service onboarding |
| **No independent verifier CLI** | Verification via API, custom scripts, or Blockscout/RPC |
| **No VC-based onboarding** | W3C Verifiable Credentials not used for agent identity |
| **No PostgreSQL / SaaS layer** | No managed multi-tenant product tier |

Additional gaps: demo mode (`POST /demo/agents`) is design-only ([09-demo-mode.md](09-demo-mode.md)); Python SDK covers event submission only; automated backup scheduling (cron/systemd timer) is not yet verified in production; no automated alerting on anchor failures.

---

## Why this release matters

v1.0.0-RC1 is the first **end-to-end, publicly deployed** VeriAgent build that connects agent-signed audit events to **on-chain Merkle roots** with **operator-automated batching** and **public verification APIs**. It is suitable as:

- A **reproducible research artifact** for papers and grant proposals
- A **live demo surface** for academic reviewers and project partners
- A **baseline** for commercial pilot planning ([13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md))

The release makes clear what is cryptographically assured (commitment integrity after anchoring, agent binding at ingestion) and what is explicitly out of scope (truthfulness, compliance, decentralization).

---

## Recommended next steps before final v1.0.0

1. **Release gates** — Complete checklist in [10-v1-release-checklist.md](10-v1-release-checklist.md): full test suite, production E2E on Besu, backup rehearsal.
2. **Version alignment** — Bump `API_VERSION` to `1.0.0`; align README, deployment guide, and dashboard badge strings.
3. **Git tags** — Create and validate a dedicated `v1.0.0-RC1` tag after final release gates pass; promote to `v1.0.0` when accepted.
4. **Ops hardening** — Confirm backup cron on VM; document `min_events` and scheduler interval for demo operators.
5. **Devlog entry** — Record v1.0.0 release in [02-devlog.md](02-devlog.md).

Post-v1.0 priorities for pilot readiness: registration request workflow, independent verifier CLI, demo mode implementation — see [13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md).

---

**Document status:** Release notes for v1.0.0-RC1 · Aligned with production API verification 2026-06-18
