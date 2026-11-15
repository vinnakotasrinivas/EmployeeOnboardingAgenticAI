"""End-to-end checks against the real Groq API. Run with: uv run pytest -q -m live"""

import pytest

from app.agents.graph import answer_question
from app.config import PROJECT_ROOT, settings
from app.ingestion import pipeline
from app.store import tables, vector_store

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not settings.groq_api_key.strip(), reason="GROQ_API_KEY is not set"),
]

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
ONBOARDING_DIRS = ("pdf", "txt", "csv", "xlsx")


@pytest.fixture(scope="module", autouse=True)
def sample_index(tmp_path_factory):
    """Index the 9 onboarding samples into a temp dir. force=True skips relevance calls to save Groq quota."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "data_dir", tmp_path_factory.mktemp("live_data"))
        vector_store.reset()
        tables.reset()
        for path in sorted(p for d in ONBOARDING_DIRS for p in (SAMPLES / d).iterdir()):
            result = pipeline.ingest_file(path.name, path.read_bytes(), force=True)
            assert result.status == "indexed", (path.name, result.message)
        yield
        vector_store.reset()
        tables.reset()


@pytest.mark.parametrize(
    ("question", "expected", "source"),
    [
        ("How many PTO days do US employees get per year?", ["20"], "employee_handbook.pdf"),
        ("Who is Siddharth Patel's manager and onboarding buddy?", ["Nisha Chowdary", "Abhishek Banerjee"],
         "team_directory.csv"),
        ("What is the 401(k) match?", ["4%"], None),
    ],
)
def test_answerable_question_is_cited(question, expected, source):
    result = answer_question(question)
    assert result["error"] is None, result["answer"]
    assert not result["refused"], result["answer"]
    for text in expected:
        assert text.lower() in result["answer"].lower(), result["answer"]
    sources = {c["source"] for c in result["citations"]}
    assert sources, "answer has no citations"
    if source:
        assert source in sources, sources


def test_off_topic_is_refused():
    result = answer_question("What's the best pizza in Rome?")
    assert result["refused"] is True
    assert result["citations"] == []
