# Development Log

## 2026-05-28

Initialized VeriAgent MVP.

Decisions:
- VeriAgent is framed as a verifiable audit commitment layer, not as a fully independent trust infrastructure.
- Phase 1 excludes blockchain, database, Merkle batching, DID/VC, ZKP, frontend, and authentication.
- Audit events are canonicalized using RFC 8785 / JCS before hashing.
- SHA-256 is used for event commitments in MVP.
- Threat model added early to avoid overclaiming.

Implemented:
- AuditEvent schema.
- RFC 8785 canonicalization.
- SHA-256 event hashing.
- FastAPI health endpoint.
- FastAPI audit hash endpoint.
- Pytest tests for hashing and API behavior.