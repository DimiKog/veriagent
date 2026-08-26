# VeriAgent

**A verifiable audit commitment layer for AI-agent actions.**

VeriAgent records structured audit events from AI agents, binds them to registered Ed25519 `did:key` identities, commits them with canonical hashing, batches them into Merkle trees, and anchors batch roots on Besu. A public dashboard walks through the full **Submitted → Batched → Anchored** lifecycle. Third parties can verify inclusion proofs and on-chain anchors with an independent CLI that does not trust the VeriAgent API for cryptographic checks.

**Release version:** `1.0.0` / **v1.0.0**, released 26 August 2026 (backend `/health`, Python SDK, and frontend badge).

## Public demo

| Resource | URL |
| --- | --- |
| Frontend dashboard | https://dimikog.github.io/veriagent/ |
| Public API | https://veriagent.dimikog.org |
| API docs (Swagger) | https://veriagent.dimikog.org/docs |
| Health check | https://veriagent.dimikog.org/health |
| Ops status | https://veriagent.dimikog.org/ops/status |
| Block explorer | https://blockexplorer.dimikog.org/ |

The public SPA ships four surfaces (**Dashboard / Register / Console / Admin**). Production signing uses the Python SDK/CLI — the browser never holds agent private keys. Architecture: [docs/16-production-architecture.md](docs/16-production-architecture.md). First-run walkthrough: [docs/17-first-run-guide.md](docs/17-first-run-guide.md).

The production API reports **`1.0.0`** with public registration (proof-of-control + admin approval), automatic batching/anchoring with crash-restart recovery, event lifecycle status, and an ops status endpoint.

The `VeriAgentAnchor` contract is deployed and verified on **Besu Edu-Net** (`0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`). Deployment notes: [docs/02-devlog.md](docs/02-devlog.md). Block explorer (Blockscout): `https://blockexplorer.dimikog.org/` — transaction links in the dashboard use `https://blockexplorer.dimikog.org/tx/{hash}`.

## What it does

VeriAgent provides a research-grade audit pipeline for AI-agent activity:

- Creates structured AI-agent audit events
- Canonicalizes JSON using RFC 8785 / JCS
- Computes SHA-256 event commitments
- Stores events locally in SQLite
- Returns signed HMAC-SHA256 ingestion receipts
- Requires Ed25519-signed audit events from registered agents
- Registers agents with spec-compliant Ed25519 `did:key` identifiers (`did:key:z...`)
- Public registration request workflow: create request → CLI ownership proof → admin approve/reject → one-time credential claim
- Break-glass admin registration (`POST /agents/register`) remains available for operators
- Restricts Merkle batch creation and on-chain anchoring to admin API key holders
- Automatically batches and anchors unbatched events on a background scheduler when enabled
- Recovers stranded or interrupted anchors: unanchored batches first, durable pending transactions, chain-aware reconciliation
- Exposes public event lifecycle at `GET /audit/events/{event_id}/status` (Submitted → Batched → Anchored)
- Exposes read-only scheduler ops status at `GET /ops/status`
- Signs audit events, registration proofs, and credential claims via the official Python SDK/CLI
- Batches event hashes into Merkle trees and generates/verifies inclusion proofs
- Anchors Merkle roots on Besu via `VeriAgentAnchor`
- Verifies event hash, Ed25519 signature, Merkle proof, and anchor metadata offline with `veriagent verify`
- Exposes separated SPA surfaces: public dashboard, registration, operator console, admin

See [docs/03-api.md](docs/03-api.md) for endpoint details. See [docs/16-production-architecture.md](docs/16-production-architecture.md) for the production surface split.

## Trust model and limitations

This is a **research prototype**, not a production compliance product.

