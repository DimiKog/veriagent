# VeriAgent

VeriAgent is a verifiable audit commitment layer for AI-agent actions.

It records structured AI-agent audit events, canonicalizes them using RFC 8785 / JCS, computes SHA-256 commitments, stores them locally, and verifies submitted events against stored commitments.

## Current MVP Status

VeriAgent currently supports:

- RFC 8785 / JCS canonicalization of AI-agent audit events
- SHA-256 event commitments
- Hash-only endpoint (`POST /audit/hash`) without persistence
- SQLite-backed local event storage
- Duplicate event detection
- Audit event retrieval
- Verification of submitted events against stored commitments
- Tamper detection
- HMAC-SHA256 signed ingestion receipts on event storage
- Local Merkle batching over stored event hashes
- API-generated Merkle inclusion proofs for stored batch events
- On-chain batch anchoring API with SQLite anchor transaction records

See [docs/03-api.md](docs/03-api.md) for endpoint details and [docs/04-testing.md](docs/04-testing.md) for the test guide.

## Local Contract Deployment (Anvil)

From the project root, run Foundry tests and deploy `VeriAgentAnchor` to a local Anvil node.

Terminal 1 — start Anvil:

```bash
anvil
```

Terminal 2 — test and deploy (uses Anvil’s unlocked default accounts; do not commit private keys):

```bash
cd contracts
forge test
forge script script/DeployVeriAgentAnchor.s.sol:DeployVeriAgentAnchor \
  --rpc-url http://127.0.0.1:8545 \
  --broadcast \
  --unlocked \
  --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
```

`0xf39F…2266` is Anvil’s first default unlocked account (local development only).

To sign with a key from your environment instead of `--unlocked`:

```bash
forge script script/DeployVeriAgentAnchor.s.sol:DeployVeriAgentAnchor \
  --rpc-url http://127.0.0.1:8545 \
  --broadcast \
  --private-key "$PRIVATE_KEY"
```

The script prints the deployed contract address and owner. Deployment artifacts are written under `contracts/broadcast/` (gitignored).

## Backend contract ABI

The FastAPI backend loads `VeriAgentAnchor` from a committed ABI file at `backend/app/abi/VeriAgentAnchor.json`. Runtime does **not** read `contracts/out/`; a backend-only VM does not need Foundry installed.

When you change `contracts/src/VeriAgentAnchor.sol`, rebuild with Foundry and refresh the committed ABI (for example, copy the `abi` array from `contracts/out/VeriAgentAnchor.sol/VeriAgentAnchor.json` into `backend/app/abi/VeriAgentAnchor.json`).

## Local Run

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export VERIAGENT_RECEIPT_SECRET="replace-with-a-long-random-secret"
python -m pytest
uvicorn app.main:app --reload
```

Backend tests and anchoring use `backend/app/abi/VeriAgentAnchor.json` only; no `forge build` is required on the backend VM.

For local-only runs you may omit `VERIAGENT_RECEIPT_SECRET`; the backend uses a clearly marked development fallback secret.

Open the API documentation at:

```text
http://127.0.0.1:8000/docs
```

## Manual Verification Flow

1. Store an event using `POST /audit/events` and save the returned `receipt`.
2. Retrieve it using `GET /audit/events/{event_id}`.
3. Verify the receipt signature matches `event_id`, `event_hash`, and `created_at`.
4. Verify the same event using `POST /audit/verify`.
5. Modify one field, such as `output_hash`, and verify again.
6. Create a Merkle batch with `POST /audit/batches`.
7. Generate an inclusion proof using `GET /audit/batches/{batch_id}/proof/{event_id}`.
8. Verify inclusion with `POST /audit/merkle/verify` using the returned batch root and proof.
9. With Anvil running and anchoring env vars set, anchor the batch with `POST /audit/batches/{batch_id}/anchor`.
10. Retrieve the stored anchor record with `GET /audit/batches/{batch_id}/anchor`.

Expected result:

- Valid receipt signature after store
- Unchanged event: `verified: true`
- Modified event: `verified: false`
- Valid Merkle proof: `verified: true`
- Tampered Merkle proof: `verified: false`
- Second `POST .../anchor` on the same batch: `already_anchored: true` and no new transaction

### Anchoring environment variables

For `POST /audit/batches/{batch_id}/anchor`:

```bash
export VERIAGENT_RPC_URL="http://127.0.0.1:8545"
export VERIAGENT_CHAIN_ID="31337"
export VERIAGENT_ANCHOR_CONTRACT_ADDRESS="0x..."
export VERIAGENT_ANCHOR_PRIVATE_KEY="0x..."
```

The backend uses `backend/app/abi/VeriAgentAnchor.json` at runtime. It does not read `contracts/out/`.

See [docs/05-deployment.md](docs/05-deployment.md) for deployment notes.

## Development Workflow

Local development is the source of truth. The VM is used only as a deployment target.

Recommended workflow:

1. Develop locally.
2. Run tests locally.
3. Commit and push to GitHub.
4. Pull the latest version on the VM.
5. Install or update dependencies.
6. Run tests on the VM.
7. Restart the backend service.

## Commit Checklist

Before committing, run:

```bash
git status
```

Do not commit:

- `backend/.venv/`
- `backend/data/veriagent.db`
- `.env`
- `__pycache__/`
- `.pytest_cache/`

Then commit and push:

```bash
git add .
git status
git commit -m "Your message here"
git push
```
