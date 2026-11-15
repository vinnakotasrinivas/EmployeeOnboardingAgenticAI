"""Data Analyst agent: the LLM writes a JSON query spec; we run it with plain pandas (no eval/query/exec)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.context import timed
from app.agents.prompts import ANALYST
from app.agents.state import AgentState, ContextItem
from app.ingestion.loaders import to_markdown
from app.llm.groq_client import extract_json, invoke_text
from app.store import tables

logger = logging.getLogger(__name__)

MAX_ROWS = 50
SCHEMA_EXAMPLES = 3
ENUM_MAX_VALUES = 12
LONG_TEXT_CHARS = 40
# Exact table lookups are trusted like a strong retrieval hit when computing confidence.
TABLE_RESULT_SCORE = 0.75

Op = Literal["==", "!=", "contains", ">", "<", ">=", "<="]
Aggregate = Literal["count", "sum", "mean", "min", "max"]


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: Op
    value: str | int | float | bool


class TableQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str
    filters: list[Filter] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    sort_by: str | None = None
    sort_desc: bool = False
    limit: int = 20
    aggregate: Aggregate | None = None
    aggregate_column: str | None = None


class AnalystPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[TableQuery] = Field(default_factory=list)


class QueryError(ValueError):
    pass


def _resolve(name: str, options: list[str], kind: str) -> str:
    if name in options:
        return name
    lowered = {o.lower(): o for o in options}
    if name.strip().lower() in lowered:
        return lowered[name.strip().lower()]
    raise QueryError(f"Unknown {kind} '{name}'.")


def _convert(series: pd.Series, value):
    if pd.api.types.is_datetime64_any_dtype(series):
        try:
            return pd.Timestamp(str(value))
        except ValueError as exc:
            raise QueryError(f"'{value}' is not a date.") from exc
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise QueryError(f"'{value}' is not a number.") from exc
    return None


def _mask(series: pd.Series, op: str, value) -> pd.Series:
    if op == "contains":
        return series.astype(str).str.contains(str(value), case=False, regex=False, na=False)
    typed = _convert(series, value)
    if typed is None:
        left, right = series.astype(str).str.strip().str.lower(), str(value).strip().lower()
    else:
        left, right = series, typed
        if isinstance(typed, pd.Timestamp) and op in ("==", "!="):
            left = series.dt.normalize()
    comparisons = {
        "==": lambda: left == right,
        "!=": lambda: left != right,
        ">": lambda: left > right,
        "<": lambda: left < right,
        ">=": lambda: left >= right,
        "<=": lambda: left <= right,
    }
    return comparisons[op]().fillna(False).astype(bool)


def _upcoming_date_column(query: TableQuery, df: pd.DataFrame) -> str | None:
    """A date column filtered with > or >= (an "upcoming" question), so results sort earliest first."""
    columns = [str(c) for c in df.columns]
    for f in query.filters:
        if f.op in (">", ">="):
            column = _resolve(f.column, columns, "column")
            if pd.api.types.is_datetime64_any_dtype(df[column]):
                return column
    return None


def _row_ranges(rows: list[int]) -> str:
    if not rows:
        return "none"
    ranges, start, prev = [], rows[0], rows[0]
    for r in rows[1:]:
        if r != prev + 1:
            ranges.append((start, prev))
            start = r
        prev = r
    ranges.append((start, prev))
    if len(ranges) > 6:
        return f"{rows[0]}-{rows[-1]} ({len(rows)} matches)"
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def describe(query: TableQuery) -> str:
    where = " and ".join(f"{f.column} {f.op} {f.value!r}" for f in query.filters) or "all rows"
    agg = f", {query.aggregate}({query.aggregate_column or ''})" if query.aggregate else ""
    return f"{query.table} where {where}{agg}"


def run_query(query: TableQuery, available: dict[str, pd.DataFrame]) -> ContextItem:
    key = _resolve(query.table, list(available), "table")
    df = available[key].reset_index(drop=True)
    columns = [str(c) for c in df.columns]
    rows = pd.Series(range(1, len(df) + 1), index=df.index)

    mask = pd.Series(True, index=df.index)
    for f in query.filters:
        mask &= _mask(df[_resolve(f.column, columns, "column")], f.op, f.value)
    result = df[mask]

    sort_col = _resolve(query.sort_by, columns, "column") if query.sort_by else _upcoming_date_column(query, df)
    if sort_col:
        result = result.sort_values(sort_col, ascending=not (query.sort_desc and query.sort_by))
    matched_rows = sorted(rows[result.index].tolist())

    source, sheet = key.split(":", 1)
    file_type = source.rsplit(".", 1)[-1].lower()

    if query.aggregate:
        if query.aggregate == "count":
            value = len(result)
        else:
            if not query.aggregate_column:
                raise QueryError(f"{query.aggregate} needs aggregate_column.")
            series = result[_resolve(query.aggregate_column, columns, "column")]
            if query.aggregate in ("sum", "mean") and not pd.api.types.is_numeric_dtype(series):
                raise QueryError(f"Cannot {query.aggregate} non-numeric column '{query.aggregate_column}'.")
            value = getattr(series, query.aggregate)()
            if isinstance(value, float):
                value = round(value, 2)
            elif isinstance(value, pd.Timestamp):
                value = value.strftime("%Y-%m-%d")
        body = f"Result: {query.aggregate} = {value} ({len(result)} matching rows)"
    else:
        limit = max(1, min(query.limit, MAX_ROWS))
        shown_cols = columns
        if query.columns:
            # Keep filter and sort columns visible so each row shows why it matched.
            wanted = [f.column for f in query.filters] + ([sort_col] if sort_col else []) + query.columns
            shown_cols = list(dict.fromkeys(_resolve(c, columns, "column") for c in wanted))
        shown = result.head(limit)[shown_cols]
        matched_rows = sorted(rows[shown.index].tolist())
        body = f"{len(result)} matching rows" + (f", showing {limit}" if len(result) > limit else "")
        body += "\n\n" + (to_markdown(shown) if len(shown) else "(no rows)")

    location = f"rows {_row_ranges(matched_rows)}"
    if file_type != "csv":
        location = f"{sheet}, {location}"
    return ContextItem(
        label=f"{source}, {location}",
        source=source,
        location=location,
        text=f"Table query: {describe(query)}\n{body}",
        score=TABLE_RESULT_SCORE,
        kind="table",
    )


def _column_hint(series: pd.Series) -> str:
    values = series.dropna()
    if values.empty:
        return ""
    if pd.api.types.is_datetime64_any_dtype(values):
        return f"{values.min():%Y-%m-%d}..{values.max():%Y-%m-%d}"
    if pd.api.types.is_numeric_dtype(values):
        return f"{values.min():g}..{values.max():g}"
    as_text = values.astype(str)
    if as_text.str.len().median() > LONG_TEXT_CHARS:
        return "free text"
    uniques = as_text.unique()
    shown = uniques if len(uniques) <= ENUM_MAX_VALUES else uniques[:SCHEMA_EXAMPLES]
    text = " | ".join(v[:30] for v in shown)
    return text + (" | ..." if len(uniques) > len(shown) else "")


def table_schemas(available: dict[str, pd.DataFrame]) -> str:
    lines = []
    for key, df in available.items():
        cols = ", ".join(f"{c} ({_column_hint(df[c])})" for c in df.columns)
        lines.append(f"- {key} ({len(df)} rows): {cols}")
    return "\n".join(lines)


def analyse(question: str) -> tuple[list[ContextItem], list[str]]:
    available = tables.all_tables()
    if not available:
        return [], ["no tables loaded"]
    system = ANALYST.format(today=date.today().isoformat(), schemas=table_schemas(available))
    # Plain-text JSON, not tool calling: the model garbles keys of this nested schema in tool-call mode.
    text = invoke_text([("system", system), ("user", question)], temperature=0.0)
    try:
        plan = AnalystPlan.model_validate(extract_json(text))
    except (ValueError, ValidationError) as exc:
        logger.info("Analyst returned an unusable query spec: %s", exc)
        return [], ["could not build a table query"]
    results, notes = [], []
    for query in plan.queries[:3]:
        try:
            item = run_query(query, available)
            results.append(item)
            notes.append(f"{describe(query)} -> {item['text'].splitlines()[1]}")
        except QueryError as exc:
            logger.info("Analyst query rejected: %s (%s)", exc, query.model_dump())
            notes.append(f"rejected query: {exc}")
    return results, notes


def analyst_node(state: AgentState) -> AgentState:
    with timed("Data Analyst") as t:
        results, notes = analyse(state["question"])
        t["summary"] = f"{len(results)} table quer{'y' if len(results) == 1 else 'ies'}: " + "; ".join(notes)
    return {"table_results": results, "trace": [t["step"]]}
