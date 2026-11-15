import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.config import PROJECT_ROOT, settings
from app.ingestion import pipeline
from app.ingestion.relevance import RelevanceDecision

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
GROQ_OK = {"key_ok": True, "chat_model_ok": True, "guard_model_ok": True, "message": "Groq key and models OK."}

ANSWER = {
    "answer": "You get 20 days of PTO [employee_handbook.pdf, p.1].",
    "confidence": "High",
    "refused": False,
    "citations": [{"source": "employee_handbook.pdf", "location": "p.1", "page": 1, "snippet": "20 days", "score": 0.74}],
    "trace": [{"agent": "Planner", "summary": "policy, 1 sub-query", "ms": 5}],
    "attempts": 1,
    "error": None,
}


@pytest.fixture
def client(temp_data_dir, fake_embeddings, monkeypatch):
    monkeypatch.setattr(main, "get_embeddings", lambda: fake_embeddings)
    monkeypatch.setattr(main, "check_models", lambda: GROQ_OK)
    monkeypatch.setattr(main, "setup_logging", lambda: None)  # keep test logs out of logs/app.log
    monkeypatch.setattr(pipeline, "classify", lambda profile: RelevanceDecision(
        relevant=True, category="facilities_faq", confidence=0.95, reason="test"))
    monkeypatch.setattr(main, "answer_question", lambda q: ANSWER)
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


def upload(client, *relative: str):
    files = [("files", (p.name, p.read_bytes())) for p in (SAMPLES / r for r in relative)]
    return client.post("/upload", files=files)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["groq"]["key_ok"] is True
    assert body["embedding_model"] == settings.embedding_model
    assert (body["chat_model"], body["guard_model"]) == (settings.groq_model, settings.groq_guard_model)
    assert (body["chunks"], body["docs"]) == (0, 0)
    assert response.headers["X-Request-ID"]


def test_upload_txt_and_image(client):
    response = upload(client, "txt/first_week_faq.txt", "invalid/photo.jpg")
    assert response.status_code == 200
    faq, photo = response.json()
    assert (faq["filename"], faq["status"]) == ("first_week_faq.txt", "indexed") and faq["chunks"] > 0
    assert photo["status"] == "error"
    assert photo["message"].startswith("Images are not supported.")
    assert client.get("/health").json()["chunks"] == faq["chunks"]


def test_documents_list_and_delete(client):
    doc_id = upload(client, "txt/first_week_faq.txt").json()[0]["doc_id"]
    docs = client.get("/documents").json()
    assert [d["id"] for d in docs] == [doc_id] and docs[0]["status"] == "indexed"

    response = client.delete(f"/documents/{doc_id}")
    assert response.status_code == 200
    assert response.json()["deleted"] is True and response.json()["chunks_removed"] > 0
    assert client.get("/documents").json() == []
    assert client.delete(f"/documents/{doc_id}").status_code == 404


def test_confirm_and_discard_pending(client, monkeypatch):
    monkeypatch.setattr(pipeline, "classify", lambda profile: RelevanceDecision(
        relevant=True, category="hr_policy", confidence=0.6, reason="unsure"))
    pending = upload(client, "txt/first_week_faq.txt", "txt/how_to_guides.txt").json()
    assert [p["status"] for p in pending] == ["pending", "pending"]

    confirmed = client.post(f"/documents/{pending[0]['doc_id']}/confirm").json()
    assert confirmed["status"] == "indexed"
    assert client.post(f"/documents/{pending[1]['doc_id']}/discard").json() == {"discarded": True}
    assert client.post(f"/documents/{pending[0]['doc_id']}/discard").status_code == 409


def test_ask(client):
    response = client.post("/ask", json={"question": "How many PTO days do I get?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == ANSWER["answer"] and body["confidence"] == "High"
    assert body["citations"][0]["source"] == "employee_handbook.pdf"
    assert isinstance(body["latency_ms"], int)


def test_ask_rate_limited_returns_503(client, monkeypatch):
    monkeypatch.setattr(main, "answer_question", lambda q: {**ANSWER, "answer": "Groq rate limit reached.", "error": "rate_limit"})
    response = client.post("/ask", json={"question": "How many PTO days do I get?"})
    assert response.status_code == 503
    assert response.json() == {"error": "Groq rate limit reached."}


def test_ask_exception_returns_friendly_500(client, monkeypatch):
    def boom(question):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(main, "answer_question", boom)
    response = client.post("/ask", json={"question": "How many PTO days do I get?"})
    assert response.status_code == 500
    assert response.json() == {"error": "Something went wrong. Please try again."}
    assert "secret" not in response.text and "Traceback" not in response.text


def test_upload_too_large(client, monkeypatch):
    monkeypatch.setattr(settings, "max_file_mb", 0.001)  # ~1 KB per file
    response = upload(client, "txt/first_week_faq.txt")
    assert response.status_code == 413
    assert "under" in response.json()["error"]


def test_unknown_document_404(client):
    assert client.post("/documents/nope/confirm").json() == {"error": "Document not found."}
    assert client.get("/documents/nope/preview").status_code == 404


def test_preview_text_and_table(client):
    faq_id, csv_id = (r["doc_id"] for r in upload(client, "txt/first_week_faq.txt",
                                                  "csv/onboarding_checklist.csv").json())
    faq = client.get(f"/documents/{faq_id}/preview").json()
    assert faq["status"] == "indexed" and faq["preview"] and faq["chunks"] > 0
    table = client.get(f"/documents/{csv_id}/preview").json()
    assert table["rows"] == 55 and table["preview"].startswith("data (55 rows)")
