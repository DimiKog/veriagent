# VeriAgent

**A verifiable audit commitment layer for AI-agent actions.**

VeriAgent records structured audit events from AI agents, commits them with canonical hashing, batches them into Merkle trees, and anchors batch roots on Besu. A public dashboard walks through the full workflow end to end.

## Public demo (v0.9.3)

| Resource | URL |
| --- | --- |
| Frontend dashboard | https://dimikog.github.io/veriagent/ |
| Public API | https://veriagent.dimikog.org |
| API docs (Swagger) | https://veriagent.dimikog.org/docs |
| Health check | https://veriagent.dimikog.org/health |
| Block explorer | https://blockexplorer.dimikog.org/ |

The `VeriAgentAnchor` contract is deployed and verified on **Besu Edu-Net**. Contract address and deployment notes are recorded in [docs/02-devlog.md](docs/02-devlog.md) (`0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A`). Block explorer (Blockscout): `https://blockexplorer.dimikog.org/` — transaction links in the dashboard use `https://blockexplorer.dimikog.org/tx/{hash}` (see `frontend/src/api/client.ts`).

## What it does

VeriAgent provides a prototype audit pipeline for AI-agent activity:

- Creates structured AI-agent audit events
- Canonicalizes JSON using RFC 8785 / JCS
- Computes SHA-256 event commitments
- Stores events locally in SQLite
- Returns signed HMAC-SHA256 ingestion receipts
- Requires Ed25519-signed audit events from registered agents (v0.9B)
- Registers agents by real Ed25519 `did:key` identifiers with admin-protected onboarding (v0.9.2)
- Restricts Merkle batch creation and on-chain anchoring to admin API key holders (v0.9.6)
- Signs audit events in the browser for demo use via the dashboard (v0.9.3)
- Batches event hashes into Merkle trees
- Generates and verifies Merkle inclusion proofs
- Anchors Merkle roots on Besu via `VeriAgentAnchor`
- Exposes a public dashboard for the workflow

See [docs/03-api.md](docs/03-api.md) for endpoint details.

## Trust model and limitations

This is a **research prototype**, not a production compliance product.

- The **backend operator is trusted** in this demo. The API stores events and submits anchor transactions.
- **SQLite is mutable** before anchoring. Local records can be changed until a batch root is anchored on chain.
- **Blockchain anchoring** provides a timestamped, public commitment *after* anchoring. It does not prove the underlying agent action occurred.
- **Event submission requires a registered agent.** `POST /audit/events` accepts events only from active agents that present a valid `X-VeriAgent-API-Key`, set `agent_id` to their registered DID, and sign the unsigned canonical event payload with their registered Ed25519 key. Public read and verification endpoints remain open.
- **This is not an EU AI Act compliance product.** It demonstrates technical building blocks only.

## Architecture

```text
AI Agent / App
      |
      v
VeriAgent API  (FastAPI, SQLite)
      |
      +--> SQLite (events, batches, anchor records)
      |
      v
Merkle batch root
      |
      v
Besu Anchor Contract  (VeriAgentAnchor)
      |
      +--> Block explorer (blockexplorer.dimikog.org)
      |
      v
Public Dashboard  (GitHub Pages)
```

## Local development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export VERIAGENT_RECEIPT_SECRET="replace-with-a-long-random-secret"
export VERIAGENT_ADMIN_API_KEY="replace-with-a-long-random-admin-key"
python -m pytest
uvicorn app.main:app --reload
```

Local API docs: http://127.0.0.1:8000/docs

To generate a signed sample event body for manual testing (emits a real `did:key:z...` agent identity):

```bash
python scripts/sign_demo_event.py
```

Agent DIDs use spec-compliant Ed25519 `did:key` encoding (`did:key:z...` with multibase public key). The legacy `did:key:demo:<sha256>` format is deprecated. `did:key` does not support key rotation by itself; agent revocation and status remain in VeriAgent's internal registry.

See [docs/03-api.md](docs/03-api.md) for the signing boundary (`signature` and `verification_method` are excluded from the canonical payload).

For local anchoring against Anvil or Besu, set `VERIAGENT_RPC_URL`, `VERIAGENT_CHAIN_ID`, `VERIAGENT_ANCHOR_CONTRACT_ADDRESS`, and `VERIAGENT_ANCHOR_PRIVATE_KEY`. See [docs/05-deployment.md](docs/05-deployment.md).

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173/veriagent/
npm run build
npm run preview
```

Local dev proxies API calls through Vite; the GitHub Pages build calls the public API directly. See [frontend/README.md](frontend/README.md).

### Contracts (optional)

Foundry tests and local Anvil deployment are documented in [docs/05-deployment.md](docs/05-deployment.md). The backend uses the committed ABI at `backend/app/abi/VeriAgentAnchor.json` and does not require Foundry at runtime.

## Deployment

| Component | How it runs |
| --- | --- |
| Backend | Linux VM — systemd service, Nginx reverse proxy, HTTPS at `veriagent.dimikog.org` |
| Frontend | GitHub Pages — automatic deploy from `master` to https://dimikog.github.io/veriagent/ |
| Secrets | Private keys and tokens only via environment variables or gitignored `.env` files on the host |

Operational details: [docs/05-deployment.md](docs/05-deployment.md). Development history: [docs/02-devlog.md](docs/02-devlog.md).

## Security note

- **Never commit** `.env`, private keys, API tokens, or deployer credentials.
- **Never commit** `backend/data/veriagent.db`, virtualenvs, or Foundry broadcast artifacts with sensitive material.
- The **frontend never handles admin keys, wallet private keys, or anchor signing secrets**. On-chain anchoring is performed server-side by the backend and requires `X-VeriAgent-Admin-Key` on `POST /audit/batches` and `POST /audit/batches/{batch_id}/anchor`. The dashboard accepts a **demo agent private key** in memory only (not persisted) to sign audit events in the browser — do not paste production signing keys into the UI.

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/03-api.md](docs/03-api.md) | API reference |
| [docs/04-testing.md](docs/04-testing.md) | Testing and manual verification flow |
| [docs/05-deployment.md](docs/05-deployment.md) | Besu, VM, CORS, and GitHub Pages deployment |
| [docs/02-devlog.md](docs/02-devlog.md) | Phase-by-phase development log |
| [frontend/README.md](frontend/README.md) | Frontend setup and Pages workflow |
