# VeriAgent v1.0-RC1 Release Checklist

**Release candidate:** v1.0-RC1  
**Backend API version:** `1.0-pre` (target stable tag: `v1.0.0`)  
**Repository state:** `master` clean and aligned with `origin/master` (verified 2026-06-18)

This document is the operator and release gate for promoting VeriAgent from `1.0-pre` to a stable **v1.0.0** tag. It consolidates capabilities, deployment status, security boundaries, environment requirements, and demo/paper readiness in one place.

**Related docs:** [08-architecture.md](08-architecture.md) · [05-deployment.md](05-deployment.md) · [06-threat-model.md](06-threat-model.md) · [07-backup-restore.md](07-backup-restore.md) · [09-demo-mode.md](09-demo-mode.md)

---

## 1. Current completed capabilities

VeriAgent v1.0-RC1 delivers an end-to-end **verifiable audit commitment pipeline** for AI-agent actions. The following are implemented and covered by automated tests.

| Area | Capability | Since |
| --- | --- | --- |
| **Audit events** | Structured JSON schema; RFC 8785 / JCS canonicalization; SHA-256 commitments | MVP |
| **Storage** | SQLite persistence; duplicate `event_id` rejection | Phase 2 |
| **Receipts** | HMAC-SHA256 ingestion receipts (`VERIAGENT_RECEIPT_SECRET`) | Phase 3 |
| **Merkle batching** | Incremental batches; sorted leaves; odd-leaf duplication; inclusion proofs | Phase 4 |
| **On-chain anchoring** | `VeriAgentAnchor` on Besu Edu-Net; `web3.py` integration; SQLite anchor records | Phase 5 |
| **Agent registry** | Admin-protected `POST /agents/register`; per-agent API keys (SHA-256 hash at rest) | Phase 6A |
| **Ingestion auth** | `X-VeriAgent-API-Key`; `agent_id` binding; inactive agent rejection | v0.8.1 |
| **Event signatures** | Ed25519 over unsigned canonical payload; signature verified before storage | v0.9B |
| **Real `did:key`** | Ed25519 multibase encoding; registration-time DID/key binding validation | v0.9.2 |
| **Dashboard signing** | Browser-side Ed25519 + JCS for demo event submission (key in memory only) | v0.9.3 |
| **Python SDK** | `sdk/python/` — identity, signing, `POST /audit/events` (no admin wrapper) | v0.9.4 |
| **Admin-protected ops** | `POST /audit/batches` and `POST .../anchor` require `X-VeriAgent-Admin-Key` | v0.9.6 |
| **SQLite backup/restore** | `scripts/backup_sqlite.sh`, `scripts/restore_sqlite.sh`; operator guide | v0.9.5 |
| **Auto batch/anchor** | Background scheduler in FastAPI lifespan; configurable interval and threshold | v1.0-pre |
| **Ops visibility** | Public `GET /ops/status` — scheduler config and last cycle metadata (no secrets) | v1.0-pre |

**Public read endpoints** (no auth): event retrieval, verify, batch metadata, Merkle proof, anchor record, `POST /audit/hash`, `POST /audit/merkle/verify`, `/health`, `/ops/status`.

**Public demo surface:**

| Component | URL |
| --- | --- |
| Dashboard | https://dimikog.github.io/veriagent/ |
| API | https://veriagent.dimikog.org |
| API docs | https://veriagent.dimikog.org/docs |
| Block explorer | https://blockexplorer.dimikog.org/ |
| Anchor contract | `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A` (Besu Edu-Net, chain `424242`) |

---

## 2. Production deployment status

| Item | Status | Notes |
| --- | --- | --- |
| **Backend VM** | Deployed | FastAPI + Nginx + systemd at `https://veriagent.dimikog.org` |
| **API version** | `1.0-pre` | `/health` returns `"version": "1.0-pre"` |
| **Frontend (Pages)** | Deployed | https://dimikog.github.io/veriagent/ via `gh-pages` workflow |
| **Dashboard UI badge** | `v0.9.6` | Static badge in frontend; does not reflect backend `1.0-pre` — cosmetic only |
| **Besu contract** | Deployed + verified | Blockscout verification complete |
| **CORS** | Configured | Allowlist includes `https://dimikog.github.io` |
| **Auto-anchor on VM** | **Enabled** | `auto_anchor_enabled: true`, `scheduler_running: true` (checked 2026-06-18) |
| **Demo mode (`POST /demo/agents`)** | Not implemented | Design only — [09-demo-mode.md](09-demo-mode.md) |
| **IaC / VM automation** | Not in scope | Manual pull + systemd restart |
| **Git tags (pre-RC)** | Present | `v1.0.0-pre-auto-anchoring`, `v1.0.0-pre-ops-status`; **no `v1.0-RC1` tag yet** |

