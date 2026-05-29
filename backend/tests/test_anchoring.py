import json
import os

import pytest

from app.anchoring import (
    CHAIN_ID_ENV,
    CONTRACT_ADDRESS_ENV,
    DEFAULT_ABI_PATH,
    PRIVATE_KEY_ENV,
    RPC_URL_ENV,
    AnchoringConfigError,
    batch_id_to_bytes32,
    load_anchoring_config,
    load_contract_abi,
    metadata_hash_for_batch,
)

SAMPLE_METADATA = {
    "batch_id": "550e8400-e29b-41d4-a716-446655440000",
    "merkle_root": "a" * 64,
    "event_count": 2,
    "created_at": "2026-05-29T12:00:00+00:00",
    "event_hashes": [
        "1111111111111111111111111111111111111111111111111111111111111111",
        "2222222222222222222222222222222222222222222222222222222222222222",
    ],
}


def test_batch_id_to_bytes32_is_deterministic():
    batch_id = "batch-abc-123"
    assert batch_id_to_bytes32(batch_id) == batch_id_to_bytes32(batch_id)
    assert len(batch_id_to_bytes32(batch_id)) == 32


def test_different_batch_ids_produce_different_bytes32():
    first = batch_id_to_bytes32("batch-one")
    second = batch_id_to_bytes32("batch-two")
    assert first != second


def test_metadata_hash_for_batch_is_deterministic():
    first = metadata_hash_for_batch(**SAMPLE_METADATA)
    second = metadata_hash_for_batch(**SAMPLE_METADATA)
    assert first == second
    assert len(first) == 32


def test_load_contract_abi_from_backend_abi_file():
    abi = load_contract_abi()
    assert DEFAULT_ABI_PATH.is_file()
    assert isinstance(abi, list)
    assert len(abi) >= 1

    function_names = {
        entry["name"] for entry in abi if entry.get("type") == "function" and "name" in entry
    }
    assert function_names >= {"anchorBatch", "getBatch", "isAnchored"}


def test_load_contract_abi_accepts_json_array(tmp_path):
    source_abi = load_contract_abi()
    abi_path = tmp_path / "VeriAgentAnchor.json"
    abi_path.write_text(json.dumps(source_abi), encoding="utf-8")

    loaded = load_contract_abi(abi_path)
    assert loaded == source_abi


def test_load_contract_abi_accepts_foundry_artifact_format(tmp_path):
    source_abi = load_contract_abi()
    abi_path = tmp_path / "artifact.json"
    abi_path.write_text(json.dumps({"abi": source_abi}), encoding="utf-8")

    loaded = load_contract_abi(abi_path)
    assert loaded == source_abi


def test_metadata_hash_changes_when_metadata_changes():
    baseline = metadata_hash_for_batch(**SAMPLE_METADATA)
    changed = metadata_hash_for_batch(
        **{**SAMPLE_METADATA, "event_count": SAMPLE_METADATA["event_count"] + 1}
    )
    assert baseline != changed


@pytest.mark.parametrize(
    "env_name",
    [
        RPC_URL_ENV,
        CHAIN_ID_ENV,
        CONTRACT_ADDRESS_ENV,
        PRIVATE_KEY_ENV,
    ],
)
def test_missing_single_env_var_raises_clear_error(monkeypatch, env_name):
    monkeypatch.setenv(RPC_URL_ENV, "http://127.0.0.1:8545")
    monkeypatch.setenv(CHAIN_ID_ENV, "31337")
    monkeypatch.setenv(
        CONTRACT_ADDRESS_ENV, "0x5FbDB2315678afecb367f032d93F642f64180aa3"
    )
    monkeypatch.setenv(
        PRIVATE_KEY_ENV,
        "0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
    )
    monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(AnchoringConfigError, match=env_name):
        load_anchoring_config()


def test_missing_all_env_vars_raises_clear_error(monkeypatch):
    for env_name in (RPC_URL_ENV, CHAIN_ID_ENV, CONTRACT_ADDRESS_ENV, PRIVATE_KEY_ENV):
        monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(AnchoringConfigError) as exc_info:
        load_anchoring_config()

    message = str(exc_info.value)
    assert "Missing required anchoring environment variable" in message
    for env_name in (RPC_URL_ENV, CHAIN_ID_ENV, CONTRACT_ADDRESS_ENV, PRIVATE_KEY_ENV):
        assert env_name in message


def test_invalid_chain_id_raises_clear_error(monkeypatch):
    monkeypatch.setenv(RPC_URL_ENV, "http://127.0.0.1:8545")
    monkeypatch.setenv(CHAIN_ID_ENV, "not-a-number")
    monkeypatch.setenv(
        CONTRACT_ADDRESS_ENV, "0x5FbDB2315678afecb367f032d93F642f64180aa3"
    )
    monkeypatch.setenv(
        PRIVATE_KEY_ENV,
        "0xac0974be39ef17b173be2378e2aeb0a2a3f8ad24c12730f728a214456643d81c6",
    )

    with pytest.raises(AnchoringConfigError, match=CHAIN_ID_ENV):
        load_anchoring_config()
