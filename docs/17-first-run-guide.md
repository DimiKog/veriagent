# VeriAgent First Run Guide

This guide walks you through a local VeriAgent setup: start the Backend and Frontend, register an agent, submit a signed audit event, and verify the result. If blockchain anchoring is configured, you can also follow the full **Submitted → Batched → Anchored** lifecycle and run offline verification.

**Two supported paths**

| Path | Configure in §1 | Sections you complete |
| --- | --- | --- |
| **Quick local run** | Skip blockchain anchoring | §§1–8, §9 (Submitted only), §10 (basic lookup) |
| **Full end-to-end** | Enable blockchain anchoring | §§1–11 |

**Crypto rule:** the browser never holds an agent private key. DID derivation, ownership proof, credential claim, and event signing are performed only by the VeriAgent CLI (installed from the Python SDK).

**Conventions:** every section states which terminal to use. Each terminal keeps its own working directory after you enter it — stay in that terminal until the guide asks you to switch. Open a new terminal only when the guide explicitly tells you to (Backend in §2, Frontend in §3; the CLI terminal is set up in §1). The first command block in each terminal section shows how to enter that directory; later blocks in the same section assume you are already there.

---

## 1. Prerequisites

Complete this section once. You do not need prior knowledge of VeriAgent — install tools, configure the Backend, and verify the CLI.

### Check required software

```bash
python3 --version   # 3.12+ required for the Backend
node --version      # 20+ required for the Frontend
npm --version
git --version
```

Install or upgrade anything that is missing. Node.js and npm are needed in §3; do not start the Frontend dev server yet.

### Create `backend/.env`

From any terminal, with your working directory at the **repository root** (the directory that contains `backend/`, `frontend/`, and `sdk/`):

```bash
cp backend/.env.example backend/.env
```

Never commit `backend/.env`. The Backend loads it automatically on startup.

### Set three required values

Edit `backend/.env`. Change only these lines:

```bash
VERIAGENT_ADMIN_API_KEY=GENERATE_BELOW
VERIAGENT_RECEIPT_SECRET=GENERATE_BELOW
VERIAGENT_REGISTRATION_ENABLED=true
```

Leave all other values as copied from `.env.example`.

| Variable | Purpose |
| --- | --- |
| `VERIAGENT_ADMIN_API_KEY` | Unlocks the Admin UI (same value you enter on the Admin page) |
| `VERIAGENT_RECEIPT_SECRET` | Signs ingestion receipts for submitted events |
| `VERIAGENT_REGISTRATION_ENABLED` | Enables registration routes (`true` is the `.env.example` default — confirm it) |

Generate secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Paste the first value into `VERIAGENT_ADMIN_API_KEY` and the second into `VERIAGENT_RECEIPT_SECRET`.

### Optional: blockchain anchoring

Skip this for a quick local run. Without anchoring you can register an agent, submit events, use the Console, and look up events on the Dashboard. You cannot complete batching, on-chain anchoring, or the full offline proof-and-anchor workflow. Anchoring API calls return **503** until configured.

For the full path, uncomment and set these in `backend/.env`, then set `VERIAGENT_AUTO_ANCHOR_ENABLED=true`:

- `VERIAGENT_RPC_URL`
- `VERIAGENT_CHAIN_ID`
- `VERIAGENT_ANCHOR_CONTRACT_ADDRESS`
- `VERIAGENT_ANCHOR_PRIVATE_KEY`

You need a reachable JSON-RPC node, matching chain ID, deployed `VeriAgentAnchor` contract, and an authorized signer key. See [05-deployment.md](05-deployment.md) for deployment detail.

### Install and verify the CLI

The Backend and the SDK use **separate Python virtual environments**. Install the CLI now; you will use it in §§4–8 and §11.

**CLI terminal** (first use) — working directory: repository root, then `sdk/python/`:

```bash
cd sdk/python
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
veriagent --help
```

Confirm the help output lists `verify`, `register` and `submit` subcommands. Leave this terminal open; remain in `sdk/python/` with the SDK venv active.

### Pre-flight checklist

Confirm the following, then continue to §2:

