import pytest

from app.config import settings
from app.ingestion import registry

pytestmark = pytest.mark.usefixtures("temp_data_dir")


def add_sample(data: bytes = b"hello", status: str = "indexed", **kwargs):
    return registry.add(
        filename=kwargs.pop("filename", "faq.txt"),
        sha256=registry.file_hash(data),
        file_type="txt",
        size_bytes=len(data),
        status=status,
        **kwargs,
    )


def test_add_and_get(temp_data_dir):
    doc = add_sample(category="facilities_faq", confidence=0.9, reason="FAQ", chunks=4)
    assert registry.settings.registry_db == temp_data_dir / "registry.db"
    assert registry.get(doc["id"]) == doc
    assert (doc["status"], doc["category"], doc["chunks"]) == ("indexed", "facilities_faq", 4)


def test_dedupe_by_hash():
    first = add_sample(b"same bytes")
    assert registry.find_by_hash(registry.file_hash(b"same bytes"))["id"] == first["id"]
    with pytest.raises(registry.DuplicateDocumentError) as info:
        add_sample(b"same bytes", filename="copy.txt")
    assert info.value.existing["id"] == first["id"]
    assert len(registry.list_documents()) == 1


def test_find_by_hash_missing():
    assert registry.find_by_hash("0" * 64) is None


def test_update_status_keeps_unset_fields():
    doc = add_sample(status="pending", reason="unsure")
    updated = registry.update_status(doc["id"], "indexed", chunks=7)
    assert (updated["status"], updated["chunks"], updated["reason"]) == ("indexed", 7, "unsure")
    updated = registry.update_status(doc["id"], "rejected", reason="user discarded")
    assert (updated["chunks"], updated["reason"]) == (7, "user discarded")


def test_update_unknown_id_or_status():
    with pytest.raises(KeyError):
        registry.update_status("missing", "indexed")
    doc = add_sample()
    with pytest.raises(ValueError):
        registry.update_status(doc["id"], "done")


def test_list_filters_by_status():
    add_sample(b"a", status="indexed")
    add_sample(b"b", status="pending")
    add_sample(b"c", status="pending")
    assert len(registry.list_documents()) == 3
    assert len(registry.list_documents("pending")) == 2


def test_pending_raw_file_saved_and_deleted():
    doc = add_sample(b"raw bytes", status="pending", raw=b"raw bytes")
    path = registry.upload_path(doc["id"], doc["filename"])
    assert path.read_bytes() == b"raw bytes"
    assert path.parent == settings.uploads_dir
    assert registry.delete(doc["id"]) is True
    assert not path.exists()
    assert registry.get(doc["id"]) is None
    assert registry.delete(doc["id"]) is False
