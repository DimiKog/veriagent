# API Reference

## GET /health

Returns service health.

## POST /audit/hash

Computes the RFC8785/JCS canonical hash of an audit event without storing it.

## POST /audit/events

Stores an audit event and returns a signed ingestion receipt. **Requires a registered active agent with a valid Ed25519 event signature.**

Requires header:
- `X-VeriAgent-API-Key` — per-agent API key issued at registration (`va_agent_...` prefix)

Request body includes all audit event fields plus:

- `verification_method` — must match the registered agent's verification method (e.g. `{agent_did}#{multibase_value}` for Ed25519 `did:key`)
- `signature` — base64-encoded Ed25519 signature over the unsigned canonical event

### Signing boundary

The signature is computed over the **RFC8785/JCS canonical JSON of the audit event excluding `signature` and `verification_method`**.

Signed (included in canonical bytes):

- `event_id`, `agent_id`, `task_id`, `model_name`, `tool_calls`, `input_hash`, `output_hash`, `policy_version`, `timestamp`, `metadata`

Not signed (excluded from canonical bytes):

- `signature`
- `verification_method`

The stored `event_hash` and Merkle leaves continue to use the **unsigned** canonical payload only. Signature metadata is stored separately.

The backend:
1. authenticates the agent by hashing the provided key and looking up `agents.api_key_hash`,
2. rejects inactive agents,
3. requires `event.agent_id` to equal the authenticated agent's `agent_did`,
4. requires `verification_method` to equal the registered agent's `verification_method`,
5. canonicalizes the unsigned event using RFC8785/JCS,
6. verifies the Ed25519 signature against the registered agent `public_key`,
7. computes a SHA-256 hash of the unsigned canonical event,
8. stores the unsigned canonical event JSON, hash, and signature metadata in SQLite,
9. signs an ingestion receipt with HMAC-SHA256.

Returns:
- `event_id`
- `event_hash`
- `created_at`
- `receipt` — signed payload containing `event_id`, `event_hash`, `created_at`, `signature`, and `algorithm` (`HMAC-SHA256`)

Receipt signing uses `VERIAGENT_RECEIPT_SECRET`. If unset, a clearly marked development-only fallback secret is used locally.

Returns `400 Bad Request` when `signature` or `verification_method` is missing.

Returns `401 Unauthorized` when the agent API key is missing or invalid.

Returns `403 Forbidden` when the agent is not `active`, when `event.agent_id` does not match the authenticated agent's DID, when `verification_method` does not match, or when the Ed25519 signature is invalid.

Duplicate `event_id` values return `409 Conflict`.

Signatures are verified **before** storage so invalid or tampered events are never committed.

## GET /audit/events/{event_id}

Retrieves stored metadata for an audit event.

Returns:
- `event_id`
- `event_hash`
- `canonical_event_json` — unsigned canonical payload (no `signature` or `verification_method`)
- `created_at`
- `verification_method`
- `signature_algorithm` — `Ed25519`

Does not return the raw event signature or agent public keys.

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

## POST /audit/batches/{batch_id}/anchor

Anchors a stored local batch on `VeriAgentAnchor` and records the transaction in SQLite.

The backend:
1. loads the local batch by `batch_id` (`404` if missing),
2. returns the existing anchor record with `already_anchored: true` if one is already stored,
3. otherwise computes `metadata_hash` with RFC 8785 / JCS + SHA-256,
4. submits `anchorBatch` via `web3.py`,
5. waits for the transaction receipt,
6. reads on-chain `getBatch` for `anchored_at` and `anchored_by`,
7. stores `batch_anchors` and returns the record with `already_anchored: false`.

Requires anchoring environment variables (see [05-deployment.md](05-deployment.md)).

Returns:
- `batch_id`
- `anchor_address` — deployed `VeriAgentAnchor` contract address
- `tx_hash`
- `block_number`
- `anchored_at` — on-chain Unix timestamp from `getBatch`
- `anchored_by` — on-chain address that submitted `anchorBatch`
- `chain_id`
- `already_anchored`

Returns `503 Service Unavailable` when anchoring configuration is missing or invalid.

Returns `502 Bad Gateway` when the anchor transaction is mined but reverts (`receipt.status == 0`). No SQLite anchor record is stored in that case.

## GET /audit/batches/{batch_id}/anchor

Returns the SQLite anchor record for a batch.

Returns `404 Not Found` when no local anchor record exists (anchoring has not been performed or recorded yet).

## POST /audit/merkle/verify

Verifies that an event hash is included in a Merkle batch root using an inclusion proof.

Request body:
- `event_hash`
- `merkle_root`
- `proof` — ordered list of `{ "sibling": "...", "side": "left" | "right" }` steps

Returns:
- `verified: true` if the proof resolves to the supplied root
- `verified: false` otherwise

## POST /agents/register

Registers an agent in the DID-based agent registry. **Admin-protected.**

Requires header:
- `X-VeriAgent-Admin-Key` — must match `VERIAGENT_ADMIN_API_KEY`

Request body:
- `agent_did` — must be a valid Ed25519 `did:key` (`did:key:z...`)
- `agent_name`
- `agent_type` — e.g. `llm-agent`
- `description` — optional
- `verification_method` — must equal `{agent_did}#{multibase_value}` (e.g. `did:key:z6Mk...#z6Mk...`)
- `public_key` — base64-encoded raw 32-byte Ed25519 public key; must match the key encoded in `agent_did`

Behavior:
1. validates `agent_did` is a decodable Ed25519 `did:key`, that `public_key` matches the DID-encoded key, and that `verification_method` is derived correctly,
2. generates a per-agent API key with prefix `va_agent_`,
3. stores only the SHA-256 hash of the API key,
4. sets `status` to `active`,
5. returns agent metadata plus the raw `api_key` **once** in the response.

Returns:
- `agent_did`
- `agent_name`
- `agent_type`
- `description`
- `verification_method`
- `public_key`
- `status`
- `created_at`
- `api_key` — shown only at registration time

Returns `401 Unauthorized` when the admin key is missing or invalid.

Returns `400 Bad Request` for invalid `agent_did`, mismatched `public_key`, or incorrect `verification_method`. Legacy `did:key:demo:...` identifiers are rejected.

`did:key` does not support key rotation by itself. Agent revocation and status are handled by VeriAgent's internal agent registry, not by DID resolution over the network.

Returns `409 Conflict` when `agent_did` is already registered.

## GET /agents/{agent_did}

Returns stored agent metadata. **Admin-protected** in Phase 6A.

Requires header:
- `X-VeriAgent-Admin-Key` — must match `VERIAGENT_ADMIN_API_KEY`

Returns:
- `agent_did`
- `agent_name`
- `agent_type`
- `description`
- `verification_method`
- `public_key`
- `status`
- `created_at`

Never returns `api_key` or `api_key_hash`.

Returns `401 Unauthorized` when the admin key is missing or invalid.

Returns `404 Not Found` when the agent is not registered.