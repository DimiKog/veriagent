# Deployment Guide

VeriAgent is developed locally first. This guide documents what is deployed today (public demo **v0.9.3**), how each component is published, and how to validate or troubleshoot releases.

## Public demo (v0.9.3)

| Component | URL | Notes |
|-----------|-----|--------|
| Dashboard | https://dimikog.github.io/veriagent/ | GitHub Pages; Vite `base` is `/veriagent/` |
| API | https://veriagent.dimikog.org | FastAPI behind Nginx on a Linux VM |
| API docs | https://veriagent.dimikog.org/docs | Swagger UI at `/docs` (not `/api/docs`) |
| Health | https://veriagent.dimikog.org/health | Returns `version: "0.9.3"` |
| Block explorer | https://blockexplorer.dimikog.org/ | Blockscout; contract and txs verified on Besu Edu-Net |
| Besu RPC (operator) | https://rpc.dimikog.org/rpc/ | Used by Foundry deploy and backend anchoring |

**Contract (Besu Edu-Net):** `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A` — deployment tx and history in [docs/02-devlog.md](02-devlog.md).

Anchoring from the **production** API requires `VERIAGENT_*` anchoring env vars on the VM. Treat on-chain anchoring as production-ready only after you have validated that configuration end to end.

## Deployment topology

```text
Browser
   |
   +-- https://dimikog.github.io/veriagent/  (static React build on gh-pages branch)
   |         |
   |         +--> API calls --> https://veriagent.dimikog.org  (CORS allowlist)
   |
   +-- https://blockexplorer.dimikog.org/tx/{hash}  (explorer links from dashboard only)

Linux VM
   +-- Nginx TLS --> uvicorn (FastAPI)
   +-- SQLite (backend/data/ or VERIAGENT_DB_PATH)
   +-- VERIAGENT_* secrets via .env / environment (never in git)

Besu Edu-Net (chain ID 424242)
   +-- VeriAgentAnchor @ 0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A
```

## What shipped in v0.9.3

Summary of deployment-relevant work (detail in [docs/02-devlog.md](02-devlog.md)):

- **End-to-end verifiable audit chain** — registered agent → signed event → HMAC receipt → Merkle batch → proof → Besu anchor; validated on Besu chain `424242`.
- **Agent registry** — admin-protected `POST /agents/register`; per-agent API keys for ingestion.
- **Signed audit events** — Ed25519 signatures required on `POST /audit/events`; public verify/read endpoints unchanged.
- **Public dashboard** — Vite + React workflow UI; **browser-side Ed25519 signing** for demo audit events (step 2 credentials + step 3); batch, proof, and anchor steps unchanged.
- **CORS** — FastAPI allowlist for `https://dimikog.github.io` and local Vite origins.
- **Block explorer links** — `BLOCKSCOUT_TX_BASE` in `frontend/src/api/client.ts`; **View on Blockscout** when `tx_hash` is set.
- **API version** — `/health` and OpenAPI metadata report `0.9.3` (matches dashboard header badge).
- **GitHub Pages pipeline** — `.github/workflows/deploy-frontend.yml` publishes `frontend/dist/` to **`gh-pages`**.
- **Documentation** — Root README, this guide, [docs/04-testing.md](04-testing.md), [frontend/README.md](../frontend/README.md).

The frontend **never** holds admin keys, wallet private keys, or anchor signing secrets. Anchoring is server-side only. The dashboard accepts a **demo agent private key** in memory only (not persisted) to sign audit events in the browser; production agents should sign via the **Python SDK** (`sdk/python/`), `scripts/sign_demo_event.py`, or direct API integration.

---

## Backend (production VM)

### Runtime requirements

- Python 3.12+
- `backend/requirements.txt` in a virtualenv
- `VERIAGENT_RECEIPT_SECRET` set for non-development use
- Writable SQLite path (`backend/data/` by default, or `VERIAGENT_DB_PATH`)
- Committed ABI: `backend/app/abi/VeriAgentAnchor.json` (does **not** read `contracts/out/` at runtime)

Optional example Nginx site config: [`deploy/nginx-veriagent-api.conf.example`](../deploy/nginx-veriagent-api.conf.example).

### Required environment variables (API host)

| Variable | Purpose |
|----------|---------|
| `VERIAGENT_RECEIPT_SECRET` | HMAC secret for ingestion receipts |
| `VERIAGENT_ADMIN_API_KEY` | Admin key for `POST /agents/register` (`X-VeriAgent-Admin-Key`) — **never commit** |
| `VERIAGENT_RPC_URL` | JSON-RPC for anchoring (Anvil or Besu) |
| `VERIAGENT_CHAIN_ID` | Chain ID for signing (Besu Edu-Net: `424242`) |
| `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` | Deployed `VeriAgentAnchor` (Besu: `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`) |
| `VERIAGENT_ANCHOR_PRIVATE_KEY` | Owner key for `anchorBatch` — **never commit** |

