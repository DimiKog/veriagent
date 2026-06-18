import json

import pytest
from eth_typing import ChecksumAddress
from fastapi.testclient import TestClient

from app.anchoring import AnchoringConfig, OnchainBatch
from app.auto_anchor_scheduler import (
    AutoAnchorConfig,
    get_auto_anchor_ops_status,
    reset_scheduler_state_for_tests,
    run_auto_anchor_cycle,
)
from app.hashing import canonicalize_event, hash_event
from app.main import API_VERSION, app
from app.models import AuditEvent
from app.storage import create_batch_from_unbatched, store_audit_event
from tests.support import sample_event_payload

client = TestClient(app)

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xC034625CAd2fc3143C52E33d7A5fdbe864C3FfCb")
FAKE_TX_HASH = "0x" + "ef" * 32
FAKE_BLOCK_NUMBER = 42
FAKE_CHAIN_TIMESTAMP = 1_760_000_000

EXPECTED_FIELDS = {
    "service",
    "version",
    "auto_anchor_enabled",
    "interval_seconds",
    "min_events",
    "scheduler_running",
    "last_run_at",
    "last_status",
    "last_batch_id",
    "last_anchor_tx",
    "last_error",
}

SECRET_MARKERS = (
    "super-secret-receipt-value",
    "super-secret-admin-value",
    "https://secret-rpc.example/rpc/",
    "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "VERIAGENT_RPC_URL",
    "VERIAGENT_ANCHOR_PRIVATE_KEY",
    "VERIAGENT_RECEIPT_SECRET",
    "VERIAGENT_ADMIN_API_KEY",
)


@pytest.fixture(autouse=True)
def reset_scheduler_state():
    reset_scheduler_state_for_tests()
    yield
    reset_scheduler_state_for_tests()


def test_ops_status_returns_expected_fields():
    response = client.get("/ops/status")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == EXPECTED_FIELDS
    assert body["service"] == "veriagent"
    assert body["version"] == API_VERSION
    assert body["last_status"] == "idle"
    assert body["last_run_at"] is None
    assert body["last_batch_id"] is None
    assert body["last_anchor_tx"] is None
    assert body["last_error"] is None


def test_ops_status_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("VERIAGENT_RPC_URL", "https://secret-rpc.example/rpc/")
    monkeypatch.setenv(
        "VERIAGENT_ANCHOR_PRIVATE_KEY",
        "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )
    monkeypatch.setenv("VERIAGENT_RECEIPT_SECRET", "super-secret-receipt-value")
    monkeypatch.setenv("VERIAGENT_ADMIN_API_KEY", "super-secret-admin-value")

    response = client.get("/ops/status")
    payload = json.dumps(response.json())

    for marker in SECRET_MARKERS:
        assert marker not in payload


def test_ops_status_reports_scheduler_config(monkeypatch):
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_ENABLED", "true")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_MIN_EVENTS", "5")

    body = get_auto_anchor_ops_status(service="veriagent", version=API_VERSION)

    assert body["auto_anchor_enabled"] is True
    assert body["interval_seconds"] == 120
    assert body["min_events"] == 5
    assert body["scheduler_running"] is False


def test_ops_status_reports_last_scheduler_state_after_mocked_cycle(
    monkeypatch,
    isolated_db,
):
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_ENABLED", "true")
    monkeypatch.setenv("VERIAGENT_AUTO_ANCHOR_MIN_EVENTS", "1")

    event = AuditEvent(**sample_event_payload(event_id="ops-status-event"))
    canonical = canonicalize_event(event).decode("utf-8")
    store_audit_event(event.event_id, canonical, hash_event(event), db_path=isolated_db)

    batch_holder: dict[str, object] = {}
    original_create = create_batch_from_unbatched

    def create_and_capture(*args, **kwargs):
        batch = original_create(*args, **kwargs)
        batch_holder["batch"] = batch

        onchain_batch = OnchainBatch(
            merkle_root=bytes.fromhex(batch.merkle_root),
            event_count=batch.event_count,
            metadata_hash=b"\x03" * 32,
            anchored_at=FAKE_CHAIN_TIMESTAMP,
            anchored_by=ANCHOR_SENDER,
        )

        def fake_anchor_batch(*_args, **_kwargs):
            return FAKE_TX_HASH

        def fake_wait(_tx_hash, **_kwargs):
            return {"blockNumber": FAKE_BLOCK_NUMBER, "status": 1}

        def fake_get_onchain_batch(batch_id, **kwargs):
            return onchain_batch

        monkeypatch.setattr("app.batch_anchoring.anchoring.anchor_batch", fake_anchor_batch)
        monkeypatch.setattr(
            "app.batch_anchoring.anchoring.wait_for_transaction_receipt",
            fake_wait,
        )
        monkeypatch.setattr(
            "app.batch_anchoring.anchoring.get_onchain_batch",
            fake_get_onchain_batch,
        )
        monkeypatch.setattr(
            "app.batch_anchoring.load_anchoring_config",
            lambda: AnchoringConfig(
                rpc_url="http://127.0.0.1:8545",
                chain_id=31337,
                contract_address=ANCHOR_CONTRACT,
                private_key="0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
            ),
        )
        return batch

    monkeypatch.setattr(
        "app.auto_anchor_scheduler.create_batch_from_unbatched",
        create_and_capture,
    )

    run_auto_anchor_cycle(
        db_path=isolated_db,
        config=AutoAnchorConfig(enabled=True, interval_seconds=300, min_events=1),
    )

    response = client.get("/ops/status")
    body = response.json()

    batch = batch_holder["batch"]
    assert body["last_status"] == "anchor_succeeded"
    assert body["last_run_at"] is not None
    assert body["last_batch_id"] == batch.batch_id
    assert body["last_anchor_tx"] == FAKE_TX_HASH
    assert body["last_error"] is None
