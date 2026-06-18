# VeriAgent Demo Mode (Design)

**Status:** Design only — not implemented.  
**Target release context:** Post v1.0-RC1 (backend `1.0-pre` with auto batch/anchor scheduler and `GET /ops/status`).

This document proposes a **safe demo mode** that makes VeriAgent easier to try on the public dashboard without exposing admin secrets in the browser or reusing production agent credentials.

---

## 1. Problem

The current public demo workflow has a high friction bar:

1. **Manual agent registration** — An operator must call `POST /agents/register` via Swagger, curl, or internal tooling with `X-VeriAgent-Admin-Key`. Casual visitors cannot self-serve.
2. **Credential juggling** — The user must obtain and paste three separate values into the dashboard:
   - Agent DID (`did:key:z...`)
   - Agent API key (`va_agent_...`, shown once at registration)
   - Ed25519 private key (base64 seed, for browser signing)
3. **No guided path** — The dashboard explains credentials but does not create them. Users who miss the registration step cannot submit events.
4. **Confusion with production** — The same registration path is used for demo and production agents. There is no explicit `demo` vs `production` separation in the registry.
5. **Batch/anchor gap (partially addressed)** — Manual batch/anchor still requires an admin key. Server-side **automatic batching/anchoring** (v1.0-pre) helps operators but does not simplify agent onboarding for demo users.

The dashboard correctly **never** holds admin keys. The missing piece is a **public, bounded, demo-only registration path** that preserves that invariant.

---

## 2. Demo mode goals

| Goal | Rationale |
| --- | --- |
| **Easy public demo** | A visitor can go from zero to a signed, stored event in one UI flow. |
| **No admin key in browser** | Admin registration stays server-side or operator-only; the public frontend must not request or store `VERIAGENT_ADMIN_API_KEY`. |
| **No production private keys** | Demo keys are ephemeral, generated in the browser, and never reused from operator key material (`scripts/demo_agent.env`, VM secrets). |
| **Clear separation from production** | Demo agents are labeled, rate-limited, short-lived, and visually distinguished in the UI. |
| **Same verifiable pipeline** | Demo events use the same canonicalization, signing, Merkle batching, and Besu anchoring as production—only onboarding differs. |
| **Safe by default** | Demo mode is **off** unless explicitly enabled on the API host. |

---

## 3. Proposed flow

End-to-end demo journey (happy path):

```text
User opens public dashboard
        ↓
Clicks "Generate demo agent"
        ↓
Browser generates Ed25519 keypair (in memory)
        ↓
Browser derives did:key + verification_method
        ↓
POST /demo/agents  { public_key, agent_did, verification_method, ... }
        ↓
Backend validates binding, creates agent (status=demo, expires_at=...)
        ↓
Returns va_agent_... API key once (+ agent_did, expires_at)
        ↓
Frontend holds private key + API key in React state only
        ↓
User builds audit event → signs in browser → POST /audit/events
        ↓
Backend verifies signature + API key → stores event → HMAC receipt
        ↓
Auto scheduler (if enabled) batches + anchors on interval
        ↓
User views batch/proof/anchor via public read APIs or dashboard steps
```

**User-visible steps (simplified UI):**

1. **Generate demo agent** — One click; no Swagger, no admin key, no pasted secrets from an operator.
2. **Create signed event** — Pre-filled demo payload; sign and submit.
3. **Watch the chain** — Poll `GET /ops/status` or dashboard sidebar for `last_status`, `last_batch_id`, `last_anchor_tx`; link to Blockscout when anchored.

**Explicit non-steps for demo users:**

- No manual `POST /agents/register` with admin key.
- No manual `POST /audit/batches` or `POST .../anchor`.
- No persistence of private keys to `localStorage` / `sessionStorage`.

---

## 4. Backend endpoint proposal

### `POST /demo/agents`

**Purpose:** Register a short-lived demo agent without admin authentication.

