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