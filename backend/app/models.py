from datetime import datetime, timezone
from typing import Any

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


class VerifyResponse(BaseModel):
    event_id: str
    verified: bool
    computed_hash: str
    stored_hash: str | None = None
    canonicalization: str = "RFC8785-JCS"
    hash_algorithm: str = "SHA-256"