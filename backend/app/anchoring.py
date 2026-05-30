import hashlib
import json
import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jcs
from eth_typing import ChecksumAddress
from eth_utils.address import is_address, to_checksum_address
from eth_utils.crypto import keccak

if TYPE_CHECKING:
    from web3 import Web3
    from web3.contract import Contract
    from web3.types import BlockIdentifier

RPC_URL_ENV = "VERIAGENT_RPC_URL"
CHAIN_ID_ENV = "VERIAGENT_CHAIN_ID"
CONTRACT_ADDRESS_ENV = "VERIAGENT_ANCHOR_CONTRACT_ADDRESS"
PRIVATE_KEY_ENV = "VERIAGENT_ANCHOR_PRIVATE_KEY"

REQUIRED_ENV_VARS = (
    RPC_URL_ENV,
    CHAIN_ID_ENV,
    CONTRACT_ADDRESS_ENV,
    PRIVATE_KEY_ENV,
)

APP_DIR = Path(__file__).resolve().parent
DEFAULT_ABI_PATH = APP_DIR / "abi" / "VeriAgentAnchor.json"
FALLBACK_ANCHOR_GAS = 500_000

logger = logging.getLogger(__name__)


class AnchoringConfigError(Exception):
    """Raised when required anchoring configuration is missing or invalid."""


class AnchorTransactionFailedError(Exception):
    """Raised when an anchor transaction receipt indicates failure or revert."""


@dataclass(frozen=True)
class AnchoringConfig:
    rpc_url: str
    chain_id: int
    contract_address: ChecksumAddress
    private_key: str


@dataclass(frozen=True)
class OnchainBatch:
    merkle_root: bytes
    event_count: int
    metadata_hash: bytes
    anchored_at: int
    anchored_by: ChecksumAddress


def _coerce_bytes32(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if hasattr(value, "hex"):
        return bytes(value)
    if isinstance(value, str):
        normalized = value.removeprefix("0x")
        return bytes.fromhex(normalized)
    raise TypeError(f"Expected bytes32-compatible value, got {type(value)!r}")


def _get_struct_field(struct: Any, camel_name: str, snake_name: str) -> Any:
    if isinstance(struct, Mapping):
        if camel_name in struct:
            return struct[camel_name]
        if snake_name in struct:
            return struct[snake_name]
    for name in (camel_name, snake_name):
        if hasattr(struct, name):
            return getattr(struct, name)
    raise KeyError(f"Batch struct missing field {camel_name!r}")


def _has_named_batch_fields(struct: Any) -> bool:
    try:
        _get_struct_field(struct, "anchoredAt", "anchored_at")
    except KeyError:
        return False
    return True


def _unwrap_batch_return(raw: Any) -> Any:
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, str)) and len(raw) == 1:
        return _unwrap_batch_return(raw[0])
    return raw


def parse_get_batch_return(raw: Any) -> OnchainBatch:
    """Parse getBatch() output from web3 (tuple, list, or ABI named struct)."""
    batch = _unwrap_batch_return(raw)

    if _has_named_batch_fields(batch):
        return OnchainBatch(
            merkle_root=_coerce_bytes32(
                _get_struct_field(batch, "merkleRoot", "merkle_root")
            ),
            event_count=int(_get_struct_field(batch, "eventCount", "event_count")),
            metadata_hash=_coerce_bytes32(
                _get_struct_field(batch, "metadataHash", "metadata_hash")
            ),
            anchored_at=int(_get_struct_field(batch, "anchoredAt", "anchored_at")),
            anchored_by=to_checksum_address(
                _get_struct_field(batch, "anchoredBy", "anchored_by")
            ),
        )

    if isinstance(batch, Sequence) and not isinstance(batch, (bytes, str)) and len(batch) == 5:
        return OnchainBatch(
            merkle_root=_coerce_bytes32(batch[0]),
            event_count=int(batch[1]),
            metadata_hash=_coerce_bytes32(batch[2]),
            anchored_at=int(batch[3]),
            anchored_by=to_checksum_address(batch[4]),
        )

    raise ValueError(f"Unexpected getBatch return shape: {type(batch)!r}")


