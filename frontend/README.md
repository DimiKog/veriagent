# VeriAgent Frontend

Minimal Vite + React + TypeScript dashboard for the VeriAgent audit workflow.

The UI talks to the deployed backend at `https://veriagent.dimikog.org`. It does not handle wallets, private keys, or any secrets — anchoring is performed server-side.

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
2. **Create audit event** — store an audit event and capture `event_id` / `event_hash`.
3. **Create Merkle batch** — batch unbatched events and capture `batch_id` / `merkle_root`.
4. **Retrieve Merkle proof** — fetch and verify an inclusion proof for the current event.
5. **Anchor batch** — submit the batch root on chain via the backend.
6. **Show anchor result** — read the stored anchor record (`tx_hash`, `chain_id`, etc.).

The **Current workflow state** sidebar tracks the latest IDs and hashes across steps. Long values are truncated with a **copy** button (full value on hover). When a transaction hash is present and Blockscout is configured, a **View on Blockscout** link appears.

The dashboard uses CSS design tokens and follows the system **dark mode** preference (`prefers-color-scheme`). Workflow panels are numbered steps 1–6 in the main column.

## API helper

Reusable fetch wrappers live in `src/api/client.ts`. They:

- target the configured `API_BASE_URL`
- parse FastAPI error `detail` fields into readable messages
- expose typed helpers for each audit endpoint used by the dashboard

## Configuration (`src/api/client.ts`)

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
