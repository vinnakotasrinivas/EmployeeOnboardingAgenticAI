from __future__ import annotations

import logging
import shutil
import threading

import faiss
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document

from app.config import settings
from app.store.embeddings import get_embeddings

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_store: FAISS | None = None


def _new_store() -> FAISS:
    embeddings = get_embeddings()
    dim = len(embeddings.embed_query("dimension probe"))
    return FAISS(
        embedding_function=embeddings,
        index=faiss.IndexFlatIP(dim),
        docstore=InMemoryDocstore(),
        index_to_docstore_id={},
        distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
    )


def _save(store: FAISS) -> None:
    settings.faiss_dir.mkdir(parents=True, exist_ok=True)
    store.save_local(str(settings.faiss_dir))


def _all_docs(store: FAISS) -> list[tuple[str, Document]]:
    return [(sid, store.docstore.search(sid)) for sid in store.index_to_docstore_id.values()]


def load_or_create() -> FAISS:
    global _store
    with _lock:
        if _store is not None:
            return _store
        if (settings.faiss_dir / "index.faiss").exists():
            try:
                # Only ever loads the index this app wrote to its own data folder.
                _store = FAISS.load_local(
                    str(settings.faiss_dir),
                    get_embeddings(),
                    allow_dangerous_deserialization=True,
                    distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
                )
                return _store
            except Exception as exc:
                logger.warning("FAISS index at %s could not be loaded (%s); rebuilding.", settings.faiss_dir, exc)
                shutil.rmtree(settings.faiss_dir, ignore_errors=True)
                _store = _new_store()
                rebuild_from_registry()
                return _store
        _store = _new_store()
        return _store


def reset(delete_files: bool = False) -> None:
    """Drop the in-memory index (and optionally the files on disk)."""
    global _store
    with _lock:
        _store = None
        if delete_files:
            shutil.rmtree(settings.faiss_dir, ignore_errors=True)


def add_documents(docs: list[Document]) -> int:
    if not docs:
        return 0
    with _lock:
        store = load_or_create()
        store.add_documents(docs, ids=[d.metadata["chunk_id"] for d in docs])
        _save(store)
    return len(docs)


def delete_doc(doc_id: str) -> int:
    with _lock:
        store = load_or_create()
        ids = [sid for sid, doc in _all_docs(store) if doc.metadata.get("doc_id") == doc_id]
        if ids:
            store.delete(ids)
            _save(store)
    return len(ids)


def search(
    query: str,
    k: int | None = None,
    category: str | None = None,
    threshold: float | None = None,
) -> list[tuple[Document, float]]:
    k = k or settings.top_k
    threshold = settings.similarity_threshold if threshold is None else threshold
    with _lock:
        store = load_or_create()
        if store.index.ntotal == 0:
            return []
        filter_ = {"category": category} if category else None
        results = store.similarity_search_with_score(query, k=k, filter=filter_, fetch_k=max(50, k * 10))
    hits = [(doc, float(score)) for doc, score in results if score >= threshold]
    return sorted(hits, key=lambda hit: hit[1], reverse=True)


def stats() -> dict[str, int]:
    with _lock:
        store = load_or_create()
        doc_ids = {doc.metadata.get("doc_id") for _, doc in _all_docs(store)}
        return {"chunks": store.index.ntotal, "docs": len(doc_ids - {None})}


def rebuild_from_registry() -> int:
    """Re-index every `indexed` registry entry from its saved upload. Returns the number of chunks added."""
    from app.ingestion import registry
    from app.ingestion.chunker import chunk
    from app.ingestion.loaders import load_file

    total = 0
    with _lock:
        for doc in registry.list_documents("indexed"):
            path = registry.upload_path(doc["id"], doc["filename"])
            if not path.exists():
                logger.warning("Cannot rebuild %s: saved upload %s is missing.", doc["filename"], path)
                continue
            loaded = load_file(doc["filename"], path.read_bytes())
            if loaded.error:
                logger.warning("Cannot rebuild %s: %s", doc["filename"], loaded.error)
                continue
            total += add_documents(chunk(loaded, doc["id"], doc["category"] or "unknown"))
    logger.warning("Rebuilt FAISS index from the registry: %d chunks.", total)
    return total
