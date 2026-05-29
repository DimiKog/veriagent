import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.merkle import merkle_root, normalize_leaves

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "veriagent.db"
DB_PATH_ENV = "VERIAGENT_DB_PATH"


class EventAlreadyExistsError(Exception):
    pass


class NoUnbatchedEventsError(Exception):
    pass


@dataclass(frozen=True)
class StoredAuditEvent:
    event_id: str
    canonical_event_json: str
    event_hash: str
    created_at: str


@dataclass(frozen=True)
class BatchLeaf:
    event_id: str
    event_hash: str
    leaf_index: int


@dataclass(frozen=True)
class StoredBatch:
    batch_id: str
    merkle_root: str
    event_count: int
    created_at: str
    event_hashes: list[str]


@dataclass(frozen=True)
class StoredBatchAnchor:
    batch_id: str
    anchor_address: str
    tx_hash: str
    block_number: int
    anchored_at: int
    anchored_by: str
    chain_id: int


def resolve_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    env_path = os.environ.get(DB_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                canonical_event_json TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_batches (
                batch_id TEXT PRIMARY KEY,
                merkle_root TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_events (
                batch_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                leaf_index INTEGER NOT NULL,
                PRIMARY KEY (batch_id, event_id),
                FOREIGN KEY (batch_id) REFERENCES audit_batches(batch_id),
                FOREIGN KEY (event_id) REFERENCES audit_events(event_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_anchors (
                batch_id TEXT PRIMARY KEY,
                anchor_address TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                block_number INTEGER NOT NULL,
                anchored_at INTEGER NOT NULL,
                anchored_by TEXT NOT NULL,
                chain_id INTEGER NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES audit_batches(batch_id)
            )
            """
        )
        conn.commit()


def store_audit_event(
    event_id: str,
    canonical_event_json: str,
    event_hash: str,
    db_path: Path | str | None = None,
) -> StoredAuditEvent:
    init_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_events (
                    event_id, canonical_event_json, event_hash, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (event_id, canonical_event_json, event_hash, created_at),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise EventAlreadyExistsError(event_id) from exc

    return StoredAuditEvent(
        event_id=event_id,
        canonical_event_json=canonical_event_json,
        event_hash=event_hash,
        created_at=created_at,
    )


def get_audit_event(
    event_id: str,
    db_path: Path | str | None = None,
) -> StoredAuditEvent | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT event_id, canonical_event_json, event_hash, created_at
            FROM audit_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()

    if row is None:
        return None

    return StoredAuditEvent(
        event_id=row["event_id"],
        canonical_event_json=row["canonical_event_json"],
        event_hash=row["event_hash"],
        created_at=row["created_at"],
    )


def list_unbatched_events(db_path: Path | str | None = None) -> list[StoredAuditEvent]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT e.event_id, e.canonical_event_json, e.event_hash, e.created_at
            FROM audit_events e
            LEFT JOIN batch_events b ON e.event_id = b.event_id
            WHERE b.event_id IS NULL
            ORDER BY e.created_at ASC, e.event_id ASC
            """
        ).fetchall()

    return [
        StoredAuditEvent(
            event_id=row["event_id"],
            canonical_event_json=row["canonical_event_json"],
            event_hash=row["event_hash"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def create_batch_from_unbatched(db_path: Path | str | None = None) -> StoredBatch:
    events = list_unbatched_events(db_path)
    if not events:
        raise NoUnbatchedEventsError()

    hash_to_event = {event.event_hash: event for event in events}
    leaves = normalize_leaves([event.event_hash for event in events])
    root = merkle_root(leaves)

    batch_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    init_db(db_path)

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO audit_batches (batch_id, merkle_root, event_count, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (batch_id, root, len(leaves), created_at),
        )
        for leaf_index, event_hash in enumerate(leaves):
            event = hash_to_event[event_hash]
            conn.execute(
                """
                INSERT INTO batch_events (batch_id, event_id, event_hash, leaf_index)
                VALUES (?, ?, ?, ?)
                """,
                (batch_id, event.event_id, event_hash, leaf_index),
            )
        conn.commit()

    return StoredBatch(
        batch_id=batch_id,
        merkle_root=root,
        event_count=len(leaves),
        created_at=created_at,
        event_hashes=leaves,
    )


def get_batch(batch_id: str, db_path: Path | str | None = None) -> StoredBatch | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT batch_id, merkle_root, event_count, created_at
            FROM audit_batches
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()
        if row is None:
            return None

        leaf_rows = conn.execute(
            """
            SELECT event_hash
            FROM batch_events
            WHERE batch_id = ?
            ORDER BY leaf_index ASC
            """,
            (batch_id,),
        ).fetchall()

    return StoredBatch(
        batch_id=row["batch_id"],
        merkle_root=row["merkle_root"],
        event_count=row["event_count"],
        created_at=row["created_at"],
        event_hashes=[leaf["event_hash"] for leaf in leaf_rows],
    )


def get_batch_event(
    batch_id: str,
    event_id: str,
    db_path: Path | str | None = None,
) -> BatchLeaf | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT event_id, event_hash, leaf_index
            FROM batch_events
            WHERE batch_id = ? AND event_id = ?
            """,
            (batch_id, event_id),
        ).fetchone()

    if row is None:
        return None

    return BatchLeaf(
        event_id=row["event_id"],
        event_hash=row["event_hash"],
        leaf_index=row["leaf_index"],
    )


def get_batch_leaves(batch_id: str, db_path: Path | str | None = None) -> list[BatchLeaf]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT event_id, event_hash, leaf_index
            FROM batch_events
            WHERE batch_id = ?
            ORDER BY leaf_index ASC
            """,
            (batch_id,),
        ).fetchall()

    return [
        BatchLeaf(
            event_id=row["event_id"],
            event_hash=row["event_hash"],
            leaf_index=row["leaf_index"],
        )
        for row in rows
    ]


def store_batch_anchor(
    batch_id: str,
    anchor_address: str,
    tx_hash: str,
    block_number: int,
    anchored_at: int,
    anchored_by: str,
    chain_id: int,
    db_path: Path | str | None = None,
) -> StoredBatchAnchor:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO batch_anchors (
                batch_id,
                anchor_address,
                tx_hash,
                block_number,
                anchored_at,
                anchored_by,
                chain_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                anchor_address,
                tx_hash,
                block_number,
                anchored_at,
                anchored_by,
                chain_id,
            ),
        )
        conn.commit()

    return StoredBatchAnchor(
        batch_id=batch_id,
        anchor_address=anchor_address,
        tx_hash=tx_hash,
        block_number=block_number,
        anchored_at=anchored_at,
        anchored_by=anchored_by,
        chain_id=chain_id,
    )


def get_batch_anchor(
    batch_id: str,
    db_path: Path | str | None = None,
) -> StoredBatchAnchor | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                batch_id,
                anchor_address,
                tx_hash,
                block_number,
                anchored_at,
                anchored_by,
                chain_id
            FROM batch_anchors
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()

    if row is None:
        return None

    return StoredBatchAnchor(
        batch_id=row["batch_id"],
        anchor_address=row["anchor_address"],
        tx_hash=row["tx_hash"],
        block_number=row["block_number"],
        anchored_at=row["anchored_at"],
        anchored_by=row["anchored_by"],
        chain_id=row["chain_id"],
    )
