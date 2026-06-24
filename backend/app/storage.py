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


class AgentAlreadyExistsError(Exception):
    pass


class RegistrationRequestNotFoundError(Exception):
    pass


class DuplicatePendingRegistrationError(Exception):
    pass


class RegistrationRequestNotPendingError(Exception):
    pass


class NoUnbatchedEventsError(Exception):
    pass


@dataclass(frozen=True)
class StoredAuditEvent:
    event_id: str
    canonical_event_json: str
    event_hash: str
    created_at: str
    signature: str | None = None
    verification_method: str | None = None
    signature_algorithm: str | None = None


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
class StoredAgent:
    agent_did: str
    agent_name: str
    agent_type: str
    description: str | None
    verification_method: str
    public_key: str
    api_key_hash: str
    status: str
    created_at: str


REGISTRATION_REQUEST_STATUSES = ("pending", "approved", "rejected", "expired")


@dataclass(frozen=True)
class StoredRegistrationRequest:
    request_id: str
    agent_did: str
    agent_name: str
    agent_type: str
    description: str | None
    organization_name: str
    contact_email: str
    use_case_summary: str
    status: str
    challenge_nonce: str
    challenge_expires_at: str
    proof_signature: str | None
    proof_submitted_at: str | None
    proof_payload_json: str
    reviewed_by: str | None
    reviewed_at: str | None
    review_notes: str | None
    approved_agent_did: str | None
    retrieval_token_hash: str | None
    credentials_retrieved_at: str | None
    client_ip_hash: str | None
    created_at: str
    updated_at: str
    public_key: str
    verification_method: str


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


def _migrate_audit_events_table(conn: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(audit_events)").fetchall()
    }
    if "signature" not in columns:
        conn.execute("ALTER TABLE audit_events ADD COLUMN signature TEXT")
    if "verification_method" not in columns:
        conn.execute("ALTER TABLE audit_events ADD COLUMN verification_method TEXT")
    if "signature_algorithm" not in columns:
        conn.execute("ALTER TABLE audit_events ADD COLUMN signature_algorithm TEXT")


def init_db(db_path: Path | str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                canonical_event_json TEXT NOT NULL,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                signature TEXT,
                verification_method TEXT,
                signature_algorithm TEXT
            )
            """
        )
        _migrate_audit_events_table(conn)
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_did TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                description TEXT,
                verification_method TEXT NOT NULL,
                public_key TEXT NOT NULL,
                api_key_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registration_requests (
                request_id TEXT PRIMARY KEY,
                agent_did TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                description TEXT,
                organization_name TEXT NOT NULL,
                contact_email TEXT NOT NULL,
                use_case_summary TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('pending', 'approved', 'rejected', 'expired')
                ),
                challenge_nonce TEXT NOT NULL,
                challenge_expires_at TEXT NOT NULL,
                proof_signature TEXT,
                proof_submitted_at TEXT,
                proof_payload_json TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TEXT,
                review_notes TEXT,
                approved_agent_did TEXT,
                retrieval_token_hash TEXT,
                credentials_retrieved_at TEXT,
                client_ip_hash TEXT,
                public_key TEXT NOT NULL,
                verification_method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (approved_agent_did) REFERENCES agents(agent_did)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_registration_requests_status
            ON registration_requests(status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_registration_requests_agent_did
            ON registration_requests(agent_did)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_registration_requests_pending_did
            ON registration_requests(agent_did)
            WHERE status = 'pending'
            """
        )
        conn.commit()


def store_audit_event(
    event_id: str,
    canonical_event_json: str,
    event_hash: str,
    signature: str | None = None,
    verification_method: str | None = None,
    signature_algorithm: str | None = None,
    db_path: Path | str | None = None,
) -> StoredAuditEvent:
    init_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    canonical_event_json,
                    event_hash,
                    created_at,
                    signature,
                    verification_method,
                    signature_algorithm
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    canonical_event_json,
                    event_hash,
                    created_at,
                    signature,
                    verification_method,
                    signature_algorithm,
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise EventAlreadyExistsError(event_id) from exc

    return StoredAuditEvent(
        event_id=event_id,
        canonical_event_json=canonical_event_json,
        event_hash=event_hash,
        created_at=created_at,
        signature=signature,
        verification_method=verification_method,
        signature_algorithm=signature_algorithm,
    )