**Live ops snapshot (2026-06-18):**

```json
{
  "version": "1.0-pre",
  "auto_anchor_enabled": true,
  "interval_seconds": 300,
  "min_events": 5,
  "scheduler_running": true,
  "last_status": "no_events"
}
```

Production uses `VERIAGENT_AUTO_ANCHOR_MIN_EVENTS=5` (not the code default of `1`). Adjust expectations for demo timing: at least five unbatched events are required before the scheduler creates a batch.

---

## 3. Security model

VeriAgent v1.0-RC1 is a **research prototype** with explicit trust boundaries. See [06-threat-model.md](06-threat-model.md) for full detail.

### Authentication layers

| Operation | Credential | Header |
| --- | --- | --- |
| Agent registration | Admin API key | `X-VeriAgent-Admin-Key` |
| Event ingestion | Per-agent API key + Ed25519 signature | `X-VeriAgent-API-Key` + signed body |
| Manual batch / anchor | Admin API key | `X-VeriAgent-Admin-Key` |
| Public reads, verify, ops status | None | — |

### What the system mitigates

- Post-commitment tampering (Merkle proofs + on-chain root after anchoring).
- Forged events without the agent's Ed25519 private key.
- Unauthorized ingestion from unregistered or inactive agents.
- Unauthorized batch creation or on-chain anchoring without the admin key.

### What the system does **not** mitigate

- Missing or false agent submissions; untruthful event content.
- Backend modification of SQLite **before** anchoring (operator is trusted).
- Stolen agent API keys or compromised Ed25519 private keys.
- Legal/regulatory compliance or EU AI Act claims.
- Network DID resolution or key rotation via `did:key` alone.

### Client-side secret handling

- **Frontend never holds:** admin key, anchor private key, receipt secret, RPC credentials.
- **Frontend may hold (demo only):** agent private key and API key in React state for the session — not persisted to `localStorage` / `sessionStorage`.
- **Backend stores:** SHA-256 hash of agent API keys only; raw keys returned once at registration.
- **`GET /ops/status`:** no secrets, RPC URL, or private keys in the response.

---

## 4. Required environment variables

### API host — required for production

| Variable | Purpose |
| --- | --- |
| `VERIAGENT_RECEIPT_SECRET` | HMAC secret for ingestion receipts — **never commit** |
| `VERIAGENT_ADMIN_API_KEY` | Admin key for registration, batch, anchor — **never commit** |
| `VERIAGENT_RPC_URL` | JSON-RPC for anchoring (Besu: `https://rpc.dimikog.org/rpc/`) |
| `VERIAGENT_CHAIN_ID` | Chain ID (`424242` for Besu Edu-Net) |
| `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` | `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A` |
| `VERIAGENT_ANCHOR_PRIVATE_KEY` | Owner key for `anchorBatch` — **never commit** |

### API host — optional

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERIAGENT_DB_PATH` | `backend/data/veriagent.db` | SQLite file path (VM: `/opt/veriagent/backend/data/veriagent.db`) |

### Auto batch/anchor (v1.0-pre)

| Variable | Default | Production (observed) |
| --- | --- | --- |
| `VERIAGENT_AUTO_ANCHOR_ENABLED` | `false` | `true` |
| `VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS` | `300` | `300` |
| `VERIAGENT_AUTO_ANCHOR_MIN_EVENTS` | `1` | `5` |

When auto-anchor is enabled, the same Besu anchoring variables as manual anchoring are required.

### Demo mode (not implemented — do not set on production)

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERIAGENT_DEMO_MODE_ENABLED` | — | Proposed master switch — **not in codebase yet** |
| `VERIAGENT_DEMO_AGENT_TTL_HOURS` | — | Proposed — see [09-demo-mode.md](09-demo-mode.md) |

### Contract deploy machine (not on API VM)

