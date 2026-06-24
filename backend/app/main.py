import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.hashing import canonicalize_event, hash_event
from app.merkle import merkle_proof, verify_inclusion_proof
from app.anchoring import AnchorTransactionFailedError, AnchoringConfigError
from app.batch_anchoring import BatchNotFoundError, perform_batch_anchor
from app.auth import (
    authenticate_agent,
    generate_agent_api_key,
    hash_agent_api_key,
    require_admin_api_key,
)
from app.models import (
    AgentResponse,
    AnchorBatchResponse,
    AuditEvent,
    BatchAnchorRecord,
    BatchProofResponse,
    BatchResponse,
    IngestionReceipt,
    MerkleProofStep,
    MerkleVerifyRequest,
    MerkleVerifyResponse,
    RegisterAgentRequest,
    RegisterAgentResponse,
    CreateRegistrationRequest,
    CreateRegistrationRequestResponse,
    SubmitRegistrationProofRequest,
    SubmitRegistrationProofResponse,
    RegistrationRequestStatusResponse,
    RegistrationProofPayload,
    OpsStatusResponse,
    SignedAuditEventRequest,
    StoreEventResponse,
    StoredEventResponse,
    VerifyResponse,
)
from app.receipts import generate_receipt
from app.signatures import (
    SIGNATURE_ALGORITHM,
    validate_ed25519_did_key_agent,
    verify_signature,
)
from app.auto_anchor_scheduler import get_auto_anchor_ops_status, start_auto_anchor_scheduler, stop_auto_anchor_scheduler
from app.registration import (
    RegistrationChallengeExpiredError,
    RegistrationProofInvalidError,
    create_registration_request_with_challenge,
    get_registration_request_status,
    hash_client_ip,
    is_registration_enabled,
    submit_registration_request_proof,
)
from app.storage import (
    AgentAlreadyExistsError,
    DuplicatePendingRegistrationError,
    EventAlreadyExistsError,
    NoUnbatchedEventsError,
    RegistrationRequestNotFoundError,
    RegistrationRequestNotPendingError,
    StoredAgent,
    StoredBatchAnchor,
    create_batch_from_unbatched,
    get_agent,
    get_audit_event,
    get_batch,
    get_batch_anchor,
    get_batch_event,
    init_db,
    register_agent,
    store_audit_event,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler_task, scheduler_stop = start_auto_anchor_scheduler()
    try:
        yield
    finally:
        await stop_auto_anchor_scheduler(scheduler_task, scheduler_stop)


API_VERSION = "1.0-pre"

app = FastAPI(title="VeriAgent API", version=API_VERSION, lifespan=lifespan)

CORS_ALLOWED_ORIGINS = [
    "https://dimikog.github.io",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "veriagent",
        "version": API_VERSION,
    }


@app.get("/ops/status", response_model=OpsStatusResponse)
def ops_status():
    return get_auto_anchor_ops_status(service="veriagent", version=API_VERSION)


def _agent_response(agent: StoredAgent) -> AgentResponse:
    return AgentResponse(
        agent_did=agent.agent_did,
        agent_name=agent.agent_name,
        agent_type=agent.agent_type,
        description=agent.description,
        verification_method=agent.verification_method,
        public_key=agent.public_key,
        status=agent.status,
        created_at=agent.created_at,
    )


def require_registration_enabled() -> None:
    if not is_registration_enabled():
        raise HTTPException(status_code=404, detail="Registration is not enabled")


def _registration_status_response(
    stored,
) -> RegistrationRequestStatusResponse:
    credentials_available = (
        stored.status == "approved"
        and stored.retrieval_token_hash is not None
        and stored.credentials_retrieved_at is None
    )
    return RegistrationRequestStatusResponse(
        request_id=stored.request_id,
        status=stored.status,
        agent_did=stored.agent_did,
        created_at=stored.created_at,
        challenge_expires_at=stored.challenge_expires_at
        if stored.status == "pending"
        else None,
        proof_submitted_at=stored.proof_submitted_at,
        reviewed_at=stored.reviewed_at,
        credentials_available=credentials_available,
    )


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
def store_event(
    event: SignedAuditEventRequest,
    agent: StoredAgent = Depends(authenticate_agent),
):
    if not event.signature:
        raise HTTPException(status_code=400, detail="signature is required")
    if not event.verification_method:
        raise HTTPException(status_code=400, detail="verification_method is required")

    unsigned_event = event.unsigned_event()

    if not hmac.compare_digest(
        unsigned_event.agent_id.encode("utf-8"),
        agent.agent_did.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=403,
            detail="event.agent_id does not match authenticated agent",
        )

    if not hmac.compare_digest(
        event.verification_method.encode("utf-8"),
        agent.verification_method.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=403,
            detail="verification_method does not match registered agent",
        )

    canonical_bytes = canonicalize_event(unsigned_event)
    canonical_event_json = canonical_bytes.decode("utf-8")
    event_hash = hash_event(unsigned_event)

    if not verify_signature(agent.public_key, canonical_bytes, event.signature):
        raise HTTPException(status_code=403, detail="Invalid event signature")

    try:
        stored = store_audit_event(
            event_id=unsigned_event.event_id,
            canonical_event_json=canonical_event_json,
            event_hash=event_hash,
            signature=event.signature,
            verification_method=event.verification_method,
            signature_algorithm=SIGNATURE_ALGORITHM,
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
        verification_method=stored.verification_method,
        signature_algorithm=stored.signature_algorithm,
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
def create_batch(_: None = Depends(require_admin_api_key)):
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


# Register specific /audit/batches/{batch_id}/... routes before GET /audit/batches/{batch_id}
# so the generic batch path does not shadow /anchor or /proof/{event_id}.


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
def anchor_batch_on_chain(batch_id: str, _: None = Depends(require_admin_api_key)):
    try:
        result = perform_batch_anchor(batch_id)
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Batch not found: {exc.args[0]}") from exc
    except AnchoringConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Anchoring is not configured: {exc}",
        ) from exc
    except AnchorTransactionFailedError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Anchor transaction failed: {exc}",
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


@app.post("/agents/register", response_model=RegisterAgentResponse)
def register_agent_endpoint(
    request: RegisterAgentRequest,
    _: None = Depends(require_admin_api_key),
):
    try:
        validate_ed25519_did_key_agent(
            request.agent_did,
            request.public_key,
            request.verification_method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    api_key = generate_agent_api_key()
    api_key_hash = hash_agent_api_key(api_key)

    try:
        stored = register_agent(
            agent_did=request.agent_did,
            agent_name=request.agent_name,
            agent_type=request.agent_type,
            description=request.description,
            verification_method=request.verification_method,
            public_key=request.public_key,
            api_key_hash=api_key_hash,
            status="active",
        )
    except AgentAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Agent already registered: {exc.args[0]}",
        ) from exc

    return RegisterAgentResponse(
        **_agent_response(stored).model_dump(),
        api_key=api_key,
    )


@app.post(
    "/registration/requests",
    response_model=CreateRegistrationRequestResponse,
)
def create_registration_request_endpoint(
    request: CreateRegistrationRequest,
    http_request: Request,
    _: None = Depends(require_registration_enabled),
):
    client_ip = http_request.client.host if http_request.client else None
    try:
        stored, proof_payload = create_registration_request_with_challenge(
            agent_did=request.agent_did,
            agent_name=request.agent_name,
            agent_type=request.agent_type,
            description=request.description,
            organization_name=request.organization_name,
            contact_email=request.contact_email,
            use_case_summary=request.use_case_summary,
            verification_method=request.verification_method,
            public_key=request.public_key,
            client_ip_hash=hash_client_ip(client_ip),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail="A registration request cannot be created for this agent DID",
        ) from exc
    except DuplicatePendingRegistrationError as exc:
        raise HTTPException(
            status_code=409,
            detail="A registration request cannot be created for this agent DID",
        ) from exc

    return CreateRegistrationRequestResponse(
        request_id=stored.request_id,
        agent_did=stored.agent_did,
        challenge_nonce=stored.challenge_nonce,
        challenge_expires_at=stored.challenge_expires_at,
        proof_payload=RegistrationProofPayload(**proof_payload),
    )


@app.post(
    "/registration/requests/{request_id}/proof",
    response_model=SubmitRegistrationProofResponse,
)
def submit_registration_proof_endpoint(
    request_id: str,
    request: SubmitRegistrationProofRequest,
    _: None = Depends(require_registration_enabled),
):
    try:
        stored = submit_registration_request_proof(
            request_id=request_id,
            proof_signature=request.proof_signature,
            verification_method=request.verification_method,
        )
    except RegistrationRequestNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Registration request not found: {exc.args[0]}",
        ) from exc
    except RegistrationRequestNotPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Registration request is not pending: {exc.args[0]}",
        ) from exc
    except RegistrationChallengeExpiredError as exc:
        raise HTTPException(
            status_code=410,
            detail=f"Registration challenge expired: {exc.args[0]}",
        ) from exc
    except RegistrationProofInvalidError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    assert stored.proof_submitted_at is not None
    return SubmitRegistrationProofResponse(
        request_id=stored.request_id,
        status=stored.status,
        proof_submitted_at=stored.proof_submitted_at,
    )


@app.get(
    "/registration/requests/{request_id}",
    response_model=RegistrationRequestStatusResponse,
)
def get_registration_request_endpoint(
    request_id: str,
    _: None = Depends(require_registration_enabled),
):
    try:
        stored = get_registration_request_status(request_id)
    except RegistrationRequestNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Registration request not found: {exc.args[0]}",
        ) from exc

    return _registration_status_response(stored)


@app.get("/agents/{agent_did}", response_model=AgentResponse)
def get_agent_endpoint(
    agent_did: str,
    _: None = Depends(require_admin_api_key),
):
    agent = get_agent(agent_did)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_did}")

    return _agent_response(agent)


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
