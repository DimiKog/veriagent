# VeriAgent Demo Script (60–90 seconds)

**Audience:** Academic reviewer · Project partner · Proposal evaluator  
**Format:** Live dashboard walkthrough or recorded screen capture  
**Surface:** [Dashboard](https://dimikog.github.io/veriagent/) · [API](https://veriagent.dimikog.org) · [Blockscout](https://blockexplorer.dimikog.org/)

Speak at a steady pace (~140 words/min). Full delivery: ~2 minutes. Short version: ~60–90 seconds by trimming optional screen narration and presenter notes.

---

## 1. Problem

> AI agents act autonomously—calling tools, invoking models, handling sensitive inputs—but their audit trails are usually opaque logs. If a record changes after the fact, there is no standard way to prove what was committed, when, and by which agent.

**[Screen]** Open the dashboard. Optional trim for 60s: skip to §2.

---

## 2. Agent identity

> VeriAgent binds every audit record to a registered agent identity: an Ed25519 `did:key` and a per-agent API key. Only registered agents can submit events; the backend verifies both the Ed25519 signature and the agent API key binding on every ingestion.

**[Screen]** Show agent credentials step (DID + API key). Mention keys are held client-side; the dashboard signs in-browser for demo only.

---

## 3. Signed event

> The agent builds a structured audit event—model, tool calls, input/output hashes, policy version—and signs it with Ed25519. The payload is canonicalized with RFC 8785 JCS so any party can reproduce the same bytes and hash.

**[Screen]** Click **Sign and submit** (or show pre-filled demo payload). Highlight `event_id`, `agent_id`, and signature fields.

---

## 4. Receipt

> On acceptance, VeriAgent stores the canonical event and returns an HMAC ingestion receipt—a server-side proof that this commitment was recorded at a specific time, before batching and anchoring.

**[Screen]** Show receipt / success response with `event_hash` and receipt token.

---

## 5. Merkle batch

> Events are grouped into Merkle batches: leaf hashes are sorted and combined into a single root. One root can commit dozens of agent actions efficiently, without re-signing each event.

> In production mode, VeriAgent can automatically batch and anchor events through a background scheduler, removing the need for manual operator intervention.

**[Screen]** Open batch view or `GET /audit/batches/{id}`—show `merkle_root` and event count. Note: production auto-batches when enough unbatched events accumulate (scheduler interval ~5 min).

---

## 6. Besu anchoring

> That Merkle root is anchored on Besu Edu-Net via the `VeriAgentAnchor` contract. The on-chain transaction is the durable timestamp: altering stored audit records after anchoring would break agreement with the anchored Merkle root on-chain.

**[Screen]** Show anchor record (`tx_hash`, block) or Blockscout link. Contract: `0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A` (chain `424242`).

---

## 7. Verification

> Anyone can verify independently—no admin access required. Fetch the event, recompute the hash, check the Merkle inclusion proof, and confirm the root on chain via public APIs or Blockscout.

**[Screen]** Run verify step or `POST /audit/merkle/verify`. Green check = inclusion under the anchored root.

---

## 8. Why this matters

> VeriAgent does not claim an agent told the truth—it provides a **tamper-evident commitment trail**: signed by the agent, batched cryptographically, anchored publicly. That is the foundation upon which auditability, accountability, and future compliance mechanisms for autonomous AI systems can be built.

**[Screen]** Return to dashboard overview or architecture slide. Pause on “commitment, not truth.”

---

## Quick reference (presenter notes)

| Step | What to say if pressed for time |
| --- | --- |
| Problem | “No standard proof that an agent audit record wasn’t altered.” |
| Identity | “Registered `did:key` + API key; signature verified on ingest.” |
| Signed event | “JCS-canonical JSON, Ed25519-signed.” |
| Receipt | “HMAC receipt at ingestion time.” |
| Merkle batch | “Many events → one Merkle root.” |
| Besu | “Root anchored on Besu; SQLite can’t disagree after that.” |
| Verification | “Public APIs + chain read; no trust in our UI.” |
| Why | “Tamper-evident agent audit trail—not a compliance product yet, but the cryptographic layer.” |

**Scope disclaimer (if asked):** Research prototype; operator controls pre-anchor storage; demo Besu network is prototype infrastructure. See [06-threat-model.md](06-threat-model.md).

**Related docs:** [08-architecture.md](08-architecture.md) · [10-v1-release-checklist.md](10-v1-release-checklist.md) · [09-demo-mode.md](09-demo-mode.md)
