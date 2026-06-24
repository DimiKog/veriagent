# VeriAgent Commercial Readiness Roadmap

**Purpose:** Describe how VeriAgent can evolve from a research-grade prototype to a commercial pilot or product, without overclaiming current capabilities.

**Audience:** Project partners, proposal evaluators, operators planning pilots, and engineering prioritization.

**Related:** [12-release-notes-v1.0.0-rc1.md](12-release-notes-v1.0.0-rc1.md) · [08-architecture.md](08-architecture.md) · [06-threat-model.md](06-threat-model.md) · [09-demo-mode.md](09-demo-mode.md)

---

## 1. Current maturity

VeriAgent v1.0.0-RC1 is a **deployed research prototype** with a complete cryptographic audit pipeline: signed events → Merkle batches → Besu anchoring → public verification. It runs on a single VM with SQLite, admin-protected registration, and an optional auto batch/anchor scheduler.

| Dimension | Maturity |
| --- | --- |
| Core cryptography | Strong — JCS, Ed25519, Merkle proofs, on-chain roots |
| Public demonstrability | High — live dashboard, API, Blockscout |
| Multi-tenant / SaaS | Not started |
| Enterprise operations | Partial — backup scripts; no monitoring stack |
| Compliance positioning | Explicit non-goal today |
| Integration surface | Python SDK (event submission only) |

**Summary:** Ready for **research evaluation, funded pilots, and partner demos**. Not ready for **multi-customer SaaS, regulated production workloads, or compliance sales** without the gaps below.

---

## 2. What is already commercially relevant

Partners evaluating VeriAgent today can rely on these properties:

- **Tamper-evident commitments** — After anchoring, event hashes cannot change without breaking Merkle proofs and disagreeing with the on-chain root.
- **Agent binding at ingestion** — Registered `did:key`, API key auth, and Ed25519 signature verification before storage.
- **Batch efficiency** — Many agent actions committed in one on-chain transaction.
- **Public verifiability** — Open read APIs, Merkle verify endpoint, block explorer links; no proprietary verifier required for basic checks.
- **Clear trust boundaries** — Documented threat model; admin vs agent credential separation; no admin keys in the browser.
- **Integration path** — Python SDK and direct API for agent middleware; structured JSON event schema.
- **Operator automation** — Background scheduler reduces manual batch/anchor labor for single-tenant deployments.
- **Deployment flexibility** — Self-hosted on a VM today; no mandatory cloud dependency beyond optional GitHub Pages for the dashboard.

These support **technical due diligence** and **pilot scoping** even before productization work.

---

## 3. Gaps before commercial pilot

| Gap | Why it matters for pilots |
| --- | --- |
| **Multi-tenant organizations** | Separate customers, data, and admin boundaries on one platform |
| **Agent registration requests** | Self-service or workflow-based onboarding without sharing the global admin key |
| **Proof-of-control challenge** | Prove DID ownership before issuing production API keys |
| **Key rotation / revocation workflow** | Operational response to compromised keys; `did:key` alone does not rotate |
| **Rate limiting / quotas** | Abuse protection on public or multi-agent deployments |
| **PostgreSQL migration** | Concurrent writers, managed backups, path to HA — when usage justifies it |
| **Offsite encrypted backups** | Disaster recovery beyond single-VM retention |
| **Monitoring and alerting** | Proactive notice on `anchor_failed`, API health, disk, scheduler stalls |
| **Independent verifier CLI** | Third-party audit without trusting API responses for verification logic |
| **Organization dashboard** | Per-org agents, events, batches, anchors — not a single global operator view |

**Near-term pilot workaround:** One dedicated VeriAgent instance per pilot customer (self-hosted or managed single-tenant), operator-mediated agent registration, manual ops monitoring via `/ops/status`.

---

## 4. Commercial roadmap

### Phase 1 — Pilot-ready

**Goal:** Support 1–5 pilot customers with operator-assisted onboarding and clear SLAs on a **single-tenant** deployment per customer.

| Work item | Outcome |
| --- | --- |
| Registration request workflow | Applicants submit org + DID; operator approves; API key issued |
| Proof-of-control challenge | Nonce signed by applicant before approval |
| Independent verifier CLI | Local verify: hash, Merkle proof, on-chain root |
| Demo mode (`POST /demo/agents`) | Safe public sandbox without admin keys ([09-demo-mode.md](09-demo-mode.md)) |
| Monitoring basics | Health + ops status alerts; anchor failure notifications |
| Offsite backup policy | Encrypted copies; restore runbook tested |
| Pilot documentation | Onboarding guide, scope disclaimer, support boundaries |

**Exit criteria:** Pilot customer can onboard agents through a defined workflow; third party can verify an anchored event without the dashboard; operator receives alert on anchor failure.

### Phase 2 — Organization-ready

**Goal:** Multiple organizations on one deployment with isolation and self-service within policy.