def read_anchor_metadata_from_receipt(
    receipt: dict[str, Any],
    batch_id: str,
    *,
    config: AnchoringConfig | None = None,
) -> tuple[int, ChecksumAddress] | None:
    """Read anchoredAt/anchoredBy from BatchAnchored logs when getBatch is unavailable."""
    cfg = config or load_anchoring_config()
    web3 = _get_web3(cfg)
    contract = get_anchor_contract(web3, cfg)
    batch_id_bytes = batch_id_to_bytes32(batch_id)

    for event in contract.events.BatchAnchored().process_receipt(receipt):
        args = event["args"]
        if args["batchId"] == batch_id_bytes:
            return (
                int(args["anchoredAt"]),
                to_checksum_address(args["anchoredBy"]),
            )
    return None


def batch_id_to_bytes32(batch_id: str) -> bytes:
    """Map a backend batch_id string to a bytes32 anchor key (keccak256 of UTF-8)."""
    return keccak(text=batch_id)


def metadata_hash_for_batch(
    *,
    batch_id: str,
    merkle_root: str,
    event_count: int,
    created_at: str,
    event_hashes: list[str],
) -> bytes:
    """Commit batch metadata with RFC 8785 / JCS canonicalization and SHA-256."""
    metadata: dict[str, Any] = {
        "batch_id": batch_id,
        "created_at": created_at,
        "event_count": event_count,
        "event_hashes": event_hashes,
        "merkle_root": merkle_root,
    }
    canonical = jcs.canonicalize(metadata)
    return hashlib.sha256(canonical).digest()


def hex_digest_to_bytes32(hex_digest: str) -> bytes:
    """Convert a 64-character hex digest (no 0x prefix) to 32 bytes."""
    normalized = hex_digest.removeprefix("0x")
    value = bytes.fromhex(normalized)
    if len(value) != 32:
        raise ValueError(f"Expected 32-byte hex digest, got {len(value)} bytes")
    return value


def load_contract_abi(abi_path: Path | None = None) -> list[dict[str, Any]]:
    path = abi_path or DEFAULT_ABI_PATH
    if not path.is_file():
        raise FileNotFoundError(f"VeriAgentAnchor ABI file not found: {path}")

    with path.open(encoding="utf-8") as abi_file:
        loaded = json.load(abi_file)

    if isinstance(loaded, list):
        abi = loaded
    elif isinstance(loaded, dict):
        abi = loaded.get("abi")
    else:
        abi = None

    if not isinstance(abi, list):
        raise ValueError(
            f"Invalid ABI file (expected JSON array or dict with 'abi' key): {path}"
        )
    return abi


def load_anchoring_config() -> AnchoringConfig:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise AnchoringConfigError(
            "Missing required anchoring environment variable(s): " + ", ".join(missing)
        )

    chain_id_raw = os.environ[CHAIN_ID_ENV].strip()
    try:
        chain_id = int(chain_id_raw)
    except ValueError as exc:
        raise AnchoringConfigError(
            f"{CHAIN_ID_ENV} must be an integer, got: {chain_id_raw!r}"
        ) from exc

    private_key = os.environ[PRIVATE_KEY_ENV].strip()
    if not private_key.startswith("0x"):
        private_key = f"0x{private_key}"

    contract_address = os.environ[CONTRACT_ADDRESS_ENV].strip()
    if not is_address(contract_address):
        raise AnchoringConfigError(
            f"{CONTRACT_ADDRESS_ENV} is not a valid Ethereum address: {contract_address!r}"
        )

    return AnchoringConfig(
        rpc_url=os.environ[RPC_URL_ENV].strip(),
        chain_id=chain_id,
        contract_address=to_checksum_address(contract_address),
        private_key=private_key,
    )


