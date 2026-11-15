import pytest

from app.config import PROJECT_ROOT, settings
from app.ingestion import relevance
from app.ingestion.loaders import load_file
from app.ingestion.relevance import RelevanceDecision, build_profile, classify, classify_by_embedding, decide
from app.llm.errors import LLMUnavailableError

SAMPLES = PROJECT_ROOT / "docs" / "sample_data"


def profile_of(relative: str) -> str:
    path = SAMPLES / relative
    return build_profile(path.name, load_file(path.name, path.read_bytes()))


def test_profile_for_table_has_sheets_headers_and_few_rows():
    profile = profile_of("xlsx/training_schedule.xlsx")
    assert profile.startswith("Filename: training_schedule.xlsx")
    assert "Sheet: Course Catalog" in profile
    assert "course_code" in profile
    assert len(profile) <= relevance.PROFILE_MAX_CHARS


def test_profile_for_pdf_uses_first_pages():
    profile = profile_of("pdf/employee_handbook.pdf")
    assert "[Page 1]" in profile and "[Page 3]" not in profile
    assert len(profile) <= relevance.PROFILE_MAX_CHARS


@pytest.mark.parametrize(
    ("relevant", "confidence", "expected"),
    [(True, 0.9, "ingest"), (True, 0.75, "ingest"), (False, 0.8, "reject"), (True, 0.6, "pending"), (False, 0.5, "pending")],
)
def test_decide(relevant, confidence, expected):
    decision = RelevanceDecision(relevant=relevant, category="benefits", confidence=confidence, reason="x")
    assert decide(decision) == expected


def test_unknown_category_becomes_other():
    assert RelevanceDecision(relevant=True, category="Payroll", confidence=1, reason="x").category == "other"


def test_llm_reply_is_parsed_from_messy_text(mock_llm):
    mock_llm.chat('<think>looks like IT setup</think>\nSure! ```json\n{"relevant": true, "category": '
                  '"it_setup_security", "confidence": 0.92, "reason": "VPN and MFA setup steps"}\n```')
    decision = classify("Filename: vpn_setup.txt\nConnect to the VPN with Okta MFA on your new laptop.")
    assert decision == RelevanceDecision(relevant=True, category="it_setup_security", confidence=0.92,
                                         reason="VPN and MFA setup steps")
    assert decide(decision) == "ingest"
    assert "vpn_setup.txt" in str(mock_llm.prompts[0])


def test_unparseable_llm_reply_falls_back_to_embeddings(mock_llm, real_embeddings):
    mock_llm.chat("I think this is probably an onboarding document.")
    decision = classify("Filename: benefits.txt\nEnroll in medical insurance and the 401(k) plan.")
    assert decision.reason.startswith("fallback:")
    assert decision.category == "benefits"


def test_fallback_without_key_suggests_category_and_needs_review(monkeypatch, real_embeddings):
    monkeypatch.setattr(settings, "groq_api_key", "")
    onboarding = classify(profile_of("csv/team_directory.csv"))
    assert onboarding.reason.startswith("fallback:")
    assert (onboarding.relevant, onboarding.category) == (True, "team_directory")
    assert decide(onboarding) == "pending"
    recipe = classify(profile_of("irrelevant/pasta_recipe.txt"))
    assert recipe.reason.startswith("fallback:")
    assert (recipe.relevant, recipe.category) == (False, "other")
    assert decide(recipe) == "pending"


def test_fallback_when_llm_fails(monkeypatch, real_embeddings):
    def boom(*args, **kwargs):
        raise LLMUnavailableError()

    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(relevance, "invoke_json", boom)
    decision = classify("Filename: vpn_setup.txt\nConnect to the VPN with Okta MFA on your new laptop.")
    assert decision.reason.startswith("fallback:")
    assert decision.category == "it_setup_security"


def test_embedding_fallback_picks_category(real_embeddings):
    decision = classify_by_embedding("Filename: benefits.txt\nEnroll in medical insurance and the 401(k) plan.")
    assert (decision.relevant, decision.category) == (True, "benefits")
