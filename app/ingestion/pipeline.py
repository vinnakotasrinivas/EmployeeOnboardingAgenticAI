from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import PurePath
from typing import Iterator, Literal

from pydantic import BaseModel

from app.ingestion import registry
from app.ingestion.chunker import chunk
from app.ingestion.loaders import load_file
from app.ingestion.models import LoadResult
from app.ingestion.relevance import build_profile, classify, decide
from app.ingestion.validator import validate_file
from app.store import tables, vector_store

logger = logging.getLogger("onboardiq.ingest")

PREVIEW_CHARS = 800
PREVIEW_ROWS = 5
UNEXPECTED = "Unexpected error while processing this file."

Status = Literal["indexed", "rejected", "pending", "error", "duplicate"]


class IngestResult(BaseModel):
    doc_id: str | None = None
    filename: str
    status: Status
    message: str
    category: str | None = None
    confidence: float | None = None
    pages: int | None = None
    rows: int | None = None
    chunks: int = 0
    preview: str = ""


@contextmanager
def _stage(name: str, filename: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        logger.info("%-10s %-30s %.2fs", name, filename, time.perf_counter() - start)


def _preview(loaded: LoadResult) -> str:
    if loaded.tables:
        key, df = next(iter(loaded.tables.items()))
        return f"{key.split(':', 1)[1]} ({len(df)} rows)\n\n{df.head(PREVIEW_ROWS).to_markdown(index=False)}"
    text = loaded.docs[0].text if loaded.docs else ""
    return text[:PREVIEW_CHARS] + ("..." if len(text) > PREVIEW_CHARS else "")


def _base(filename: str, loaded: LoadResult | None = None, **fields) -> dict:
    stats = loaded.stats if loaded else {}
    extra = {"pages": stats.get("pages"), "rows": stats.get("rows"), "preview": _preview(loaded)} if loaded else {}
    return {"filename": filename, **extra, **fields}


def _index(doc_id: str, filename: str, loaded: LoadResult, category: str) -> int:
    """Chunk and add to FAISS and the table store. Returns the chunk count."""
    with _stage("chunk", filename):
        docs = chunk(loaded, doc_id, category)
    with _stage("embed", filename):
        added = vector_store.add_documents(docs)
    tables.register(doc_id, loaded.tables)
    return added


def _duplicate_message(existing: dict) -> str:
    when = datetime.fromisoformat(existing["created_at"]).astimezone().strftime("%d %b %Y")
    return {
        "indexed": f"Already uploaded on {when} and indexed as '{existing['filename']}'.",
        "pending": f"Already uploaded on {when} and waiting for your review.",
        "rejected": f"Already uploaded on {when} and rejected: {existing['reason']}",
        "error": f"Already uploaded on {when} and it could not be read: {existing['reason']}",
    }[existing["status"]]


def ingest_file(filename: str, data: bytes, force: bool = False) -> IngestResult:
    """Validate, load, check relevance, chunk and index one file. `force=True` skips the relevance gate."""
    filename = PurePath(filename).name
    sha = registry.file_hash(data)

    existing = registry.find_by_hash(sha)
    if existing:
        return IngestResult(
            doc_id=existing["id"],
            filename=filename,
            status="duplicate",
            message=_duplicate_message(existing),
            category=existing["category"],
            confidence=existing["confidence"],
            chunks=existing["chunks"],
        )

    with _stage("validate", filename):
        check = validate_file(filename, data)
    if not check.ok:
        return IngestResult(filename=filename, status="error", message=check.message)

    with _stage("load", filename):
        loaded = load_file(filename, data)
    if loaded.error:
        doc = registry.add(filename, sha, check.file_type, len(data), "error", reason=loaded.error)
        return IngestResult(**_base(filename, loaded, doc_id=doc["id"], status="error", message=loaded.error))

    if force:
        category, confidence, reason, decision = "unknown", None, "Added without relevance check.", "ingest"
    else:
        with _stage("relevance", filename):
            verdict = classify(build_profile(filename, loaded))
        category, confidence, reason, decision = verdict.category, verdict.confidence, verdict.reason, decide(verdict)

    common = {"category": category, "confidence": confidence, "reason": reason}
    if decision == "reject":
        doc = registry.add(filename, sha, check.file_type, len(data), "rejected", **common)
        message = f"Not an onboarding document: {reason}"
        return IngestResult(**_base(filename, loaded, doc_id=doc["id"], status="rejected", message=message,
                                    category=category, confidence=confidence))
    if decision == "pending":
        doc = registry.add(filename, sha, check.file_type, len(data), "pending", raw=data, **common)
        message = f"Needs your review before indexing: {reason}"
        return IngestResult(**_base(filename, loaded, doc_id=doc["id"], status="pending", message=message,
                                    category=category, confidence=confidence))

    doc_id = str(uuid.uuid4())
    chunks = _index(doc_id, filename, loaded, category)
    try:
        registry.add(filename, sha, check.file_type, len(data), "indexed", chunks=chunks, raw=data, doc_id=doc_id,
                     **common)
    except Exception:
        _remove_from_stores(doc_id)
        raise
    return IngestResult(**_base(filename, loaded, doc_id=doc_id, status="indexed",
                                message=f"Indexed {chunks} chunks.", chunks=chunks,
                                category=category, confidence=confidence))


def ingest_many(files: list[tuple[str, bytes]]) -> list[IngestResult]:
    results = []
    for filename, data in files:
        try:
            results.append(ingest_file(filename, data))
        except Exception:
            logger.exception("Ingest failed for %s", filename)
            results.append(IngestResult(filename=PurePath(filename).name, status="error", message=UNEXPECTED))
    return results


def confirm_pending(doc_id: str) -> IngestResult:
    doc = registry.get(doc_id)
    if not doc or doc["status"] != "pending":
        return IngestResult(doc_id=doc_id, filename=doc["filename"] if doc else "", status="error",
                            message="This document is not waiting for review.")
    path = registry.upload_path(doc_id, doc["filename"])
    if not path.exists():
        registry.update_status(doc_id, "error", reason="The saved upload is missing; upload the file again.")
        return IngestResult(doc_id=doc_id, filename=doc["filename"], status="error",
                            message="The saved upload is missing; delete it and upload the file again.")
    loaded = load_file(doc["filename"], path.read_bytes())
    if loaded.error:
        registry.update_status(doc_id, "error", reason=loaded.error)
        return IngestResult(**_base(doc["filename"], loaded, doc_id=doc_id, status="error", message=loaded.error))

    try:
        chunks = _index(doc_id, doc["filename"], loaded, doc["category"] or "unknown")
        registry.update_status(doc_id, "indexed", chunks=chunks, reason="Confirmed by user.")
    except Exception:
        logger.exception("Confirm failed for %s", doc["filename"])
        _remove_from_stores(doc_id)
        return IngestResult(doc_id=doc_id, filename=doc["filename"], status="error", message=UNEXPECTED)
    return IngestResult(**_base(doc["filename"], loaded, doc_id=doc_id, status="indexed",
                                message=f"Indexed {chunks} chunks.", chunks=chunks,
                                category=doc["category"], confidence=doc["confidence"]))


def preview_document(doc_id: str) -> IngestResult | None:
    """Preview text or table head plus page/row counts for a stored document. None if it doesn't exist."""
    doc = registry.get(doc_id)
    if not doc:
        return None
    fields = {"doc_id": doc_id, "status": doc["status"], "category": doc["category"],
              "confidence": doc["confidence"], "chunks": doc["chunks"]}
    path = registry.upload_path(doc_id, doc["filename"])
    if not path.exists():
        return IngestResult(filename=doc["filename"], message="The original file is not stored, so there is "
                            "no preview.", **fields)
    loaded = load_file(doc["filename"], path.read_bytes())
    return IngestResult(**_base(doc["filename"], loaded, message=loaded.error or doc["reason"] or "", **fields))


def _remove_from_stores(doc_id: str) -> None:
    vector_store.delete_doc(doc_id)
    tables.remove(doc_id)


def delete_document(doc_id: str) -> bool:
    """Remove a document from FAISS, the table store, the registry and uploads/."""
    _remove_from_stores(doc_id)
    return registry.delete(doc_id)


def discard_pending(doc_id: str) -> bool:
    doc = registry.get(doc_id)
    if not doc or doc["status"] != "pending":
        return False
    return delete_document(doc_id)
