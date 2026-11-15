import pytest

from app.config import PROJECT_ROOT
from app.ingestion import pipeline, registry
from app.ingestion.relevance import RelevanceDecision
from app.store import tables, vector_store

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"

VERDICTS = {
    "first_week_faq.txt": (True, "facilities_faq", 0.95),
    "team_directory.csv": (True, "team_directory", 0.97),
    "pasta_recipe.txt": (False, "other", 0.98),
    "borderline.txt": (True, "hr_policy", 0.6),
}


@pytest.fixture(autouse=True)
def isolated(temp_data_dir, fake_embeddings, monkeypatch):
    def fake_classify(profile: str) -> RelevanceDecision:
        name = profile.splitlines()[0].removeprefix("Filename: ")
        relevant, category, confidence = VERDICTS[name]
        return RelevanceDecision(relevant=relevant, category=category, confidence=confidence, reason=f"test {name}")

    monkeypatch.setattr(pipeline, "classify", fake_classify)


def sample(relative: str) -> tuple[str, bytes]:
    path = SAMPLES / relative
    return path.name, path.read_bytes()


def test_relevant_doc_is_indexed():
    result = pipeline.ingest_file(*sample("txt/first_week_faq.txt"))
    assert (result.status, result.category) == ("indexed", "facilities_faq")
    assert result.chunks > 0 and result.preview.startswith("NORTHWIND LABS")
    doc = registry.get(result.doc_id)
    assert (doc["status"], doc["chunks"]) == ("indexed", result.chunks)
    assert registry.upload_path(doc["id"], doc["filename"]).exists()
    assert vector_store.stats() == {"chunks": result.chunks, "docs": 1}


def test_table_doc_registers_dataframe_and_survives_restart():
    result = pipeline.ingest_file(*sample("csv/team_directory.csv"))
    assert result.status == "indexed" and result.rows == 184
    assert "team_directory.csv:data" in tables.all_tables()
    tables.reset()
    assert len(tables.all_tables()["team_directory.csv:data"]) == 184


def test_irrelevant_doc_is_rejected():
    result = pipeline.ingest_file(*sample("irrelevant/pasta_recipe.txt"))
    assert result.status == "rejected"
    assert result.message.startswith("Not an onboarding document")
    assert registry.get(result.doc_id)["status"] == "rejected"
    assert vector_store.stats()["chunks"] == 0


def test_duplicate_upload():
    first = pipeline.ingest_file(*sample("txt/first_week_faq.txt"))
    again = pipeline.ingest_file("renamed.txt", sample("txt/first_week_faq.txt")[1])
    assert again.status == "duplicate"
    assert again.doc_id == first.doc_id
    assert "indexed" in again.message
    assert vector_store.stats()["docs"] == 1


def test_image_is_error_and_not_registered():
    result = pipeline.ingest_file(*sample("invalid/photo.jpg"))
    assert result.status == "error"
    assert result.message.startswith("Images are not supported.")
    assert registry.list_documents() == []


def test_batch_with_corrupt_file_indexes_the_others():
    results = pipeline.ingest_many(
        [sample("txt/first_week_faq.txt"), sample("invalid/corrupt.pdf"), sample("csv/team_directory.csv")]
    )
    assert [r.status for r in results] == ["indexed", "error", "indexed"]
    assert results[1].message == "Could not read this PDF. It may be damaged."


def test_unexpected_exception_is_isolated(monkeypatch):
    original = pipeline.ingest_file

    def flaky(filename, data, force=False):
        if filename == "boom.txt":
            raise RuntimeError("kaboom")
        return original(filename, data, force)

    monkeypatch.setattr(pipeline, "ingest_file", flaky)
    results = pipeline.ingest_many([("boom.txt", b"x"), sample("txt/first_week_faq.txt")])
    assert (results[0].status, results[0].message) == ("error", pipeline.UNEXPECTED)
    assert results[1].status == "indexed"


def test_pending_then_confirm():
    text = b"Employees may work remotely two days a week with manager approval."
    pending = pipeline.ingest_file("borderline.txt", text)
    assert pending.status == "pending"
    assert registry.upload_path(pending.doc_id, "borderline.txt").exists()
    assert vector_store.stats()["chunks"] == 0

    confirmed = pipeline.confirm_pending(pending.doc_id)
    assert (confirmed.status, confirmed.doc_id) == ("indexed", pending.doc_id)
    assert registry.get(pending.doc_id)["status"] == "indexed"
    assert vector_store.search("remote work policy", threshold=0)[0][0].metadata["doc_id"] == pending.doc_id
    assert pipeline.confirm_pending(pending.doc_id).status == "error"


def test_discard_pending():
    pending = pipeline.ingest_file("borderline.txt", b"Some borderline policy text about remote days.")
    assert pipeline.discard_pending(pending.doc_id) is True
    assert registry.get(pending.doc_id) is None
    assert not registry.upload_path(pending.doc_id, "borderline.txt").exists()


def test_delete_document_removes_everything():
    result = pipeline.ingest_file(*sample("csv/team_directory.csv"))
    assert pipeline.delete_document(result.doc_id) is True
    assert vector_store.stats() == {"chunks": 0, "docs": 0}
    assert tables.all_tables() == {}
    assert registry.get(result.doc_id) is None
    assert not registry.upload_path(result.doc_id, "team_directory.csv").exists()


def test_force_skips_relevance(monkeypatch):
    monkeypatch.setattr(pipeline, "classify", lambda profile: pytest.fail("classify should not be called"))
    result = pipeline.ingest_file("notes.txt", b"Badge photos are taken at reception on day one.", force=True)
    assert (result.status, result.category) == ("indexed", "unknown")
