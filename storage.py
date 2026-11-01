"""Opt-in local persistence for Dobara, using only Python's sqlite3.

Data lives in data/dobara.sqlite3 next to this file. The file is plain SQLite:
Dobara does not encrypt it. Every function opens its own short-lived
connection, so there is no shared connection state between requests.
"""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("dobara")

# Resolved relative to the application directory, not the working directory.
# Tests point this at a temporary file.
DB_PATH = Path(__file__).resolve().parent / "data" / "dobara.sqlite3"
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS comparisons (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES comparisons(id) ON DELETE SET NULL,
    title TEXT,
    source_url TEXT,
    claim TEXT NOT NULL,
    earlier_source TEXT NOT NULL,
    current_source TEXT NOT NULL,
    result_json TEXT NOT NULL,
    verdict TEXT NOT NULL,
    model TEXT NOT NULL,
    saved_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comparisons_saved_at ON comparisons(saved_at);
CREATE TABLE IF NOT EXISTS reviews (
    comparison_id TEXT PRIMARY KEY REFERENCES comparisons(id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK (
        decision IN ('not_reviewed', 'keep_claim', 'revise_claim', 'find_more_evidence')
    ),
    note TEXT NOT NULL CHECK (length(note) <= 500),
    updated_at TEXT NOT NULL
);
"""

# This optional helper table does not alter the v0.3.0 comparisons schema.
# Keeping user_version=1 allows v0.3.0 to read the same comparisons on rollback.
REVIEW_DECISIONS = frozenset({
    "not_reviewed", "keep_claim", "revise_claim", "find_more_evidence",
})


def empty_review():
    return {"decision": "not_reviewed", "note": "", "updated_at": None}


class StorageError(Exception):
    """The local database could not be read or written."""


class NotFound(StorageError):
    """No saved comparison has this ID."""


@contextmanager
def _db():
    """Open a connection, commit on success, roll back on error, always close."""
    conn = None
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StorageError("Saved data was created by a newer Dobara version.")
        conn.executescript(_SCHEMA)
        if version == 0:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        yield conn
        conn.commit()
    except StorageError:
        if conn is not None:
            conn.rollback()
        raise
    except (sqlite3.Error, OSError) as error:
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
        # Log only the exception class: never SQL parameters or source text.
        logger.warning("Local database error: %s", type(error).__name__)
        raise StorageError("The local database could not be accessed.") from None
    finally:
        if conn is not None:
            conn.close()


def save_comparison(*, title, source_url, claim, earlier_source, current_source,
                    result, parent_id=None):
    """Save one finished comparison. Returns its ID, timestamp and actual parent.

    If parent_id does not exist (for example it was deleted), the new record is
    saved without a link instead of failing.
    """
    record_id = uuid.uuid4().hex
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _db() as conn:
        if parent_id is not None:
            found = conn.execute(
                "SELECT 1 FROM comparisons WHERE id = ?", (parent_id,)
            ).fetchone()
            if found is None:
                parent_id = None
        conn.execute(
            "INSERT INTO comparisons (id, parent_id, title, source_url, claim, "
            "earlier_source, current_source, result_json, verdict, model, saved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record_id, parent_id, title, source_url, claim, earlier_source,
             current_source, json.dumps(result, ensure_ascii=False),
             result["verdict"], result["model"], saved_at),
        )
    return {"id": record_id, "saved_at": saved_at, "parent_id": parent_id}


def list_comparisons():
    """Summaries, newest first."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT c.id, c.parent_id, c.title, c.source_url, c.claim, c.verdict, "
            "c.model, c.saved_at, COALESCE(r.decision, 'not_reviewed') AS review_decision "
            "FROM comparisons c LEFT JOIN reviews r ON r.comparison_id = c.id "
            "ORDER BY c.saved_at DESC, c.rowid DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_comparison(record_id):
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM comparisons WHERE id = ?", (record_id,)
        ).fetchone()
        review = conn.execute(
            "SELECT decision, note, updated_at FROM reviews WHERE comparison_id = ?",
            (record_id,),
        ).fetchone()
    if row is None:
        raise NotFound("Saved comparison not found.")
    record = dict(row)
    record["review"] = dict(review) if review is not None else empty_review()
    try:
        record["result"] = json.loads(record.pop("result_json"))
    except ValueError:
        raise StorageError("The saved record could not be read.") from None
    return record


def delete_comparison(record_id):
    """Delete one record. Children keep existing; their parent link is cleared."""
    with _db() as conn:
        cursor = conn.execute("DELETE FROM comparisons WHERE id = ?", (record_id,))
        if cursor.rowcount == 0:
            raise NotFound("Saved comparison not found.")


def save_review(record_id, *, decision, note):
    """Update only the human review, never the original comparison or model result."""
    if decision not in REVIEW_DECISIONS or not isinstance(note, str) or len(note) > 500:
        raise ValueError("Invalid reviewer decision or note.")
    updated_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with _db() as conn:
        if conn.execute(
            "SELECT 1 FROM comparisons WHERE id = ?", (record_id,)
        ).fetchone() is None:
            raise NotFound("Saved comparison not found.")
        conn.execute(
            "INSERT INTO reviews (comparison_id, decision, note, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(comparison_id) DO UPDATE SET "
            "decision=excluded.decision, note=excluded.note, updated_at=excluded.updated_at",
            (record_id, decision, note, updated_at),
        )
    return {"decision": decision, "note": note, "updated_at": updated_at}
