# VeriAgent Registration Request & Approval Workflow (Design)

**Status:** Design only — not implemented.  
**Target release context:** Post v1.0-RC1; aligns with [13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md) Phase 1 (pilot-ready) and [09-demo-mode.md](09-demo-mode.md) §7 (future production onboarding).

This document designs a **registration request and approval workflow** that lets agent operators apply for production access without sharing the global admin key, while preserving VeriAgent's existing cryptographic binding model (Ed25519 `did:key`, per-agent API keys, signature verification at ingestion).

---

## 1. Current admin registration model

VeriAgent v1.0-RC1 registers agents through a single **admin-protected** endpoint. There is no self-service or approval queue today.

### Endpoint and authentication

| Item | Current behavior |
| --- | --- |
| Route | `POST /agents/register` |
| Auth | Header `X-VeriAgent-Admin-Key` must match env `VERIAGENT_ADMIN_API_KEY` |
| Lookup | `GET /agents/{agent_did}` — same admin auth |
| SDK | Python SDK submits events only; admin registration is manual (curl, Swagger, operator scripts) |

### Request payload

The caller supplies agent identity metadata and the public half of the Ed25519 keypair:

- `agent_did` — Ed25519 `did:key:z...`
- `agent_name`, `agent_type`, optional `description`
- `public_key` — base64-encoded 32-byte Ed25519 public key
- `verification_method` — must equal `{agent_did}#{multibase_fragment}`

The backend validates DID/key binding via `validate_ed25519_did_key_agent()` (same rules as event signature verification). Legacy `did:key:demo:...` identifiers are rejected.

### Persistence and issuance

On success:

1. A `va_agent_...` API key is generated with `secrets.token_urlsafe(32)`.
2. Only the **SHA-256 hash** of the API key is stored (`api_key_hash`).
3. Agent `status` is set to **`active`** immediately.
4. The raw `api_key` is returned **once** in the response body.

### SQLite `agents` table (current)

```sql
CREATE TABLE agents (
    agent_did TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    description TEXT,
    verification_method TEXT NOT NULL,
    public_key TEXT NOT NULL,
    api_key_hash TEXT NOT NULL,
    status TEXT NOT NULL,          -- "active" today
    created_at TEXT NOT NULL
);
```

### Ingestion gate

`POST /audit/events` requires:

- Valid `X-VeriAgent-API-Key` (lookup by hash)
- `agent_id` matching the authenticated agent DID
- Ed25519 signature over the unsigned canonical event
- `status == active` (inactive agents receive `403`)

Batch creation and on-chain anchoring remain admin-protected separately.

---

## 2. Problems with current onboarding

The admin registration model is appropriate for a single-operator research deployment but blocks pilot and commercial scale.

| Problem | Impact |
| --- | --- |
| **Global admin key sharing** | Pilot customers or partners cannot register agents without receiving `VERIAGENT_ADMIN_API_KEY`, which also authorizes batch/anchor mutations. |
| **No proof-of-control** | Registration validates DID/key *format* at submit time but does not require the applicant to demonstrate possession of the private key before issuance. An operator could register a DID they do not control if they know the public material. |
| **Immediate production access** | Every successful admin call creates an `active` agent with no review step, quota, or org attribution. |
| **High demo friction** | Public dashboard users need operator-prepared credentials or manual Swagger registration ([09-demo-mode.md](09-demo-mode.md)). |
| **No audit trail of onboarding decisions** | SQLite stores the agent row but not who approved registration, when, or on what basis. |
| **No expiry for abandoned applications** | N/A today (no application entity); stale partial onboarding is an operator coordination problem. |
| **Same path for demo and production** | No registry distinction until demo mode ships; confuses trust boundaries for evaluators. |

These gaps are called out in [13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md) and [12-release-notes-v1.0.0-rc1.md](12-release-notes-v1.0.0-rc1.md) as intentional v1.0-RC1 limitations.

---

## 3. Registration request model

Introduce a **registration request** as a first-class entity separate from the `agents` table. A request captures intent to onboard; an **approved** request (after proof-of-control and operator review) triggers agent creation and API key issuance.

### Conceptual fields

