import pandas as pd
import pytest
from langchain_core.documents import Document

from app.agents import analyst, graph, planner, reasoner, validator
from app.agents.analyst import Filter, QueryError, TableQuery, run_query
from app.agents.context import MAX_CHUNK_TOKENS, build_context, count_tokens, match_citations, truncate_tokens
from app.agents.planner import Plan
from app.agents.prompts import NO_DOCUMENTS, REFUSAL
from app.agents.validator import Validation
from app.store import tables, vector_store

PEOPLE = pd.DataFrame(
    {
        "first_name": ["Asha", "Ravi", "Siddharth", "Mei"],
        "last_name": ["Rao", "Kumar", "Patel", "Lin"],
        "team": ["Platform Engineering", "Data", "Platform Engineering", "Sales"],
        "salary_band": [3, 4, 2, 5],
        "start_date": pd.to_datetime(["2024-01-10", "2026-10-05", "2026-10-05", "2025-06-01"]),
        "manager_name": ["Kevin Hall", "Kevin Hall", "Nisha Chowdary", "Kevin Hall"],
    }
)
TABLES = {"team_directory.csv:data": PEOPLE}


# ---------- Data Analyst query executor ----------


def test_filter_and_columns():
    q = TableQuery(
        table="team_directory.csv:data",
        filters=[Filter(column="first_name", op="contains", value="sidd"), Filter(column="last_name", op="==", value="patel")],
        columns=["manager_name"],
    )
    item = run_query(q, TABLES)
    assert "Nisha Chowdary" in item["text"]
    assert "first_name" in item["text"]  # filter columns stay visible
    assert item["label"] == "team_directory.csv, rows 3"
    assert item["kind"] == "table"


def test_count_aggregate():
    q = TableQuery(table="team_directory.csv:data", filters=[Filter(column="team", op="==", value="platform engineering")], aggregate="count")
    item = run_query(q, TABLES)
    assert "count = 2" in item["text"]
    assert item["location"] == "rows 1, 3"


@pytest.mark.parametrize(("agg", "expected"), [("sum", "14"), ("mean", "3.5"), ("min", "2"), ("max", "5")])
def test_numeric_aggregates(agg, expected):
    item = run_query(TableQuery(table="team_directory.csv:data", aggregate=agg, aggregate_column="salary_band"), TABLES)
    assert f"{agg} = {expected}" in item["text"]


def test_date_filter_sorts_upcoming_first():
    q = TableQuery(table="team_directory.csv:data", filters=[Filter(column="start_date", op=">=", value="2025-01-01")], limit=1)
    item = run_query(q, TABLES)
    assert "Mei" in item["text"] and "3 matching rows, showing 1" in item["text"]


def test_numeric_comparison():
    q = TableQuery(table="team_directory.csv:data", filters=[Filter(column="salary_band", op=">", value="3")], aggregate="count")
    assert "count = 2" in run_query(q, TABLES)["text"]


@pytest.mark.parametrize(
    "query",
    [
        TableQuery(table="team_directory.csv:data", filters=[Filter(column="password", op="==", value="x")]),
        TableQuery(table="team_directory.csv:data", columns=["__class__"]),
        TableQuery(table="secrets.csv:data"),
        TableQuery(table="team_directory.csv:data", sort_by="nope"),
        TableQuery(table="team_directory.csv:data", aggregate="sum", aggregate_column="team"),
        TableQuery(table="team_directory.csv:data", filters=[Filter(column="salary_band", op=">", value="high")]),
    ],
)
def test_rejects_unknown_names_and_bad_values(query):
    with pytest.raises(QueryError):
        run_query(query, TABLES)


def test_limit_is_capped():
    big = pd.DataFrame({"n": range(500)})
    item = run_query(TableQuery(table="t.csv:data", limit=10_000), {"t.csv:data": big})
    assert "showing 50" in item["text"]


def test_analyst_spec_rejects_garbled_keys():
    with pytest.raises(ValueError):
        TableQuery.model_validate({"table": "t", "filters": [{"colum": "a", "op": "==", "value": 1}]})


# ---------- context helpers ----------


def test_truncate_keeps_whole_lines():
    text = "| header |\n" + "\n".join(f"| row {i} |" for i in range(500))
    cut = truncate_tokens(text, 50)
    assert cut.startswith("| header |") and cut.endswith("[...truncated]")


def test_match_citations_accepts_shortened_sheet_label():
    item = {"label": "x.xlsx, Sheet A, rows 1-25", "source": "x.xlsx", "location": "Sheet A, rows 1-25",
            "text": "t", "score": 0.5, "kind": "chunk"}
    assert match_citations("Answer [x.xlsx, rows 1-25].", [item]) == [item]
    assert match_citations("Answer [y.pdf, p.1].", [item]) == []


def test_build_context_respects_budgets():
    long = {"label": "a.csv, rows 1-25", "source": "a.csv", "location": "rows 1-25", "text": "| r |\n" * 5000,
            "score": 0.7, "kind": "chunk"}
    items = build_context([], [long, long, long])
    assert sum(count_tokens(i["text"]) for i in items) <= MAX_CHUNK_TOKENS
    assert all(i["text"].endswith("[...truncated]") for i in items)


# ---------- graph ----------


