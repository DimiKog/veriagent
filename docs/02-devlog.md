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

## 2026-05-28 (Phase 2)

Decisions:
- Local SQLite persistence only; no blockchain, auth, or observability yet.
- Store canonical JCS JSON and committed hash for later verification.
- Verification recomputes hash from submitted event and compares to stored commitment.

Implemented:
- SQLite storage layer (`storage.py`) with `event_id`, `canonical_event_json`, `event_hash`, `created_at`.
- `POST /audit/events`, `GET /audit/events/{event_id}`, `POST /audit/verify`.
- Pytest coverage for storage and verification API flows.

## 2026-05-28

Completed VeriAgent Phase 2 local storage and verification.

Implemented:
- SQLite-backed audit event storage.
- `POST /audit/events` for storing canonicalized audit events.
- `GET /audit/events/{event_id}` for retrieving stored event commitments.
- `POST /audit/verify` for recomputing and comparing event hashes.
- Duplicate event detection using `event_id`.
- Isolated test database setup using `VERIAGENT_DB_PATH`.

Tested:
- Event storage.
- Event retrieval.
- Valid event verification.
- Tampered event detection.
- Duplicate event rejection.
- Missing event handling.

Current limitation:
- Events are stored in mutable SQLite before later Merkle anchoring.
- Integrity guarantees are local and post-storage only at this stage.