| Field | Purpose |
| --- | --- |
| `request_id` | Opaque UUID primary key; safe for status polling only — **not** a credential for API key retrieval |
| `agent_did` | Requested Ed25519 `did:key` |
| `public_key`, `verification_method` | Public identity material (validated at submit) |
| `agent_name`, `agent_type`, `description` | Agent metadata |
| `organization_name` | Applicant org (free text in Phase 1; FK to `organizations` in Phase 2) |
| `contact_email` | Operator notification and applicant status updates |
| `use_case_summary` | Short text for approval review |
| `status` | `pending` → `approved` \| `rejected` \| `expired` |
| `challenge_nonce` | Server-issued nonce for proof-of-control |
| `challenge_expires_at` | TTL for nonce and overall pending window |
| `proof_signature` | Applicant's Ed25519 signature over challenge payload (set when proof submitted) |
| `proof_submitted_at` | Timestamp of successful proof |
| `reviewed_by` | Operator identifier (email or service account) |
| `reviewed_at`, `review_notes` | Approval/rejection audit |
| `approved_agent_did` | Set on approval; links to `agents.agent_did` |
| `created_at`, `updated_at` | Lifecycle timestamps |
| `client_ip_hash` | Optional SHA-256 of applicant IP for abuse signals (never store raw IP long-term) |

### Design principles

- **Requests are not agents.** No API key exists until approval completes.
- **Proof-of-control is mandatory** for production requests before an operator (or policy engine) may approve.
- **Admin registration remains** for break-glass, migrations, and operator-initiated agents — it bypasses the request queue but should be logged separately (Phase 3).
- **One active request per DID.** If `agent_did` is already registered or has a non-terminal pending request, reject with `409`.

---

## 4. SQLite schema proposal

Add tables alongside the existing `agents` schema. Column types follow current conventions (ISO 8601 UTC text timestamps).

### `registration_requests`

```sql
CREATE TABLE registration_requests (
    request_id TEXT PRIMARY KEY,
    agent_did TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    description TEXT,
    organization_name TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    use_case_summary TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'approved', 'rejected', 'expired')
    ),
    challenge_nonce TEXT NOT NULL,
    challenge_expires_at TEXT NOT NULL,
    proof_signature TEXT,
    proof_submitted_at TEXT,
    proof_payload_json TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_notes TEXT,
    approved_agent_did TEXT,
    retrieval_token_hash TEXT,
    credentials_retrieved_at TEXT,
    client_ip_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (approved_agent_did) REFERENCES agents(agent_did)
);

CREATE INDEX idx_registration_requests_status
    ON registration_requests(status);

CREATE INDEX idx_registration_requests_agent_did
    ON registration_requests(agent_did);

CREATE UNIQUE INDEX idx_registration_requests_pending_did
    ON registration_requests(agent_did)
    WHERE status = 'pending';
```

### Optional `registration_audit_log` (Phase 2+)

Append-only log for operator actions and automated state transitions:

```sql
CREATE TABLE registration_audit_log (
    log_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (request_id) REFERENCES registration_requests(request_id)
);
```

### Future `agents` extensions (demo mode + multi-tenant)

These align with [09-demo-mode.md](09-demo-mode.md) and Phase 2 org model; apply when those features ship:

```sql
-- Proposed columns on agents (not required for request workflow Phase 1)
ALTER TABLE agents ADD COLUMN expires_at TEXT;
ALTER TABLE agents ADD COLUMN organization_id TEXT;
ALTER TABLE agents ADD COLUMN registration_request_id TEXT;
```

---

## 5. Request states

```text
                    POST /registration/requests
                              │
                              ▼
                         ┌─────────┐
         proof timeout   │ pending │◄─── resubmit proof (same request)
         or max TTL      └────┬────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ expired  │   │ rejected │   │ approved │
        └──────────┘   └──────────┘   └──────────┘
              │               │               │
              └───────────────┴───────────────┘
                         terminal
```

| State | Meaning | Transitions |
| --- | --- | --- |
| **`pending`** | Request created; awaiting proof-of-control and/or operator review. | → `approved`, `rejected`, `expired` |
| **`approved`** | Proof verified; operator approved; agent row created; API key issued once. | Terminal |
| **`rejected`** | Operator denied the request (with optional `review_notes`). | Terminal; applicant may submit a **new** request with a new `request_id` |
| **`expired`** | `challenge_expires_at` passed without approval, or background job marked stale pending requests. | Terminal; applicant may submit a new request |

### State rules