**Authentication:** None (public). Protected by demo-mode flag, rate limits, and quotas instead.

**Request body (proposal):**

```json
{
  "agent_did": "did:key:z6Mk...",
  "verification_method": "did:key:z6Mk...#z6Mk...",
  "public_key": "<base64 Ed25519 public key>",
  "agent_name": "Demo Agent",
  "agent_type": "llm-agent"
}
```

**Behavior:**

1. Reject unless `VERIAGENT_DEMO_MODE_ENABLED=true`.
2. Validate Ed25519 `did:key` binding (same rules as admin registration).
3. Create agent row with:
   - `status`: `"demo"` (distinct from `"active"` production agents)
   - `expires_at`: ISO timestamp (e.g. now + 24 hours)
   - Optional `demo_session_id` for cleanup correlation
4. Issue `va_agent_...` API key; store SHA-256 hash only.
5. Return raw `api_key` **once** (same as admin registration).

**Response (proposal):**

```json
{
  "agent_did": "did:key:z6Mk...",
  "verification_method": "did:key:z6Mk...#z6Mk...",
  "public_key": "...",
  "status": "demo",
  "created_at": "...",
  "expires_at": "...",
  "api_key": "va_agent_..."
}
```

**Errors:**

| Code | Condition |
| --- | --- |
| `403` | Demo mode disabled |
| `429` | Rate limit or demo quota exceeded |
| `400` | Invalid DID / key binding |
| `409` | DID already registered (non-expired) |

**Related (future, not required for phase 2):**

- `GET /demo/agents/{agent_did}` — public metadata only (no API key); optional.
- Background job deletes expired demo agents and optionally orphan demo events.

**Not in scope for demo endpoint:**

- Batch or anchor operations (remain admin-only or automatic scheduler).
- Admin key acceptance on this route.

---

## 5. Safety controls

Demo mode must be **disabled by default** and bounded when enabled.

