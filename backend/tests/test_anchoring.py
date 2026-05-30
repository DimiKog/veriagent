import json
import logging
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from eth_typing import ChecksumAddress

from app.anchoring import (
    CHAIN_ID_ENV,
    CONTRACT_ADDRESS_ENV,
    DEFAULT_ABI_PATH,
    FALLBACK_ANCHOR_GAS,
    PRIVATE_KEY_ENV,
    RPC_URL_ENV,
    AnchorTransactionFailedError,
    AnchoringConfig,
    AnchoringConfigError,
    anchor_batch,
    batch_id_to_bytes32,
    load_anchoring_config,
    load_contract_abi,
    metadata_hash_for_batch,
    wait_for_transaction_receipt,
)

ANCHOR_CONTRACT = ChecksumAddress("0x5FbDB2315678afecb367f032d93F642f64180aa3")
ANCHOR_SENDER = ChecksumAddress("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
TEST_PRIVATE_KEY = "0xac0974bec39a713e79292259bf58859cb0783e6fdc6274d536bb63ac40d05891f"
FAKE_TX_HASH = "0x" + "cd" * 32

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


def test_wait_for_transaction_receipt_raises_on_reverted_status(monkeypatch):
    fake_web3 = MagicMock()
    fake_web3.eth.wait_for_transaction_receipt.return_value = {
        "blockNumber": 99,
        "status": 0,
    }
    monkeypatch.setattr("app.anchoring._get_web3", lambda config=None: fake_web3)

    with pytest.raises(AnchorTransactionFailedError, match="reverted"):
        wait_for_transaction_receipt(FAKE_TX_HASH, config=_test_config())


def test_anchor_batch_logs_estimate_gas_failure(caplog, monkeypatch):
    built_tx: dict = {}

    class FakeAnchorFunction:
        def estimate_gas(self, _tx):
            raise ValueError("execution reverted: BatchAlreadyAnchored")

        def build_transaction(self, params):
            built_tx.update(params)
            return {
                "from": params["from"],
                "nonce": params["nonce"],
                "chainId": params["chainId"],
                "gas": params["gas"],
                "gasPrice": params["gasPrice"],
                "to": ANCHOR_CONTRACT,
                "data": b"",
                "value": 0,
            }

    class FakeContractFunctions:
        def anchorBatch(self, *_args):
            return FakeAnchorFunction()

    class FakeContract:
        functions = FakeContractFunctions()

    fake_web3 = MagicMock()
    fake_web3.eth.gas_price = 1_000_000_000
    fake_web3.eth.get_transaction_count.return_value = 0
    fake_web3.eth.send_raw_transaction.return_value = bytes.fromhex(FAKE_TX_HASH[2:])

    monkeypatch.setattr("app.anchoring._get_web3", lambda config=None: fake_web3)
    monkeypatch.setattr(
        "app.anchoring.get_anchor_contract",
        lambda web3, config=None: FakeContract(),
    )
    fake_account = MagicMock()
    fake_account.address = ANCHOR_SENDER
    fake_account.sign_transaction.return_value = SimpleNamespace(
        raw_transaction=bytes.fromhex(FAKE_TX_HASH[2:])
    )
    monkeypatch.setattr("eth_account.Account.from_key", lambda _key: fake_account)

    caplog.set_level(logging.WARNING, logger="app.anchoring")
    tx_hash = anchor_batch(
        "batch-gas-fallback",
        "a" * 64,
        1,
        b"\x01" * 32,
        config=_test_config(),
    )

    assert tx_hash
    assert built_tx["gas"] == FALLBACK_ANCHOR_GAS
    assert any(
        "gas estimation failed" in record.message and "batch-gas-fallback" in record.message
        for record in caplog.records
        if record.levelname == "WARNING"
    )


def _test_config() -> AnchoringConfig:
    return AnchoringConfig(
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=ANCHOR_CONTRACT,
        private_key=TEST_PRIVATE_KEY,
    )