| Variable | Purpose |
| --- | --- |
| `BESU_RPC_URL` | Besu JSON-RPC for Foundry deploy |
| `BESU_PRIVATE_KEY` | Deployer key — **never commit** |

### Local / test only

| Variable | Purpose |
| --- | --- |
| `VERIAGENT_DEMO_PRIVATE_KEY` | In `scripts/demo_agent.env` (gitignored) for `sign_demo_event.py` and SDK examples |

Store all production secrets in a gitignored `.env` on the VM or a secrets manager. Never commit `.env`, keys, or `backend/data/veriagent.db`.

---

## 5. Backup status

| Item | Status |
| --- | --- |
| **Backup script** | Implemented — `scripts/backup_sqlite.sh` |
| **Restore script** | Implemented — `scripts/restore_sqlite.sh` |
| **Operator guide** | [07-backup-restore.md](07-backup-restore.md) |
| **Method** | SQLite online `.backup` (not raw `cp`); gzip; 14-backup retention |
| **Default backup dir** | `/opt/veriagent/backups/sqlite/` |
| **Scheduled cron on VM** | **Not verified in this RC** — documented example only; operator must confirm |

### Pre-v1.0 backup gate

- [ ] `chmod +x` backup and restore scripts on the VM
- [ ] `/opt/veriagent/backups/sqlite/` exists with restricted permissions (e.g. `700`)
- [ ] Manual backup succeeds: `sudo /opt/veriagent/scripts/backup_sqlite.sh`
- [ ] Cron installed (recommended: daily at 03:15 UTC) and log monitored
- [ ] Restore rehearsed on a **non-production copy** at least once
- [ ] Off-site copy policy defined (VM retention alone does not protect against disk loss)

---

## 6. Auto-anchor status

| Item | Status |
| --- | --- |
| **Feature** | Implemented in `backend/app/auto_anchor_scheduler.py` |
| **Production** | Enabled (`VERIAGENT_AUTO_ANCHOR_ENABLED=true`) |
| **Scheduler** | Running inside API process (FastAPI lifespan) |
| **Interval** | 300 seconds |
| **Threshold** | 5 unbatched events (production config) |
| **Monitoring** | `GET /ops/status` — public, no auth |
| **Failure handling** | Batch retained in SQLite on anchor failure; next cycle continues |
| **Manual admin routes** | Still available when auto mode is on |

### Ops fields to watch

| Field | Meaning |
| --- | --- |
| `scheduler_running` | Background task active |
| `last_status` | `idle`, `no_events`, `below_threshold`, `batch_created`, `anchor_succeeded`, `anchor_failed` |
| `last_batch_id` | Most recent batch from scheduler |
| `last_anchor_tx` | Most recent successful anchor tx hash |
| `last_error` | Last anchor failure message (if any) |

```bash
curl -s https://veriagent.dimikog.org/ops/status | jq .
```

### Pre-v1.0 auto-anchor gate

- [ ] Submit ≥ `min_events` signed events; within one interval, `last_status` becomes `anchor_succeeded`
- [ ] `last_anchor_tx` appears and matches a tx on Blockscout
- [ ] Induce anchor failure (e.g. wrong RPC in staging); confirm batch remains and `last_error` is set
- [ ] Confirm API starts even if scheduler startup logs a non-fatal error

---

## 7. Known limitations

### Architecture and scope

- **SQLite is single-node** — no replication or multi-region HA.
- **Centralized registry** — agent records in operator SQLite, not a public DID network.
- **No VC-based onboarding** — admin registration only; demo mode is design-only ([09-demo-mode.md](09-demo-mode.md)).
- **No independent verifier CLI** — verification via API, custom scripts, or Blockscout/RPC.
- **No off-chain blob store** — events reference content by hash only.
- **Research prototype** — not an EU AI Act compliance product.

### Product / UX gaps

- **Agent onboarding friction** — demo users need operator-prepared credentials or admin `POST /agents/register`; no one-click demo agent.
- **Dashboard vs backend version mismatch** — UI badge `v0.9.6`; API `1.0-pre`; health step shows live API version.
- **Dashboard batch/anchor UX** — public UI does **not** create batches or submit anchors (admin-protected since v0.9.6). Users inspect evidence via read-only lookup (batch ID, proof, anchor record). Auto-anchor is server-side only; dashboard does not poll `/ops/status` yet.
- **Python SDK scope** — event submission only; no admin registration, async client, or TypeScript SDK.