- The **backend operator is trusted** in this demo. The API stores events and submits anchor transactions.
- **SQLite is mutable** before anchoring. Local records can be changed until a batch root is anchored on chain.
- **Blockchain anchoring** provides a timestamped, public commitment *after* anchoring. It does not prove the underlying agent action occurred.
- **Event submission requires a registered agent.** `POST /audit/events` accepts events only from active agents that present a valid `X-VeriAgent-API-Key`, set `agent_id` to their registered DID, and sign the unsigned canonical event payload with their registered Ed25519 key. Public read and verification endpoints remain open.
- **Public registration requires proof-of-control.** Applicants create a request, sign a challenge with their Ed25519 private key, wait for admin approval, then claim the API key once with a second ownership signature. The admin key is not shared with applicants. The raw `va_agent_...` key is returned only on claim, never on approve or status poll.
- **Production signing is SDK/CLI-only.** The browser never holds agent private keys. Registration proof, credential claim, event submit, and independent verify run beside the agent via `veriagent` CLI / Python SDK.
- **Auto batch/anchor is server-side.** When enabled, the scheduler runs inside the API process; `/console` and `/dashboard` observe lifecycle via public/agent read APIs.
- **Independent verification does not trust the API for crypto checks.** `veriagent verify` recomputes the event hash, signature, Merkle inclusion, and anchor metadata from local JSON files.
- **Anchor crash-restart** persists pending transactions and reconciles from chain when a batch is already anchored. A narrow pre-confirmation window can still produce one extra reverted `anchorBatch` (the contract rejects duplicates). Residual risk: [docs/06-threat-model.md](docs/06-threat-model.md).
- **This is not an EU AI Act compliance product.** It demonstrates technical building blocks only.

## Architecture

```text
Applicant / Agent host          Public SPA                 Offline
  Python SDK / CLI              Dashboard / Register         veriagent verify
  • register request|prove|claim  Console / Admin            (no API trust)
  • submit signed events              |
        |                             |
        v                             v
              VeriAgent API  (FastAPI, SQLite)
                    |
                    +--> SQLite (events, registration, batches, anchors)
                    |
                    +--> Auto batch/anchor scheduler  (optional)
                    |      unanchored-first + pending-tx recovery
                    v
              Merkle batch root
                    |
                    v
              Besu Anchor Contract  (VeriAgentAnchor)
                    |
                    +--> Block explorer (blockexplorer.dimikog.org)
```

Production workflow:

1. Applicant creates a registration request on `/register` (public identity only).
2. CLI proves key ownership (`veriagent register prove`); admin approves on `/admin`.
3. CLI claims the one-time agent API key (`veriagent register claim`).
4. Agent runtime submits signed events (`veriagent submit` or Python SDK).
5. Scheduler (or admin) batches and anchors; Console/Dashboard show **Submitted → Batched → Anchored**.
6. Anyone can download proof/anchor JSON and run `veriagent verify` offline.

## Local development

Newcomers should follow **[docs/17-first-run-guide.md](docs/17-first-run-guide.md)** (install, register, submit, observe lifecycle, independently verify). The sections below are the short form.

### Backend

Python **3.12+**. Activate the virtualenv before running tests or the server:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit secrets; loaded automatically on startup
python -m pytest
uvicorn app.main:app --reload
```

Local API docs: http://127.0.0.1:8000/docs

The API loads `backend/.env` when the file exists (same behavior locally and in production). Variables already exported in the process environment take precedence over `.env`. See `.env.example` for registration, admin, auto-anchor, and blockchain settings. Full rules: [docs/05-deployment.md](docs/05-deployment.md#how-configuration-is-loaded-local-and-production).

Check scheduler ops status locally:

```bash
curl -s http://127.0.0.1:8000/ops/status | jq .
```

To generate a signed sample event body for manual testing (emits a real `did:key:z...` agent identity):

```bash
python scripts/sign_demo_event.py
```

Agent DIDs use spec-compliant Ed25519 `did:key` encoding (`did:key:z...` with multibase public key). The legacy `did:key:demo:<sha256>` format is deprecated. `did:key` does not support key rotation by itself; agent revocation and status remain in VeriAgent's internal registry.

See [docs/03-api.md](docs/03-api.md) for the signing boundary (`signature` and `verification_method` are excluded from the canonical payload).

#### Anchoring (manual or scheduler)

For on-chain anchoring (manual admin routes or the auto scheduler), set:

| Variable | Purpose |
| --- | --- |
| `VERIAGENT_RPC_URL` | JSON-RPC endpoint (Anvil or Besu) |
| `VERIAGENT_CHAIN_ID` | Chain ID (`424242` for Besu Edu-Net) |
| `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` | Deployed `VeriAgentAnchor` address |
| `VERIAGENT_ANCHOR_PRIVATE_KEY` | Owner key for `anchorBatch` — **never commit** |

Registration and event submit still work without these. Anchoring API calls return **503** until they are set.

#### Automatic batching and anchoring

Optional background scheduler (disabled by default):

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERIAGENT_AUTO_ANCHOR_ENABLED` | `false` | Enable automatic batch + anchor cycles |
| `VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS` | `300` | Seconds between scheduler runs |
| `VERIAGENT_AUTO_ANCHOR_MIN_EVENTS` | `1` | Minimum unbatched events before creating a batch |

