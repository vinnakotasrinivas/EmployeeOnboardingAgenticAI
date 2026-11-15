from __future__ import annotations

import hashlib
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

STATUSES = ("indexed", "rejected", "pending", "error")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    filename    TEXT NOT NULL,
    sha256      TEXT NOT NULL UNIQUE,
    file_type   TEXT,
    size_bytes  INTEGER NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('indexed', 'rejected', 'pending', 'error')),
    category    TEXT,
    confidence  REAL,
    reason      TEXT,
    chunks      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)
"""


class DuplicateDocumentError(Exception):
    def __init__(self, existing: dict[str, Any]):
        self.existing = existing
        super().__init__(f"'{existing['filename']}' was already uploaded (status: {existing['status']}).")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    path = settings.registry_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upload_path(doc_id: str, filename: str) -> Path:
    return settings.uploads_dir / f"{doc_id}_{Path(filename).name}"


def find_by_hash(sha: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM documents WHERE sha256 = ?", (sha,)).fetchone()
    return dict(row) if row else None


def get(doc_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def add(
    filename: str,
    sha256: str,
    file_type: str | None,
    size_bytes: int,
    status: str,
    category: str | None = None,
    confidence: float | None = None,
    reason: str | None = None,
    chunks: int = 0,
    raw: bytes | None = None,
    doc_id: str | None = None,
) -> dict[str, Any]:
    """Insert a document. Pass `raw` for pending and indexed documents: it is saved to uploads/ so pending
    ones can be indexed after confirmation and indexed ones can be re-indexed if FAISS is rebuilt."""
    if status not in STATUSES:
        raise ValueError(f"Unknown status '{status}'.")
    doc_id = doc_id or str(uuid.uuid4())
    now = _now()
    try:
        with closing(_connect()) as conn, conn:
            conn.execute(
                "INSERT INTO documents (id, filename, sha256, file_type, size_bytes, status, category,"
                " confidence, reason, chunks, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, filename, sha256, file_type, size_bytes, status, category, confidence, reason, chunks,
                 now, now),
            )
    except sqlite3.IntegrityError:
        existing = find_by_hash(sha256)
        if existing:
            raise DuplicateDocumentError(existing) from None
        raise
    if raw is not None:
        path = upload_path(doc_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return get(doc_id)  # type: ignore[return-value]


def update_status(doc_id: str, status: str, chunks: int | None = None, reason: str | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"Unknown status '{status}'.")
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE documents SET status = ?, chunks = COALESCE(?, chunks), reason = COALESCE(?, reason),"
            " updated_at = ? WHERE id = ?",
            (status, chunks, reason, _now(), doc_id),
        )
    if cur.rowcount == 0:
        raise KeyError(doc_id)
    return get(doc_id)  # type: ignore[return-value]


def list_documents(status: str | None = None) -> list[dict[str, Any]]:
    query, params = "SELECT * FROM documents", ()
    if status:
        query, params = query + " WHERE status = ?", (status,)
    with closing(_connect()) as conn:
        rows = conn.execute(query + " ORDER BY created_at DESC, filename", params).fetchall()
    return [dict(r) for r in rows]


def delete(doc_id: str) -> bool:
    doc = get(doc_id)
    if not doc:
        return False
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    upload_path(doc_id, doc["filename"]).unlink(missing_ok=True)
    return True