def test_empty_index_short_circuits_without_llm(temp_data_dir, mock_llm):
    mock_llm.reply(planner, "invoke_json", AssertionError("LLM must not be called"))
    result = graph.answer_question("How many PTO days do I get?")
    assert result["answer"] == NO_DOCUMENTS
    assert result["refused"] is True
    assert mock_llm.calls == []


@pytest.fixture
def indexed(temp_data_dir, real_embeddings):
    doc = Document(
        page_content="US employees receive 20 days of paid time off per year.",
        metadata={"doc_id": "hb", "chunk_id": "hb:0", "source": "employee_handbook.pdf", "page": 2,
                  "category": "hr_policy", "file_type": "pdf"},
    )
    vector_store.add_documents([doc])


GROUNDED = Validation(grounded=True, unsupported_claims=[], has_citations=True)


def _mock_plan(mock_llm, needs_tables=False):
    plan = Plan(type="policy", needs_tables=needs_tables, sub_queries=["paid time off days"], category_hint=None)
    mock_llm.reply(planner, "invoke_json", plan)


def test_validator_fails_once_then_passes(indexed, mock_llm):
    _mock_plan(mock_llm)
    mock_llm.reply(reasoner, "invoke_text", "You get 25 days [employee_handbook.pdf, p.2].",
                   "You get 20 days of PTO [employee_handbook.pdf, p.2].")
    mock_llm.reply(validator, "invoke_json",
                   Validation(grounded=False, unsupported_claims=["25 days"], has_citations=True), GROUNDED)

    result = graph.answer_question("How many PTO days do I get?")
    assert result["attempts"] == 2
    assert result["refused"] is False
    assert "20 days" in result["answer"]
    assert result["citations"][0]["source"] == "employee_handbook.pdf"
    assert result["citations"][0]["page"] == 2
    agents = [s["agent"] for s in result["trace"]]
    assert agents == ["InputGuard", "Planner", "Retriever", "Reasoner", "Validator", "Reasoner", "Validator",
                      "Answer", "OutputGuard"]


def test_ungrounded_twice_refuses(indexed, mock_llm):
    _mock_plan(mock_llm)
    mock_llm.reply(reasoner, "invoke_text", "You get 99 days [employee_handbook.pdf, p.2].")
    mock_llm.reply(validator, "invoke_json", Validation(grounded=False, unsupported_claims=["99"], has_citations=True))
    result = graph.answer_question("How many PTO days?")
    assert (result["answer"], result["refused"], result["confidence"], result["attempts"]) == (REFUSAL, True, "Low", 2)


def test_uncited_draft_fails_without_validator_llm(indexed, mock_llm):
    _mock_plan(mock_llm)
    mock_llm.reply(reasoner, "invoke_text", "You get 20 days.", "You get 20 days [employee_handbook.pdf, p.2].")
    mock_llm.reply(validator, "invoke_json", GROUNDED)
    result = graph.answer_question("How many PTO days?")
    assert result["attempts"] == 2 and not result["refused"]
    assert mock_llm.count("validator.invoke_json") == 1


def test_nothing_retrieved_refuses_without_reasoner(indexed, mock_llm, monkeypatch):
    _mock_plan(mock_llm)
    import app.agents.retriever as retriever_mod
    monkeypatch.setattr(retriever_mod.vector_store, "search", lambda *a, **k: [])
    mock_llm.reply(reasoner, "invoke_text", AssertionError("Reasoner must not be called"))
    result = graph.answer_question("What is the stock price?")
    assert result["refused"] is True and result["answer"] == REFUSAL
    assert result["trace"][-2]["summary"].startswith("no relevant context")
    assert mock_llm.count("reasoner.invoke_text") == 0


def test_needs_tables_routes_through_analyst(indexed, mock_llm):
    tables.register("dir", TABLES)
    _mock_plan(mock_llm, needs_tables=True)
    mock_llm.reply(analyst, "invoke_text",
                   '{"queries": [{"table": "team_directory.csv:data", "filters": '
                   '[{"column": "team", "op": "==", "value": "Platform Engineering"}], "aggregate": "count"}]}')
    mock_llm.reply(reasoner, "invoke_text", "2 people [team_directory.csv, rows 1, 3].")
    mock_llm.reply(validator, "invoke_json", GROUNDED)
    result = graph.answer_question("How many people are in Platform Engineering?")
    assert "Data Analyst" in [s["agent"] for s in result["trace"]]
    assert result["confidence"] == "High"
    assert result["citations"][0]["rows"] == "rows 1, 3"


def test_simple_question_skips_analyst(indexed, mock_llm):
    _mock_plan(mock_llm, needs_tables=False)
    mock_llm.reply(analyst, "invoke_text", AssertionError("Analyst must not be called"))
    mock_llm.reply(reasoner, "invoke_text", "You get 20 days [employee_handbook.pdf, p.2].")
    mock_llm.reply(validator, "invoke_json", GROUNDED)
    result = graph.answer_question("How many PTO days?")
    assert "Data Analyst" not in [s["agent"] for s in result["trace"]]
    assert mock_llm.calls == ["planner.invoke_json", "reasoner.invoke_text", "validator.invoke_json"]


def test_llm_error_returns_friendly_message(indexed, mock_llm):
    from app.llm.errors import LLMRateLimitError

    mock_llm.reply(planner, "invoke_json", LLMRateLimitError())
    result = graph.answer_question("How many PTO days?")
    assert result["refused"] is True
    assert "rate limit" in result["answer"].lower()
