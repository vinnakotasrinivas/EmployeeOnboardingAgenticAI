"""In-memory DataFrames of indexed CSV/Excel documents, for the Data Analyst agent."""

from __future__ import annotations

import logging
import threading

import pandas as pd

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_tables: dict[str, dict[str, pd.DataFrame]] | None = None  # doc_id -> {"file.csv:sheet": DataFrame}

TABLE_TYPES = ("csv", "xlsx", "xls")


def _ensure_loaded() -> dict[str, dict[str, pd.DataFrame]]:
    global _tables
    with _lock:
        if _tables is None:
            _tables = {}
            _rebuild_from_registry(_tables)
        return _tables


def _rebuild_from_registry(target: dict[str, dict[str, pd.DataFrame]]) -> None:
    from app.ingestion import registry
    from app.ingestion.loaders import load_file

    for doc in registry.list_documents("indexed"):
        if doc["file_type"] not in TABLE_TYPES:
            continue
        path = registry.upload_path(doc["id"], doc["filename"])
        if not path.exists():
            logger.warning("Tables: saved upload for %s is missing.", doc["filename"])
            continue
        loaded = load_file(doc["filename"], path.read_bytes())
        if loaded.tables:
            target[doc["id"]] = loaded.tables


def register(doc_id: str, tables: dict[str, pd.DataFrame]) -> None:
    if tables:
        with _lock:
            _ensure_loaded()[doc_id] = tables


def remove(doc_id: str) -> bool:
    with _lock:
        return _ensure_loaded().pop(doc_id, None) is not None


def get_tables(doc_id: str) -> dict[str, pd.DataFrame]:
    with _lock:
        return dict(_ensure_loaded().get(doc_id, {}))


def all_tables() -> dict[str, pd.DataFrame]:
    """All tables keyed by "file:sheet"; if two documents share a key, the later one wins."""
    with _lock:
        return {key: df for per_doc in _ensure_loaded().values() for key, df in per_doc.items()}


def reset() -> None:
    """Forget the in-memory tables; they are rebuilt from the registry on next access."""
    global _tables
    with _lock:
        _tables = None