| Work item | Outcome |
| --- | --- |
| Multi-tenant organization model | Org ID on agents, events, batches; admin scoped per org |
| Organization dashboard | Org admins manage agents and view audit trail |
| Rate limiting / quotas | Per-org and global ingestion and registration limits |
| Key revocation and status API | Deactivate agents; document re-registration path |
| PostgreSQL option | Migration path when concurrent load or ops requirements exceed SQLite |
| TypeScript SDK | Frontend and Node agent integrations |

**Exit criteria:** Two or more orgs on shared infrastructure without cross-tenant data leakage; org admin can register agents within quota without global admin key.

### Phase 3 — Compliance / enterprise-ready

**Goal:** Support enterprise procurement conversations with operational and governance depth — still **not** claiming automatic legal compliance.

| Work item | Outcome |
| --- | --- |
| VC-based or federated onboarding | Optional W3C VC verification before `active` status |
| HSM / key custody integrations | Enterprise signing and anchor key management |
| Audit log for operator actions | Registration approvals, batch/anchor mutations |
| SLA-backed managed offering | Defined uptime, backup RPO/RTO, support tiers |
| Consortium anchoring options | Shared Besu network or public-chain anchoring choices |
| Formal compliance mapping | Gap analysis vs EU AI Act / sector rules — advisory, not product certification |

**Exit criteria:** Enterprise security review pack; documented data residency and key custody; optional VC onboarding path.

---

## 5. Deployment models

| Model | Description | Fit today |
| --- | --- | --- |
| **Self-hosted** | Customer runs API + SQLite on their VM; optional own Besu or shared chain | **Yes** — matches current architecture |
| **Managed instance** | Vendor operates one VeriAgent VM per customer; customer holds agent keys | **Yes** — with operator labor |
| **Consortium deployment** | Shared Besu network; multiple orgs anchor to common chain; VeriAgent per org or shared multi-tenant API | **Partial** — chain exists; multi-tenant API not |
| **Academic / research infrastructure** | Public demo + Edu-Net Besu; ephemeral agents; paper reproducibility | **Yes** — current public deployment |

Anchoring can remain on **customer-operated Besu**, a **consortium chain**, or eventually **public L2** — the commitment layer is chain-agnostic at the contract interface level.

---

## 6. Product positioning

| VeriAgent is | VeriAgent is not |
| --- | --- |
| A **verifiable audit commitment layer** for AI-agent actions | An **AI model monitor** (latency, drift, prompt logging UI) |
| Cryptographic proof of **what was committed, when, and by which registered agent** | A **compliance product by itself** (EU AI Act, SOC 2, etc.) |
| Infrastructure for **tamper-evident audit trails** after ingestion | Proof that **event content is truthful** |
| A building block for **middleware** between agents and governance tools | A replacement for enterprise GRC or SIEM platforms |

**Elevator line:** VeriAgent gives autonomous AI systems a standard way to **commit** signed audit records and **prove** they were not altered after anchoring — the layer regulators and partners inspect before arguing about policy compliance.

---

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| **Overclaiming compliance** | Keep scope disclaimer in all pilots; map gaps explicitly; no “AI Act certified” marketing |
| **Operating own Besu network** | Prototype Edu-Net is fine for research; pilots should define chain governance, finality, and exit strategy |
| **Private key management** | Agent keys and anchor keys are customer/operator responsibility; document HSM path for enterprise |
| **Onboarding friction** | Admin registration blocks scale; prioritize request workflow and demo mode |
| **Pre-anchor operator trust** | SQLite mutable before anchoring; shorten anchor intervals; external witnesses for sensitive pilots |
| **SQLite at scale** | Defer PostgreSQL until measured need; avoid premature migration cost |
| **Stolen API keys** | Rate limits, revocation, monitoring anomalous ingestion patterns |

---

## 8. Recommended next engineering priorities

Ordered for **pilot value** and **honest scope**:

1. **Registration request workflow** — Removes global admin key sharing; unlocks partner self-service with approval.
2. **Independent verifier CLI** — Critical for third-party trust and paper reproducibility.
3. **Multi-tenant organization model** — Required before shared hosted offering.
4. **PostgreSQL migration** — **Only after real usage** demonstrates SQLite limits (concurrency, backup ops, multi-tenant queries).
5. **Monitoring and alerting** — Low effort, high ops value for any pilot.
6. **Demo mode** — Lowers public and evaluator friction without weakening security model.

Defer until Phase 2+: TypeScript SDK, VC onboarding, public-chain anchoring, HSM integrations.

---

## References

- Release baseline: [12-release-notes-v1.0.0-rc1.md](12-release-notes-v1.0.0-rc1.md)
- Release gates: [10-v1-release-checklist.md](10-v1-release-checklist.md)
- Future production onboarding: [09-demo-mode.md](09-demo-mode.md) §7
- Demo script: [11-demo-script.md](11-demo-script.md)

---

**Document status:** Commercial readiness roadmap · v1.0.0-RC1 baseline