- **`pending` without proof:** Visible to applicant for status polling; not visible in operator approval queue until `proof_submitted_at` is set (configurable: allow review-only queue in Phase 1b).
- **`pending` with proof:** Eligible for operator approval.
- **Approval is atomic:** Single transaction — update request → `approved`, insert `agents` row, return API key. Roll back on any failure.
- **Rejection does not create an agent.**
- **Expiry does not delete data** in Phase 1; retention policy documented for operators (GDPR/contact_email handling in Phase 3).

---

## 6. Proof-of-control challenge design

Goal: prove the applicant holds the Ed25519 private key for the requested `agent_did` **before** a production API key is issued.

### Challenge issuance

When `POST /registration/requests` succeeds:

1. Validate DID/key binding (same as `POST /agents/register`).
2. Generate `challenge_nonce = secrets.token_urlsafe(32)`.
3. Set `challenge_expires_at = now + VERIAGENT_REGISTRATION_CHALLENGE_TTL` (default **15 minutes**).
4. Store request with `status = pending`, `proof_signature = NULL`.

Return to applicant:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_did": "did:key:z6Mk...",
  "challenge_nonce": "xY9...",
  "challenge_expires_at": "2026-06-24T12:15:00+00:00",
  "proof_payload": {
    "purpose": "veriagent-registration",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_did": "did:key:z6Mk...",
    "nonce": "xY9...",
    "issued_at": "2026-06-24T12:00:00+00:00",
    "expires_at": "2026-06-24T12:15:00+00:00"
  }
}
```

The `proof_payload` object is the **unsigned** material to canonicalize and sign (RFC 8785 / JCS — same library path as audit events).

### Proof submission

`POST /registration/requests/{request_id}/proof`

```json
{
  "proof_signature": "<base64 Ed25519 signature>",
  "verification_method": "did:key:z6Mk...#z6Mk..."
}
```

Backend steps:

1. Load request; reject if not `pending` or if `now > challenge_expires_at` → transition to `expired`.
2. Reconstruct canonical bytes from stored `proof_payload_json` (or recompute from stored fields — prefer stored JSON for stability).
3. Verify signature with registered `public_key` and `verification_method`.
4. Set `proof_signature`, `proof_submitted_at`, `updated_at`.

### Security properties

| Property | Mechanism |
| --- | --- |
| **Replay resistance** | Nonce is single-use; bound to `request_id` and `agent_did` |
| **Time bound** | `challenge_expires_at` enforced on proof and approval |
| **Algorithm alignment** | Same Ed25519 + JCS stack as audit event ingestion |
| **No private key transit** | Applicant signs locally (SDK, CLI, or secure enclave) |

### Applicant tooling

- Extend Python SDK with `submit_registration_request()` and `submit_registration_proof()` (Phase 2).
- Document a minimal curl + OpenSSL/libsodium example for pilots (Phase 1).
- Dashboard **must not** be required for production onboarding; browser keygen remains demo-only ([06-threat-model.md](06-threat-model.md)).

---

## 7. Approval workflow

### Actors

| Actor | Role |
| --- | --- |
| **Applicant** | Submits request, completes proof, polls status |
| **Operator / approver** | Reviews pending proved requests; approves or rejects |
| **System** | Expires stale requests; enforces quotas |

### Proposed API surface

| Method | Route | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/registration/requests` | Public (rate-limited) | Create request + challenge |
| `POST` | `/registration/requests/{id}/proof` | Public (rate-limited) | Submit proof signature |
| `GET` | `/registration/requests/{id}` | Public (request_id) | Applicant status poll — **no API key** |
| `GET` | `/registration/requests` | Admin | List/filter queue (`status=pending` + proof submitted) |
| `POST` | `/registration/requests/{id}/approve` | Admin | Approve → create agent + issue key (returned once here) |
| `POST` | `/registration/requests/{id}/reject` | Admin | Reject with notes |
| `POST` | `/registration/requests/{id}/credentials` | One-time retrieval token | Applicant fetches `api_key` once (optional self-service path) |

Public routes are protected by rate limits and optional CAPTCHA (Phase 3), not by shared secrets.

### Operator review flow

