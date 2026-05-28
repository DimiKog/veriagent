from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.hashing import canonicalize_event, hash_event
from app.models import AuditEvent, StoredEventResponse, VerifyResponse
from app.storage import EventAlreadyExistsError, get_audit_event, init_db, store_audit_event


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="VeriAgent API", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "veriagent",
        "version": "0.2.0",
    }


@app.post("/audit/hash")
def create_event_hash(event: AuditEvent):
    return {
        "event_id": event.event_id,
        "event_hash": hash_event(event),
        "canonicalization": "RFC8785-JCS",
        "hash_algorithm": "SHA-256",
    }


@app.post("/audit/events", response_model=StoredEventResponse)
def store_event(event: AuditEvent):
    canonical_bytes = canonicalize_event(event)
    canonical_event_json = canonical_bytes.decode("utf-8")
    event_hash = hash_event(event)

    try:
        stored = store_audit_event(
            event_id=event.event_id,
            canonical_event_json=canonical_event_json,
            event_hash=event_hash,
        )
    except EventAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Event already stored: {exc.args[0]}",
        ) from exc

    return StoredEventResponse(
        event_id=stored.event_id,
        event_hash=stored.event_hash,
        canonical_event_json=stored.canonical_event_json,
        created_at=stored.created_at,
    )


@app.get("/audit/events/{event_id}", response_model=StoredEventResponse)
def get_stored_event(event_id: str):
    stored = get_audit_event(event_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    return StoredEventResponse(
        event_id=stored.event_id,
        event_hash=stored.event_hash,
        canonical_event_json=stored.canonical_event_json,
        created_at=stored.created_at,
    )


@app.post("/audit/verify", response_model=VerifyResponse)
def verify_event(event: AuditEvent):
    stored = get_audit_event(event.event_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Event not found: {event.event_id}")

    computed_hash = hash_event(event)
    verified = computed_hash == stored.event_hash

    return VerifyResponse(
        event_id=event.event_id,
        verified=verified,
        computed_hash=computed_hash,
        stored_hash=stored.event_hash,
    )
