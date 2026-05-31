import hashlib
import hmac
import os
import secrets

from fastapi import Header, HTTPException

ADMIN_API_KEY_ENV = "VERIAGENT_ADMIN_API_KEY"
ADMIN_API_KEY_HEADER = "X-VeriAgent-Admin-Key"
AGENT_API_KEY_PREFIX = "va_agent_"


def get_admin_api_key() -> str | None:
    value = os.environ.get(ADMIN_API_KEY_ENV, "").strip()
    return value or None


def verify_admin_api_key(provided: str | None, expected: str | None) -> bool:
    if not expected:
        return False
    provided_key = provided or ""
    return hmac.compare_digest(provided_key.encode("utf-8"), expected.encode("utf-8"))


def require_admin_api_key(
    x_veriagent_admin_key: str | None = Header(None, alias=ADMIN_API_KEY_HEADER),
) -> None:
    if not verify_admin_api_key(x_veriagent_admin_key, get_admin_api_key()):
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key")


def generate_agent_api_key() -> str:
    return AGENT_API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_agent_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