- [ ] Python 3.12+, Node 20+, npm, and git are available
- [ ] `backend/.env` exists with generated secrets and `VERIAGENT_REGISTRATION_ENABLED=true`
- [ ] `veriagent --help` works in the CLI terminal
- [ ] Blockchain variables unchanged (quick path) or configured (full path)
- [ ] Frontend dev server not started yet (§3)

---

## 2. Start the Backend

Open a new **Backend terminal** (do not reuse the CLI terminal from §1). Keep it open for the rest of this guide. The API must stay running through §11.

### Install dependencies and start the API

**Backend terminal** (first use) — working directory: repository root, then `backend/`:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Remain in `backend/` with the Backend venv active. Do not close this terminal.

The database is created automatically on first startup. No separate migrate step is required.

If the API starts successfully and `/health` responds as shown below, `backend/.env` has been loaded correctly. If Uvicorn fails to start because of missing configuration or environment variables, stop the server (`Ctrl+C`), return to §1, correct `backend/.env`, and start the Backend again.

### Verify the API

- [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) — confirms the Backend process is up and serving traffic.
- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — opens the interactive OpenAPI UI for exploring Backend routes.
- [http://127.0.0.1:8000/ops/status](http://127.0.0.1:8000/ops/status) — reports auto-anchor settings and the latest batch/anchor run status.

**`/health`** — expected response:

```json
{
  "status": "ok",
  "service": "veriagent",
  "version": "1.0.0-rc.1"
}
```

**`/ops/status`** — expected shape with default `.env.example` (anchoring disabled):

```json
{
  "service": "veriagent",
  "version": "1.0.0-rc.1",
  "auto_anchor_enabled": false,
  "interval_seconds": 300,
  "min_events": 1,
  "scheduler_running": false,
  "last_run_at": null,
  "last_status": "idle",
  "last_batch_id": null,
  "last_anchor_tx": null,
  "last_error": null
}
```

If you enabled anchoring in §1, expect `auto_anchor_enabled: true` and `scheduler_running: true` when chain configuration is complete.

Continue to §3 to start the Frontend.

---

## 3. Start the Frontend

Open a new **Frontend terminal** (do not reuse the Backend or CLI terminal). Working directory: repository root, then `frontend/`:

```bash
cd frontend
npm install
npm run dev
```

Note: `npm install` may report known vulnerabilities in development dependencies. For the current Release Candidate, these are expected and do not prevent the Frontend from running. Continue unless the installation itself fails.

Remain in `frontend/`. Do not close this terminal.

### Three terminals

From §4 onward, three terminals run in parallel:

| Terminal | Directory | Activate | Purpose |
| --- | --- | --- | --- |
| **Backend** | `backend/` | `source .venv/bin/activate` | API (`uvicorn`) — §2 |
| **Frontend** | `frontend/` | — | Dev server (`npm run dev`) — above |
| **CLI** | `sdk/python/` | `source .venv/bin/activate` | `veriagent` commands — §§4–8, 11 |

If you must open a new CLI shell, enter `sdk/python/`, activate the venv, and stay there for all CLI steps.

### Expected URLs

| Mode | URL |
| --- | --- |
| Dev | [http://localhost:5173/veriagent/](http://localhost:5173/veriagent/) |

Vite `base` and React Router basename are both `/veriagent`.

### Available routes

| Path | Page | Role |
| --- | --- | --- |
| `/veriagent/` | Redirect | → Dashboard |
| `/veriagent/dashboard` | Dashboard | Public read-only verification |
| `/veriagent/register` | Register | Create registration request + status poll |
| `/veriagent/console` | Console | Operator view of your agent’s events (API key unlock) |
| `/veriagent/admin` | Admin | Approve/reject registrations (admin key unlock) |

### Before continuing

Confirm the following before starting registration:

- [ ] Backend API is running (`uvicorn` in the Backend terminal, working directory `backend/`)
- [ ] Frontend is available at [http://localhost:5173/veriagent/](http://localhost:5173/veriagent/) (Frontend terminal, working directory `frontend/`)
- [ ] CLI is installed and the SDK venv is active (CLI terminal, working directory `sdk/python/`)
- [ ] All three terminals from above are open and left running

You are now ready to register your first agent.

---

## 4. Register a new agent

Registration spans three surfaces: the **Register** page creates the request, the **CLI** proves ownership and claims credentials, and **Admin** approves.

**CLI terminal** — working directory `sdk/python/`, SDK venv active. Only if you opened a new shell since §1, run `cd sdk/python && source .venv/bin/activate` once, then stay in this terminal.

**Time limit:** challenges expire after `VERIAGENT_REGISTRATION_CHALLENGE_TTL_MINUTES` (default **15**). Complete prove → Admin approval → claim before expiry, or increase the TTL in `backend/.env` and restart the Backend.

### Generate an agent keypair

Stay in `sdk/python/` with the SDK venv active. These commands create a private credential directory in your home directory, outside the repository. You do not need to `cd` into it:

```bash
mkdir -p ~/.veriagent
chmod 700 ~/.veriagent
```

Create a private key (32-byte Ed25519 seed, base64). The command writes directly to `~/.veriagent/agent.key`. Do not commit this file or paste it into the UI:

```bash
python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; import base64; print(base64.b64encode(Ed25519PrivateKey.generate().private_bytes_raw()).decode())" > ~/.veriagent/agent.key
chmod 600 ~/.veriagent/agent.key
```

Derive the public identity fields for the Register form:

```bash
python3 - <<'PY'
from pathlib import Path
from veriagent import derive_agent_identity
pk = Path.home().joinpath(".veriagent", "agent.key").read_text().strip()
public_key, agent_did, verification_method = derive_agent_identity(pk)
print("public_key:", public_key)
print("agent_did:", agent_did)
print("verification_method:", verification_method)
PY
```

Save the three printed values for the form. Keep `~/.veriagent/agent.key` on disk.


### Fill the registration form

**Browser** — Frontend dev server from §3 (no terminal commands):

1. Open [http://localhost:5173/veriagent/register](http://localhost:5173/veriagent/register).
2. Complete the form:

   | Field | Source |
   | --- | --- |
   | Agent name | Your choice |
   | Agent type | e.g. `llm-agent` |
   | Agent DID | `agent_did` from derivation |
   | Verification method | `verification_method` from derivation |
   | Public key | `public_key` from derivation |
   | Organization name | Your choice |
   | Contact email | Your choice |
   | Use case summary | Short description |
   | Description | Optional |

3. Submit. The page shows `request_id`, `challenge_expires_at`, and challenge metadata.

### Save the `request_id`

Copy `request_id` from the Register page badge or success JSON. You need the same id for prove and claim in §§5 and 7.

### Registration status reference

The Register page polls status every ~4 seconds. Backend values: `pending` | `approved` | `rejected` | `expired`.

| UI phase | Meaning |
| --- | --- |
| Requested / Proof required | Challenge issued; proof not yet submitted |
| Pending approval | Proof accepted; waiting for Admin |
| Approved | Admin approved; credentials available to claim once |
| Credentials claimed | API key already retrieved |
| Rejected / Expired | Terminal — start a new request |

Reloading the Register page does not resume an existing `request_id`. Keep the tab open through approval, or continue with the saved id in the CLI.

Continue to §5 to prove ownership.

---

## 5. Prove agent ownership

**CLI terminal** — working directory `sdk/python/`, SDK venv active.

Replace uppercase placeholders such as `REQUEST_ID_HERE` with the actual value. Do not add `<` or `>`.

```bash
veriagent register prove \
  --request-id REQUEST_ID_HERE \
  --api-base-url http://127.0.0.1:8000 \
  --private-key-file ~/.veriagent/agent.key
```

The CLI loads your private key locally, fetches the challenge `proof_payload`, signs it with Ed25519, and submits `POST /registration/requests/{request_id}/proof`. Only the signature is sent over the network.

**Expected result:** status remains `pending` with `proof_submitted_at` set. The Register page moves to **Pending approval**.

Continue to §6 for Admin approval.

---

## 6. Admin approval

**Browser** — Frontend dev server from §3 (no terminal commands):

1. Open [http://localhost:5173/veriagent/admin](http://localhost:5173/veriagent/admin).
2. Enter your `VERIAGENT_ADMIN_API_KEY` value and unlock.
3. Review the pending queue. If the request was already visible before you ran `register prove`, click **Refresh queue** afterward — the Admin page can keep a stale queue until you refresh.
4. Confirm the request now shows that proof has been submitted. **Approve** is enabled only then.
5. Optionally add review notes, then **Approve**.

**After approval:**

- Request status becomes `approved` and an active agent record is created.
- A one-time API key is prepared server-side. The Admin response includes a `retrieval_token` (`vrt_…`) — not the agent API key.
- The Register page shows **Approved** and the claim CLI snippet while `credentials_available` is true.

Approve before `challenge_expires_at`. Pending requests expire when the challenge TTL elapses.

Continue to §7 to claim credentials.

---

## 7. Claim credentials

**CLI terminal** — working directory `sdk/python/`, SDK venv active:

```bash
veriagent register claim \
  --request-id REQUEST_ID_HERE \
  --api-base-url http://127.0.0.1:8000 \
  --private-key-file ~/.veriagent/agent.key \
  --output-key-file ~/.veriagent/agent.api_key
```

Optional: `--retrieval-token RETRIEVAL_TOKEN_HERE` from the Admin approve response.

The CLI signs a claim payload locally, calls `POST /registration/requests/{request_id}/credentials`, and writes the one-time API key (`va_agent_…`) to `~/.veriagent/agent.api_key`.

**Storage:** keep `~/.veriagent/` at mode `700` (directory) and `600` (files). Never commit credentials or paste the API key into Dashboard or Register. A second claim fails after credentials are consumed.

Continue to §8 to submit your first audit event.

---

## 8. Submit the first audit event

**CLI terminal** — working directory `sdk/python/`, SDK venv active:

```bash
export VERIAGENT_API_KEY="$(cat ~/.veriagent/agent.api_key)"

veriagent submit \
  --api-base-url http://127.0.0.1:8000 \
  --api-key "$VERIAGENT_API_KEY" \
  --private-key-file ~/.veriagent/agent.key \
  --event-id "event-first-run-001" \
  --task-id "task-001" \
  --model-name "demo-model" \
  --tool-calls search,calculator \
  --input-hash "sha256:input123" \
  --output-hash "sha256:output456" \
  --policy-version "policy-v0.1" \
  --output-event ~/.veriagent/event.json
```

Alternatively, pass `--event ~/.veriagent/event-unsigned.json` for unsigned fields; the CLI adds `agent_id`, `signature`, and `verification_method`. Save the signed output with `--output-event` for §11.

**Expected response:**

```json
{
  "event_id": "event-first-run-001",
  "event_hash": "<64 hex>",
  "created_at": "<ISO timestamp>",
  "receipt": {
    "event_id": "event-first-run-001",
    "event_hash": "<64 hex>",
    "created_at": "<ISO timestamp>",
    "signature": "<hmac hex>",
    "algorithm": "HMAC-SHA256"
  }
}
```

Save `event_id` and `~/.veriagent/event.json` for §11.

Continue to §9 to observe the event lifecycle.

---

## 9. Observe the event lifecycle

> **Without anchoring (quick path):** events remain at **Submitted**. You can confirm them in the Console and look them up on the Dashboard. Skip to §10 for basic lookup, or configure anchoring in §1 and restart the Backend to continue below.

> **With anchoring (full path):** ensure §1 anchoring variables are set and `VERIAGENT_AUTO_ANCHOR_ENABLED=true`. Restart the Backend if you changed `.env` after §2.

**Browser** — Frontend dev server from §3 (no terminal commands):

1. Open [http://localhost:5173/veriagent/console](http://localhost:5173/veriagent/console).
2. Unlock with your agent API key.
3. Select your event and refresh the lifecycle view.

| State | Meaning |
| --- | --- |
| **Submitted** | Event stored; not yet in a Merkle batch (`batched=false`) |
| **Batched** | Included in a batch; `batch_id` and `merkle_root` set (`batched=true`, `anchored=false`) |
| **Anchored** | Merkle root on-chain; `tx_hash`, `block_number`, `chain_id`, `anchored_at` present |

With auto-anchor enabled, the scheduler batches unbatched events and anchors them. Monitor `/ops/status` (or the Admin ops panel) for `last_status`, `last_batch_id`, and `last_anchor_tx`.

Use **Refresh lifecycle** in the Console while waiting. Once **Anchored**, continue to §10 on the Dashboard to download proof and anchor JSON for offline verification.

Continue to §10 for public verification on the Dashboard.

---

## 10. Public verification

**Browser** — Frontend dev server from §3 (no terminal commands):

The Dashboard is the recommended place to **inspect and download** evidence for offline verification (§11). It is read-only, needs no credentials, and matches the public verification model. The Console (§9) exposes the same evidence actions for operators, but does not include download buttons — use the Dashboard when preparing local files for `veriagent verify`.

1. Open [http://localhost:5173/veriagent/dashboard](http://localhost:5173/veriagent/dashboard).
2. Enter your `event_id` (`event-first-run-001`) and wait until lifecycle shows **Anchored** (full path) or confirm **Submitted** (quick path). Use **Refresh lifecycle** while waiting; `batch_id` fills in automatically once batched.
3. When **Anchored**, use the evidence actions in order:

   | Action | Purpose |
   | --- | --- |
   | **Lookup batch** | Batch metadata including Merkle root (optional sanity check) |
   | **Get & verify proof** | Fetches the Merkle inclusion proof from the backend and runs a server-side verify |
   | **Get anchor record** | Fetches the on-chain anchor record for the batch |

4. After each successful fetch above, **Download proof JSON** and **Download anchor JSON** appear below the action buttons. Use them to save the exact API responses:

   - Click **Download proof JSON** → save/move the file to `~/.veriagent/proof.json`
   - Click **Download anchor JSON** → save/move the file to `~/.veriagent/anchor.json`

   Your browser may save to `~/Downloads/proof.json` and `~/Downloads/anchor.json` first. Move or copy them into `~/.veriagent/` with those exact names.

5. Confirm you already have the signed event from §8:

   ```bash
   ls -l ~/.veriagent/event.json
   ```

   That file was created by `veriagent submit --output-event ~/.veriagent/event.json` in §8.

The Dashboard does not hold private keys. Downloading evidence JSON is a read-only operation — it does not modify audit records.

When a `tx_hash` is present, the UI links to the configured block explorer.

On the full path, continue to §11 for independent offline verification using the three local JSON files.

---

## 11. Independent verification

Full path only. Requires a batched and anchored event from §9 and evidence files from §10.

Prove the evidence locally without trusting the VeriAgent server for cryptographic checks. The offline verifier **does not fetch** missing files — you must supply all three JSON paths yourself.

### Three local files

| File | Created in | Contents |
| --- | --- | --- |
| `~/.veriagent/event.json` | §8 (`veriagent submit --output-event`) | Signed audit event |
| `~/.veriagent/proof.json` | §10 (**Download proof JSON** on Dashboard) | Merkle inclusion proof (`GET /audit/batches/{batch_id}/proof/{event_id}` response) |
| `~/.veriagent/anchor.json` | §10 (**Download anchor JSON** on Dashboard) | Anchor record (`GET /audit/batches/{batch_id}/anchor` response) |

**Sequence:**

1. §8 — `veriagent submit --output-event ~/.veriagent/event.json` creates `event.json`.
2. §9 — wait until the event is **Batched** then **Anchored**.
3. §10 — on the Dashboard, run **Get & verify proof** then **Get anchor record**, then use **Download proof JSON** and **Download anchor JSON**. Save/move the downloads to `~/.veriagent/proof.json` and `~/.veriagent/anchor.json`.
4. Pre-check — all three files must exist before continuing:

   ```bash
   ls -l ~/.veriagent/event.json ~/.veriagent/proof.json ~/.veriagent/anchor.json
   ```

   If any file is missing, return to §10 (or §8 for `event.json`). The verifier will fail with `Unable to read file` when a path is absent.

### Fully offline CLI (recommended)

Uses only local files — no live API calls:

**CLI terminal** — working directory `sdk/python/`, SDK venv active:

```bash
veriagent verify \
  --event ~/.veriagent/event.json \
  --proof ~/.veriagent/proof.json \
  --anchor ~/.veriagent/anchor.json
```

Expected output starts with `PASS` and lists checks for event hash, Ed25519 signature, Merkle inclusion, and anchor metadata. Exit codes: `0` PASS, `1` FAIL, `2` malformed input.

### API-assisted CLI (checks still local)

Alternative when you have `event.json` but not the proof/anchor files. The CLI **fetches** proof and anchor JSON from the backend, then runs the same local verifier — it does not write `proof.json` or `anchor.json` for you:

**CLI terminal** — working directory `sdk/python/`, SDK venv active:

```bash
veriagent verify \
  --event ~/.veriagent/event.json \
  --api-base-url http://127.0.0.1:8000 \
  --batch-id BATCH_ID_HERE \
  --event-id event-first-run-001
```

Replace `BATCH_ID_HERE` with the `batch_id` from the Dashboard lifecycle view. Fetched JSON is input to the local verifier only; the CLI does not re-query the chain via RPC (`getBatch`).

**Summary**

| Method | Needs network | Local files required |
| --- | --- | --- |
| Dashboard inspect + download (§10) | Yes (read-only) | Saves `proof.json`, `anchor.json` for offline use |
| Fully offline verify | No | All three: `event.json`, `proof.json`, `anchor.json` |
| API-assisted CLI verify | Yes (fetch proof/anchor) | `event.json` only |

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Registration routes **404** | `VERIAGENT_REGISTRATION_ENABLED` not truthy | Set `true` in `backend/.env` and restart the Backend |
| Frontend talks to wrong API | `VITE_API_BASE_URL` override or remote build | Unset `VITE_API_BASE_URL` for local default `http://127.0.0.1:8000`, or set it explicitly |
| Env vars ignored | `.env` missing or wrong working directory | Ensure `backend/.env` exists beside `requirements.txt`; restart Uvicorn; exported vars override `.env` |
| **Registration expired** | Challenge TTL elapsed (including while waiting for admin) | Increase `VERIAGENT_REGISTRATION_CHALLENGE_TTL_MINUTES`, create a new request, prove promptly |
| **Proof rejected** (403) | Wrong private key, stale/wrong payload, DID mismatch | Use the same `~/.veriagent/agent.key` that produced the form DID; fetch fresh `proof_payload` |
| **Approval missing / Approve disabled** | Proof not submitted, or request expired | Run `register prove`; approve before expiry |
| **Credentials already claimed** | One-time claim consumed | Use stored `~/.veriagent/agent.api_key`; start a new registration only if you lost it and ops re-register |
| **Anchoring disabled** | Auto-anchor off or chain env incomplete | Enable `VERIAGENT_AUTO_ANCHOR_ENABLED` and set RPC/chain/contract/key; check `/ops/status` |
| **Scheduler stopped** | Process restarted with auto-anchor false, or task crashed | Confirm env, restart API, inspect `last_error` on `/ops/status` |
| **Invalid signature** on submit | Event fields changed after signing, wrong key, inactive agent | Resubmit via CLI/SDK with matching key and active agent |
| **Event not found** | Wrong id, different DB, or never stored | Confirm submit response; check Console list with the same API key / same backend DB |
| Admin unlock fails | Wrong admin key | Match `VERIAGENT_ADMIN_API_KEY` exactly |
| Claim fails after approve | DID/key mismatch or missing approval | Confirm Register status is Approved; use the registration private key |

---

## 13. Architecture summary

VeriAgent separates **custody**, **orchestration**, and **verification**:

| Component | Responsibility |
| --- | --- |
| **CLI / SDK** | Owns the agent private key. Derives DID, proves registration, claims the API key, signs audit events, runs offline verify. |
| **Backend** | Stores registration and audit data, verifies signatures, batches events, anchors Merkle roots, issues one-time credentials, exposes public evidence reads and ops status. |
| **Console** | Operator portal to list your submitted events and watch Submitted → Batched → Anchored. Does not sign. |
| **Dashboard** | Public, read-only evidence viewer. Platform-assisted verification for auditors. |
| **Admin** | Human review of registration requests; approve/reject. Never generates agent keypairs. |
| **Offline verifier** | Recomputes hash, signature, Merkle inclusion, and anchor metadata locally. |

**Invariants:**

- The browser never owns the agent private key.
- All agent cryptographic operations run in the CLI / SDK.
- The Dashboard is read-only by design.
- Offline verification is the final step for independent assurance.

For architecture diagrams and auth detail, see [16-production-architecture.md](./16-production-architecture.md). For verifier detail, see [15-independent-verifier.md](./15-independent-verifier.md).
