# VeriAgent production architecture (v1 surfaces)

**Status:** Multi-surface SPA + SDK/CLI split.  
**Crypto rule:** The browser is never the custodian of an agent private key. DID generation, registration proof, API key claim, and event signing happen in the official SDK/CLI.

---

## 1. Architecture diagram

```text
                    ┌──────────────────────────────────────────────┐
                    │              Public Internet                   │
                    └──────────────────────────────────────────────┘
                         │              │              │
                         ▼              ▼              ▼
                  ┌────────────┐ ┌────────────┐ ┌────────────┐
                  │ /dashboard │ │ /register  │ │  Offline   │
                  │ read-only  │ │ onboarding │ │ CLI verify │
                  │ evidence   │ │ (no keys)  │ │ (no trust  │
                  └─────┬──────┘ └─────┬──────┘ │  in API)   │
                        │              │        └────────────┘
                        │              │ create request
                        │              │ poll status
                        ▼              ▼
                  ┌─────────────────────────────────────┐
                  │         VeriAgent API (FastAPI)      │
                  │  public reads · registration · ops  │
                  └───────────────┬─────────────────────┘
                        ▲         │
   machine credential*  │         │ admin (dev unlock)*
   list events (today)  │         │ approve/reject
                        │         ▼
                  ┌────────────┐ ┌────────────┐
                  │ /console   │ │  /admin    │
                  │ operator   │ │  control   │
                  │ portal     │ │  plane     │
                  └─────▲──────┘ └────────────┘
                        │
                        │ observes events submitted by
                        │
                  ┌─────┴──────────────────────────────┐
                  │  Agent runtime (SDK / CLI)         │
                  │  • register prove / claim          │
                  │  • submit (sign + POST events)     │
                  │  Agent API key = machine credential│
                  │  Private key stays on agent host   │
                  └────────────────────────────────────┘
                                      │
                                      ▼
                            Auto batch + Besu anchor

* Temporary development auth — see §7.
```

### Trust story (explicit)

| Surface | Trust statement |
| --- | --- |
| **Dashboard** | “The platform verifies the evidence.” |
| **Offline CLI (`veriagent verify`)** | “I independently verify the evidence without trusting the VeriAgent server.” |

---

## 2. Route map

Base path (GitHub Pages / Vite): `/veriagent/`

| Route | Audience | Auth in UI | Mutates audit data? |
| --- | --- | --- | --- |
| `/veriagent/` → `/dashboard` | Auditors, partners | None | No |
| `/veriagent/dashboard` | Public | None | No |
| `/veriagent/register` | Agent developers | None (public registration API) | Creates registration request only |
| `/veriagent/console` | Registered operators | **Dev:** agent API key in `sessionStorage` | No (read + observe) |
| `/veriagent/admin` | VeriAgent admins | **Dev:** admin key in `sessionStorage` | Approves/rejects registrations |

External (not SPA routes):

| Tool | Role |
| --- | --- |
| `veriagent register request\|prove\|claim` | Cryptographic onboarding |
| `veriagent submit` | Production event signing + ingest |
| `veriagent verify` | Offline independent verification |

---

## 3. Frontend navigation

Primary nav (shared `AppLayout`):

1. **Dashboard** — public verification  
2. **Register** — agent onboarding  
3. **Console** — operator portal  
4. **Admin** — administrative control plane  

Plus external links: API Docs, GitHub, Contract.

Each surface shows an explicit **cryptographic boundary** note (SDK/CLI vs backend vs frontend).

---

## 4. Sequence diagram (production workflow)

```text
Applicant          /register UI         CLI/SDK            API              /admin UI         Besu
    │                   │                  │                │                   │               │
    │  fill public form │                  │                │                   │               │
    │──────────────────►│ POST /registration/requests       │                   │               │
    │                   │──────────────────────────────────►│                   │               │
    │◄──────────────────│ request_id + challenge            │                   │               │
    │  show prove CLI   │                  │                │                   │               │
    │─────────────────────────────────────►│ prove (sign)   │                   │               │
    │                   │                  │ POST .../proof │                   │               │
    │                   │                  │───────────────►│                   │               │
    │  poll: Proof verified → Pending approval              │  list pending     │               │
    │◄──────────────────│                  │                │◄──────────────────│               │
    │                   │                  │                │  approve          │               │
    │                   │                  │                │◄──────────────────│               │
    │  poll: Approved + credentials_available               │                   │               │
    │─────────────────────────────────────►│ claim (sign)   │                   │               │
    │                   │                  │ POST .../credentials               │               │
    │                   │                  │───────────────►│ api_key once      │               │
    │  poll: Credentials claimed           │                │                   │               │
    │                   │                  │ submit event   │                   │               │
    │                   │                  │───────────────►│                   │               │
    │                   │                  │                │── auto batch ─────┼── anchor ─────►│
    │            /console observes lifecycle                │                   │               │
    │            /dashboard verifies evidence               │                   │               │
    │            veriagent verify (offline, no API trust)   │                   │               │
```

