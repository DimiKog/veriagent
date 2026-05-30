"""Orchestrate anchoring a local SQLite batch to VeriAgentAnchor (mockable in tests)."""

from dataclasses import dataclass
from typing import Any

# Module-level `anchoring` import keeps the namespace at app.batch_anchoring.anchoring
# so tests can monkeypatch app.batch_anchoring.anchoring.anchor_batch (and siblings).
from app import anchoring
from app.anchoring import (
    AnchoringConfig,
    load_anchoring_config,
    metadata_hash_for_batch,
)
from app.storage import (
    StoredBatchAnchor,
    get_batch,
    get_batch_anchor,
    store_batch_anchor,
)


class BatchNotFoundError(Exception):
    """Raised when a local audit batch does not exist."""


@dataclass(frozen=True)
class BatchAnchorResult:
    anchor: StoredBatchAnchor
    already_anchored: bool


def perform_batch_anchor(
    batch_id: str,
    *,
    db_path: Any = None,
    config: AnchoringConfig | None = None,
) -> BatchAnchorResult:
    batch = get_batch(batch_id, db_path=db_path)
    if batch is None:
        raise BatchNotFoundError(batch_id)

    existing = get_batch_anchor(batch_id, db_path=db_path)
    if existing is not None:
        return BatchAnchorResult(anchor=existing, already_anchored=True)

    cfg = config or load_anchoring_config()
    metadata_hash = metadata_hash_for_batch(
        batch_id=batch.batch_id,
        merkle_root=batch.merkle_root,
        event_count=batch.event_count,
        created_at=batch.created_at,
        event_hashes=batch.event_hashes,
    )

    tx_hash = anchoring.anchor_batch(
        batch.batch_id,
        batch.merkle_root,
        batch.event_count,
        metadata_hash,
        config=cfg,
    )
    receipt = anchoring.wait_for_transaction_receipt(tx_hash, config=cfg)
    block_number = int(receipt["blockNumber"])
    onchain = anchoring.get_onchain_batch(
        batch.batch_id,
        block_identifier=block_number,
        config=cfg,
    )

    anchored_at = int(onchain.anchored_at)
    anchored_by = str(onchain.anchored_by)
    if anchored_at == 0 or anchored_by == "0x0000000000000000000000000000000000000000":
        fallback = anchoring.read_anchor_metadata_from_receipt(
            receipt,
            batch.batch_id,
            config=cfg,
        )
        if fallback is not None:
            anchored_at, anchored_by_checksum = fallback
            anchored_by = str(anchored_by_checksum)

    stored = store_batch_anchor(
        batch_id=batch.batch_id,
        anchor_address=str(cfg.contract_address),
        tx_hash=_normalize_tx_hash(tx_hash),
        block_number=block_number,
        anchored_at=anchored_at,
        anchored_by=anchored_by,
        chain_id=cfg.chain_id,
        db_path=db_path,
    )
    return BatchAnchorResult(anchor=stored, already_anchored=False)


def _normalize_tx_hash(tx_hash: str) -> str:
    normalized = tx_hash.strip()
    if not normalized.startswith("0x"):
        normalized = f"0x{normalized}"
    return normalized