When enabled, each cycle **anchors unanchored batches first** (resume pending txs or reconcile from chain), then creates a Merkle batch from unbatched events and anchors it using the same logic as the admin `POST` routes. Manual admin routes remain available. Monitor state via `GET /ops/status` — no secrets are returned. `last_status` includes `anchor_submitted`, `anchor_pending`, `anchor_reconciled`, `anchor_succeeded`, and `anchor_failed`.

See [docs/05-deployment.md](docs/05-deployment.md) for production configuration.

#### Public registration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERIAGENT_REGISTRATION_ENABLED` | `true` in `.env.example` | Master switch for `/registration/*` routes |
| `VERIAGENT_REGISTRATION_CHALLENGE_TTL_MINUTES` | `15` | Pending-request / challenge expiry window |

### Python SDK and CLI

External agents submit signed events and complete registration without hand-rolling JCS or Ed25519 signing:

```bash
cd sdk/python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -v
veriagent --help
```

| Command | Role |
| --- | --- |
| `veriagent register request\|prove\|claim` | Public onboarding (ownership proof + one-time API key claim) |
| `veriagent submit` | Sign and ingest an audit event |
| `veriagent verify` | Offline independent verification (event + Merkle proof + anchor) |

Usage and examples: [sdk/python/README.md](sdk/python/README.md). Verifier evidence format: [docs/15-independent-verifier.md](docs/15-independent-verifier.md).

### Frontend

Node.js **20+**.

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173/veriagent/ → API http://127.0.0.1:8000
npm run build
npm run preview
```

Local `npm run dev` talks to `http://127.0.0.1:8000` by default. Override with `VITE_API_BASE_URL` (e.g. production). The GitHub Pages build uses the public API. See [frontend/README.md](frontend/README.md).

| Surface | Audience | What it does |
| --- | --- | --- |
| `/dashboard` | Public | Read-only lookup, lifecycle, Merkle proof, Blockscout links |
| `/register` | Applicants | Create registration request; CLI snippets for prove/claim |
| `/console` | Operators | Event list and lifecycle (dev: agent API key in `sessionStorage`) |
| `/admin` | Admins | Approve/reject registration requests (dev: admin key in `sessionStorage`) |

### Contracts (optional)

Foundry tests and local Anvil deployment are documented in [docs/05-deployment.md](docs/05-deployment.md). The backend uses the committed ABI at `backend/app/abi/VeriAgentAnchor.json` and does not require Foundry at runtime.

## Registration workflow

Preferred onboarding path (no shared admin key):

```text
POST /registration/requests          → request_id + challenge
veriagent register prove             → Ed25519 ownership proof
Admin: POST .../approve | .../reject
veriagent register claim             → va_agent_... API key once
```

- Status polling never returns `api_key`, challenge nonce, or proof payload after the pending window.
- Approve returns a one-time `retrieval_token`; the agent API key is issued only on `POST .../credentials`.
- Break-glass: `POST /agents/register` with `X-VeriAgent-Admin-Key` still creates an active agent immediately.

Design and API: [docs/14-registration-workflow.md](docs/14-registration-workflow.md), [docs/03-api.md](docs/03-api.md).

## Event lifecycle

