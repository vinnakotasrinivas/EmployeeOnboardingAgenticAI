import importlib.util

import yaml

from app.config import PROJECT_ROOT

_spec = importlib.util.spec_from_file_location("run_eval", PROJECT_ROOT / "scripts" / "run_eval.py")
run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_eval)


def test_question_file_shape():
    cases = yaml.safe_load(run_eval.QUESTIONS.read_text(encoding="utf-8"))
    assert len(cases) == 20 and len({c["id"] for c in cases}) == 20
    answerable = [c for c in cases if not c["should_refuse"]]
    assert len(answerable) == 15
    assert all(c["expect_contains"] and c["expect_source"] for c in answerable)
    sources = set()
    for c in answerable:
        sources.update(c["expect_source"] if isinstance(c["expect_source"], list) else [c["expect_source"]])
    sample_files = {p.name for d in run_eval.ONBOARDING_DIRS for p in (run_eval.SAMPLES / d).iterdir()}
    assert sources <= sample_files and len(sample_files) == 9 and sources == sample_files


def test_contains_all_normalises_numbers_and_alternatives():
    assert run_eval.contains_all("Probation lasts six months.", ["6 months"])
    assert run_eval.contains_all("Report it within one hour.", ["1 hour"])
    assert run_eval.contains_all("The deadline is 2026-11-18.", [["18 November", "2026-11-18"]])
    assert not run_eval.contains_all("You get 18 days.", ["18", "30"])


def test_score_answerable_and_refusal():
    case = {"id": "pto", "question": "PTO?", "expect_contains": ["20"], "expect_source": "employee_handbook.pdf",
            "should_refuse": False}
    result = {"answer": "20 days [employee_handbook.pdf, p.1]", "refused": False, "confidence": "High",
              "citations": [{"source": "employee_handbook.pdf"}], "error": None}
    row = run_eval.score(case, result, 1000)
    assert (row["answer_correct"], row["source_correct"], row["refusal_correct"]) == (True, True, True)

    refused = run_eval.score({"id": "x", "question": "pizza?", "should_refuse": True},
                             {**result, "refused": True, "citations": []}, 10)
    assert (refused["answer_correct"], refused["refusal_correct"]) == (None, True)
    totals = run_eval.summarise([row, refused])
    assert (totals["answer_accuracy"], totals["refusal_accuracy"]) == (1.0, 1.0)
