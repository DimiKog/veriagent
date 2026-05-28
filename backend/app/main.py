from fastapi import FastAPI

from app.hashing import hash_event
from app.models import AuditEvent

app = FastAPI(title="VeriAgent API", version="0.1.0")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "veriagent",
        "version": "0.1.0",
    }


@app.post("/audit/hash")
def create_event_hash(event: AuditEvent):
    return {
        "event_id": event.event_id,
        "event_hash": hash_event(event),
        "canonicalization": "RFC8785-JCS",
        "hash_algorithm": "SHA-256",
    }