# VeriAgent Frontend

Vite + React + TypeScript multi-route SPA for VeriAgent verification, registration, operator console, and admin controls.

The UI talks to the local backend at `http://127.0.0.1:8000` during `npm run dev`, and to `https://veriagent.dimikog.org` in production builds.

## Production crypto boundary

**The browser must never ask for, paste, or store agent private keys in production flows.**

| Surface | Credentials allowed | Signing |
| --- | --- | --- |
| Dashboard | None (public read-only) | None |
| Register | Public key + DID only | Prove/claim via CLI |
| Console | Agent API key in `sessionStorage` | Submit via CLI/SDK |
| Admin | Admin key in `sessionStorage` (header, not query params) | N/A |

Signing and private-key material stay in the agent runtime, CI, or the Python CLI/SDK (`veriagent register prove`, `veriagent register claim`, `veriagent submit`, `veriagent verify`). The production frontend contains **no** browser crypto utilities for agent identity.

## Routes

| Path | Page |
| --- | --- |
| `/` | Redirects to `/dashboard` |
| `/dashboard` | Public read-only verification |
| `/register` | Agent onboarding (no private keys) |
| `/console` | Operator portal (API key session) |
| `/admin` | Admin control plane |

Router basename is `/veriagent` (matches Vite `base`). Local URLs look like `http://localhost:5173/veriagent/dashboard`.

## Prerequisites

- Node.js 20+ (or another current LTS release)
- npm

## Setup

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
| `lint` | `npm run lint` | Run ESLint |

## Local development

```bash
npm run dev
```

Open:

```text
http://localhost:5173/veriagent/
```

By default, local dev calls `http://127.0.0.1:8000` (start the backend first). Override with `VITE_API_BASE_URL` if needed (for example the production API). An optional Vite proxy at `/veriagent-api` also targets the local backend. CLI snippets in the UI use `CLI_API_BASE_URL` (absolute host) so they work outside the browser.

## Production build

```bash
npm run build
```

Output is written to `frontend/dist/`. Preview:

```bash
npm run preview
```

Then open `http://localhost:4173/veriagent/`.

## Surfaces

### Dashboard (`/dashboard`)

Read-only by design. Anyone can verify evidence; no unauthenticated user can create or modify audit records.

- Event ID lookup with lifecycle polling (Submitted → Batched → Anchored)
- Batch lookup, Merkle proof get + verify, anchor record + Blockscout link
- Optional ops/public stats via `GET /ops/status`
- Distinguishes platform verification from independent offline trust (`veriagent verify`)

### Register (`/register`)

Submit `POST /registration/requests` with public identity fields only. Then:

1. Prove ownership: `veriagent register prove --request-id <id> --api-base-url <API>`
2. Poll status until approved / rejected / expired
3. Claim credentials: `veriagent register claim --request-id <id> --api-base-url <API>`

### Console (`/console`)

Paste agent API key (sessionStorage). Lists `GET /audit/events`, lifecycle polling, and evidence tools. Submit guidance points to CLI/SDK — no browser signing.

### Admin (`/admin`)

Admin key in sessionStorage as `X-VeriAgent-Admin-Key`. Pending registration queue with approve/reject, ops scheduler panel, and placeholders for agents / key management endpoints not yet available.

## Project structure

```text
src/
  main.tsx              BrowserRouter basename="/veriagent"
  App.tsx               Routes only
  layout/AppLayout.tsx  Nav + outlet
  pages/                Dashboard, Register, Console, Admin
  components/           StatusBox, HashValue, LifecycleStepper, …
  hooks/                useLifecyclePolling
  api/client.ts         Typed API helpers
  types.ts              Response types matching backend models
  lib/                  Formatting and registration phase helpers
```

## API helper

`src/api/client.ts` targets `API_BASE_URL`, parses FastAPI `detail` errors, and exposes typed helpers including registration, ops, agent event list, and admin review. Custom headers (agent / admin keys) are passed per call.

## Configuration

- **API docs** — `{API host}/docs` via `API_DOCS_URL`
- **Blockscout** — `BLOCKSCOUT_TX_BASE` (`https://blockexplorer.dimikog.org/tx/`)
- **GitHub Pages** — Vite `base` is `/veriagent/`; CI builds `frontend/dist/` and deploys that output to `gh-pages` (build artifacts are not kept on `master`)

## GitHub Pages deployment

Deployed automatically on push to **`master`** via [`.github/workflows/deploy-frontend.yml`](../.github/workflows/deploy-frontend.yml). Site: `https://dimikog.github.io/veriagent/`.