---

## 5. Registration lifecycle (UI + API)

Backend `status` remains: `pending` | `approved` | `rejected` | `expired`.

Status poll also returns (additive, non-breaking):

| Field | Meaning |
| --- | --- |
| `credentials_available` | Approved and one-time claim still possible |
| `credentials_claimed` | Applicant has claimed the API key |
| `credentials_claimed_at` | Timestamp (`credentials_retrieved_at`) when claimed |

Frontend maps these into a reviewer-friendly ladder:

```text
Requested → Proof required → Proof verified → Pending approval
  → Approved → Credentials claimed
```

(plus terminal `Rejected` / `Expired`). “Proof verified” and “Pending approval” share backend `pending` + `proof_submitted_at`; the stepper marks proof verified complete once approval is awaited.

---

## 6. Cryptographic responsibility (enforced)

| Layer | Responsibility |
| --- | --- |
| **SDK / CLI** | DID generation, registration proof, credential claim, event signing |
| **Backend** | Signature verification, batching, anchoring, status APIs |
| **Frontend** | Orchestration, monitoring, visualization, verification UI |

Production UI **must not**:

- generate agent keypairs  
- request or store agent private keys  
- sign registration challenges  
- sign audit events  

Legacy browser signing helpers under `frontend/src/utils/` have been **removed**. Production frontend contains no key generation, registration proof signing, or audit event signing code.

---

## 7. Authentication model (current vs intended)

### Console — agent API key

**Current (temporary development mechanism):**  
Operators paste an agent API key into `sessionStorage` so `/console` can call `GET /audit/events` with `X-VeriAgent-API-Key`.

**Intended production model:**

- Human operators authenticate with their **own** user session (SSO/OAuth/etc.).
- The Console retrieves agents and events scoped to that operator/org.
- The **agent API key remains a machine credential** used only by the SDK/CLI on the agent host.

Do **not** build additional product features that depend on browser-managed agent API keys.

### Admin — admin API key

**Current:** Development authentication. Admin key in `sessionStorage`, sent as `X-VeriAgent-Admin-Key` (never in query parameters).

**Intended:** Replace with proper authenticated sessions (SSO/OAuth/Keycloak/etc.).

Do **not** build additional admin product features that depend on this unlock mechanism beyond the temporary gate.

---

## 8. Backend changes (minimal) + remaining gaps

### Implemented

| Change | Why |
| --- | --- |
| `pending_api_key` + `retrieval_token` on approve | Credential claim path; approve never returns `api_key` |
| `POST /registration/requests/{id}/credentials` | Sole issuance of agent API key after ownership proof |
| `proof_payload` on pending status GET | CLI `register prove --request-id` |
| `GET /audit/events` (agent API key) | Console event history (dev auth) |
| `credentials_claimed` + `credentials_claimed_at` on status | Complete registration UX ladder |

### Remaining inconsistencies / gaps

| Gap | Impact | Direction |
| --- | --- | --- |
| Console uses machine API key as human login | Weakens credential boundary | Operator user sessions + agent membership APIs |
| Admin key paste | Not production SSO | Sessions / IdP |
| No list/revoke agents APIs | Admin placeholders only | Small admin APIs later |
| No org-scoped event APIs | Console cannot show multi-agent fleets without key paste | Operator session + agent directory |
| GH Pages SPA deep links | Need `404.html` rewrite for client routes | Deploy config |

---

## 9. Migration plan

| Phase | Action | Risk |
| --- | --- | --- |
| **0 — Done** | Split SPA; no browser private keys; prove/claim/submit CLI; approve without `api_key` | Low |
| **1 — Deploy** | Enable registration + auto-anchor; publish CLI | Low |
| **2 — Operator cutover** | register → prove → approve → claim → submit | Medium |
| **3 — Auth hardening** | Operator + admin sessions; retire key paste; agent list/revoke | Medium |
| **4 — Acceptance tests** | Full E2E including offline `veriagent verify` | — |

### Compatibility

- Direct `POST /agents/register` (admin) remains for break-glass.
- Public audit read endpoints unchanged.
- Offline verifier remains independent of all UI surfaces.