### Operational gaps

- **Backup cron** — scripts exist; production schedule not confirmed in this RC.
- **Deployment docs** — [05-deployment.md](05-deployment.md) still references dashboard v0.9.3 in places; reconcile before v1.0.0.
- **Monitoring/alerts** — no automated alerting on `last_status=anchor_failed`; operator must poll `/ops/status` or logs.

---

## 8. Final checks before tagging v1.0.0

Complete these gates before creating git tag **`v1.0.0`** (and optionally **`v1.0-RC1`** immediately before final validation).

### Code and tests

- [ ] `master` clean; all intended changes merged
- [ ] `cd backend && python -m pytest` — full suite green
- [ ] `cd frontend && npm run build && npm run lint` — pass
- [ ] `cd sdk/python && python -m pytest -v` — pass
- [ ] Bump `API_VERSION` in `backend/app/main.py` from `1.0-pre` to `1.0.0` (or keep `1.0.0` for stable tag only)
- [ ] Align README, deployment guide, and dashboard badge with stable version strings

### Production VM

- [ ] Pull latest `master` on VM; reinstall deps if `requirements.txt` changed
- [ ] All required env vars set (§4); secrets not in git
- [ ] Restart `veriagent` systemd unit
- [ ] `curl -s https://veriagent.dimikog.org/health | jq .` → `"version": "1.0.0"` (after bump)
- [ ] CORS preflight returns `200` for `Origin: https://dimikog.github.io`

### End-to-end chain (Besu `424242`)

- [ ] Register agent (admin) or use existing demo agent
- [ ] Submit signed event (dashboard, SDK, or `scripts/sign_demo_event.py`)
- [ ] Confirm HMAC receipt and stored `event_hash`
- [ ] Wait for auto-anchor (or manual admin batch + anchor in staging)
- [ ] Fetch Merkle proof; `POST /audit/merkle/verify` → `verified: true`
- [ ] Confirm `tx_hash` on https://blockexplorer.dimikog.org/tx/{hash}

### Backup and ops

- [ ] Backup cron active; latest `.db.gz` readable
- [ ] `/ops/status` reflects production config after restart
- [ ] Document production `min_events` and interval for demo operators

### Release artifacts

- [ ] Tag `v1.0-RC1` (optional RC marker) then `v1.0.0` after gates pass
- [ ] GitHub Pages workflow succeeded; `gh-pages` has fresh assets
- [ ] Update [02-devlog.md](02-devlog.md) with v1.0.0 release entry

---

## 9. Demo checklist

Use this for live demos, stakeholder walkthroughs, and pre-presentation rehearsal.

### Before the demo

- [ ] API healthy: https://veriagent.dimikog.org/health
- [ ] Ops status sane: https://veriagent.dimikog.org/ops/status (`scheduler_running`, no stale `last_error`)
- [ ] Dashboard loads: https://dimikog.github.io/veriagent/ (hard refresh or private window)
- [ ] **Agent credentials prepared** — operator registers agent via admin API **before** the session:
  - Agent DID (`did:key:z...`)
  - `va_agent_...` API key (shown once at registration)
  - Base64 Ed25519 private key matching the DID (demo key only — not production secrets)
- [ ] Know current `min_events` (production: **5**) — plan to submit enough events for auto-anchor within ~5 minutes, or pre-seed unbatched events
- [ ] Blockscout and contract links ready for the “on-chain proof” moment

### During the demo (dashboard flow)

| Step | Action | Expected result |
| --- | --- | --- |
| 1 | **Check health** | `veriagent` healthy; API version displayed |
| 2 | **Agent credentials** | Paste DID, API key, private key → **Use agent credentials** → **Ready** |
| 3 | **Create signed audit event** | Unique `event_id`; submit → `event_id`, `event_hash`, receipt in sidebar |
| 3× | **Repeat if needed** | Submit until unbatched count ≥ `min_events` for auto-anchor |
| 4 | **Wait / poll ops** | `curl /ops/status` or explain scheduler interval (~5 min) |
| 5 | **Evidence lookup** | Enter `batch_id` from ops or operator → **Lookup batch** |
| 6 | **Merkle proof** | Enter `batch_id` + `event_id` → proof retrieved; verify success |
| 7 | **Anchor record** | **Get anchor record** → `tx_hash` in sidebar |
| 8 | **Blockscout** | **View on Blockscout** → tx visible on Besu Edu-Net |

