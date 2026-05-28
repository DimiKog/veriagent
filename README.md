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

See [docs/03-api.md](docs/03-api.md) for endpoint details.

## Local Run

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
uvicorn app.main:app --reload
```

Open the API documentation at:

```text
http://127.0.0.1:8000/docs
```

## Manual Verification Flow

1. Store an event using `POST /audit/events`.
2. Retrieve it using `GET /audit/events/{event_id}`.
3. Verify the same event using `POST /audit/verify`.
4. Modify one field, such as `output_hash`.
5. Verify again.

Expected result:

- Unchanged event: `verified: true`
- Modified event: `verified: false`

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