Public `GET /audit/events/{event_id}/status` returns whether an event is batched and anchored (`batched`, `batch_id`, `merkle_root`, `anchored`, `tx_hash`, `block_number`, `chain_id`). The Dashboard and Console poll this endpoint and show **Submitted → Batched → Anchored**. The response does not include signatures, canonical JSON, or credentials.

## Deployment

| Component | How it runs |
| --- | --- |
| Backend | Linux VM — systemd service, Nginx reverse proxy, HTTPS at `veriagent.dimikog.org` |
| Frontend | GitHub Pages — CI builds on push to `master` and publishes `frontend/dist/` to `gh-pages` (build output is not kept on `master`) |
| Secrets | Private keys and tokens only via environment variables or gitignored `.env` files on the host |

After deploy, verify:

```bash
curl -s https://veriagent.dimikog.org/health | jq .
curl -s https://veriagent.dimikog.org/ops/status | jq .
```

Operational details: [docs/05-deployment.md](docs/05-deployment.md). SQLite backup/restore: [docs/07-backup-restore.md](docs/07-backup-restore.md). Development history: [docs/02-devlog.md](docs/02-devlog.md).

## Security note

- **Never commit** `.env`, private keys, API tokens, or deployer credentials.
- **Never commit** `backend/data/veriagent.db`, virtualenvs, or Foundry broadcast artifacts with sensitive material.
- The **frontend never handles agent private keys, admin keys in query params, wallet private keys, or anchor signing secrets**. Registration proof, credential claim, and event signing run in the Python SDK/CLI. On-chain anchoring is performed server-side by the backend.
- **Console/Admin currently use `sessionStorage` for development unlock** (agent API key / admin key). That is a temporary operator-unlock model, not production SSO. See [docs/16-production-architecture.md](docs/16-production-architecture.md).
- **`GET /ops/status` and `GET /audit/events/{event_id}/status` are public** and return scheduler / lifecycle metadata only — no admin key, receipt secret, RPC URL, private keys, or registration credentials.

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/00-vision.md](docs/00-vision.md) | Project vision |
| [docs/03-api.md](docs/03-api.md) | API reference (`/health`, `/ops/status`, audit, batch, anchor, agents, registration) |
| [docs/04-testing.md](docs/04-testing.md) | Testing and manual verification flow |
| [docs/05-deployment.md](docs/05-deployment.md) | Besu, VM, auto-anchor, CORS, and GitHub Pages deployment |
| [docs/06-threat-model.md](docs/06-threat-model.md) | Threat model, security boundaries, RC1 residual risks |
| [docs/07-backup-restore.md](docs/07-backup-restore.md) | SQLite backup and restore on the VM |
| [docs/08-architecture.md](docs/08-architecture.md) | System architecture (v1.0-RC1) |
| [docs/09-demo-mode.md](docs/09-demo-mode.md) | Demo mode design — safe public onboarding without admin keys (design only) |
| [docs/10-v1-release-checklist.md](docs/10-v1-release-checklist.md) | v1.0-RC1 release checklist and demo gates |
| [docs/11-demo-script.md](docs/11-demo-script.md) | 60–90 second presentation demo script |
| [docs/12-release-notes-v1.0.0-rc1.md](docs/12-release-notes-v1.0.0-rc1.md) | v1.0.0-RC1 release notes |
| [docs/13-commercial-readiness-roadmap.md](docs/13-commercial-readiness-roadmap.md) | Research → commercial pilot roadmap |
| [docs/14-registration-workflow.md](docs/14-registration-workflow.md) | Registration request, proof, admin review, credential claim |
| [docs/15-independent-verifier.md](docs/15-independent-verifier.md) | Independent verifier CLI (`veriagent verify`) |
| [docs/16-production-architecture.md](docs/16-production-architecture.md) | Production surfaces: dashboard / register / console / admin + SDK/CLI |
| [docs/17-first-run-guide.md](docs/17-first-run-guide.md) | Install, register, submit, observe, and independently verify |
| [docs/02-devlog.md](docs/02-devlog.md) | Phase-by-phase development log |
| [sdk/python/README.md](sdk/python/README.md) | Python SDK/CLI install and usage |
| [frontend/README.md](frontend/README.md) | Frontend setup and Pages workflow |