### Demo talking points

- Events are **signed** by the agent and **verified** before storage.
- Only **hashes and Merkle roots** go on-chain — not raw prompts or outputs.
- **Admin keys and anchor keys never enter the browser.**
- Auto-anchor removes manual batch/anchor steps for operators; the dashboard shows **read-only verification** of the chain.

### Demo fallbacks

| Problem | Fallback |
| --- | --- |
| Auto-anchor slow | Show pre-anchored `batch_id` / `tx_hash` via evidence lookup |
| CORS / API down | Walk through Swagger at `/docs` with curl examples from [04-testing.md](04-testing.md) |
| No agent credentials | Use Python SDK + `sign_demo_event.py` from terminal; explain future demo mode ([09-demo-mode.md](09-demo-mode.md)) |
| `403 Invalid event signature` | Re-validate DID matches private key; check JCS alignment |

---

## 10. Paper / demo readiness notes

### Suitable claims for papers and presentations

- VeriAgent implements a **tamper-evident audit commitment layer**: canonical hashing, Merkle batching, and Besu anchoring for AI-agent audit events.
- **Cryptographic binding** at ingestion: registered `did:key` agent, API key auth, and Ed25519 signature over the unsigned canonical event.
- **Public verifiability** after anchoring: inclusion proofs and on-chain batch roots independently checkable via API and Blockscout.
- **Operator-controlled mutations** with a clear split: agents ingest; admin (or scheduler) batches and anchors.
- Prototype deployed on **Besu Edu-Net** with a verified smart contract and public dashboard.

### Claims to avoid or qualify

- Do **not** claim EU AI Act compliance, legal admissibility, or production-grade security.
- Do **not** claim the system proves agents **told the truth** — only that a registered key signed a payload and it was committed.
- Do **not** claim immutability **before** anchoring — SQLite is operator-controlled until the batch root is on chain.
- Do **not** claim decentralized trust — the backend operator and Besu Edu-Net governance are trusted in this prototype.
- Qualify **demo browser signing** as evaluation-only; production agents should use the Python SDK or server-side signing.

### Suggested demo narrative (5–10 minutes)

1. **Problem** — AI agents need auditable, verifiable records without putting raw data on-chain.
2. **Identity** — `did:key` registration and per-agent API keys (admin onboarding today).
3. **Ingestion** — Live signed event from dashboard; show receipt and hash.
4. **Commitment** — Explain Merkle batching; show auto-anchor via `/ops/status` or pre-anchored evidence.
5. **Verification** — Merkle proof + Blockscout tx; optional `POST /audit/merkle/verify`.
6. **Limits** — Operator trust pre-anchor, no truthfulness guarantee, demo mode roadmap.

### Materials to attach or cite

| Resource | Use |
| --- | --- |
| [08-architecture.md](08-architecture.md) | System diagram and lifecycle for paper appendix |
| [06-threat-model.md](06-threat-model.md) | Security scope and non-goals |
| Contract + explorer URLs | Reproducible on-chain evidence |
| `GET /ops/status` JSON | Live operational proof of scheduler |
| [sdk/python/README.md](../sdk/python/README.md) | Integration path for agent developers |

### Post-v1.0 research directions (optional slide footer)

- Public `POST /demo/agents` and one-click dashboard onboarding ([09-demo-mode.md](09-demo-mode.md))
- Independent verifier CLI and TypeScript SDK
- VC-based or federated agent onboarding
- Shorter anchor intervals, public-chain anchoring, external witnesses
- Key rotation, revocation workflows, and HSM integration

---

## Quick reference commands

```bash
# Health and ops
curl -s https://veriagent.dimikog.org/health | jq .
curl -s https://veriagent.dimikog.org/ops/status | jq .

# Backend tests (local)
cd backend && source .venv/bin/activate && python -m pytest

# Manual backup (VM)
sudo /opt/veriagent/scripts/backup_sqlite.sh

# CORS check
curl -sI -H "Origin: https://dimikog.github.io" https://veriagent.dimikog.org/health \
  | grep -i access-control-allow-origin
```

---

**Document status:** Release checklist for v1.0-RC1 · Last verified against production API 2026-06-18
