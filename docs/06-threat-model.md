# Threat Model

## MVP Assumptions

- The backend operator is trusted during MVP operation.
- The Besu Edu-Net anchor is prototype infrastructure.
- Raw audit events are stored off-chain.
- On-chain data will store only cryptographic commitments.
- Event submission is initially self-attested by the demo agent or client.
- As of v0.8.1, `POST /audit/events` requires a registered active agent API key and matching `agent_id` (DID binding).
- As of v0.9B, `POST /audit/events` also requires a valid Ed25519 signature over the unsigned canonical event, verified against the registered agent `public_key` and `verification_method` before storage.

## VeriAgent MVP Protects Against

- Post-commitment modification of audit records.
- Undetected tampering after a record has been committed.
- False inclusion claims when Merkle proofs are invalid.
- Later disputes about whether a committed record existed.
- Unauthorized audit event ingestion from unregistered or inactive agents (v0.8.1: `POST /audit/events` requires a valid agent API key and matching `agent_id`).
- Forged or tampered audit events from agents without the registered private key (v0.9B: Ed25519 signature verified before storage).

## VeriAgent MVP Does Not Yet Protect Against

- An AI agent failing to submit an event.
- An AI agent submitting false event data.
- Backend modification before anchoring.
- Operator-controlled private-chain governance risks.
- Full legal or regulatory compliance.
- Stolen or leaked agent API keys (possession of the key still grants ingestion as that agent unless the private signing key is also protected separately).
- Compromised agent Ed25519 private keys (attacker can sign arbitrary events as that agent).

## Phase 6A (partial)

Implemented:
- Admin-protected agent registration (`VERIAGENT_ADMIN_API_KEY` / `X-VeriAgent-Admin-Key`).
- DID metadata storage with per-agent API keys (SHA-256 hash only at rest).
- Constant-time admin key comparison via `hmac.compare_digest`.

Not yet implemented (at Phase 6A):
- DID resolution or verification of `public_key` against a DID document on chain or in a registry.

## v0.8.1 (partial)

Implemented:
- Agent API key authentication on `POST /audit/events` via `X-VeriAgent-API-Key`.
- Lookup by SHA-256 hash; inactive agents rejected.
- `event.agent_id` must match authenticated agent DID (constant-time string compare).

Not yet implemented:
- DID resolution or verification of `public_key` against a DID document.
- Auth on batch creation, anchoring, or other operator endpoints.

## v0.9B (partial)

Implemented:
- Ed25519 event signatures required on `POST /audit/events`.
- Signature verified over RFC8785/JCS canonical bytes of the unsigned event (excluding `signature` and `verification_method`).
- `verification_method` must match the registered agent record.
- Invalid signatures rejected before SQLite storage.
- Signature metadata stored with the event; Merkle commitments remain on unsigned canonical hashes.

Not yet implemented:
- Real `did:key` multibase encoding (demo DID helpers only).
- DID resolution.
- Frontend or agent SDK signing integration.
- Auth on batch creation, anchoring, or other operator endpoints.

## Future Mitigations

- Short anchoring intervals.
- Public-chain or consortium anchoring.
- External witnesses.
- Middleware-based event capture outside the agent's control.