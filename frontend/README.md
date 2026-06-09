# VeriAgent Frontend

Minimal Vite + React + TypeScript dashboard for the VeriAgent audit workflow.

The UI talks to the deployed backend at `https://veriagent.dimikog.org`. As of **v0.9.3**, storing audit events requires a registered **agent API key**, a matching **Agent DID**, and an **Ed25519 signature** over the unsigned canonical event payload. The dashboard can sign events in the browser for demo purposes. It never handles admin keys, wallet private keys, or anchor signing secrets — batch anchoring remains server-side.

## Prerequisites

- Node.js 20+ (or another current LTS release)
- npm

## Setup

From the project root:

```bash
cd frontend
npm install
```

## Scripts

| Script | Command | Purpose |
| --- | --- | --- |
| `dev` | `npm run dev` | Start the Vite dev server with hot reload |
| `build` | `npm run build` | Type-check and build production assets to `dist/` |
| `preview` | `npm run preview` | Serve the production build locally |

## Local development

```bash
npm run dev
```

Open the URL shown in the terminal. Because the app is configured for GitHub Pages, use the `/veriagent/` path — typically:

```text
http://localhost:5173/veriagent/
```

Local dev routes API calls through a Vite proxy (`/veriagent-api` → `https://veriagent.dimikog.org`) so you can develop without backend CORS. Override with `VITE_API_BASE_URL` if needed.

The GitHub Pages deployment calls the API directly and **requires** backend CORS for `https://dimikog.github.io` (see [docs/05-deployment.md](../docs/05-deployment.md)).

## Production build

```bash
npm run build
```

Output is written to `frontend/dist/`.

Preview the production build locally (uses the same `/veriagent/` base path as GitHub Pages):

```bash
npm run preview
```

Then open:

```text
http://localhost:4173/veriagent/
```

## GitHub Pages deployment

The frontend is deployed automatically when changes are pushed to the **`master`** branch.

Workflow file: [`.github/workflows/deploy-frontend.yml`](../.github/workflows/deploy-frontend.yml)

It:

1. installs dependencies from `frontend/package-lock.json`
2. runs `npm run build` in `frontend/`
3. pushes `frontend/dist/` to the **`gh-pages`** branch

### One-time repository setup

In the GitHub repository settings:

1. Go to **Settings → Pages**
2. Under **Build and deployment**, set **Source** to **Deploy from a branch**
3. Choose branch **`gh-pages`**, folder **`/ (root)`**

Do **not** select **GitHub Actions** as the Pages source for this workflow. That mode expects a `github-pages` deployment environment and a different Actions setup; if Pages is not configured that way, workflow runs fail with:

```text
Value 'github-pages' is not valid
```

After the first successful workflow run on `master`, the site is available at:

```text
https://<github-username>.github.io/veriagent/
```

For this repository, that is:

```text
https://dimikog.github.io/veriagent/
```

The Vite `base` path is set to `/veriagent/` in `vite.config.ts` so asset URLs resolve correctly on GitHub Pages project sites.

## Dashboard workflow

Use the sections in order for a full end-to-end demo:

1. **API health check** — confirm the backend is reachable.
2. **Agent credentials** — enter the registered **Agent DID**, **Agent API Key** (`va_agent_…`), and **Agent Private Key** (base64 Ed25519 seed, demo mode). Click **Use agent credentials** to derive the public key, verify the DID matches, and compute `verification_method`.
3. **Create signed audit event** — build an unsigned event, canonicalize and sign it in the browser, then submit with `X-VeriAgent-API-Key`. Requires step 2.
4. **Create Merkle batch** — batch unbatched events and capture `batch_id` / `merkle_root`.
5. **Retrieve Merkle proof** — fetch and verify an inclusion proof for the current event.
6. **Anchor batch** — submit the batch root on chain via the backend.
7. **Show anchor result** — read the stored anchor record (`tx_hash`, `chain_id`, etc.).

### Frontend signed event demo (v0.9.3)

- **Agent DID** — registered `did:key:z…` identifier. Used as `agent_id` on the audit event payload. Must match the public key derived from the demo private key.
- **Agent API Key** — masked password field; sent only as header `X-VeriAgent-API-Key` on `POST /audit/events`.
- **Agent Private Key** — base64-encoded 32-byte Ed25519 seed. Used only in demo mode to sign events in the browser. **Not** persisted to `localStorage` or `sessionStorage`; kept in React state for the current page session only.
- **Signing boundary** — the browser signs the RFC 8785 / JCS canonical JSON of the unsigned event (fields only; `signature` and `verification_method` are excluded). Implementation lives in `src/utils/canonicalize.ts`; the Python backend remains the source of truth.
- **did:key helpers** — `src/utils/didKey.ts` mirrors backend behavior: multicodec prefix `0xed 0x01`, base58btc, `did:key:z…`, and `verification_method` = `DID#multibase`.
- Production agents should normally sign outside the browser (agent runtime, CI, or an SDK). This UI exposes demo signing so you can walk through the full workflow without a separate signer.

### Agent credentials validation

- **Use agent credentials** requires all three fields.
- The UI derives the Ed25519 public key from the private key, builds the expected `did:key`, and marks credentials **Ready** only when it matches the pasted Agent DID.
- **401** — invalid or missing agent API key.
- **403** — agent/DID/key mismatch, wrong `verification_method`, or invalid event signature.

Agent registration and the admin API key are intentionally **not** exposed in the public dashboard.

The **Current workflow state** sidebar tracks the latest IDs and hashes across steps. Long values are truncated with a **copy** button (full value on hover). When a transaction hash is present and Blockscout is configured, a **View on Blockscout** link appears.

The dashboard uses CSS design tokens and follows the system **dark mode** preference (`prefers-color-scheme`). Workflow panels are numbered steps 1–7 in the main column.

## API helper

Reusable fetch wrappers live in `src/api/client.ts`. They:

- target the configured `API_BASE_URL`
- parse FastAPI error `detail` fields into readable messages
- expose typed helpers for each audit endpoint used by the dashboard

## Configuration (`src/api/client.ts`)

### API docs URL

Swagger UI is at `{API host}/docs` (e.g. `https://veriagent.dimikog.org/docs`). The dashboard **API Docs** nav link uses `API_DOCS_URL` in `client.ts` — do not use a GitHub Pages path like `/veriagent/api/docs`.

### API base URL

Edit `API_BASE_URL` if you need to point at a local backend during development, for example:

```typescript
export const API_BASE_URL = 'http://127.0.0.1:8000'
```

When doing so, ensure the backend allows browser requests from your dev origin (CORS), or use the Vite dev-server proxy.

### Blockscout transaction link

`BLOCKSCOUT_TX_BASE` is the transaction URL prefix (must end with `/tx/`). It is currently:

```text
https://blockexplorer.dimikog.org/tx/
```

While the value contains `example`, `BLOCKSCOUT_CONFIGURED` is `false` and the UI hides the explorer link. With a live base URL, **View on Blockscout** appears in the workflow sidebar when `tx_hash` is set.

## Lint

```bash
npm run lint
```