```text
Applicant                          VeriAgent API                    Operator
    │                                    │                              │
    │  POST /registration/requests       │                              │
    │ ──────────────────────────────────►│                              │
    │◄────────────────────────────────── │  challenge + request_id      │
    │                                    │                              │
    │  POST .../proof (signed nonce)       │                              │
    │ ──────────────────────────────────►│                              │
    │                                    │                              │
    │                                    │  GET /registration/requests  │
    │                                    │◄─────────────────────────────│
    │                                    │  pending + proof_submitted   │
    │                                    │                              │
    │                                    │  POST .../approve            │
    │                                    │◄─────────────────────────────│
    │                                    │──► api_key (+ optional        │
    │                                    │    retrieval_token) once     │
    │                                    │                              │
    │  GET .../requests/{id}             │         operator relays      │
    │ ──────────────────────────────────►│         key securely, or     │
    │◄────────────────────────────────── │         applicant uses       │
    │         status=approved (no key)   │         POST .../credentials │
```

### Approval preconditions

Before `approve` succeeds:

1. `status == pending`
2. `proof_submitted_at` is not null
3. `now <= challenge_expires_at` **or** configurable post-proof grace window (e.g. 7 days for operator SLA — separate env `VERIAGENT_REGISTRATION_REVIEW_TTL`)
4. `agent_did` not already in `agents`
5. Optional: global active agent quota not exceeded

### Rejection

`POST .../reject` with `{ "review_notes": "..." }` sets `status = rejected`, `reviewed_by`, `reviewed_at`. No agent row is created.

---

## 8. API key issuance

On approval, reuse the **existing** issuance path used by `POST /agents/register`:

1. `api_key = generate_agent_api_key()` → `va_agent_...`
2. `api_key_hash = hash_agent_api_key(api_key)`
3. `register_agent(..., status="active", ...)`
4. Set `registration_requests.approved_agent_did`, `status = approved`, review metadata
5. Return `api_key` **once** — never on `GET /registration/requests/{id}` (see delivery options below)

### Delivery (one-time only)

`GET /registration/requests/{id}` returns status metadata only (`pending`, `approved`, `rejected`, `expired`, timestamps). It must **not** include `api_key`. Returning the key on poll would make `request_id` a long-lived bearer secret.

Use one of these delivery paths:

| Path | Mechanism | Fit |
| --- | --- | --- |
| **A — Operator relay** | `POST .../approve` returns `api_key` in the **admin response only**; operator transmits to applicant via agreed secure channel | Simplest pilots; operator-mediated onboarding |
| **B — One-time retrieval token** | On approval, server generates a separate `retrieval_token`, stores SHA-256 hash only, returns token once in admin response (or emails to `contact_email`). Applicant calls `POST .../credentials` with `X-VeriAgent-Retrieval-Token`; response returns `api_key` once; token invalidated | Self-service pilots without exposing key on status poll |

### Admin approve response (includes key once)

```json
{
  "request_id": "...",
  "status": "approved",
  "agent_did": "did:key:z6Mk...",
  "agent_name": "...",
  "verification_method": "...",
  "public_key": "...",
  "agent_status": "active",
  "created_at": "...",
  "api_key": "va_agent_...",
  "retrieval_token": "vrt_..."
}
```

`retrieval_token` is omitted when using operator relay only (Path A).

### Applicant status poll (no secrets)

```json
{
  "request_id": "...",
  "status": "approved",
  "agent_did": "did:key:z6Mk...",
  "reviewed_at": "...",
  "credentials_available": true
}
```

`credentials_available` indicates the applicant may use Path B if they hold the retrieval token; it does not reveal the key.

### Post-issuance

- Applicant configures SDK/middleware with `api_key` and private signing key.
- **`GET /agents/{agent_did}`** continues to never return the API key.
- Key rotation/revocation remains a separate roadmap item ([13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md)); approval workflow does not solve compromised keys.

---

## 9. Demo mode integration

Demo mode ([09-demo-mode.md](09-demo-mode.md)) and the registration request workflow serve **different trust levels** and must remain separate code paths.

| Aspect | Demo (`POST /demo/agents`) | Registration requests |
| --- | --- | --- |
| **Auth** | None; gated by `VERIAGENT_DEMO_MODE_ENABLED` | Public create/proof; admin approve |
| **Proof-of-control** | Implicit (immediate registration after DID validation) | Explicit signed challenge |
| **Review** | None | Operator approval required |
| **Agent status** | `demo` + `expires_at` | `active`, no TTL |
| **API key** | Issued immediately | Issued on approval only |
| **Rate limits** | Demo quotas per IP/global | Registration quotas per IP/global |

### Recommended interaction

Demo mode can ship independently before or after the registration workflow. Both are separate code paths:

