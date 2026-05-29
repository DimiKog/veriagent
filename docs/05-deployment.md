# Deployment Guide

VeriAgent is developed locally first. This guide covers backend and contract deployment targets available today. Besu Edu-Net and production VM rollout are not part of the current MVP.

## Backend-only deployment (no Foundry)

The FastAPI backend can run on a host with Python 3.12+ without installing Foundry.

Requirements:

- `backend/requirements.txt` installed in a virtualenv
- `VERIAGENT_RECEIPT_SECRET` set for non-development use
- SQLite data directory writable (`backend/data/` by default, or `VERIAGENT_DB_PATH`)
- Committed contract ABI at `backend/app/abi/VeriAgentAnchor.json`

The backend does **not** read `contracts/out/` at runtime.

## Local contract deployment (Anvil)

Use Foundry on a developer machine to test the anchor contract:

1. `cd contracts && forge test`
2. Start `anvil`
3. Deploy with `forge script` (see root [README.md](../README.md))

Record the deployed contract address for backend anchoring.

## Backend anchoring configuration

When using `POST /audit/batches/{batch_id}/anchor`, set:

| Variable | Purpose |
|----------|---------|
| `VERIAGENT_RPC_URL` | JSON-RPC endpoint (local Anvil or future Besu node) |
| `VERIAGENT_CHAIN_ID` | Chain ID for transaction signing |
| `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` | Deployed `VeriAgentAnchor` address |
| `VERIAGENT_ANCHOR_PRIVATE_KEY` | Owner key allowed to call `anchorBatch` |

Never commit private keys. Inject them via environment or a secrets manager on the host.

Optional:

| Variable | Purpose |
|----------|---------|
| `VERIAGENT_DB_PATH` | SQLite database file path |
| `VERIAGENT_RECEIPT_SECRET` | HMAC secret for ingestion receipts |

## Typical local anchoring flow

1. Run the backend (`uvicorn app.main:app`).
2. Store events and create a batch via the audit API.
3. Deploy `VeriAgentAnchor` to Anvil and set the four anchoring variables.
4. `POST /audit/batches/{batch_id}/anchor` — stores `tx_hash`, `block_number`, and on-chain metadata in `batch_anchors`.
5. `GET /audit/batches/{batch_id}/anchor` — returns the stored record.

Repeating step 4 returns `already_anchored: true` without submitting another transaction.

## What is not deployed yet

- Hyperledger Besu Edu-Net anchoring
- Production VM automation for VeriAgent
- Frontend integration for anchor status
- DID/VC, ZKP, authentication, and OpenTelemetry

Update `backend/app/abi/VeriAgentAnchor.json` when the Solidity contract ABI changes, then redeploy the contract and point `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` at the new deployment.
