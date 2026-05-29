from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.hashing import canonicalize_event, hash_event
from app.merkle import merkle_proof, verify_inclusion_proof
from app.anchoring import AnchoringConfigError
from app.batch_anchoring import BatchNotFoundError, perform_batch_anchor
from app.models import (
    AnchorBatchResponse,
    AuditEvent,
    BatchAnchorRecord,
    BatchProofResponse,
    BatchResponse,
    IngestionReceipt,
    MerkleProofStep,
    MerkleVerifyRequest,
    MerkleVerifyResponse,
    StoreEventResponse,
    StoredEventResponse,
    VerifyResponse,
)
from app.receipts import generate_receipt
from app.storage import (
    EventAlreadyExistsError,
    NoUnbatchedEventsError,
    StoredBatchAnchor,
    create_batch_from_unbatched,
    get_audit_event,
    get_batch,
    get_batch_anchor,
    get_batch_event,
    init_db,
    store_audit_event,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="VeriAgent API", version="0.5.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "veriagent",
        "version": "0.5.0",
    }


def _batch_anchor_record(anchor: StoredBatchAnchor) -> BatchAnchorRecord:
    return BatchAnchorRecord(
        batch_id=anchor.batch_id,
        anchor_address=anchor.anchor_address,
        tx_hash=anchor.tx_hash,
        block_number=anchor.block_number,
        anchored_at=anchor.anchored_at,
        anchored_by=anchor.anchored_by,
        chain_id=anchor.chain_id,
    )


@app.post("/audit/hash")
def create_event_hash(event: AuditEvent):
    return {
        "event_id": event.event_id,
        "event_hash": hash_event(event),
        "canonicalization": "RFC8785-JCS",
        "hash_algorithm": "SHA-256",
    }


@app.post("/audit/events", response_model=StoreEventResponse)
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

    receipt_data = generate_receipt(
        event_id=stored.event_id,
        event_hash=stored.event_hash,
        created_at=stored.created_at,
    )
    receipt = IngestionReceipt(**receipt_data)

    return StoreEventResponse(
        event_id=stored.event_id,
        event_hash=stored.event_hash,
        created_at=stored.created_at,
        receipt=receipt,
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


@app.post("/audit/batches", response_model=BatchResponse)
def create_batch():
    try:
        batch = create_batch_from_unbatched()
    except NoUnbatchedEventsError as exc:
        raise HTTPException(
            status_code=400,
            detail="No unbatched events available to create a batch",
        ) from exc

    return BatchResponse(
        batch_id=batch.batch_id,
        merkle_root=batch.merkle_root,
        event_count=batch.event_count,
        created_at=batch.created_at,
        event_hashes=batch.event_hashes,
    )


@app.get("/audit/batches/{batch_id}/proof/{event_id}", response_model=BatchProofResponse)
def get_batch_inclusion_proof(batch_id: str, event_id: str):
    batch = get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

    stored = get_audit_event(event_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    membership = get_batch_event(batch_id, event_id)
    if membership is None or stored.event_hash not in batch.event_hashes:
        raise HTTPException(
            status_code=404,
            detail=f"Event not included in batch: {event_id}",
        )

    proof_steps = merkle_proof(batch.event_hashes, stored.event_hash)
    proof = [MerkleProofStep(sibling=sibling, side=side) for sibling, side in proof_steps]

    return BatchProofResponse(
        batch_id=batch.batch_id,
        event_id=stored.event_id,
        event_hash=stored.event_hash,
        merkle_root=batch.merkle_root,
        proof=proof,
    )


@app.post("/audit/batches/{batch_id}/anchor", response_model=AnchorBatchResponse)
def anchor_batch_on_chain(batch_id: str):
    try:
        result = perform_batch_anchor(batch_id)
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Batch not found: {exc.args[0]}") from exc
    except AnchoringConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Anchoring is not configured: {exc}",
        ) from exc

    record = _batch_anchor_record(result.anchor)
    return AnchorBatchResponse(**record.model_dump(), already_anchored=result.already_anchored)


@app.get("/audit/batches/{batch_id}/anchor", response_model=BatchAnchorRecord)
def get_batch_anchor_record(batch_id: str):
    anchor = get_batch_anchor(batch_id)
    if anchor is None:
        raise HTTPException(
            status_code=404,
            detail=f"Anchor record not found for batch: {batch_id}",
        )

    return _batch_anchor_record(anchor)


@app.get("/audit/batches/{batch_id}", response_model=BatchResponse)
def get_batch_by_id(batch_id: str):
    batch = get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

    return BatchResponse(
        batch_id=batch.batch_id,
        merkle_root=batch.merkle_root,
        event_count=batch.event_count,
        created_at=batch.created_at,
        event_hashes=batch.event_hashes,
    )


@app.post("/audit/merkle/verify", response_model=MerkleVerifyResponse)
def verify_merkle_inclusion(request: MerkleVerifyRequest):
    proof_steps = [(step.sibling, step.side) for step in request.proof]
    verified = verify_inclusion_proof(
        event_hash=request.event_hash,
        merkle_root=request.merkle_root,
        proof=proof_steps,
    )

    return MerkleVerifyResponse(
        event_hash=request.event_hash,
        merkle_root=request.merkle_root,
        verified=verified,
    )
