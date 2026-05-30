# Deployment Guide

VeriAgent is developed locally first. This guide covers backend and contract deployment targets available today.

`VeriAgentAnchor` has been deployed and verified on Besu Edu-Net. Backend production VM rollout and Besu end-to-end anchoring validation are still in progress.

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

## Besu Edu-Net contract deployment

`VeriAgentAnchor` is deployed on Besu Edu-Net. Record the live contract address and deployment transaction hash in operator notes (not in git).

### Required environment variables (deploy machine)

| Variable | Purpose |
|----------|---------|
| `BESU_RPC_URL` | Besu Edu-Net JSON-RPC endpoint |
| `BESU_PRIVATE_KEY` | Deployer private key (must remain secret) |

**Security:** Never commit `BESU_PRIVATE_KEY`, `.env` files, or any key material to the repository. Use environment variables or a local gitignored `.env` on the deploy host only.

### Foundry settings (`contracts/foundry.toml`)

Besu deployment uses:

```toml
evm_version = "paris"
optimizer = true
optimizer_runs = 200
```

Solc `0.8.20` is set in the same file.

### Deploy command

`contracts/foundry.toml` defines `[rpc_endpoints]` aliases (`anvil`, `besu`). Export `BESU_RPC_URL` before using `--rpc-url besu`.

From `contracts/`:

```bash
export BESU_RPC_URL="https://rpc.dimikog.org/rpc/"
export BESU_PRIVATE_KEY="0x..."   # never commit this value

forge script script/DeployVeriAgentAnchor.s.sol:DeployVeriAgentAnchor \
  --rpc-url besu \
  --broadcast \
  --private-key "$BESU_PRIVATE_KEY" \
  --legacy \
  --with-gas-price 1000000000
```

You can still pass `--rpc-url "$BESU_RPC_URL"` directly if you prefer not to use the alias.

- `--legacy` — legacy transaction type required for this Besu network configuration.
- `--with-gas-price 1000000000` — `1 gwei`.

After broadcast, note the deployed contract address (placeholder until recorded):

```text
VERIAGENT_ANCHOR_CONTRACT_ADDRESS=0x...
```

### Blockscout verification

Verify `VeriAgentAnchor` on Blockscout with settings that match the deployment artifact:

| Setting | Value |
|---------|--------|
| Compiler | `0.8.20` |
| EVM version | `paris` |
| Optimizer | enabled |
| Optimizer runs | `200` |
| Constructor arguments | none |

Verification for the Besu Edu-Net deployment completed successfully.

## Backend anchoring configuration

When using `POST /audit/batches/{batch_id}/anchor`, set:

| Variable | Purpose |
|----------|---------|
| `VERIAGENT_RPC_URL` | JSON-RPC endpoint (local Anvil or Besu Edu-Net) |
| `VERIAGENT_CHAIN_ID` | Chain ID for transaction signing |
| `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` | Deployed `VeriAgentAnchor` address |
| `VERIAGENT_ANCHOR_PRIVATE_KEY` | Owner key allowed to call `anchorBatch` |

Never commit private keys. Inject them via environment or a secrets manager on the host.

Optional:

| Variable | Purpose |
|----------|---------|
| `VERIAGENT_DB_PATH` | SQLite database file path |
| `VERIAGENT_RECEIPT_SECRET` | HMAC secret for ingestion receipts |

## Typical local anchoring flow (Anvil)

1. Run the backend (`uvicorn app.main:app`).
2. Store events and create a batch via the audit API.
3. Deploy `VeriAgentAnchor` to Anvil and set the four anchoring variables.
4. `POST /audit/batches/{batch_id}/anchor` — stores `tx_hash`, `block_number`, and on-chain metadata in `batch_anchors`.
5. `GET /audit/batches/{batch_id}/anchor` — returns the stored record.

Repeating step 4 returns `already_anchored: true` without submitting another transaction.

## Next step: backend testing against Besu

With the Besu contract live and verified:

1. Point local backend anchoring env vars at Besu (`VERIAGENT_RPC_URL`, `VERIAGENT_CHAIN_ID`, `VERIAGENT_ANCHOR_CONTRACT_ADDRESS`, `VERIAGENT_ANCHOR_PRIVATE_KEY`).
2. Run the usual audit batch flow locally.
3. Call `POST /audit/batches/{batch_id}/anchor` and confirm the transaction on Blockscout.
4. Confirm `GET /audit/batches/{batch_id}/anchor` returns the stored SQLite record.

Backend VM deployment is not done yet; validate locally before promoting to the VM.

## What is not deployed yet

- Backend production VM deployment
- Production VM automation for VeriAgent
- Frontend integration for anchor status
- DID/VC, ZKP, authentication, and OpenTelemetry

Update `backend/app/abi/VeriAgentAnchor.json` when the Solidity contract ABI changes, then redeploy the contract and point `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` at the new deployment.
