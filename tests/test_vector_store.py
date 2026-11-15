import pytest
from langchain_core.documents import Document

from app.config import settings
from app.ingestion import registry
from app.store import vector_store


pytestmark = pytest.mark.usefixtures("temp_data_dir", "real_embeddings")


def make_doc(doc_id: str, n: int, text: str, category: str) -> Document:
    return Document(
        page_content=text,
        metadata={"doc_id": doc_id, "chunk_id": f"{doc_id}:{n}", "source": f"{doc_id}.txt", "category": category},
    )


@pytest.fixture
def indexed():
    docs = [
        make_doc("leave", 0, "US employees receive 20 days of paid time off (PTO) per year.", "payroll_leave"),
        make_doc("leave", 1, "India employees earn 18 days of earned leave each year.", "payroll_leave"),
        make_doc("vpn", 0, "Connect to the VPN with Zscaler and sign in with Okta MFA.", "it_setup_security"),
    ]
    assert vector_store.add_documents(docs) == 3
    return docs


def test_search_returns_right_doc(indexed):
    hits = vector_store.search("How many PTO days do I get?")
    assert hits[0][0].metadata["doc_id"] == "leave"
    assert [s for _, s in hits] == sorted((s for _, s in hits), reverse=True)
    assert 0 < hits[0][1] <= 1.0


def test_category_filter(indexed):
    hits = vector_store.search("How many PTO days do I get?", category="it_setup_security", threshold=0)
    assert hits and all(d.metadata["category"] == "it_setup_security" for d, _ in hits)


def test_threshold_filters_unrelated_query(indexed):
    assert vector_store.search("pasta carbonara recipe", threshold=0.5) == []


def test_delete_doc_and_stats(indexed):
    assert vector_store.stats() == {"chunks": 3, "docs": 2}
    assert vector_store.delete_doc("leave") == 2
    assert vector_store.stats() == {"chunks": 1, "docs": 1}
    assert all(d.metadata["doc_id"] != "leave" for d, _ in vector_store.search("PTO days", threshold=0))
    assert vector_store.delete_doc("leave") == 0


def test_index_persists_to_disk(indexed):
    vector_store.reset()
    assert vector_store.stats()["chunks"] == 3


def test_corrupt_index_is_rebuilt_from_registry(tmp_path):
    raw = b"Parking is free in the basement garage for all employees."
    doc = registry.add("parking.txt", registry.file_hash(raw), "txt", len(raw), "indexed", category="facilities_faq", raw=raw)
    settings.faiss_dir.mkdir(parents=True)
    (settings.faiss_dir / "index.faiss").write_bytes(b"not a faiss index")
    (settings.faiss_dir / "index.pkl").write_bytes(b"garbage")
    vector_store.reset()
    hits = vector_store.search("Where can I park?", threshold=0)
    assert hits and hits[0][0].metadata["doc_id"] == doc["id"]
