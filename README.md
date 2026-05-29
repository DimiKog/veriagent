# VeriAgent

VeriAgent is a verifiable audit commitment layer for AI-agent actions.

It records structured AI-agent audit events, canonicalizes them using RFC 8785 / JCS, computes SHA-256 commitments, stores them locally, and verifies submitted events against stored commitments.

## Current MVP Status

VeriAgent currently supports:

- RFC 8785 / JCS canonicalization of AI-agent audit events
- SHA-256 event commitments
- Hash-only endpoint (`POST /audit/hash`) without persistence
- SQLite-backed local event storage
- Duplicate event detection
- Audit event retrieval
- Verification of submitted events against stored commitments
- Tamper detection
- HMAC-SHA256 signed ingestion receipts on event storage
- Local Merkle batching over stored event hashes with inclusion proofs

See [docs/03-api.md](docs/03-api.md) for endpoint details and [docs/04-testing.md](docs/04-testing.md) for the test guide.

## Local Run

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export VERIAGENT_RECEIPT_SECRET="replace-with-a-long-random-secret"
python -m pytest
uvicorn app.main:app --reload
```

For local-only runs you may omit `VERIAGENT_RECEIPT_SECRET`; the backend uses a clearly marked development fallback secret.

Open the API documentation at:

```text
http://127.0.0.1:8000/docs
```

## Manual Verification Flow

1. Store an event using `POST /audit/events` and save the returned `receipt`.
2. Retrieve it using `GET /audit/events/{event_id}`.
3. Verify the receipt signature matches `event_id`, `event_hash`, and `created_at`.
4. Verify the same event using `POST /audit/verify`.
5. Modify one field, such as `output_hash`, and verify again.
6. Create a Merkle batch with `POST /audit/batches`.
7. Verify inclusion with `POST /audit/merkle/verify` using the batch root and proof.

Expected result:

- Valid receipt signature after store
- Unchanged event: `verified: true`
- Modified event: `verified: false`
- Valid Merkle proof: `verified: true`
- Tampered Merkle proof: `verified: false`

## Development Workflow

Local development is the source of truth. The VM is used only as a deployment target.

Recommended workflow:

1. Develop locally.
2. Run tests locally.
3. Commit and push to GitHub.
4. Pull the latest version on the VM.
5. Install or update dependencies.
6. Run tests on the VM.
7. Restart the backend service.

## Commit Checklist

Before committing, run:

```bash
git status
```

Do not commit:

- `backend/.venv/`
- `backend/data/veriagent.db`
- `.env`
- `__pycache__/`
- `.pytest_cache/`

Then commit and push:

```bash
git add .
git status
git commit -m "Your message here"
git push
```
