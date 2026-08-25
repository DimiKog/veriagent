"""Orchestrate anchoring a local SQLite batch to VeriAgentAnchor (mockable in tests)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# Module-level `anchoring` import keeps the namespace at app.batch_anchoring.anchoring
# so tests can monkeypatch app.batch_anchoring.anchoring.anchor_batch (and siblings).
from app import anchoring
from app.anchoring import (
    AnchorMetadataMismatchError,
    AnchorReceiptPendingError,
    AnchorReconciliationError,
    AnchorTransactionFailedError,
    AnchoringConfig,
    BatchAnchoredLog,
    OnchainBatch,
    load_anchoring_config,
    metadata_hash_for_batch,
)
from app.storage import (
    StoredBatch,
    StoredBatchAnchor,
    get_batch,
    get_batch_anchor,
    get_pending_anchor_transaction,
    store_batch_anchor,
    upsert_pending_anchor_transaction,
)

logger = logging.getLogger(__name__)


class BatchNotFoundError(Exception):
    """Raised when a local audit batch does not exist."""


@dataclass(frozen=True)
class BatchAnchorResult:
    anchor: StoredBatchAnchor
    already_anchored: bool
    reconciled: bool = False


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
        logger.info(
            "auto anchor: local anchor record already present batch_id=%s",
            batch_id,
        )
        return BatchAnchorResult(
            anchor=existing,
            already_anchored=True,
            reconciled=False,
        )

    cfg = config or load_anchoring_config()

    pending = get_pending_anchor_transaction(batch_id, db_path=db_path)
    if pending is not None and pending.status == "submitted":
        logger.info(
            "auto anchor: pending transaction resumed batch_id=%s tx_hash=%s",
            batch_id,
            pending.tx_hash,
        )
        return _complete_submitted_transaction(
            batch,
            pending.tx_hash,
            cfg=cfg,
            db_path=db_path,
            resumed=True,
        )

    if anchoring.is_batch_anchored(batch_id, config=cfg):
        logger.info(
            "auto anchor: existing on-chain anchor detected batch_id=%s",
            batch_id,
        )
        return _reconcile_onchain_anchor(batch, cfg=cfg, db_path=db_path)

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
    normalized_tx = _normalize_tx_hash(tx_hash)
    upsert_pending_anchor_transaction(
        batch_id=batch.batch_id,
        tx_hash=normalized_tx,
        status="submitted",
        db_path=db_path,
    )
    logger.info(
        "auto anchor: transaction submitted batch_id=%s tx_hash=%s",
        batch.batch_id,
        normalized_tx,
    )

    return _complete_submitted_transaction(
        batch,
        normalized_tx,
        cfg=cfg,
        db_path=db_path,
        resumed=False,
    )


def _reconcile_onchain_anchor(
    batch: StoredBatch,
    *,
    cfg: AnchoringConfig,
    db_path: Any,
) -> BatchAnchorResult:
    logger.info(
        "auto anchor: reconciling on-chain state batch_id=%s",
        batch.batch_id,
    )
    onchain = anchoring.get_onchain_batch(batch.batch_id, config=cfg)
    _assert_onchain_matches_local(batch, onchain)

    anchored_log = anchoring.find_batch_anchored_log(batch.batch_id, config=cfg)
    if anchored_log is None:
        logger.error(
            "auto anchor: reconciliation failure batch_id=%s reason=missing_BatchAnchored_log",
            batch.batch_id,
        )
        raise AnchorReconciliationError(
            f"On-chain anchor exists for batch {batch.batch_id} but no "
            "BatchAnchored log was found; cannot recover transaction hash"
        )

    _assert_log_matches_local(batch, anchored_log)
    _assert_log_matches_onchain(onchain, anchored_log)

    stored = store_batch_anchor(
        batch_id=batch.batch_id,
        anchor_address=str(cfg.contract_address),
        tx_hash=_normalize_tx_hash(anchored_log.tx_hash),
        block_number=anchored_log.block_number,
        anchored_at=int(onchain.anchored_at),
        anchored_by=str(onchain.anchored_by),
        chain_id=cfg.chain_id,
        db_path=db_path,
    )
    upsert_pending_anchor_transaction(
        batch_id=batch.batch_id,
        tx_hash=stored.tx_hash,
        status="confirmed",
        block_number=stored.block_number,
        confirmed_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
        db_path=db_path,
    )
    logger.info(
        "auto anchor: local anchor record persisted (reconciled) "
        "batch_id=%s tx_hash=%s block_number=%s",
        batch.batch_id,
        stored.tx_hash,
        stored.block_number,
    )
    return BatchAnchorResult(anchor=stored, already_anchored=True, reconciled=True)


def _complete_submitted_transaction(
    batch: StoredBatch,
    tx_hash: str,
    *,
    cfg: AnchoringConfig,
    db_path: Any,
    resumed: bool,
) -> BatchAnchorResult:
    normalized_tx = _normalize_tx_hash(tx_hash)
    try:
        receipt = anchoring.wait_for_transaction_receipt(normalized_tx, config=cfg)
    except AnchorReceiptPendingError as exc:
        upsert_pending_anchor_transaction(
            batch_id=batch.batch_id,
            tx_hash=normalized_tx,
            status="submitted",
            last_error=str(exc),
            db_path=db_path,
        )
        logger.info(
            "auto anchor: receipt pending batch_id=%s tx_hash=%s",
            batch.batch_id,
            normalized_tx,
        )
        raise
    except AnchorTransactionFailedError as exc:
        upsert_pending_anchor_transaction(
            batch_id=batch.batch_id,
            tx_hash=normalized_tx,
            status="failed",
            last_error=str(exc),
            db_path=db_path,
        )
        raise

    logger.info(
        "auto anchor: receipt confirmed batch_id=%s tx_hash=%s",
        batch.batch_id,
        normalized_tx,
    )
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

    if onchain.anchored_at != 0:
        _assert_onchain_matches_local(batch, onchain)

    stored = store_batch_anchor(
        batch_id=batch.batch_id,
        anchor_address=str(cfg.contract_address),
        tx_hash=normalized_tx,
        block_number=block_number,
        anchored_at=anchored_at,
        anchored_by=anchored_by,
        chain_id=cfg.chain_id,
        db_path=db_path,
    )
    upsert_pending_anchor_transaction(
        batch_id=batch.batch_id,
        tx_hash=normalized_tx,
        status="confirmed",
        block_number=block_number,
        confirmed_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
        db_path=db_path,
    )
    logger.info(
        "auto anchor: local anchor record persisted batch_id=%s tx_hash=%s resumed=%s",
        batch.batch_id,
        normalized_tx,
        resumed,
    )
    return BatchAnchorResult(anchor=stored, already_anchored=False, reconciled=False)


def _normalize_hex32(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.hex().lower()
    return value.removeprefix("0x").lower()


def _assert_onchain_matches_local(batch: StoredBatch, onchain: OnchainBatch) -> None:
    local_root = _normalize_hex32(batch.merkle_root)
    onchain_root = _normalize_hex32(onchain.merkle_root)
    if local_root != onchain_root:
        logger.error(
            "auto anchor: metadata mismatch batch_id=%s field=merkle_root",
            batch.batch_id,
        )
        raise AnchorMetadataMismatchError(
            f"On-chain merkle_root does not match local batch {batch.batch_id}"
        )
    if int(onchain.event_count) != int(batch.event_count):
        logger.error(
            "auto anchor: metadata mismatch batch_id=%s field=event_count",
            batch.batch_id,
        )
        raise AnchorMetadataMismatchError(
            f"On-chain event_count does not match local batch {batch.batch_id}"
        )


def _assert_log_matches_local(batch: StoredBatch, anchored_log: BatchAnchoredLog) -> None:
    local_root = _normalize_hex32(batch.merkle_root)
    log_root = _normalize_hex32(anchored_log.merkle_root)
    if local_root != log_root:
        logger.error(
            "auto anchor: metadata mismatch batch_id=%s field=BatchAnchored.merkleRoot",
            batch.batch_id,
        )
        raise AnchorMetadataMismatchError(
            f"BatchAnchored merkleRoot does not match local batch {batch.batch_id}"
        )
    if int(anchored_log.event_count) != int(batch.event_count):
        logger.error(
            "auto anchor: metadata mismatch batch_id=%s field=BatchAnchored.eventCount",
            batch.batch_id,
        )
        raise AnchorMetadataMismatchError(
            f"BatchAnchored eventCount does not match local batch {batch.batch_id}"
        )


def _assert_log_matches_onchain(
    onchain: OnchainBatch,
    anchored_log: BatchAnchoredLog,
) -> None:
    if _normalize_hex32(onchain.merkle_root) != _normalize_hex32(anchored_log.merkle_root):
        raise AnchorMetadataMismatchError(
            "BatchAnchored merkleRoot does not match getBatch merkleRoot"
        )
    if int(onchain.event_count) != int(anchored_log.event_count):
        raise AnchorMetadataMismatchError(
            "BatchAnchored eventCount does not match getBatch eventCount"
        )


def _normalize_tx_hash(tx_hash: str) -> str:
    normalized = tx_hash.strip()
    if not normalized.startswith("0x"):
        normalized = f"0x{normalized}"
    return normalized
