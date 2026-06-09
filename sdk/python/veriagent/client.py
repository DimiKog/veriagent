"""HTTP client for submitting signed audit events to VeriAgent."""

from __future__ import annotations

from typing import Any

import httpx

from veriagent.identity import derive_agent_identity
from veriagent.signing import build_signed_event_payload, utc_now_timestamp


class VeriAgentClient:
    def __init__(
        self,
        api_base_url: str,
        agent_api_key: str,
        private_key_base64: str,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.agent_api_key = agent_api_key
        self.private_key_base64 = private_key_base64
        (
            self.public_key_base64,
            self.agent_did,
            self.verification_method,
        ) = derive_agent_identity(private_key_base64)

    def build_signed_payload(
        self,
        event_id: str,
        task_id: str,
        model_name: str,
        tool_calls: list[str],
        input_hash: str,
        output_hash: str,
        policy_version: str,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_timestamp = timestamp if timestamp is not None else utc_now_timestamp()
        return build_signed_event_payload(
            private_key_base64=self.private_key_base64,
            verification_method=self.verification_method,
            event_id=event_id,
            agent_id=self.agent_did,
            task_id=task_id,
            model_name=model_name,
            tool_calls=tool_calls,
            input_hash=input_hash,
            output_hash=output_hash,
            policy_version=policy_version,
            timestamp=event_timestamp,
            metadata=metadata,
        )

    def submit_event(
        self,
        event_id: str,
        task_id: str,
        model_name: str,
        tool_calls: list[str],
        input_hash: str,
        output_hash: str,
        policy_version: str,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self.build_signed_payload(
            event_id=event_id,
            task_id=task_id,
            model_name=model_name,
            tool_calls=tool_calls,
            input_hash=input_hash,
            output_hash=output_hash,
            policy_version=policy_version,
            timestamp=timestamp,
            metadata=metadata,
        )
        response = httpx.post(
            f"{self.api_base_url}/audit/events",
            json=payload,
            headers={"X-VeriAgent-API-Key": self.agent_api_key},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