### Configuration (proposal)

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERIAGENT_DEMO_MODE_ENABLED` | `false` | Master switch for `POST /demo/agents` |
| `VERIAGENT_DEMO_AGENT_TTL_HOURS` | `24` | Lifetime of demo agent records |
| `VERIAGENT_DEMO_MAX_AGENTS` | `100` | Max concurrent non-expired demo agents |
| `VERIAGENT_DEMO_RATE_LIMIT_PER_IP` | `5/hour` | Registrations per client IP |
| `VERIAGENT_DEMO_RATE_LIMIT_GLOBAL` | `50/hour` | Global registration cap |

Production deployments should leave demo mode **off** on operator/production API hosts unless running an intentional public sandbox.

### Rate limiting

- Apply per-IP and global limits on `POST /demo/agents`.
- Return `429 Too Many Requests` with `Retry-After` when exceeded.
- Consider CDN/proxy IP headers (`X-Forwarded-For`) behind Nginx.

### Demo agent quota

- Count agents where `status = demo` and `expires_at > now`.
- Reject new registrations when at `VERIAGENT_DEMO_MAX_AGENTS`.

### Expiry and cleanup

- Demo agents cannot submit events after `expires_at` (treat as inactive).
- Scheduled cleanup job (phase 4) removes expired demo agents and optionally aged demo events/batches to control SQLite growth.

### UI warning (frontend)

When demo mode is active, display a persistent banner, for example:

> **Demo mode** — Ephemeral agent credentials. Keys exist only in this browser tab. Not for production or sensitive data.

### Ops visibility

- `GET /ops/status` does **not** expose demo secrets.
- Optional future field: `demo_mode_enabled` (boolean) for dashboard gating—design TBD in phase 2.

### What demo mode does not weaken

- Ed25519 signature verification on `POST /audit/events` unchanged.
- Admin-protected manual batch/anchor unchanged.
- No exposure of `VERIAGENT_ADMIN_API_KEY`, anchoring private key, RPC URL, or receipt secret via demo endpoints.

---

## 6. Why not expose admin registration

Exposing `POST /agents/register` (or the admin key) in the public frontend would:

1. **Leak operator credentials** — Anyone viewing page source, network traffic, or browser storage could capture the admin key.
2. **Allow unlimited production agents** — Attackers could register persistent `active` agents without approval.
3. **Blur trust boundaries** — Production onboarding requires operator intent; a public admin key makes every visitor an operator.
4. **Increase anchor abuse risk** — While batch/anchor remain admin-protected today, a leaked admin key enables arbitrary batch/anchor mutations and agent provisioning.
5. **Violate the existing security model** — Documented in [06-threat-model.md](06-threat-model.md) and [08-architecture.md](08-architecture.md): admin mutations are server-side only.

Demo registration is a **separate, rate-limited, expiring** code path—not a shortcut around admin auth.

---

## 7. Future production onboarding

Demo mode is not production onboarding. A future production path should include:

| Stage | Description |
| --- | --- |
| **Registration requests** | Agent operator submits a request (organization, use case, contact); no immediate API key. |
| **DID proof-of-control challenge** | Server issues a nonce; applicant signs with the DID's private key to prove control before approval. |
| **Organization approval** | Human or policy engine approves/rejects; audit trail of approver and timestamp. |
| **Verifiable Credentials** | Optional VC attesting organization or agent class; VC verified before issuing `active` status and API key. |
| **Active agent issuance** | Admin or automated approver calls internal registration; `status=active`, no short TTL. |

Production agents would use the **Python SDK** or agent runtime for signing—not browser demo key generation.

See [08-architecture.md](08-architecture.md) §10–11 for current limitations and roadmap.

---

## 8. Implementation phases

### Phase 1 — Design only (this document)

- Document problem, goals, flow, endpoint, safety controls, and phased rollout.
- Align with existing v1.0-pre scheduler and `/ops/status` (no code changes).
- Review with operators before enabling any public demo registration on production.

**Exit criteria:** Approved design; threat-model update drafted; env vars documented.

---

### Phase 2 — Backend demo registration

- Add `VERIAGENT_DEMO_MODE_ENABLED` and related env vars.
- Implement `POST /demo/agents` with DID validation, `status=demo`, TTL, rate limits, quota.
- Reject event ingestion for expired demo agents.
- Tests: disabled by default, rate limit, expiry, no secret leakage, valid registration flow.
- Update [03-api.md](03-api.md), [04-testing.md](04-testing.md), [05-deployment.md](05-deployment.md), [06-threat-model.md](06-threat-model.md).

**Exit criteria:** Backend demo registration works via curl; demo mode off in production by default.

---

### Phase 3 — Frontend demo button

- Replace manual credential paste with **Generate demo agent** (keygen + `POST /demo/agents`).
- Keep private key and API key in memory only; show expiry and demo banner.
- Simplify step 2/3 of dashboard workflow; rely on auto scheduler for batch/anchor visibility.
- Optional: poll `/ops/status` for anchor progress instead of manual batch/anchor buttons.

**Exit criteria:** Public dashboard E2E without Swagger or admin key; documented in [frontend/README.md](../frontend/README.md).

---

### Phase 4 — Cleanup / expiry job

- Background task or cron: delete expired demo agents (and optionally old demo events/batches).
- Metrics/logging: demo registrations, active demo count, cleanup runs.
- Operator runbook for demo sandbox VM vs production VM.

**Exit criteria:** SQLite growth bounded; expired agents cannot authenticate; ops documented in [07-backup-restore.md](07-backup-restore.md) / deployment guide.

---

## References

- [08-architecture.md](08-architecture.md) — System components and agent/event lifecycle
- [03-api.md](03-api.md) — Current API (`POST /agents/register`, `POST /audit/events`, `/ops/status`)
- [06-threat-model.md](06-threat-model.md) — Security boundaries
- [frontend/README.md](../frontend/README.md) — Current dashboard credential flow
