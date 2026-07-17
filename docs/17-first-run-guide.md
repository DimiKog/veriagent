# VeriAgent First Run Guide

This guide walks a new developer through installing VeriAgent, running the backend and frontend, completing agent registration, submitting a signed audit event, watching it batch and anchor, and independently verifying the evidence.

**Crypto rule:** the browser never holds an agent private key. DID derivation, ownership proof, credential claim, and event signing are performed only by the official Python SDK / CLI.

**Assumed layout:** commands below are relative to the repository root unless noted.

---

## 1. Prerequisites

### Runtime

| Requirement | Version / notes |
| --- | --- |
| Python | **3.12+** for the backend (SDK alone allows ≥3.11) |
| Node.js | **20+** (current LTS) and npm |
| OS tools | `git`, a shell (`bash` / `zsh`) |

### Backend dependencies

Installed from `backend/requirements.txt` (FastAPI, Uvicorn, cryptography, web3, jcs, …). No separate migrate CLI is required.

### SDK / CLI

Install the editable package under `sdk/python` so the `veriagent` console command is available (prove, claim, submit, verify).

### Environment variables

The API reads configuration from the **process environment**. Local and production use the same loader:

1. Copy `backend/.env.example` → `backend/.env` and edit values (never commit `.env`).
2. On startup, the API loads `backend/.env` if present.
3. Variables already set in the process environment (shell export, systemd `EnvironmentFile`, container env) take precedence over `.env`.

