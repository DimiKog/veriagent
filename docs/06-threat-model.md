# Threat Model

## MVP Assumptions

- The backend operator is trusted during MVP operation.
- The Besu Edu-Net anchor is prototype infrastructure.
- Raw audit events are stored off-chain.
- On-chain data will store only cryptographic commitments.
- Event submission is initially self-attested by the demo agent or client.
- As of v0.8.1, `POST /audit/events` requires a registered active agent API key and matching `agent_id` (DID binding).

## VeriAgent MVP Protects Against

- Post-commitment modification of audit records.
- Undetected tampering after a record has been committed.
- False inclusion claims when Merkle proofs are invalid.
- Later disputes about whether a committed record existed.
- Unauthorized audit event ingestion from unregistered or inactive agents (v0.8.1: `POST /audit/events` requires a valid agent API key and matching `agent_id`).

## VeriAgent MVP Does Not Yet Protect Against

- An AI agent failing to submit an event.
- An AI agent submitting false event data.
- Backend modification before anchoring.
- Operator-controlled private-chain governance risks.
- Full legal or regulatory compliance.
- Stolen or leaked agent API keys (possession of the key still grants ingestion as that agent).

## Phase 6A (partial)

Implemented:
- Admin-protected agent registration (`VERIAGENT_ADMIN_API_KEY` / `X-VeriAgent-Admin-Key`).
- DID metadata storage with per-agent API keys (SHA-256 hash only at rest).
- Constant-time admin key comparison via `hmac.compare_digest`.

Not yet implemented (at Phase 6A):
- Cryptographic event signatures tied to agent DIDs.
- DID resolution or verification of `public_key` against the DID document.

## v0.8.1 (partial)

Implemented:
- Agent API key authentication on `POST /audit/events` via `X-VeriAgent-API-Key`.
- Lookup by SHA-256 hash; inactive agents rejected.
- `event.agent_id` must match authenticated agent DID (constant-time string compare).

Not yet implemented:
- Cryptographic event signatures tied to agent DIDs.
- DID resolution or verification of `public_key` against the DID document.
- Auth on batch creation, anchoring, or other operator endpoints.

## Future Mitigations

- Cryptographic event signatures at ingestion time.
- Short anchoring intervals.
- Public-chain or consortium anchoring.
- External witnesses.
- Middleware-based event capture outside the agent's control.