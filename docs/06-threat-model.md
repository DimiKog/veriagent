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

## Future Mitigations

- Signed receipt at ingestion time.
- Short anchoring intervals.
- Public-chain or consortium anchoring.
- External witnesses.
- Middleware-based event capture outside the agent's control.