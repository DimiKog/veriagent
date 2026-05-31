# Threat Model

## MVP Assumptions

- The backend operator is trusted during MVP operation.
- The Besu Edu-Net anchor is prototype infrastructure.
- Raw audit events are stored off-chain.
- On-chain data will store only cryptographic commitments.
- Event submission is initially self-attested by the demo agent or client.

## VeriAgent MVP Protects Against

- Post-commitment modification of audit records.
- Undetected tampering after a record has been committed.
- False inclusion claims when Merkle proofs are invalid.
- Later disputes about whether a committed record existed.

## VeriAgent MVP Does Not Yet Protect Against

- An AI agent failing to submit an event.
- An AI agent submitting false event data.
- Backend modification before anchoring.
- Operator-controlled private-chain governance risks.
- Full legal or regulatory compliance.
- Unauthorized audit event ingestion (`POST /audit/events` is still open in Phase 6A).

## Phase 6A (partial)

Implemented:
- Admin-protected agent registration (`VERIAGENT_ADMIN_API_KEY` / `X-VeriAgent-Admin-Key`).
- DID metadata storage with per-agent API keys (SHA-256 hash only at rest).
- Constant-time admin key comparison via `hmac.compare_digest`.

Not yet implemented:
- Agent API key enforcement on `POST /audit/events`.
- Cryptographic event signatures tied to agent DIDs.
- DID resolution or verification of `public_key` against the DID document.

## Future Mitigations

- Agent API key authentication for audit ingestion.
- Signed receipt at ingestion time.
- Short anchoring intervals.
- Public-chain or consortium anchoring.
- External witnesses.
- Middleware-based event capture outside the agent's control.