1. Ship **registration requests** (§13 Phases 1–4) for pilot customers who need persistent `active` agents with operator approval.
2. Ship **demo mode** (§13 Phase 5, parallel track) to reduce public dashboard friction without opening production onboarding.
3. Do **not** route demo registrations through the approval queue — demo agents should never appear in the operator pending list.
4. Shared implementation: both paths call the same internal `register_agent()` helper with different `status`, TTL, and precondition checks.

### UI separation

- Dashboard: **Generate demo agent** → `POST /demo/agents` (ephemeral banner).
- Separate **Request production access** form (future) → registration request API; no admin key in browser.

---

## 10. Multi-tenant future integration

Phase 2 ([13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md)) adds organizations. The registration workflow should anticipate but not require multi-tenancy in Phase 1.

### Phase 1 (single-tenant pilot)

- `organization_name` is free text on the request.
- Global operator approves all requests.
- All approved agents belong to the single deployment tenant.

### Phase 2 (multi-tenant)

| Change | Description |
| --- | --- |
| **`organizations` table** | `org_id`, name, quotas, billing metadata |
| **Org-scoped approvers** | `POST .../approve` requires org admin auth, not global admin key |
| **`organization_id` on agents** | Filter events, batches, and dashboards per org |
| **Request routing** | Applicant selects or proves membership in an org (invite link or email domain policy) |
| **Quotas** | Per-org max active agents; pending request caps |

### Request table migration

Add nullable `organization_id TEXT` to `registration_requests` when orgs ship. Backfill NULL for legacy pilot requests.

### Exit criteria alignment

> Org admin can register agents within quota **without global admin key** — achieved when approval auth is scoped to `organization_id` and global `POST /agents/register` is restricted to platform break-glass.

---

## 11. Security considerations

### Threats addressed

| Threat | Mitigation |
| --- | --- |
| **Admin key proliferation** | Applicants never receive `VERIAGENT_ADMIN_API_KEY`; approval uses server-side admin auth only |
| **DID squatting without key possession** | Proof-of-control challenge before approval |
| **Unbounded agent creation** | Rate limits on public endpoints; operator approval; optional quotas |
| **Challenge replay** | Nonce bound to request; single proof acceptance |
| **`request_id` as bearer secret** | Status poll never returns `api_key`; one-time delivery via admin approve response or separate retrieval token |
| **Enumeration of registered DIDs** | Generic errors on create (`409` without revealing whether DID is active vs pending) — tune message carefully |

### Residual risks (unchanged from v1.0-RC1)

- Stolen **agent API key** still allows ingestion as that agent until revocation ships.
- Compromised **Ed25519 private key** allows forged signed events.
- **Operator trust** before anchoring — SQLite mutable until Merkle batch is anchored on chain.
- **Contact email** on requests is PII — restrict admin list endpoints, encrypt backups, define retention.

### AuthZ matrix (target)

| Action | Applicant | Admin | Public read |
| --- | --- | --- | --- |
| Create request | Yes (rate-limited) | Yes | No |
| Submit proof | Yes (request_id) | No | No |
| Poll own request | Yes (request_id) | No | No |
| Retrieve API key | Yes (one-time retrieval token only) | Yes (approve response) | No |
| List all requests | No | Yes | No |
| Approve / reject | No | Yes | No |
| `POST /agents/register` | No | Yes (break-glass) | No |
| `POST /demo/agents` | Yes (if demo enabled) | N/A | No |