def _get_web3(config: AnchoringConfig | None = None) -> "Web3":
    from web3 import Web3

    cfg = config or load_anchoring_config()
    web3 = Web3(Web3.HTTPProvider(cfg.rpc_url))
    if not web3.is_connected():
        raise AnchoringConfigError(f"Unable to connect to RPC endpoint: {cfg.rpc_url}")
    return web3


def get_anchor_contract(
    web3: "Web3 | None" = None,
    config: AnchoringConfig | None = None,
) -> "Contract":
    cfg = config or load_anchoring_config()
    w3 = web3 or _get_web3(cfg)
    abi = load_contract_abi()
    return w3.eth.contract(address=cfg.contract_address, abi=abi)


def anchor_batch(
    batch_id: str,
    merkle_root: str,
    event_count: int,
    metadata_hash: bytes,
    *,
    config: AnchoringConfig | None = None,
) -> str:
    """Submit anchorBatch on VeriAgentAnchor; returns the transaction hash hex."""
    from eth_account import Account

    cfg = config or load_anchoring_config()
    web3 = _get_web3(cfg)
    contract = get_anchor_contract(web3, cfg)

    account = Account.from_key(cfg.private_key)
    batch_id_bytes = batch_id_to_bytes32(batch_id)
    merkle_root_bytes = hex_digest_to_bytes32(merkle_root)
    if len(metadata_hash) != 32:
        raise ValueError(f"metadata_hash must be 32 bytes, got {len(metadata_hash)}")

    nonce = web3.eth.get_transaction_count(account.address)
    gas_price = web3.eth.gas_price
    function = contract.functions.anchorBatch(
        batch_id_bytes,
        merkle_root_bytes,
        event_count,
        metadata_hash,
    )
    try:
        estimated_gas = function.estimate_gas({"from": account.address})
    except Exception as exc:
        logger.warning(
            "anchor_batch gas estimation failed for batch_id=%s from=%s; "
            "using fallback gas=%s: %s",
            batch_id,
            account.address,
            FALLBACK_ANCHOR_GAS,
            exc,
            exc_info=True,
        )
        estimated_gas = FALLBACK_ANCHOR_GAS

    transaction = function.build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "chainId": cfg.chain_id,
            "gas": estimated_gas,
            "gasPrice": gas_price,
        }
    )

    signed = account.sign_transaction(transaction)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


def get_onchain_batch(
    batch_id: str,
    *,
    block_identifier: "BlockIdentifier" = "latest",
    config: AnchoringConfig | None = None,
) -> OnchainBatch:
    cfg = config or load_anchoring_config()
    web3 = _get_web3(cfg)
    contract = get_anchor_contract(web3, cfg)
    batch_id_bytes = batch_id_to_bytes32(batch_id)

    raw = contract.functions.getBatch(batch_id_bytes).call(
        block_identifier=block_identifier
    )
    return parse_get_batch_return(raw)


def is_batch_anchored(
    batch_id: str,
    *,
    config: AnchoringConfig | None = None,
) -> bool:
    cfg = config or load_anchoring_config()
    web3 = _get_web3(cfg)
    contract = get_anchor_contract(web3, cfg)
    batch_id_bytes = batch_id_to_bytes32(batch_id)
    return bool(contract.functions.isAnchored(batch_id_bytes).call())


def _receipt_status(receipt: dict[str, Any]) -> int:
    status = receipt.get("status")
    if status is None:
        raise AnchorTransactionFailedError("Anchor transaction receipt is missing status")
    return int(status)


def wait_for_transaction_receipt(
    tx_hash: str,
    *,
    config: AnchoringConfig | None = None,
) -> dict[str, Any]:
    """Wait for a submitted anchor transaction and return the receipt dict."""
    cfg = config or load_anchoring_config()
    web3 = _get_web3(cfg)
    normalized = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"
    receipt = dict(web3.eth.wait_for_transaction_receipt(normalized))
    if _receipt_status(receipt) == 0:
        raise AnchorTransactionFailedError(
            f"Anchor transaction reverted (status=0): tx_hash={normalized}"
        )
    return receipt
