import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

# Load backend/.env if present. Existing exported env vars take precedence.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.is_file():
    load_dotenv(_ENV_FILE, override=False)

from app.hashing import canonicalize_event, hash_event
from app.merkle import merkle_proof, verify_inclusion_proof
from app.anchoring import (
    AnchorMetadataMismatchError,
    AnchorReceiptPendingError,
    AnchorReconciliationError,
    AnchorTransactionFailedError,
    AnchoringConfigError,
)
from app.batch_anchoring import BatchNotFoundError, perform_batch_anchor
from app.auth import (
    authenticate_agent,
    generate_agent_api_key,
    hash_agent_api_key,
    require_admin_api_key,
)
from app.models import (
    AgentAuditEventListResponse,
    AgentAuditEventSummary,
    AgentResponse,
    AnchorBatchResponse,
    AuditEvent,
    BatchAnchorRecord,
    BatchProofResponse,
    BatchResponse,
    ClaimRegistrationCredentialsRequest,
    ClaimRegistrationCredentialsResponse,
    EventLifecycleStatusResponse,
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
    RegistrationRequestReviewBody,
    AdminRegistrationRequestSummary,
    AdminRegistrationRequestListResponse,
    ApproveRegistrationRequestResponse,
    RejectRegistrationRequestResponse,
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
    RETRIEVAL_TOKEN_HEADER,
    RegistrationChallengeExpiredError,
    RegistrationProofInvalidError,
    approve_registration_request_by_admin,
    claim_registration_credentials,
    create_registration_request_with_challenge,
    get_registration_request_status,
    hash_client_ip,
    is_registration_enabled,
    list_registration_requests_for_admin,
    reject_registration_request_by_admin,
    submit_registration_request_proof,
)
from app.storage import (
    AgentAlreadyExistsError,
    DuplicatePendingRegistrationError,
    EventAlreadyExistsError,
    NoUnbatchedEventsError,
    RegistrationCredentialsAlreadyClaimedError,
    RegistrationCredentialsNotAvailableError,
    RegistrationProofNotSubmittedError,
    RegistrationRequestExpiredError,
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
    get_event_lifecycle_status,
    init_db,
    list_audit_events_for_agent,
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


API_VERSION = "1.0.0-rc.1"

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
    credentials_claimed = (
        stored.status == "approved" and stored.credentials_retrieved_at is not None
    )
    credentials_available = (
        stored.status == "approved"
        and stored.credentials_retrieved_at is None
        and stored.pending_api_key is not None
    )
    proof_payload = None
    if stored.status == "pending" and stored.proof_submitted_at is None:
        try:
            proof_payload = RegistrationProofPayload(
                **json.loads(stored.proof_payload_json)
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            proof_payload = None
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
        credentials_claimed=credentials_claimed,
        credentials_claimed_at=stored.credentials_retrieved_at
        if credentials_claimed
        else None,
        proof_payload=proof_payload,
    )


def _admin_registration_request_summary(
    stored,
) -> AdminRegistrationRequestSummary:
    return AdminRegistrationRequestSummary(
        request_id=stored.request_id,
        agent_did=stored.agent_did,
        agent_name=stored.agent_name,
        agent_type=stored.agent_type,
        description=stored.description,
        organization_name=stored.organization_name,
        contact_email=stored.contact_email,
        use_case_summary=stored.use_case_summary,
        status=stored.status,
        verification_method=stored.verification_method,
        public_key=stored.public_key,
        challenge_expires_at=stored.challenge_expires_at,
        proof_submitted_at=stored.proof_submitted_at,
        reviewed_by=stored.reviewed_by,
        reviewed_at=stored.reviewed_at,
        review_notes=stored.review_notes,
        approved_agent_did=stored.approved_agent_did,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


def _batch_anchor_record(
    anchor: StoredBatchAnchor,
    *,
    merkle_root: str,
) -> BatchAnchorRecord:
    return BatchAnchorRecord(
        batch_id=anchor.batch_id,
        merkle_root=merkle_root,
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


@app.get("/audit/events", response_model=AgentAuditEventListResponse)
def list_agent_audit_events(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    agent: StoredAgent = Depends(authenticate_agent),
):
    events = list_audit_events_for_agent(
        agent_did=agent.agent_did,
        limit=limit,
        offset=offset,
    )
    return AgentAuditEventListResponse(
        events=[
            AgentAuditEventSummary(
                event_id=event.event_id,
                event_hash=event.event_hash,
                created_at=event.created_at,
                batched=event.batched,
                anchored=event.anchored,
            )
            for event in events
        ]
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


@app.get("/audit/events/{event_id}/status", response_model=EventLifecycleStatusResponse)
def get_event_lifecycle_status_endpoint(event_id: str):
    status = get_event_lifecycle_status(event_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    return EventLifecycleStatusResponse(
        event_id=status.event_id,
        event_hash=status.event_hash,
        created_at=status.created_at,
        batched=status.batched,
        batch_id=status.batch_id,
        merkle_root=status.merkle_root,
        anchored=status.anchored,
        tx_hash=status.tx_hash,
        block_number=status.block_number,
        chain_id=status.chain_id,
        anchored_at=status.anchored_at,
        anchored_by=status.anchored_by,
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
    except AnchorReceiptPendingError as exc:
        raise HTTPException(
            status_code=202,
            detail=f"Anchor transaction submitted; receipt pending: {exc}",
        ) from exc
    except (AnchorMetadataMismatchError, AnchorReconciliationError) as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Anchor reconciliation failed: {exc}",
        ) from exc
    except AnchorTransactionFailedError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Anchor transaction failed: {exc}",
        ) from exc

    record = _batch_anchor_record(
        result.anchor,
        merkle_root=_merkle_root_for_anchor_batch(batch_id),
    )
    return AnchorBatchResponse(**record.model_dump(), already_anchored=result.already_anchored)


def _merkle_root_for_anchor_batch(batch_id: str) -> str:
    batch = get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
    return batch.merkle_root


@app.get("/audit/batches/{batch_id}/anchor", response_model=BatchAnchorRecord)
def get_batch_anchor_record(batch_id: str):
    anchor = get_batch_anchor(batch_id)
    if anchor is None:
        raise HTTPException(
            status_code=404,
            detail=f"Anchor record not found for batch: {batch_id}",
        )

    return _batch_anchor_record(
        anchor,
        merkle_root=_merkle_root_for_anchor_batch(batch_id),
    )


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
    "/registration/requests",
    response_model=AdminRegistrationRequestListResponse,
)
def list_registration_requests_endpoint(
    status: str | None = None,
    _: None = Depends(require_registration_enabled),
    __: None = Depends(require_admin_api_key),
):
    if status is not None and status not in {
        "pending",
        "approved",
        "rejected",
        "expired",
    }:
        raise HTTPException(status_code=400, detail="Invalid registration request status")

    stored_requests = list_registration_requests_for_admin(status=status)

    return AdminRegistrationRequestListResponse(
        requests=[
            _admin_registration_request_summary(stored)
            for stored in stored_requests
        ]
    )


@app.post(
    "/registration/requests/{request_id}/approve",
    response_model=ApproveRegistrationRequestResponse,
)
def approve_registration_request_endpoint(
    request_id: str,
    request: RegistrationRequestReviewBody,
    _: None = Depends(require_registration_enabled),
    __: None = Depends(require_admin_api_key),
):
    try:
        stored_request, stored_agent, retrieval_token = (
            approve_registration_request_by_admin(
                request_id=request_id,
                review_notes=request.review_notes,
            )
        )
    except RegistrationRequestNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Registration request not found: {exc.args[0]}",
        ) from exc
    except RegistrationProofNotSubmittedError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Registration proof not submitted: {exc.args[0]}",
        ) from exc
    except RegistrationRequestExpiredError as exc:
        raise HTTPException(
            status_code=410,
            detail=f"Registration request expired: {exc.args[0]}",
        ) from exc
    except RegistrationRequestNotPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Registration request is not pending: {exc.args[0]}",
        ) from exc
    except AgentAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Agent already registered: {exc.args[0]}",
        ) from exc

    assert stored_request.reviewed_at is not None
    assert stored_request.approved_agent_did is not None
    return ApproveRegistrationRequestResponse(
        request_id=stored_request.request_id,
        status=stored_request.status,
        agent_did=stored_agent.agent_did,
        agent_name=stored_agent.agent_name,
        agent_type=stored_agent.agent_type,
        description=stored_agent.description,
        verification_method=stored_agent.verification_method,
        public_key=stored_agent.public_key,
        agent_status=stored_agent.status,
        created_at=stored_agent.created_at,
        reviewed_at=stored_request.reviewed_at,
        review_notes=stored_request.review_notes,
        approved_agent_did=stored_request.approved_agent_did,
        retrieval_token=retrieval_token,
    )


