import sys

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from app.config import PROJECT_ROOT

UI_DIR = PROJECT_ROOT / "ui"
sys.path.insert(0, str(UI_DIR))

import api_client  # noqa: E402

APP = str(UI_DIR / "streamlit_app.py")
HEALTH = {
    "status": "ok",
    "groq": {"key_ok": True, "chat_model_ok": True, "guard_model_ok": True, "message": "OK"},
    "chat_model": "qwen/qwen3.8-27b",
    "guard_model": "openai/gpt-oss-safeguard-20b",
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "chunks": 48,
    "docs": 9,
}
DOCS = [{"id": "d1", "filename": "employee_handbook.pdf", "file_type": "pdf", "size_bytes": 1, "status": "indexed",
         "category": "hr_policy", "confidence": 0.9, "reason": "ok", "chunks": 6,
         "created_at": "2026-10-25T00:00:00+00:00", "updated_at": "2026-10-25T00:00:00+00:00"}]
ANSWER = {
    "answer": "The 401(k) match is 100% of the first 4% [benefits_enrollment.xlsx, Plan Catalog, rows 17].",
    "confidence": "High",
    "refused": False,
    "citations": [{"source": "benefits_enrollment.xlsx", "location": "Plan Catalog, rows 17", "page": None,
                   "rows": "Plan Catalog, rows 17", "snippet": "401(k) | 100% match", "score": 0.75}],
    "trace": [{"agent": "Planner", "summary": "policy", "ms": 500}, {"agent": "Reasoner", "summary": "ok", "ms": 600}],
    "latency_ms": 1200,
}


@pytest.fixture(autouse=True)
def clear_cache():
    st.cache_data.clear()  # cached /health results would leak between tests


@pytest.fixture
def stub_api(monkeypatch):
    monkeypatch.setattr(api_client, "health", lambda: HEALTH)
    monkeypatch.setattr(api_client, "documents", lambda: DOCS)
    monkeypatch.setattr(api_client, "ask", lambda q: ANSWER)


def run(at: AppTest) -> AppTest:
    at.run(timeout=30)
    assert not at.exception, at.exception
    return at


def test_api_down_shows_banner(monkeypatch):
    monkeypatch.setenv("API_URL", "http://127.0.0.1:9")
    at = run(AppTest.from_file(APP))
    assert at.title[0].value == "OnboardIQ - Your onboarding assistant"
    assert "not running" in at.error[0].value
    assert at.chat_input[0].disabled


def test_layout_and_sample_question(stub_api):
    at = run(AppTest.from_file(APP))
    assert not at.error
    assert any("48" in m.value for m in at.markdown)
    assert at.sidebar.header[0].value == "Step 1 - Upload onboarding documents"
    assert any("employee_handbook.pdf" in m.value for m in at.sidebar.markdown)

    at.button(key="sample_0").click()
    run(at)
    assert len(at.chat_message) == 2
    assert any("100% of the first 4%" in m.value for m in at.markdown)
    assert any("Sources used" in e.label for e in at.expander)


def test_refusal_uses_info(stub_api, monkeypatch):
    monkeypatch.setattr(api_client, "ask", lambda q: {**ANSWER, "answer": "I can only help with onboarding.",
                                                       "refused": True, "confidence": "Low", "citations": []})
    at = run(AppTest.from_file(APP))
    at.chat_input[0].set_value("What's the best pizza in Rome?")
    run(at)
    assert at.info[0].value == "I can only help with onboarding."
