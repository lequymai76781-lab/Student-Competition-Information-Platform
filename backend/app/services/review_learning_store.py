"""Immutable review-learning sidecar; this module never opens a business DB.

The caller owns authentication, manifest verification and committed audit validation.
Only trusted server provenance may be passed here. Every write is an INSERT into
this separate database. Derived state never rewrites captured evidence.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from uuid import uuid4

from app.services.review_learning_metrics import compare_prediction


_APPLICATION_ID = 0x524C5331  # RLS1, checked before opening an existing SQLite file.
_INITIALIZATION_LOCK = threading.RLock()
_HUMAN_FIELDS = (
    "human_primary_type", "human_secondary_type", "human_policy", "human_risk_level",
    "human_action", "human_field_decisions", "human_relation_decision", "human_note",
)
_TABLES = ("learning_metadata", "learning_sessions", "learning_events", "learning_examples", "learning_batches", "learning_batch_members")
_REPLACEMENT_KEYS = {
    "learning_metadata": "old.schema_version=NEW.schema_version",
    "learning_sessions": "old.sequence=NEW.sequence OR old.session_id=NEW.session_id",
    "learning_events": "old.sequence=NEW.sequence OR old.event_id=NEW.event_id",
    "learning_examples": """old.sequence=NEW.sequence OR old.example_id=NEW.example_id
        OR old.supersedes_example_id=NEW.supersedes_example_id
        OR (old.namespace=NEW.namespace AND old.decision_key=NEW.decision_key)
        OR (old.session_id=NEW.session_id AND old.supersedes_example_id IS NULL AND NEW.supersedes_example_id IS NULL)""",
    "learning_batches": "old.sequence=NEW.sequence OR old.batch_id=NEW.batch_id",
    "learning_batch_members": "old.rowid=NEW.rowid OR (old.namespace=NEW.namespace AND old.example_id=NEW.example_id)",
}


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _same_path(left: Path, right: Path) -> bool:
    if os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve())):
        return True
    return left.exists() and right.exists() and os.path.samefile(left, right)


def _guard_path(path) -> Path:
    raw = os.fspath(path)
    if not raw or raw == ":memory:" or raw.startswith(("file:", "sqlite:")):
        raise ValueError("Learning store requires a separate filesystem path")
    resolved = Path(raw).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[3]
    forbidden = [project_root / "data" / name for name in ("v02.sqlite", "dev.sqlite")]
    # Resolve configured business URLs without connecting to the business engine.
    from app.core.config import get_settings

    urls = {os.environ.get("DATABASE_URL", ""), get_settings().database_url}
    for url in urls:
        if url.startswith("sqlite:///"):
            database_path = url[len("sqlite:///"):].split("?", 1)[0]
            if database_path and database_path != ":memory:":
                if re.match(r"^/[A-Za-z]:/", database_path):
                    database_path = database_path[1:]
                forbidden.append(Path(database_path).expanduser().resolve())
    if any(_same_path(resolved, target) for target in forbidden):
        raise ValueError("Learning store cannot use a business database path")
    if resolved.exists() and not resolved.is_file():
        raise ValueError("Learning store path must be a file")
    return resolved


def _check_header(path: Path) -> None:
    if path.exists() and path.stat().st_size:
        # Read only the format marker. Never issue even a read-only SQL query on
        # an unrelated SQLite file, and never add learning tables to that file.
        with path.open("rb") as source:
            header = source.read(100)
        if len(header) < 100 or header[:16] != b"SQLite format 3\x00" or int.from_bytes(header[68:72], "big") != _APPLICATION_ID:
            raise ValueError("Existing file is not a review-learning sidecar")


def _human_labels(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Human ground truth must be an object")
    if any(key not in _HUMAN_FIELDS for key in value):
        raise ValueError("Unknown human ground truth dimension")
    result = {key: value.get(key) for key in _HUMAN_FIELDS}
    if not isinstance(result["human_primary_type"], str) or not result["human_primary_type"].strip():
        raise ValueError("An explicit human primary type is required")
    if result["human_policy"] is not None and not isinstance(result["human_policy"], bool):
        raise ValueError("Human policy must be a boolean or null")
    if result["human_field_decisions"] is not None and not isinstance(result["human_field_decisions"], dict):
        raise ValueError("Human field decisions must be an object or null")
    return json.loads(_canonical(result))


def _require_real_human(provenance: dict) -> None:
    if provenance.get("origin") != "real_candidate" or provenance.get("actor_mode") != "human" or provenance.get("source") != "review_audit":
        raise PermissionError("Only verified real-candidate human review evidence can become a learning example")
    if not isinstance(provenance.get("dataset_id"), str) or not provenance["dataset_id"].strip():
        raise ValueError("Verified dataset identity is required")
    fingerprint = provenance.get("candidate_sha256")
    if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint) is None:
        raise ValueError("Verified candidate SHA256 is required")


class ReviewLearningStore:
    def __init__(self, path, namespace="default"):
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValueError("A non-empty learning namespace is required")
        self.path = _guard_path(path)
        self.namespace = namespace
        with _INITIALIZATION_LOCK:
            _check_header(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection(write=True) as connection:
                connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
                statements = (
                    "CREATE TABLE IF NOT EXISTS learning_metadata (schema_version INTEGER PRIMARY KEY, created_at TEXT NOT NULL)",
                    """CREATE TABLE IF NOT EXISTS learning_sessions (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL UNIQUE,
                        namespace TEXT NOT NULL, admin_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL,
                        identity_key TEXT NOT NULL, input_features TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
                        shadow_prediction TEXT NOT NULL, provenance TEXT NOT NULL, started_at TEXT NOT NULL)""",
                    """CREATE TABLE IF NOT EXISTS learning_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                        namespace TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES learning_sessions(session_id),
                        admin_id INTEGER NOT NULL, event TEXT NOT NULL CHECK(event IN ('source_open','decision','submit')),
                        details TEXT NOT NULL, created_at TEXT NOT NULL)""",
                    """CREATE TABLE IF NOT EXISTS learning_examples (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT, example_id TEXT NOT NULL UNIQUE,
                        namespace TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES learning_sessions(session_id),
                        admin_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL, decision_key TEXT,
                        human_ground_truth TEXT NOT NULL, review_context TEXT NOT NULL, comparison TEXT NOT NULL,
                        supersedes_example_id TEXT UNIQUE REFERENCES learning_examples(example_id),
                        correction_reason TEXT, created_at TEXT NOT NULL, UNIQUE(namespace, decision_key))""",
                    """CREATE UNIQUE INDEX IF NOT EXISTS learning_one_completion_per_session
                        ON learning_examples(session_id) WHERE supersedes_example_id IS NULL""",
                    """CREATE TABLE IF NOT EXISTS learning_batches (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL UNIQUE,
                        namespace TEXT NOT NULL, min_samples INTEGER NOT NULL CHECK(min_samples IN (100,300,500)),
                        sample_count INTEGER NOT NULL, dataset_hash TEXT NOT NULL, dataset_snapshot TEXT NOT NULL,
                        class_distribution TEXT NOT NULL, created_at TEXT NOT NULL)""",
                    """CREATE TABLE IF NOT EXISTS learning_batch_members (
                        namespace TEXT NOT NULL, example_id TEXT NOT NULL REFERENCES learning_examples(example_id),
                        batch_id TEXT NOT NULL REFERENCES learning_batches(batch_id), PRIMARY KEY(namespace,example_id))""",
                    "CREATE INDEX IF NOT EXISTS learning_session_identity ON learning_sessions(namespace,identity_key,sequence)",
                    "CREATE INDEX IF NOT EXISTS learning_event_session ON learning_events(session_id,sequence)",
                    "CREATE INDEX IF NOT EXISTS learning_example_namespace ON learning_examples(namespace,sequence)",
                )
                for statement in statements:
                    connection.execute(statement)
                for table in _TABLES:
                    for action in ("UPDATE", "DELETE"):
                        connection.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                            BEFORE {action} ON {table} BEGIN
                            SELECT RAISE(ABORT, 'learning records are immutable'); END""")
                    # SQLite REPLACE may omit DELETE triggers when the caller's
                    # recursive_triggers flag is off, so reject replacement
                    # conflicts before SQLite's conflict algorithm executes.
                    connection.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_replace
                        BEFORE INSERT ON {table}
                        WHEN EXISTS (SELECT 1 FROM {table} old WHERE {_REPLACEMENT_KEYS[table]})
                        BEGIN SELECT RAISE(ABORT, 'learning records are immutable'); END""")
                if connection.execute("SELECT 1 FROM learning_metadata WHERE schema_version=1").fetchone() is None:
                    connection.execute("INSERT INTO learning_metadata(schema_version,created_at) VALUES (1,?)", (_now(),))

    @contextmanager
    def _connection(self, *, write=False):
        _check_header(self.path)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _session_row(self, connection, session_id, admin_id=None):
        row = connection.execute("SELECT * FROM learning_sessions WHERE namespace=? AND session_id=?", (self.namespace, session_id)).fetchone()
        if row is None:
            raise KeyError("Review session not found")
        if admin_id is not None and row["admin_id"] != admin_id:
            raise PermissionError("Review session belongs to another administrator")
        return row

    def _session_view(self, connection, row):
        completed = connection.execute("SELECT 1 FROM learning_examples WHERE session_id=? LIMIT 1", (row["session_id"],)).fetchone() is not None
        events = [self._event_view(event) for event in connection.execute("SELECT * FROM learning_events WHERE session_id=? ORDER BY sequence", (row["session_id"],))]
        return {
            "id": row["session_id"], "session_id": row["session_id"], "namespace": row["namespace"],
            "admin_id": row["admin_id"], "candidate_id": row["candidate_id"],
            "input_features": json.loads(row["input_features"]), "snapshot_sha256": row["snapshot_sha256"],
            "shadow_prediction": json.loads(row["shadow_prediction"]), "provenance": json.loads(row["provenance"]),
            "started_at": row["started_at"], "state": "completed" if completed else "observing", "events": events,
        }

    @staticmethod
    def _event_view(row):
        return {
            "id": row["event_id"], "event_id": row["event_id"], "session_id": row["session_id"],
            "admin_id": row["admin_id"], "event": row["event"], "details": json.loads(row["details"]),
            "at": row["created_at"], "timestamp": row["created_at"], "state": "recorded",
        }

    def start_session(self, *, admin_id, candidate_id, input_features, shadow_prediction, provenance):
        if not isinstance(admin_id, int) or isinstance(admin_id, bool) or admin_id <= 0:
            raise ValueError("An administrator identity is required")
        if not isinstance(candidate_id, int) or isinstance(candidate_id, bool) or candidate_id <= 0:
            raise ValueError("A candidate identity is required")
        if not all(isinstance(value, dict) for value in (input_features, shadow_prediction, provenance)):
            raise ValueError("Session evidence must be JSON objects")
        snapshot_sha256 = _digest(input_features)
        identity_key = _digest([admin_id, candidate_id, snapshot_sha256, provenance])
        with self._connection(write=True) as connection:
            existing = connection.execute("""SELECT s.* FROM learning_sessions s
                WHERE s.namespace=? AND s.identity_key=?
                AND NOT EXISTS (SELECT 1 FROM learning_examples e WHERE e.session_id=s.session_id)
                ORDER BY s.sequence DESC LIMIT 1""", (self.namespace, identity_key)).fetchone()
            if existing is not None:
                return self._session_view(connection, existing)
            session_id = str(uuid4())
            connection.execute("""INSERT INTO learning_sessions(session_id,namespace,admin_id,candidate_id,
                identity_key,input_features,snapshot_sha256,shadow_prediction,provenance,started_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (session_id, self.namespace, admin_id, candidate_id, identity_key,
                _canonical(input_features), snapshot_sha256, _canonical(shadow_prediction), _canonical(provenance), _now()))
            return self._session_view(connection, self._session_row(connection, session_id, admin_id))

    def get_session(self, session_id, admin_id):
        with self._connection() as connection:
            return self._session_view(connection, self._session_row(connection, session_id, admin_id))

    def pending_sessions(self, admin_id, candidate_id=None):
        """Owned, incomplete submit evidence for the server's after-commit hook."""
        with self._connection() as connection:
            rows = connection.execute("""SELECT s.* FROM learning_sessions s WHERE s.namespace=? AND s.admin_id=?
                AND (? IS NULL OR s.candidate_id=?)
                AND EXISTS (SELECT 1 FROM learning_events ev WHERE ev.session_id=s.session_id AND ev.event='submit')
                AND NOT EXISTS (SELECT 1 FROM learning_examples e WHERE e.session_id=s.session_id)
                ORDER BY s.sequence""", (self.namespace, admin_id, candidate_id, candidate_id)).fetchall()
            return [self._session_view(connection, row) for row in rows]

    def event(self, session_id, admin_id, event, details=None):
        if event not in {"source_open", "decision", "submit"}:
            raise ValueError("Unsupported review event")
        if details is not None and not isinstance(details, dict):
            raise ValueError("Review event details must be an object")
        with self._connection(write=True) as connection:
            self._session_row(connection, session_id, admin_id)
            event_id = str(uuid4())
            connection.execute("""INSERT INTO learning_events(event_id,namespace,session_id,admin_id,event,details,created_at)
                VALUES (?,?,?,?,?,?,?)""", (event_id, self.namespace, session_id, admin_id, event, _canonical(details or {}), _now()))
            return self._event_view(connection.execute("SELECT * FROM learning_events WHERE event_id=?", (event_id,)).fetchone())

    def _example_view(self, connection, row):
        session = self._session_row(connection, row["session_id"])
        successor = connection.execute("SELECT example_id FROM learning_examples WHERE supersedes_example_id=?", (row["example_id"],)).fetchone()
        status = "superseded" if successor else "corrected" if row["supersedes_example_id"] else "active"
        return {
            "id": row["example_id"], "example_id": row["example_id"], "namespace": row["namespace"],
            "session_id": row["session_id"], "admin_id": row["admin_id"], "candidate_id": row["candidate_id"],
            "decision_key": row["decision_key"], "input_features": json.loads(session["input_features"]),
            "snapshot_sha256": session["snapshot_sha256"], "shadow_prediction": json.loads(session["shadow_prediction"]),
            "human_ground_truth": json.loads(row["human_ground_truth"]), "review_context": json.loads(row["review_context"]),
            "comparison": json.loads(row["comparison"]), "provenance": json.loads(session["provenance"]),
            "model_version": json.loads(session["shadow_prediction"]).get("shadow_model_version"),
            "supersedes_example_id": row["supersedes_example_id"],
            "superseded_by_example_id": successor["example_id"] if successor else None,
            "correction_reason": row["correction_reason"], "learning_status": status,
            "created_at": row["created_at"], "started_at": session["started_at"],
        }

    def complete(self, session_id, admin_id, *, human_ground_truth, review_context, decision_key):
        human = _human_labels(human_ground_truth)
        if not isinstance(review_context, dict) or not review_context:
            raise ValueError("Committed review context is required")
        if not isinstance(decision_key, str) or not decision_key.strip():
            raise ValueError("A unique committed decision key is required")
        human_json, context_json = _canonical(human), _canonical(review_context)
        with self._connection(write=True) as connection:
            session = self._session_row(connection, session_id, admin_id)
            _require_real_human(json.loads(session["provenance"]))
            existing = connection.execute("SELECT * FROM learning_examples WHERE namespace=? AND decision_key=?", (self.namespace, decision_key)).fetchone()
            if existing is not None:
                if existing["session_id"] != session_id or existing["human_ground_truth"] != human_json or existing["review_context"] != context_json:
                    raise ValueError("Decision already belongs to different immutable review evidence")
                return self._example_view(connection, existing)
            if connection.execute("SELECT 1 FROM learning_examples WHERE session_id=? LIMIT 1", (session_id,)).fetchone():
                raise ValueError("Review session already completed; append a correction instead")
            example_id = str(uuid4())
            comparison = compare_prediction(json.loads(session["shadow_prediction"]), human)
            connection.execute("""INSERT INTO learning_examples(example_id,namespace,session_id,admin_id,candidate_id,
                decision_key,human_ground_truth,review_context,comparison,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (example_id, self.namespace, session_id, admin_id, session["candidate_id"], decision_key, human_json, context_json, _canonical(comparison), _now()))
            return self._example_view(connection, connection.execute("SELECT * FROM learning_examples WHERE example_id=?", (example_id,)).fetchone())

    def examples(self, active_only=True):
        with self._connection() as connection:
            rows = connection.execute("""SELECT e.* FROM learning_examples e WHERE e.namespace=?
                AND (?=0 OR NOT EXISTS (SELECT 1 FROM learning_examples c WHERE c.supersedes_example_id=e.example_id))
                ORDER BY e.sequence""", (self.namespace, int(bool(active_only)))).fetchall()
            return [self._example_view(connection, row) for row in rows]

    def correct(self, example_id, admin_id, *, human_ground_truth, reason):
        if not isinstance(human_ground_truth, dict) or not human_ground_truth:
            raise ValueError("A human label correction is required")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A correction reason is required")
        if not isinstance(admin_id, int) or isinstance(admin_id, bool) or admin_id <= 0:
            raise ValueError("An administrator identity is required")
        with self._connection(write=True) as connection:
            original = connection.execute("SELECT * FROM learning_examples WHERE namespace=? AND example_id=?", (self.namespace, example_id)).fetchone()
            if original is None:
                raise KeyError("Learning example not found")
            human = _human_labels({**json.loads(original["human_ground_truth"]), **human_ground_truth})
            human_json = _canonical(human)
            session = self._session_row(connection, original["session_id"])
            _require_real_human(json.loads(session["provenance"]))
            successor = connection.execute("SELECT * FROM learning_examples WHERE supersedes_example_id=?", (example_id,)).fetchone()
            if successor is not None:
                if successor["admin_id"] == admin_id and successor["human_ground_truth"] == human_json and successor["correction_reason"] == reason:
                    return self._example_view(connection, successor)
                raise ValueError("Example has already been superseded; correct its current successor")
            corrected_id = str(uuid4())
            comparison = compare_prediction(json.loads(session["shadow_prediction"]), human)
            connection.execute("""INSERT INTO learning_examples(example_id,namespace,session_id,admin_id,candidate_id,
                human_ground_truth,review_context,comparison,supersedes_example_id,correction_reason,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (corrected_id, self.namespace, original["session_id"], admin_id,
                original["candidate_id"], human_json, original["review_context"], _canonical(comparison), example_id, reason, _now()))
            return self._example_view(connection, connection.execute("SELECT * FROM learning_examples WHERE example_id=?", (corrected_id,)).fetchone())

    @staticmethod
    def _batch_view(row):
        snapshot = json.loads(row["dataset_snapshot"])
        return {
            "id": row["batch_id"], "batch_id": row["batch_id"], "namespace": row["namespace"],
            "min_samples": row["min_samples"], "sample_count": row["sample_count"],
            "dataset_hash": row["dataset_hash"], "dataset_snapshot": snapshot,
            "example_ids": [example["example_id"] for example in snapshot],
            "class_distribution": json.loads(row["class_distribution"]),
            "created_at": row["created_at"], "status": "ready_for_evaluation",
        }

    def create_batch(self, min_samples=100):
        if type(min_samples) is not int or min_samples not in {100, 300, 500}:
            raise ValueError("Batch minimum must be 100, 300 or 500")
        with self._connection(write=True) as connection:
            rows = connection.execute("""SELECT e.* FROM learning_examples e WHERE e.namespace=?
                AND NOT EXISTS (SELECT 1 FROM learning_examples c WHERE c.supersedes_example_id=e.example_id)
                AND NOT EXISTS (SELECT 1 FROM learning_batch_members b WHERE b.namespace=e.namespace AND b.example_id=e.example_id)
                ORDER BY e.example_id""", (self.namespace,)).fetchall()
            if len(rows) < min_samples:
                raise ValueError(f"Need {min_samples} new effective samples; only {len(rows)} available")
            snapshot = [self._example_view(connection, row) for row in rows]
            distribution = dict(Counter(example["human_ground_truth"]["human_primary_type"] for example in snapshot))
            batch_id = str(uuid4())
            connection.execute("""INSERT INTO learning_batches(batch_id,namespace,min_samples,sample_count,
                dataset_hash,dataset_snapshot,class_distribution,created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (batch_id, self.namespace, min_samples, len(snapshot), _digest(snapshot), _canonical(snapshot), _canonical(distribution), _now()))
            connection.executemany("INSERT INTO learning_batch_members(namespace,example_id,batch_id) VALUES (?,?,?)",
                [(self.namespace, row["example_id"], batch_id) for row in rows])
            return self._batch_view(connection.execute("SELECT * FROM learning_batches WHERE batch_id=?", (batch_id,)).fetchone())

    def batches(self):
        with self._connection() as connection:
            return [self._batch_view(row) for row in connection.execute("SELECT * FROM learning_batches WHERE namespace=? ORDER BY sequence", (self.namespace,))]