Details: [05-deployment.md](05-deployment.md#how-configuration-is-loaded-local-and-production).

| Variable | Required for | Purpose |
| --- | --- | --- |
| `VERIAGENT_ADMIN_API_KEY` | Admin UI / admin routes | Value sent as `X-VeriAgent-Admin-Key` |
| `VERIAGENT_RECEIPT_SECRET` | Production-like receipts | HMAC-SHA256 ingestion receipts (dev has a fallback if unset) |
| `VERIAGENT_REGISTRATION_ENABLED` | Public registration | Set to `true` (or `1` / `yes` / `on`) or registration routes return **404** |
| `VERIAGENT_REGISTRATION_CHALLENGE_TTL_MINUTES` | Registration | Challenge / pending window (default **15**). Pending requests (including proved-but-unapproved) expire when this elapses |
| `VERIAGENT_DB_PATH` | Optional | SQLite path (default `backend/data/veriagent.db`) |
| `VERIAGENT_AUTO_ANCHOR_ENABLED` | Auto batch + anchor | `true` to start the in-process scheduler |
| `VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS` | Auto anchor | Default `300` |
| `VERIAGENT_AUTO_ANCHOR_MIN_EVENTS` | Auto anchor | Default `1` |
| `VERIAGENT_RPC_URL` | Anchoring | JSON-RPC endpoint |
| `VERIAGENT_CHAIN_ID` | Anchoring | e.g. `424242` (Besu Edu-Net) |
| `VERIAGENT_ANCHOR_CONTRACT_ADDRESS` | Anchoring | Deployed `VeriAgentAnchor` |
| `VERIAGENT_ANCHOR_PRIVATE_KEY` | Anchoring | Signer allowed to call `anchorBatch` |

### Blockchain node (when anchoring is enabled)

You need a reachable JSON-RPC node, a matching chain ID, the `VeriAgentAnchor` contract address, and a funded/authorized owner key for `anchorBatch`. Foundry is **not** required on the API host at runtime.

Without these four anchoring variables, the rest of the stack (registration, submit, Console/Dashboard reads) still works; anchoring returns **503** until configured.

### Admin API key

Choose a long random string and set `VERIAGENT_ADMIN_API_KEY`. You will paste the same value into the Admin page unlock field.

### Registration enabled flag

For this guide:

```bash
export VERIAGENT_REGISTRATION_ENABLED=true
```

### Frontend → local API

Local `npm run dev` calls `http://127.0.0.1:8000` by default. Override with `VITE_API_BASE_URL` only if you need a different host (for example production). CLI snippets in the UI use the same absolute base.

---

## 2. Start the backend

### Install dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Initialize the database

No separate migrate step. On startup, the FastAPI lifespan calls `init_db()`, which creates SQLite tables under `backend/data/` (or `VERIAGENT_DB_PATH`) and applies light column migrations.

### Configure environment variables

Copy the example file and edit secrets:

```bash
cd backend
cp .env.example .env
# edit VERIAGENT_ADMIN_API_KEY, VERIAGENT_RECEIPT_SECRET, registration, and optional anchoring
```

Minimum for this guide (already reflected in `.env.example` defaults you can tighten):

- `VERIAGENT_ADMIN_API_KEY` — long random string  
- `VERIAGENT_RECEIPT_SECRET` — long random string  
- `VERIAGENT_REGISTRATION_ENABLED=true`  
- Optionally raise `VERIAGENT_REGISTRATION_CHALLENGE_TTL_MINUTES` for a slower walkthrough  
- Optionally enable auto-anchor and set blockchain variables if you want on-chain anchors  

If you prefer not to use a `.env` file, export the same variables in the Uvicorn shell instead.

### Start the API

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- OpenAPI UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Verify `/health`

Open [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) in a browser, or use any HTTP client. Expected JSON:

```json
{
  "status": "ok",
  "service": "veriagent",
  "version": "1.0.0-rc.1"
}
```

### Verify `/ops/status`

Open [http://127.0.0.1:8000/ops/status](http://127.0.0.1:8000/ops/status). Expected shape (values depend on your env):

```json
{
  "service": "veriagent",
  "version": "1.0.0-rc.1",
  "auto_anchor_enabled": true,
  "interval_seconds": 60,
  "min_events": 1,
  "scheduler_running": true,
  "last_run_at": null,
  "last_status": "idle",
  "last_batch_id": null,
  "last_anchor_tx": null,
  "last_error": null
}
```

If `VERIAGENT_AUTO_ANCHOR_ENABLED` is unset/false, expect `auto_anchor_enabled: false` and `scheduler_running: false`. `last_status` may later be `idle`, `no_events`, `below_threshold`, `batch_created`, `anchor_succeeded`, or `anchor_failed`.

---

## 3. Start the frontend

### Install dependencies

```bash
cd frontend
npm install
```

### Run the SPA against the local API

```bash
cd frontend
npm run dev
```

The SPA uses `http://127.0.0.1:8000` by default in development. No source edits required.

### Expected URLs

| Mode | URL |
| --- | --- |
| Dev | [http://localhost:5173/veriagent/](http://localhost:5173/veriagent/) |
| Preview (after build) | [http://localhost:4173/veriagent/](http://localhost:4173/veriagent/) |

Vite `base` and React Router basename are both `/veriagent`.

### Available routes

| Path | Page | Role |
| --- | --- | --- |
| `/veriagent/` | Redirect | → Dashboard |
| `/veriagent/dashboard` | Dashboard | Public read-only verification |
| `/veriagent/register` | Register | Create registration request + status poll |
| `/veriagent/console` | Console | Operator view of your agent’s events (API key unlock) |
| `/veriagent/admin` | Admin | Approve/reject registrations (admin key unlock) |

---

## 4. Register a new agent

Registration is a multi-surface workflow: **Register page** creates the public request; **CLI** proves ownership and later claims credentials; **Admin** approves.

### Generate an agent keypair (SDK only — never in the browser)

Install the CLI first (keep this shell for later steps):

```bash
cd sdk/python
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Store credentials **outside the repository** under `~/.veriagent/` (create once):

```bash
mkdir -p ~/.veriagent
chmod 700 ~/.veriagent
```

Create a private key file (32-byte Ed25519 seed, base64). Do not commit this file or paste it into the UI:

```bash
python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; import base64; print(base64.b64encode(Ed25519PrivateKey.generate().private_bytes_raw()).decode())" > ~/.veriagent/agent.key
chmod 600 ~/.veriagent/agent.key
```

Derive the public identity fields the Register form needs:

```bash
python - <<'PY'
from pathlib import Path
from veriagent import derive_agent_identity
pk = Path.home().joinpath(".veriagent", "agent.key").read_text().strip()
public_key, agent_did, verification_method = derive_agent_identity(pk)
print("public_key:", public_key)
print("agent_did:", agent_did)
print("verification_method:", verification_method)
PY
```

Keep `~/.veriagent/agent.key` on disk. You will use the three printed values only as **public** form fields.

> Alternative: `veriagent register request …` creates the same request from the CLI and derives identity from the private key automatically. This section uses the Register page as requested.

### Fill the registration form

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

3. Submit. The page calls `POST /registration/requests` and shows a success payload including `request_id`, `challenge_expires_at`, and challenge metadata.

### Obtain the `request_id`

Copy `request_id` from:

- the badge / challenge summary on the Register page, and/or
- the success status JSON

Save it; prove and claim require the same id.

### Understand registration status

The page polls `GET /registration/requests/{request_id}` about every 4 seconds. Backend statuses: `pending` | `approved` | `rejected` | `expired`.

UI phases you will see after create:

| Phase | Meaning |
| --- | --- |
| Requested / Proof required | Challenge issued; ownership proof not yet submitted |
| Pending approval | Proof accepted; waiting for Admin |
| Approved | Admin approved; credentials available to claim once |
| Credentials claimed | API key already retrieved |
| Rejected / Expired | Terminal; start a new request |

While pending and before proof, the status response may include `proof_payload` for the CLI. After proof, the page shows the prove/claim CLI snippets with your `request_id`.

**Note:** Reloading the Register page does not resume an existing `request_id` in the UI. Keep the tab open through approval, or continue with CLI prove/claim using the saved id.

---

## 5. Prove agent ownership

Use the official CLI. Private keys stay on your machine; only a signature is sent.

```bash
cd sdk/python
source .venv/bin/activate

veriagent register prove \
  --request-id <request_id> \
  --api-base-url http://127.0.0.1:8000 \
  --private-key-file ~/.veriagent/agent.key
```

### What the CLI does

1. Loads the private key from `--private-key-file` (or `--private-key` / `VERIAGENT_PRIVATE_KEY`). Prefer a file; never put the key in the browser.
2. Derives `agent_did` and `verification_method` from that key.
3. Retrieves the challenge `proof_payload` via `GET /registration/requests/{request_id}` (or from `--proof-payload` if you saved the create response).
4. Canonicalizes the payload with RFC 8785 / JCS and signs it locally with Ed25519.
5. Submits `POST /registration/requests/{request_id}/proof` with `{ proof_signature, verification_method }`.

Expected result: status remains `pending`, with `proof_submitted_at` set. The Register page should move to **Pending approval**.

The CLI never prints the private key.

---

## 6. Admin approval

1. Open [http://localhost:5173/veriagent/admin](http://localhost:5173/veriagent/admin).
2. Enter the same value as `VERIAGENT_ADMIN_API_KEY` and unlock. The key is stored only in `sessionStorage` for this browser session and sent as `X-VeriAgent-Admin-Key`.
3. Review the pending queue (`GET /registration/requests?status=pending`). Confirm proof was submitted (Approve is disabled until then).
4. Optionally add review notes, then **Approve**.

### What changes after approval

- Request status becomes `approved`.
- An agent record is created as `active`.
- A one-time agent API key is prepared server-side (`pending_api_key`).
- The Admin response JSON includes a `retrieval_token` (`vrt_…`) — **not** the agent API key. The applicant still claims credentials with the CLI.
- Register page shows **Approved** and the claim CLI snippet while `credentials_available` is true.

Approve before `challenge_expires_at`. There is no separate review grace period in the current implementation.

---

## 7. Claim credentials

After approval:

```bash
veriagent register claim \
  --request-id <request_id> \
  --api-base-url http://127.0.0.1:8000 \
  --private-key-file ~/.veriagent/agent.key \
  --output-key-file ~/.veriagent/agent.api_key
```

Optional: `--retrieval-token <vrt_…>` (from the Admin approve response) as an extra binding header.

### What the CLI does

1. Builds claim payload `{ purpose: "veriagent-credentials-claim", request_id, agent_did }`.
2. Signs it locally (ownership verification).
3. Calls `POST /registration/requests/{request_id}/credentials`.
4. Receives the agent API key **once** (`va_agent_…`).
5. Writes the key to `--output-key-file` when provided, and prints the claim JSON (includes `api_key`).

### Secure storage

- Keep credentials under `~/.veriagent/` with mode `600` for files and `700` for the directory.
- Treat `~/.veriagent/agent.api_key` like a password: never commit, never paste into Dashboard/Register.
- Console may use the API key only as a temporary operator unlock for listing your events (dev auth). Production operators should keep the key on the agent host that runs the SDK/CLI.
- A second claim fails once credentials are already claimed.

---

## 8. Submit the first audit event

Do **not** sign in the browser. Use the CLI or SDK.

### CLI

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

Or pass `--event ~/.veriagent/event-unsigned.json` for unsigned fields (the CLI adds `agent_id`, `signature`, and `verification_method`). Use `--output-event` to keep the signed payload for section 11.

### What happens

1. The CLI derives the agent DID from the private key and builds the unsigned event (`agent_id` = DID).
2. It JCS-canonicalizes the unsigned event and signs with Ed25519.
3. It `POST`s to `/audit/events` with header `X-VeriAgent-API-Key`.

### Expected response

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

Save `event_id` and the signed event from `--output-event` (needed for offline `veriagent verify`). Prefer `~/.veriagent/` over paths inside the git checkout.

### Python SDK equivalent

```python
from pathlib import Path
from veriagent import VeriAgentClient

client = VeriAgentClient(
    api_base_url="http://127.0.0.1:8000",
    agent_api_key=Path.home().joinpath(".veriagent", "agent.api_key").read_text().strip(),
    private_key_base64=Path.home().joinpath(".veriagent", "agent.key").read_text().strip(),
)
response = client.submit_event(
    event_id="event-first-run-001",
    task_id="task-001",
    model_name="demo-model",
    tool_calls=["search", "calculator"],
    input_hash="sha256:input123",
    output_hash="sha256:output456",
    policy_version="policy-v0.1",
)
print(response)
```

---

## 9. Observe the event lifecycle

1. Open [http://localhost:5173/veriagent/console](http://localhost:5173/veriagent/console).
2. Unlock with the agent API key (`X-VeriAgent-API-Key` in session storage).
3. Refresh the event list (`GET /audit/events`). Select your event.

Lifecycle is derived from `GET /audit/events/{event_id}/status`:

| State | Meaning |
| --- | --- |
| **Submitted** | Event is stored and hash-committed; not yet in a Merkle batch (`batched=false`) |
| **Batched** | Included in a batch; `batch_id` and `merkle_root` are set (`batched=true`, `anchored=false`) |
| **Anchored** | Batch Merkle root written on-chain; `tx_hash`, `block_number`, `chain_id`, `anchored_at` present |

With auto-anchor enabled and anchoring configured, the scheduler periodically creates a batch from unbatched events and anchors it. Watch `/ops/status` (also shown on Admin) for `last_status`, `last_batch_id`, and `last_anchor_tx`.

From Console you can also look up the batch, fetch and verify the Merkle proof against the API’s verifier, and load the anchor record. Use **Refresh lifecycle** while waiting.

If anchoring is disabled or not configured, events remain **Submitted** (or **Batched** if you create a batch manually via admin API) without progressing to **Anchored**.

---

## 10. Public verification

1. Open [http://localhost:5173/veriagent/dashboard](http://localhost:5173/veriagent/dashboard). No credentials.
2. Paste the `event_id` (and `batch_id` once known).
3. Refresh lifecycle until **Anchored**.
4. Use the evidence actions:

   - **Lookup batch** — batch metadata including Merkle root  
   - **Get & verify proof** — inclusion proof for the event hash, then server-side Merkle verify  
   - **Get anchor record** — `tx_hash`, block, chain id, timestamps  

### What the reviewer is verifying

The Dashboard answers: *“Does the platform’s stored evidence show this signed event was batched and anchored?”*

It is a **read-only** trust surface. It does not hold private keys, does not submit events, and does not replace independent offline verification.

When a `tx_hash` is present, the UI can link to the configured block explorer.

---

## 11. Independent verification

This is the final trust step: prove the evidence yourself without trusting VeriAgent for the cryptographic checks.

### Prepare inputs

You need:

1. The **signed event** JSON from `--output-event` (for example `~/.veriagent/event.json`), or fetch public event metadata and use its canonical form as documented in [15-independent-verifier.md](./15-independent-verifier.md).
2. Merkle **proof** from `GET /audit/batches/{batch_id}/proof/{event_id}` (save e.g. to `~/.veriagent/proof.json`).
3. **Anchor** record from `GET /audit/batches/{batch_id}/anchor` (save e.g. to `~/.veriagent/anchor.json`).

Discover `batch_id` from Dashboard/Console lifecycle status, or `GET /audit/events/{event_id}/status`.

### Offline CLI (recommended)

```bash
veriagent verify \
  --event ~/.veriagent/event.json \
  --proof ~/.veriagent/proof.json \
  --anchor ~/.veriagent/anchor.json
```

Expected human output starts with `PASS` and lists checks such as:

- event canonical hash  
- proof event-hash match  
- Ed25519 signature vs `did:key`  
- Merkle inclusion  
- anchor Merkle root / batch id match  
- anchor metadata present  

Exit codes: `0` PASS, `1` FAIL, `2` malformed input / fetch error.

### API-assisted fetch (checks still local)

```bash
veriagent verify \
  --event ~/.veriagent/event.json \
  --api-base-url http://127.0.0.1:8000 \
  --batch-id <batch_id> \
  --event-id event-first-run-001
```

Fetched JSON is only input to the same local verifier. The CLI does **not** yet re-query the chain via RPC (`getBatch`); that remains a documented future enhancement.

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Registration routes **404** | `VERIAGENT_REGISTRATION_ENABLED` not truthy | Export `true` and restart Uvicorn |
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

VeriAgent’s production trust model separates **custody**, **orchestration**, and **verification**:

| Component | Responsibility |
| --- | --- |
| **SDK / CLI** | Owns the agent private key. Derives DID, proves registration, claims the API key, signs audit events, runs offline verify. |
| **Backend API** | Stores registration and audit data, verifies signatures server-side, batches events, anchors Merkle roots, issues one-time credentials, exposes public evidence reads and ops status. |
| **Console** | Operator portal to list *your* submitted events and watch Submitted → Batched → Anchored. Does not sign. |
| **Dashboard** | Public, read-only evidence viewer. Platform-assisted verification for auditors. |
| **Admin** | Human review of registration requests; approve/reject. Never the place to generate agent keypairs. |
| **Offline Verifier** | Recomputes hash, signature, Merkle inclusion, and anchor metadata locally so a third party need not trust the VeriAgent server for those checks. |

Emphasized invariants:

- The **browser never owns** the agent private key.
- All cryptographic operations for agents are performed by the **SDK/CLI**.
- The **Dashboard is read-only by design**.
- The **Offline Verifier** is the final step for independent assurance without trusting the VeriAgent server.

For surface diagrams and auth notes, see [16-production-architecture.md](./16-production-architecture.md). For verifier details, see [15-independent-verifier.md](./15-independent-verifier.md).
