# Deployment Guide

VeriAgent is developed locally first. This guide documents what is deployed today (public demo **v0.7**), how each component is published, and how to validate or troubleshoot releases.

## Public demo (v0.7)

| Component | URL | Notes |
|-----------|-----|--------|
| Dashboard | https://dimikog.github.io/veriagent/ | GitHub Pages; Vite `base` is `/veriagent/` |
| API | https://veriagent.dimikog.org | FastAPI behind Nginx on a Linux VM |
| API docs | https://veriagent.dimikog.org/docs | Swagger UI at `/docs` (not `/api/docs`) |
| Health | https://veriagent.dimikog.org/health | Returns `version: "0.7.0"` after backend redeploy |
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

Besu Edu-Net
   +-- VeriAgentAnchor @ 0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A
```

## What shipped in v0.7

Summary of deployment-relevant work (detail in [docs/02-devlog.md](02-devlog.md)):

- **Public dashboard** — Vite + React workflow UI (steps 1–6), design tokens, system dark mode, workflow sidebar with truncated hashes and copy buttons.
- **CORS** — FastAPI allowlist for `https://dimikog.github.io` and local Vite origins so the Pages app can call the production API.
- **Block explorer links** — `BLOCKSCOUT_TX_BASE` in `frontend/src/api/client.ts` (`https://blockexplorer.dimikog.org/tx/`); **View on Blockscout** in the sidebar when `tx_hash` is set.
- **API version** — `/health` and OpenAPI metadata use `0.7.0` (aligned with dashboard header badge).
- **GitHub Pages pipeline** — `.github/workflows/deploy-frontend.yml` builds on push to `master` and publishes `frontend/dist/` to the **`gh-pages`** branch.
- **Documentation** — Root README, this guide, [docs/04-testing.md](04-testing.md) dashboard checklist, [frontend/README.md](../frontend/README.md).

The frontend **never** holds private keys; anchoring is server-side only.

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
| `VERIAGENT_RPC_URL` | JSON-RPC for anchoring (Anvil or Besu) |
| `VERIAGENT_CHAIN_ID` | Chain ID for signing |
| `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` | Deployed `VeriAgentAnchor` (Besu: `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`) |
| `VERIAGENT_ANCHOR_PRIVATE_KEY` | Owner key for `anchorBatch` — **never commit** |

| Variable | Purpose |
|----------|---------|
| `VERIAGENT_DB_PATH` | Optional SQLite file path |

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

Expected includes `"version": "0.7.0"`. If you still see `0.5.0`, the running process was not restarted after the version bump.

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

1. **API health check** — expect healthy status and API `0.7.0`.
2. **Create audit event** — `event_id` / `event_hash` in sidebar.
3. **Create Merkle batch** — `batch_id` / `merkle_root`.
4. **Retrieve Merkle proof** — verification success in status panel.
5. **Anchor batch** — requires production anchoring env on VM; then `tx_hash` in sidebar.
6. **Show anchor result** — stored anchor metadata.
7. **View on Blockscout** — opens `https://blockexplorer.dimikog.org/tx/{hash}`.

Full API-level steps: [docs/04-testing.md](04-testing.md).

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

1. Set anchoring env vars to Besu RPC and `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`.
2. Run the audit batch flow locally.
3. Anchor and confirm the tx on https://blockexplorer.dimikog.org/.
4. Optionally mirror the flow on the public dashboard after VM anchoring is configured.

Validate locally before changing production keys or contract addresses on the VM.

---

## Release checklist

Use this after a tagged demo release (e.g. v0.7):

| # | Check |
|---|--------|
| 1 | `master` pushed; backend tests green on VM after pull |
| 2 | Backend restarted; `/health` shows `0.7.0` |
| 3 | CORS preflight and `access-control-allow-origin` for `https://dimikog.github.io` |
| 4 | Frontend workflow succeeded; `gh-pages` has fresh `index.html` + assets |
| 5 | Pages settings: branch `gh-pages`, folder `/ (root)` |
| 6 | https://dimikog.github.io/veriagent/ shows new UI and health step reports `0.7.0` |
| 7 | After anchor test: **View on Blockscout** opens the correct tx URL |

---

## ABI updates

When `contracts/src/VeriAgentAnchor.sol` changes:

1. Rebuild with Foundry and refresh `backend/app/abi/VeriAgentAnchor.json`.
2. Redeploy the contract if needed.
3. Update `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` on the API host.
4. Restart the backend and re-run tests.

---

## What is not in scope yet

- Production VM automation / IaC for VeriAgent
- DID/VC, ZKP, authentication, and OpenTelemetry