@app.post(
    "/registration/requests/{request_id}/credentials",
    response_model=ClaimRegistrationCredentialsResponse,
)
def claim_registration_credentials_endpoint(
    request_id: str,
    request: ClaimRegistrationCredentialsRequest,
    _: None = Depends(require_registration_enabled),
    x_veriagent_retrieval_token: str | None = Header(
        None,
        alias=RETRIEVAL_TOKEN_HEADER,
    ),
):
    try:
        stored_request, stored_agent, api_key = claim_registration_credentials(
            request_id=request_id,
            proof_signature=request.proof_signature,
            verification_method=request.verification_method,
            retrieval_token=x_veriagent_retrieval_token,
        )
    except RegistrationRequestNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Registration request not found: {exc.args[0]}",
        ) from exc
    except RegistrationCredentialsAlreadyClaimedError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Registration credentials already claimed: {exc.args[0]}",
        ) from exc
    except RegistrationCredentialsNotAvailableError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Registration credentials not available: {exc.args[0]}",
        ) from exc
    except RegistrationProofInvalidError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return ClaimRegistrationCredentialsResponse(
        request_id=stored_request.request_id,
        agent_did=stored_agent.agent_did,
        api_key=api_key,
        agent_status=stored_agent.status,
        verification_method=stored_agent.verification_method,
    )


@app.post(
    "/registration/requests/{request_id}/reject",
    response_model=RejectRegistrationRequestResponse,
)
def reject_registration_request_endpoint(
    request_id: str,
    request: RegistrationRequestReviewBody,
    _: None = Depends(require_registration_enabled),
    __: None = Depends(require_admin_api_key),
):
    try:
        stored = reject_registration_request_by_admin(
            request_id=request_id,
            review_notes=request.review_notes,
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

    assert stored.reviewed_at is not None
    assert stored.reviewed_by is not None
    return RejectRegistrationRequestResponse(
        request_id=stored.request_id,
        status=stored.status,
        agent_did=stored.agent_did,
        reviewed_at=stored.reviewed_at,
        reviewed_by=stored.reviewed_by,
        review_notes=stored.review_notes,
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
