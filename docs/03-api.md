# API Reference

## GET /health

Returns service health.

## POST /audit/hash

Computes the RFC8785/JCS canonical hash of an audit event without storing it.

## POST /audit/events

Stores an audit event.

The backend:
1. canonicalizes the event using RFC8785/JCS,
2. computes a SHA-256 hash,
3. stores the canonical event JSON and hash in SQLite.

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