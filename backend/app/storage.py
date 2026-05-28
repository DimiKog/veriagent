import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "veriagent.db"
DB_PATH_ENV = "VERIAGENT_DB_PATH"


class EventAlreadyExistsError(Exception):
    pass


@dataclass(frozen=True)
class StoredAuditEvent:
    event_id: str
    canonical_event_json: str
    event_hash: str
    created_at: str


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
