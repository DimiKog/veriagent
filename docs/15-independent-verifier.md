# VeriAgent Independent Verifier CLI

**Status:** Implemented in `sdk/python` (v1.0.0-rc.1).

The independent verifier lets third parties validate VeriAgent audit evidence **without trusting the VeriAgent API** for cryptographic checks. Verification runs entirely from local JSON files using the same rules as the backend:

- RFC 8785 / JCS canonicalization of the **unsigned** audit event
- SHA-256 event commitment
- Ed25519 signature verification against the public key encoded in `event.agent_id` (`did:key`)
- Merkle inclusion proof over sorted batch leaves
- Anchor metadata consistency (`merkle_root`, `tx_hash`, `block_number`, `chain_id`, `anchored_at`)

No private keys, agent API keys, admin keys, or SQLite access are required.

---

## Install

```bash
cd sdk/python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `veriagent` console script.

---

## Offline verification (recommended)

Prepare three JSON files:

### 1. `event.json` — signed audit event

The verifier hashes the **unsigned** event (`signature` and `verification_method` are stripped). It also requires a valid Ed25519 `signature` over the JCS-canonicalized unsigned bytes, verified against the public key encoded in `agent_id` (`did:key:z...`):

```json
{
  "event_id": "event-proof-1",
  "agent_id": "did:key:z6Mk...",
  "task_id": "task-001",
  "model_name": "demo-model",
  "tool_calls": ["search", "calculator"],
  "input_hash": "sha256:input123",
  "output_hash": "sha256:output456",
  "policy_version": "policy-v0.1",
  "timestamp": "2026-05-26T18:00:00Z",
  "metadata": {"purpose": "verifier-test"},
  "verification_method": "did:key:z6Mk...#z6Mk...",
  "signature": "<base64 Ed25519 signature>"
}
```

### 2. `proof.json` — Merkle proof (`BatchProofResponse` shape)

From `GET /audit/batches/{batch_id}/proof/{event_id}`:

```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_id": "event-proof-1",
  "event_hash": "<64 hex>",
  "merkle_root": "<64 hex>",
  "proof": [
    {"sibling": "<64 hex>", "side": "left"}
  ]
}
```

### 3. `anchor.json` — anchor bundle

From `GET /audit/batches/{batch_id}/anchor` (includes `merkle_root` from the local batch record):

```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "merkle_root": "<64 hex>",
  "anchor_address": "0x30546417E83A0C96bf87BEdfEe59De8FBdf1187A",
  "tx_hash": "0xabab...",
  "block_number": 42,
  "anchored_at": 1700000000,
  "anchored_by": "0xf39F...",
  "chain_id": 424242
}
```

Run:

```bash
veriagent verify --event event.json --proof proof.json --anchor anchor.json
```

Expected human output:

```text
PASS
  [ok] event_canonical_hash: Computed SHA-256 over RFC8785/JCS canonical unsigned event
  [ok] proof_event_hash_match: Computed event hash matches proof.event_hash
  [ok] ed25519_signature: Ed25519 signature verified against did:key-derived public key
  [ok] merkle_inclusion_proof: Merkle proof reconstructs proof.merkle_root
  [ok] anchor_merkle_root_match: proof.merkle_root matches anchor.merkle_root
  [ok] batch_id_match: proof.batch_id matches anchor.batch_id
  [ok] anchor_metadata_present: Anchor metadata present: tx_hash, block_number, chain_id, anchored_at
event_hash=...
merkle_root=...
batch_id=...
anchor_tx_hash=0x...
```

Structured JSON:

```bash
veriagent verify --event event.json --proof proof.json --anchor anchor.json --json
```

Exit codes: `0` = PASS, `1` = verification failed, `2` = malformed input or fetch error.

---

## Optional API-assisted fetch

The verifier can **fetch** public read-only evidence, then perform the same local checks. Fetched responses are not trusted for verification logic — only used as input to local recomputation.

```bash
veriagent verify \
  --event event.json \
  --api-base-url https://veriagent.dimikog.org \
  --batch-id 550e8400-e29b-41d4-a716-446655440000 \
  --event-id event-proof-1
```

When `--proof` / `--anchor` are omitted, the CLI fetches:

- `GET /audit/batches/{batch_id}/proof/{event_id}`
- `GET /audit/batches/{batch_id}/anchor`

To discover `batch_id` from `event_id` alone, use:

- `GET /audit/events/{event_id}/status`

That endpoint returns `batched`, `anchored`, `batch_id`, and anchor metadata without exposing API keys, private keys, or registration data.

You can also fetch the stored event canonical JSON:

```bash
veriagent verify \
  --event stored-event-wrapper.json \
  --proof proof.json \
  --anchor anchor.json \
  --api-base-url https://veriagent.dimikog.org \
  --event-id event-proof-1
```

---

## Verification steps

| Step | Check |
| --- | --- |
| 1 | Canonicalize unsigned event with RFC8785/JCS |
| 2 | Compute SHA-256 `event_hash` |
| 3 | Compare computed hash to `proof.event_hash` |
| 4 | Verify Ed25519 `signature` against `did:key` public key from `agent_id` |
| 5 | Verify Merkle proof reconstructs `proof.merkle_root` |
| 6 | Compare `proof.merkle_root` to `anchor.merkle_root` |
| 7 | Require `anchor.tx_hash`, `block_number`, `chain_id`, `anchored_at` |
| 8 | Emit `PASS` / `FAIL` (and optional `--json` report) |

---

## Python API

```python
from veriagent import verify_audit_evidence

result = verify_audit_evidence(event_payload, proof_payload, anchor_payload)
assert result.verified
print(result.to_dict())
```

Modules:

| Module | Role |
| --- | --- |
| `veriagent/verifier.py` | Orchestration, CLI helpers, optional HTTP fetch |
| `veriagent/hashing.py` | JCS + SHA-256 over unsigned events |
| `veriagent/signatures.py` | `did:key` decode and Ed25519 verification |
| `veriagent/merkle.py` | Merkle root and inclusion proof verification |
| `veriagent_cli.py` | `veriagent` console entry point |

---

## What the verifier does not do (yet)

- On-chain RPC `getBatch` comparison (optional future `--rpc-url`)
- HMAC ingestion receipt verification (separate trust boundary from commitment chain)

These are intentionally out of scope for the initial offline evidence bundle verifier.

---

## Tests

```bash
cd sdk/python
python -m pytest tests/test_verifier.py -v
```

Coverage includes valid bundles, invalid or missing signatures, tampered events, bad proofs, mismatched Merkle roots, and malformed JSON inputs.

---

## Related docs

- [03-api.md](03-api.md) — public proof and anchor endpoints
- [04-testing.md](04-testing.md) — backend verification tests
- [08-architecture.md](08-architecture.md) — trust boundaries
- [13-commercial-readiness-roadmap.md](13-commercial-readiness-roadmap.md) — pilot priority #2 (implemented)