def _stored_audit_event_from_row(row: sqlite3.Row) -> StoredAuditEvent:
    return StoredAuditEvent(
        event_id=row["event_id"],
        canonical_event_json=row["canonical_event_json"],
        event_hash=row["event_hash"],
        created_at=row["created_at"],
        signature=row["signature"],
        verification_method=row["verification_method"],
        signature_algorithm=row["signature_algorithm"],
    )


def get_audit_event(
    event_id: str,
    db_path: Path | str | None = None,
) -> StoredAuditEvent | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                event_id,
                canonical_event_json,
                event_hash,
                created_at,
                signature,
                verification_method,
                signature_algorithm
            FROM audit_events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()

    if row is None:
        return None

    return _stored_audit_event_from_row(row)


def list_unbatched_events(db_path: Path | str | None = None) -> list[StoredAuditEvent]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                e.event_id,
                e.canonical_event_json,
                e.event_hash,
                e.created_at,
                e.signature,
                e.verification_method,
                e.signature_algorithm
            FROM audit_events e
            LEFT JOIN batch_events b ON e.event_id = b.event_id
            WHERE b.event_id IS NULL
            ORDER BY e.created_at ASC, e.event_id ASC
            """
        ).fetchall()

    return [_stored_audit_event_from_row(row) for row in rows]


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


def register_agent(
    agent_did: str,
    agent_name: str,
    agent_type: str,
    description: str | None,
    verification_method: str,
    public_key: str,
    api_key_hash: str,
    status: str,
    db_path: Path | str | None = None,
) -> StoredAgent:
    init_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    agent_did,
                    agent_name,
                    agent_type,
                    description,
                    verification_method,
                    public_key,
                    api_key_hash,
                    status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_did,
                    agent_name,
                    agent_type,
                    description,
                    verification_method,
                    public_key,
                    api_key_hash,
                    status,
                    created_at,
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise AgentAlreadyExistsError(agent_did) from exc

    return StoredAgent(
        agent_did=agent_did,
        agent_name=agent_name,
        agent_type=agent_type,
        description=description,
        verification_method=verification_method,
        public_key=public_key,
        api_key_hash=api_key_hash,
        status=status,
        created_at=created_at,
    )


def get_agent(
    agent_did: str,
    db_path: Path | str | None = None,
) -> StoredAgent | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                agent_did,
                agent_name,
                agent_type,
                description,
                verification_method,
                public_key,
                api_key_hash,
                status,
                created_at
            FROM agents
            WHERE agent_did = ?
            """,
            (agent_did,),
        ).fetchone()

    if row is None:
        return None

    return StoredAgent(
        agent_did=row["agent_did"],
        agent_name=row["agent_name"],
        agent_type=row["agent_type"],
        description=row["description"],
        verification_method=row["verification_method"],
        public_key=row["public_key"],
        api_key_hash=row["api_key_hash"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _stored_registration_request_from_row(row: sqlite3.Row) -> StoredRegistrationRequest:
    return StoredRegistrationRequest(
        request_id=row["request_id"],
        agent_did=row["agent_did"],
        agent_name=row["agent_name"],
        agent_type=row["agent_type"],
        description=row["description"],
        organization_name=row["organization_name"],
        contact_email=row["contact_email"],
        use_case_summary=row["use_case_summary"],
        status=row["status"],
        challenge_nonce=row["challenge_nonce"],
        challenge_expires_at=row["challenge_expires_at"],
        proof_signature=row["proof_signature"],
        proof_submitted_at=row["proof_submitted_at"],
        proof_payload_json=row["proof_payload_json"],
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
        review_notes=row["review_notes"],
        approved_agent_did=row["approved_agent_did"],
        retrieval_token_hash=row["retrieval_token_hash"],
        credentials_retrieved_at=row["credentials_retrieved_at"],
        client_ip_hash=row["client_ip_hash"],
        public_key=row["public_key"],
        verification_method=row["verification_method"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_registration_request(
    request_id: str,
    agent_did: str,
    agent_name: str,
    agent_type: str,
    description: str | None,
    organization_name: str,
    contact_email: str,
    use_case_summary: str,
    verification_method: str,
    public_key: str,
    challenge_nonce: str,
    challenge_expires_at: str,
    proof_payload_json: str,
    client_ip_hash: str | None = None,
    db_path: Path | str | None = None,
) -> StoredRegistrationRequest:
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO registration_requests (
                    request_id,
                    agent_did,
                    agent_name,
                    agent_type,
                    description,
                    organization_name,
                    contact_email,
                    use_case_summary,
                    status,
                    challenge_nonce,
                    challenge_expires_at,
                    proof_payload_json,
                    public_key,
                    verification_method,
                    client_ip_hash,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    agent_did,
                    agent_name,
                    agent_type,
                    description,
                    organization_name,
                    contact_email,
                    use_case_summary,
                    challenge_nonce,
                    challenge_expires_at,
                    proof_payload_json,
                    public_key,
                    verification_method,
                    client_ip_hash,
                    now,
                    now,
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        raise DuplicatePendingRegistrationError(agent_did) from exc

    stored = get_registration_request(request_id, db_path=db_path)
    assert stored is not None
    return stored


def get_registration_request(
    request_id: str,
    db_path: Path | str | None = None,
) -> StoredRegistrationRequest | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                request_id,
                agent_did,
                agent_name,
                agent_type,
                description,
                organization_name,
                contact_email,
                use_case_summary,
                status,
                challenge_nonce,
                challenge_expires_at,
                proof_signature,
                proof_submitted_at,
                proof_payload_json,
                reviewed_by,
                reviewed_at,
                review_notes,
                approved_agent_did,
                retrieval_token_hash,
                credentials_retrieved_at,
                client_ip_hash,
                public_key,
                verification_method,
                created_at,
                updated_at
            FROM registration_requests
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

    if row is None:
        return None

    return _stored_registration_request_from_row(row)


def submit_registration_proof(
    request_id: str,
    proof_signature: str,
    db_path: Path | str | None = None,
) -> StoredRegistrationRequest:
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status FROM registration_requests WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()
        if row is None:
            raise RegistrationRequestNotFoundError(request_id)
        if row["status"] != "pending":
            raise RegistrationRequestNotPendingError(request_id)

        conn.execute(
            """
            UPDATE registration_requests
            SET proof_signature = ?,
                proof_submitted_at = ?,
                updated_at = ?
            WHERE request_id = ?
            """,
            (proof_signature, now, now, request_id),
        )
        conn.commit()

    stored = get_registration_request(request_id, db_path=db_path)
    assert stored is not None
    return stored


def mark_registration_request_expired(
    request_id: str,
    db_path: Path | str | None = None,
) -> StoredRegistrationRequest:
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status FROM registration_requests WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()
        if row is None:
            raise RegistrationRequestNotFoundError(request_id)
        if row["status"] != "pending":
            raise RegistrationRequestNotPendingError(request_id)

        conn.execute(
            """
            UPDATE registration_requests
            SET status = 'expired', updated_at = ?
            WHERE request_id = ?
            """,
            (now, request_id),
        )
        conn.commit()

    stored = get_registration_request(request_id, db_path=db_path)
    assert stored is not None
    return stored


def expire_stale_requests(db_path: Path | str | None = None) -> int:
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE registration_requests
            SET status = 'expired', updated_at = ?
            WHERE status = 'pending'
              AND challenge_expires_at < ?
            """,
            (now, now),
        )
        conn.commit()
        return cursor.rowcount


def get_agent_by_api_key_hash(
    api_key_hash: str,
    db_path: Path | str | None = None,
) -> StoredAgent | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                agent_did,
                agent_name,
                agent_type,
                description,
                verification_method,
                public_key,
                api_key_hash,
                status,
                created_at
            FROM agents
            WHERE api_key_hash = ?
            """,
            (api_key_hash,),
        ).fetchone()

    if row is None:
        return None

    return StoredAgent(
        agent_did=row["agent_did"],
        agent_name=row["agent_name"],
        agent_type=row["agent_type"],
        description=row["description"],
        verification_method=row["verification_method"],
        public_key=row["public_key"],
        api_key_hash=row["api_key_hash"],
        status=row["status"],
        created_at=row["created_at"],
    )