### Configuration (proposal)

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERIAGENT_REGISTRATION_ENABLED` | `false` | Master switch for public registration endpoints |
| `VERIAGENT_REGISTRATION_CHALLENGE_TTL_MINUTES` | `15` | Proof challenge lifetime |
| `VERIAGENT_REGISTRATION_REVIEW_TTL_DAYS` | `7` | Max time in `pending` after proof for operator review |
| `VERIAGENT_REGISTRATION_RATE_LIMIT_PER_IP` | `10/day` | Abuse control on create + proof |
| `VERIAGENT_REGISTRATION_MAX_PENDING` | `500` | Global cap on concurrent pending requests |

Production deployments enable registration only when operator review capacity exists.

---

## 12. Migration path from current `/agents/register`

The existing endpoint remains **supported and unchanged** in Phase 1 to avoid breaking operator scripts, tests, and deployment runbooks.

### Coexistence strategy

| Path | When to use |
| --- | --- |
| **`POST /agents/register`** (admin) | Break-glass, CI/E2E tests, operator-provisioned agents, migrations |
| **Registration request workflow** | Pilot self-service, partners, any onboarding without sharing admin key |
| **`POST /demo/agents`** | Public sandbox only |

### Migration steps for operators

1. **Enable** `VERIAGENT_REGISTRATION_ENABLED=true` on pilot hosts.
2. **Publish** applicant guide: generate Ed25519 `did:key`, submit request, sign challenge, wait for approval.
3. **Keep** admin key on secure operator workstation only; use approval endpoints instead of direct register for human-driven onboarding.
4. **Optional:** Add `registration_request_id` on new agent rows for traceability; backfill not required for pre-existing agents.
5. **Deprecate direct register for routine use** in Phase 2 docs (not removal) once org-scoped approval exists.

### Test compatibility

- Existing tests in `backend/tests/test_agents_api.py` continue to use admin `POST /agents/register`.
- New test module `test_registration_requests.py` covers the request lifecycle without altering current agent tests.

### Documentation updates (when implemented)

- [03-api.md](03-api.md) — new routes
- [04-testing.md](04-testing.md) — E2E request flow
- [05-deployment.md](05-deployment.md) — env vars and operator queue
- [06-threat-model.md](06-threat-model.md) — onboarding boundaries
- [09-demo-mode.md](09-demo-mode.md) — cross-link production path

---

## 13. Recommended implementation phases

Phases 1–4 and 6 are sequential for the registration workflow. **Phase 5 (demo mode) is a parallel track** — it can ship independently before, after, or alongside registration phases. Ordered for pilot value and minimal risk to v1.0-RC1 behavior.

### Phase 1 — Schema and storage

- Add `registration_requests` table and storage helpers (`create_request`, `submit_proof`, `approve_request`, `reject_request`, `expire_stale_requests`).
- Unit tests for state transitions and uniqueness constraints.
- **Exit criteria:** CRUD and state machine covered in tests; feature flag off by default.

### Phase 2 — Public request + proof API

- Implement `POST /registration/requests`, `POST .../proof`, `GET .../{id}` behind `VERIAGENT_REGISTRATION_ENABLED`.
- Integrate JCS canonicalization + Ed25519 verify for proof payload.
- Rate limiting on public routes.
- **Exit criteria:** Applicant can complete proof via curl; no agent row until approval.

### Phase 3 — Admin approval API

- Implement `GET /registration/requests`, `POST .../approve`, `POST .../reject`, optional `POST .../credentials`.
- Approval calls existing `register_agent()`; returns one-time `api_key` in admin response only (optional `retrieval_token` for applicant self-fetch).
- `GET .../{id}` returns status only — never `api_key`.
- Background job or scheduler hook to mark `expired` requests.
- **Exit criteria:** Operator can approve proved request without using direct `/agents/register`; pilot onboarding doc validated.

### Phase 4 — SDK and operator tooling

- Python SDK helpers for request + proof.
- Optional CLI or Makefile targets for operator queue review.
- Email webhook or notification on new proved request (optional).
- **Exit criteria:** Pilot customer onboards without manual JSON crafting.

### Phase 5 — Demo mode (parallel track)

- Implement `POST /demo/agents` per [09-demo-mode.md](09-demo-mode.md) independently of registration requests.
- Ensure demo agents use `status=demo` and never enter approval queue.
- **Exit criteria:** Public dashboard E2E without admin key; production registration still via Phase 2–3.

### Phase 6 — Multi-tenant org scoping

- `organizations` table; org-scoped approvers; quotas on `approve`.
- Link `agents.organization_id` and `registration_requests.organization_id`.
- **Exit criteria:** Matches Phase 2 exit criteria in [13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md).

---

## References

- Current API: [03-api.md](03-api.md) — `POST /agents/register`, agent ingestion auth
- Architecture: [08-architecture.md](08-architecture.md) — agent registry and lifecycle
- Threat model: [06-threat-model.md](06-threat-model.md) — admin vs agent boundaries
- Demo mode: [09-demo-mode.md](09-demo-mode.md) — public sandbox vs production onboarding
- Commercial roadmap: [13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md) — Phase 1 pilot priorities
- Release limitations: [12-release-notes-v1.0.0-rc1.md](12-release-notes-v1.0.0-rc1.md)

---

**Document status:** Registration workflow design · v1.0.0-RC1 baseline · design only, no code changes
