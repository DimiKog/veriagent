from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    event_id: str
    agent_id: str
    task_id: str
    model_name: str
    tool_calls: list[str] = Field(default_factory=list)
    input_hash: str
    output_hash: str
    policy_version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] | None = None


class SignedAuditEventRequest(AuditEvent):
    verification_method: str | None = None
    signature: str | None = None

    def unsigned_event(self) -> AuditEvent:
        return AuditEvent(
            **self.model_dump(exclude={"verification_method", "signature"})
        )


class IngestionReceipt(BaseModel):
    event_id: str
    event_hash: str
    created_at: str
    signature: str
    algorithm: str = "HMAC-SHA256"


class StoreEventResponse(BaseModel):
    event_id: str
    event_hash: str
    created_at: str
    receipt: IngestionReceipt


class StoredEventResponse(BaseModel):
    event_id: str
    event_hash: str
    canonical_event_json: str
    created_at: str
    verification_method: str | None = None
    signature_algorithm: str | None = None


class VerifyResponse(BaseModel):
    event_id: str
    verified: bool
    computed_hash: str
    stored_hash: str | None = None
    canonicalization: str = "RFC8785-JCS"
    hash_algorithm: str = "SHA-256"


class MerkleProofStep(BaseModel):
    sibling: str
    side: Literal["left", "right"]


class MerkleVerifyRequest(BaseModel):
    event_hash: str
    merkle_root: str
    proof: list[MerkleProofStep]


class MerkleVerifyResponse(BaseModel):
    event_hash: str
    merkle_root: str
    verified: bool


class BatchResponse(BaseModel):
    batch_id: str
    merkle_root: str
    event_count: int
    created_at: str
    event_hashes: list[str] = Field(default_factory=list)


class BatchProofResponse(BaseModel):
    batch_id: str
    event_id: str
    event_hash: str
    merkle_root: str
    proof: list[MerkleProofStep]


class BatchAnchorRecord(BaseModel):
    batch_id: str
    anchor_address: str
    tx_hash: str
    block_number: int
    anchored_at: int
    anchored_by: str
    chain_id: int


class AnchorBatchResponse(BatchAnchorRecord):
    already_anchored: bool


class RegisterAgentRequest(BaseModel):
    agent_did: str
    agent_name: str
    agent_type: str
    description: str | None = None
    verification_method: str
    public_key: str


class RegisterAgentResponse(BaseModel):
    agent_did: str
    agent_name: str
    agent_type: str
    description: str | None = None
    verification_method: str
    public_key: str
    status: str
    created_at: str
    api_key: str


class AgentResponse(BaseModel):
    agent_did: str
    agent_name: str
    agent_type: str
    description: str | None = None
    verification_method: str
    public_key: str
    status: str
    created_at: str


class CreateRegistrationRequest(BaseModel):
    agent_did: str
    agent_name: str
    agent_type: str
    description: str | None = None
    verification_method: str
    public_key: str
    organization_name: str
    contact_email: str
    use_case_summary: str


class RegistrationProofPayload(BaseModel):
    purpose: str
    request_id: str
    agent_did: str
    nonce: str
    issued_at: str
    expires_at: str


class CreateRegistrationRequestResponse(BaseModel):
    request_id: str
    agent_did: str
    challenge_nonce: str
    challenge_expires_at: str
    proof_payload: RegistrationProofPayload


class SubmitRegistrationProofRequest(BaseModel):
    proof_signature: str
    verification_method: str


class SubmitRegistrationProofResponse(BaseModel):
    request_id: str
    status: str
    proof_submitted_at: str


class RegistrationRequestStatusResponse(BaseModel):
    request_id: str
    status: str
    agent_did: str
    created_at: str
    challenge_expires_at: str | None = None
    proof_submitted_at: str | None = None
    reviewed_at: str | None = None
    credentials_available: bool = False


AutoAnchorLastStatus = Literal[
    "idle",
    "no_events",
    "below_threshold",
    "batch_created",
    "anchor_succeeded",
    "anchor_failed",
]


class OpsStatusResponse(BaseModel):
    service: str
    version: str
    auto_anchor_enabled: bool
    interval_seconds: int
    min_events: int
    scheduler_running: bool
    last_run_at: str | None = None
    last_status: AutoAnchorLastStatus
    last_batch_id: str | None = None
    last_anchor_tx: str | None = None
    last_error: str | None = None