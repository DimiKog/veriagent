# API Reference

## GET /health

Returns service health.

## POST /audit/hash

Computes the RFC8785/JCS canonical hash of an audit event without storing it.

## POST /audit/events

Stores an audit event and returns a signed ingestion receipt.

The backend:
1. canonicalizes the event using RFC8785/JCS,
2. computes a SHA-256 hash,
3. stores the canonical event JSON and hash in SQLite,
4. signs an ingestion receipt with HMAC-SHA256.

Returns:
- `event_id`
- `event_hash`
- `created_at`
- `receipt` — signed payload containing `event_id`, `event_hash`, `created_at`, `signature`, and `algorithm` (`HMAC-SHA256`)

Receipt signing uses `VERIAGENT_RECEIPT_SECRET`. If unset, a clearly marked development-only fallback secret is used locally.

Duplicate `event_id` values return `409 Conflict`.

## GET /audit/events/{event_id}

Retrieves stored metadata for an audit event.

Returns:
- `event_id`
- `event_hash`
- `canonical_event_json`
- `created_at`

Missing events return `404 Not Found`.

## POST /audit/verify

Verifies a submitted audit event against the stored commitment.

Returns:
- `verified: true` if the recomputed hash matches the stored hash
- `verified: false` if the submitted event has been modified

Missing events return `404 Not Found`.

## POST /audit/batches

Creates a Merkle batch from all stored audit events that are not yet assigned to a batch.

The backend:
1. collects unbatched events in stable storage order,
2. sorts event hashes lexicographically for a deterministic Merkle tree,
3. computes a SHA-256 Merkle root (duplicating the last leaf when the leaf count is odd),
4. stores `batch_id`, `merkle_root`, `event_count`, and `created_at` in SQLite.

Returns:
- `batch_id`
- `merkle_root`
- `event_count`
- `created_at`
- `event_hashes` — sorted leaf hashes included in the batch

Returns `400 Bad Request` when no unbatched events are available.

## GET /audit/batches/{batch_id}

Retrieves stored batch metadata.

Missing batches return `404 Not Found`.

## GET /audit/batches/{batch_id}/proof/{event_id}

Returns a Merkle inclusion proof for a stored event in a batch.

The backend:
1. loads the batch by `batch_id`,
2. loads the stored event by `event_id`,
3. checks that the event is included in the batch,
4. generates a proof with `merkle_proof(batch.event_hashes, event_hash)`.

Returns:
- `batch_id`
- `event_id`
- `event_hash`
- `merkle_root`
- `proof` — ordered list of `{ "sibling": "...", "side": "left" | "right" }` steps

Returns `404 Not Found` when the batch, event, or batch membership is missing.

## POST /audit/merkle/verify

Verifies that an event hash is included in a Merkle batch root using an inclusion proof.

Request body:
- `event_hash`
- `merkle_root`
- `proof` — ordered list of `{ "sibling": "...", "side": "left" | "right" }` steps

Returns:
- `verified: true` if the proof resolves to the supplied root
- `verified: false` otherwise