| Variable | Purpose |
|----------|---------|
| `VERIAGENT_DB_PATH` | Optional SQLite file path |

| Variable | Default | Purpose |
|----------|---------|---------|
| `VERIAGENT_AUTO_ANCHOR_ENABLED` | `false` | Enable background batch + anchor scheduler |
| `VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS` | `300` | Seconds between scheduler runs |
| `VERIAGENT_AUTO_ANCHOR_MIN_EVENTS` | `1` | Minimum unbatched events before creating a batch |

When `VERIAGENT_AUTO_ANCHOR_ENABLED=true`, the API batches and anchors unbatched events on the configured interval without manual `POST /audit/batches` or `POST .../anchor` calls. Requires the same Besu anchoring env vars as manual anchoring. See [03-api.md](03-api.md#automatic-batching-and-anchoring-v10-pre).

Store secrets in a gitignored `.env` on the host or your secrets manager.

### Deploy or update the backend on the VM

1. Pull latest `master` on the VM.
2. Activate the virtualenv and install deps if `requirements.txt` changed.
3. Run tests: `cd backend && python -m pytest`
4. Restart the systemd unit (or uvicorn process) so code and env changes load.
5. Verify health and version:

```bash
curl -s https://veriagent.dimikog.org/health | jq .
```

Expected includes `"version": "0.9.3"`. If you still see `0.9.0` or older, the running process was not restarted after the version bump.

6. Verify CORS for the dashboard (see [CORS](#cors-browser-frontend) below).

### Backend-only deployment (no Foundry on the API host)

The API VM does not need Foundry installed. Contract deployment and `forge test` run on a developer or deploy machine only.

---

## CORS (browser frontend)

The backend uses FastAPI `CORSMiddleware` with an explicit allowlist (not `*`), because the API can submit on-chain anchor transactions.

| Origin | Use case |
|--------|----------|
| `https://dimikog.github.io` | GitHub Pages dashboard (`/veriagent/`) |
| `http://localhost:5173` | Local Vite dev server |
| `http://127.0.0.1:5173` | Local Vite (loopback alias) |

Allowed methods: `GET`, `POST`, `OPTIONS`. Configuration: `CORS_ALLOWED_ORIGINS` in `backend/app/main.py`.

### After changing CORS or API code on the VM

1. `python -m pytest tests/test_cors.py`
2. Restart the backend service
3. Check allowlist header:

```bash
curl -sI -H "Origin: https://dimikog.github.io" https://veriagent.dimikog.org/health \
  | grep -i access-control-allow-origin
```

Expected: `access-control-allow-origin: https://dimikog.github.io`

4. Preflight must return `200`:

```bash
curl -sI -X OPTIONS \
  -H "Origin: https://dimikog.github.io" \
  -H "Access-Control-Request-Method: POST" \
  https://veriagent.dimikog.org/audit/events
```

Use **either** FastAPI CORS **or** nginx CORS from the example config — not both.

---

## Frontend (GitHub Pages)

### How publishing works

| Step | What happens |
|------|----------------|
| 1 | Push to **`master`** (frontend source under `frontend/src/`, not only `dist/`) |
| 2 | GitHub Actions runs [`.github/workflows/deploy-frontend.yml`](../.github/workflows/deploy-frontend.yml) |
| 3 | Workflow runs `npm ci` and `npm run build` in `frontend/` |
| 4 | `peaceiris/actions-gh-pages` pushes **`frontend/dist/`** to the **`gh-pages`** branch |
| 5 | GitHub Pages serves the site from **`gh-pages`** at the repo root |

**Important:** Committing `frontend/dist/` on `master` does **not** update the live site unless Pages is incorrectly pointed at `master`. The live dashboard is whatever is on **`gh-pages`** after a successful workflow run.

### One-time GitHub repository setup

1. **Settings → Pages**
2. **Build and deployment → Source:** **Deploy from a branch**
3. Branch: **`gh-pages`**, folder: **`/ (root)`**

Do **not** set the Pages source to **GitHub Actions** for this repo. That mode conflicts with `peaceiris/actions-gh-pages` and can produce:

```text
Value 'github-pages' is not valid
```

### Local vs production API

| Mode | API target |
|------|------------|
| `npm run dev` | Vite proxy `/veriagent-api` → `https://veriagent.dimikog.org` (see `vite.config.ts`) |
| Production build (Pages) | `https://veriagent.dimikog.org` directly (`frontend/src/api/client.ts`) |

Override with `VITE_API_BASE_URL` if needed. More detail: [frontend/README.md](../frontend/README.md).

### Frontend configuration (`frontend/src/api/client.ts`)

| Constant | Production value |
|----------|------------------|
| `API_BASE_URL` | `https://veriagent.dimikog.org` (non-dev build) |
| `BLOCKSCOUT_TX_BASE` | `https://blockexplorer.dimikog.org/tx/` |
| `BLOCKSCOUT_CONFIGURED` | `true` when the base URL does not contain `example` |
| `API_DOCS_URL` | `https://veriagent.dimikog.org/docs` (production); `http://127.0.0.1:8000/docs` in Vite dev |

### Deploy or update the dashboard

1. Merge/push frontend changes to **`master`**.
2. Open **Actions → Deploy frontend to GitHub Pages** — confirm the latest run **succeeded**.
3. On GitHub, open branch **`gh-pages`** and check `index.html` script tags (hashed filenames should match a recent build, e.g. `index-B0M4wE9O.js`, not an old bundle).
4. Open https://dimikog.github.io/veriagent/ (include **`/veriagent/`**).
5. Hard refresh or use a private window (Pages CDN cache is ~10 minutes).

### Troubleshooting: “I pushed but still see the old UI”

| Symptom | Likely cause | What to check |
|---------|----------------|---------------|
| Old layout / `v0.5.0` badge | Pages not serving latest `gh-pages` | **Settings → Pages** source = `gh-pages` / `(root)` |
| `index.html` references old `assets/index-*.js` | Stale Pages deployment or failed workflow | **Actions** workflow status; compare live page source vs `gh-pages` branch |
| Changes only on `master` in `frontend/dist/` | Dist on `master` is not the Pages source | Wait for workflow or fix Pages source |
| API still `0.5.0` on health | Backend not restarted | VM restart after pull (see [Backend](#backend-production-vm)) |
| CORS errors in browser console | CORS not deployed on API | CORS tests + VM restart |

Live check — page source should load JS/CSS under `/veriagent/assets/` that exist on the current `gh-pages` commit. Mismatched hashes between the live URL and the `gh-pages` branch mean Pages is out of sync with git.

### Dashboard end-to-end (production)

Use https://dimikog.github.io/veriagent/ in order:

1. **API health check** — expect healthy status and API `0.9.3`.
2. **Agent credentials** — registered Agent DID, `va_agent_...` API key, and base64 demo private key; click **Use agent credentials**.
3. **Create signed audit event** — browser signs and stores the event; confirm `event_id` / `event_hash`.
4. **Create Merkle batch** — `batch_id` / `merkle_root`.
5. **Retrieve Merkle proof** — verification success in status panel.
6. **Anchor batch** — requires production anchoring env on VM (`VERIAGENT_CHAIN_ID=424242`); then `tx_hash` in sidebar.
7. **Show anchor result** — stored anchor metadata.
8. **View on Blockscout** — opens `https://blockexplorer.dimikog.org/tx/{hash}`.

Full signed-ingestion and API-level steps: [docs/04-testing.md](04-testing.md).

---

## Besu Edu-Net contract deployment

`VeriAgentAnchor` is deployed and verified on Besu Edu-Net.

### Deploy machine environment

| Variable | Purpose |
|----------|---------|
| `BESU_RPC_URL` | Besu JSON-RPC (e.g. `https://rpc.dimikog.org/rpc/`) |
| `BESU_PRIVATE_KEY` | Deployer key — **never commit** |

### Foundry settings (`contracts/foundry.toml`)

```toml
evm_version = "paris"
optimizer = true
optimizer_runs = 200
```

Solc `0.8.20`.

### Deploy command

From `contracts/` (alias `besu` in `foundry.toml`):

```bash
export BESU_RPC_URL="https://rpc.dimikog.org/rpc/"
export BESU_PRIVATE_KEY="0x..."   # never commit

forge script script/DeployVeriAgentAnchor.s.sol:DeployVeriAgentAnchor \
  --rpc-url besu \
  --broadcast \
  --private-key "$BESU_PRIVATE_KEY" \
  --legacy \
  --with-gas-price 1000000000
```

- `--legacy` — required for this Besu network configuration.
- `--with-gas-price 1000000000` — `1 gwei`.

Recorded deployment:

```text
VERIAGENT_ANCHOR_CONTRACT_ADDRESS=0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A
```

### Blockscout verification

| Setting | Value |
|---------|--------|
| Compiler | `0.8.20` |
| EVM version | `paris` |
| Optimizer | enabled |
| Optimizer runs | `200` |
| Constructor arguments | none |

Verification completed successfully for the Besu Edu-Net deployment.

### Block explorer (Blockscout)

| Resource | URL |
|----------|-----|
| Explorer home | https://blockexplorer.dimikog.org/ |
| Contract | https://blockexplorer.dimikog.org/address/0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A |
| Transaction | https://blockexplorer.dimikog.org/tx/{tx_hash} |

Dashboard links are frontend-only via `BLOCKSCOUT_TX_BASE`.

---

## Local development flows

### Local contract deployment (Anvil)

1. `cd contracts && forge test`
2. Start `anvil`
3. Deploy with `forge script` (see root [README.md](../README.md))
4. Point backend anchoring env vars at the deployed address

### Typical local anchoring flow (Anvil)

1. Run `uvicorn app.main:app --reload` in `backend/`.
2. Store events and create a batch via the API or dashboard.
3. Set `VERIAGENT_RPC_URL`, `VERIAGENT_CHAIN_ID`, `VERIAGENT_ANCHOR_CONTRACT_ADDRESS`, `VERIAGENT_ANCHOR_PRIVATE_KEY`.
4. `POST /audit/batches/{batch_id}/anchor` — persists `tx_hash`, block metadata in `batch_anchors`.
5. `GET /audit/batches/{batch_id}/anchor` — read stored record.

A second `POST .../anchor` on the same batch returns `already_anchored: true` without a new transaction.

### Local backend testing against Besu

1. Set anchoring env vars to Besu RPC, `VERIAGENT_CHAIN_ID=424242`, and contract `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`.
2. Run the audit batch flow locally.
3. Anchor and confirm the tx on https://blockexplorer.dimikog.org/.
4. Optionally mirror the flow on the public dashboard after VM anchoring is configured.

Validate locally before changing production keys or contract addresses on the VM.

---

## Release checklist

Use this after a tagged demo release (e.g. v0.9.3):

| # | Check |
|---|--------|
| 1 | Tag pushed (e.g. `v0.9.3`); `master` on VM; backend tests green after pull |
| 2 | `VERIAGENT_RECEIPT_SECRET`, `VERIAGENT_ADMIN_API_KEY`, and Besu anchoring env vars set on VM |
| 3 | Backend restarted; `/health` shows `0.9.3` |
| 4 | CORS preflight and `access-control-allow-origin` for `https://dimikog.github.io` |
| 5 | Agent registration works with admin key; signed `POST /audit/events` accepts registered agent payloads |
| 6 | Frontend workflow succeeded; `gh-pages` has fresh `index.html` + assets |
| 7 | Pages settings: branch `gh-pages`, folder `/ (root)` |
| 8 | https://dimikog.github.io/veriagent/ health step reports `0.9.3` |
| 9 | Full chain on Besu `424242`: signed event (dashboard or API) → batch → proof → anchor; **View on Blockscout** opens correct tx URL |

---

## ABI updates

When `contracts/src/VeriAgentAnchor.sol` changes:

1. Rebuild with Foundry and refresh `backend/app/abi/VeriAgentAnchor.json`.
2. Redeploy the contract if needed.
3. Update `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` on the API host.
4. Restart the backend and re-run tests.

---

## Python Agent SDK (v0.9.4)

External agents can submit signed events without implementing JCS or HTTP auth headers manually.

| Item | Location |
|------|----------|
| Package | `sdk/python/veriagent/` |
| Install | `cd sdk/python && pip install -e .` |
| Docs | [sdk/python/README.md](../sdk/python/README.md) |
| Tests | `cd sdk/python && pip install -e ".[dev]" && python -m pytest -v` |

The SDK derives `agent_did` and `verification_method` from a base64 Ed25519 private key, canonicalizes the unsigned event with Python `jcs`, signs, and POSTs to `/audit/events` with `X-VeriAgent-API-Key`. Admin agent registration is **not** included yet — register agents via `POST /agents/register` on the API host first.

Demo private key for local testing: `scripts/demo_agent.env` (`VERIAGENT_DEMO_PRIVATE_KEY`).

---

## What is not in scope yet

- Production VM automation / IaC for VeriAgent
- DID resolution over the network, key rotation via DID, and VC/ZKP
- SDK admin registration wrapper, async client, TypeScript SDK
- SQLite backup/recovery automation on the VM
- OpenTelemetry and authenticated batch/anchor endpoints
