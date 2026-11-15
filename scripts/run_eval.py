"""Measure answer quality with the real LLM on tests/eval_questions.yaml and write docs/eval_results.md.

Run: uv run python scripts/run_eval.py [--sleep 3] [--only pto_days_us --only buddy_lookup]
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.agents.graph import answer_question
from app.config import PROJECT_ROOT, settings
from app.ingestion import pipeline
from app.store import vector_store

QUESTIONS = PROJECT_ROOT / "tests" / "eval_questions.yaml"
RESULTS = PROJECT_ROOT / "docs" / "eval_results.md"
SAMPLES = PROJECT_ROOT / "docs" / "sample_data"
ONBOARDING_DIRS = ("pdf", "txt", "csv", "xlsx")
ANSWER_TARGET, REFUSAL_TARGET = 0.85, 1.0
RATE_LIMIT_PAUSE_S = 60

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fourteen": "14", "eighteen": "18", "twenty": "20",
    "thirty": "30",
}
_NUMBER_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)


def normalise(text: str) -> str:
    """Lower-case, unify dashes/spaces and turn number words into digits ("six months" -> "6 months")."""
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u00a0", " ").replace("\u202f", " ")
    return _NUMBER_RE.sub(lambda m: NUMBER_WORDS[m.group(1).lower()], text).lower()


def contains_all(answer: str, expected: list[Any]) -> bool:
    text = normalise(answer)
    for item in expected:
        options = item if isinstance(item, list) else [item]
        if not any(normalise(str(o)) in text for o in options):
            return False
    return True


def ensure_index() -> None:
    if vector_store.stats()["chunks"]:
        return
    print("Index is empty: ingesting the sample onboarding documents...")
    files = [(p.name, p.read_bytes()) for d in ONBOARDING_DIRS for p in sorted((SAMPLES / d).iterdir())]
    for result in pipeline.ingest_many(files):
        if result.status == "pending" and result.doc_id:
            result = pipeline.confirm_pending(result.doc_id)
        print(f"  {result.filename:28} {result.status:9} {result.message}")
    print("Index:", vector_store.stats())


def ask(question: str) -> tuple[dict[str, Any], int]:
    """Answer one question; on a Groq rate limit, pause once and retry."""
    for attempt in (1, 2):
        start = time.perf_counter()
        result = answer_question(question)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if result.get("error") != "rate_limit" or attempt == 2:
            return result, latency_ms
        print(f"  rate limited; pausing {RATE_LIMIT_PAUSE_S}s and retrying")
        time.sleep(RATE_LIMIT_PAUSE_S)
    raise AssertionError("unreachable")


def score(case: dict[str, Any], result: dict[str, Any], latency_ms: int) -> dict[str, Any]:
    should_refuse = bool(case.get("should_refuse"))
    sources = [c["source"] for c in result["citations"]]
    row = {
        "id": case["id"],
        "question": case["question"],
        "should_refuse": should_refuse,
        "refused": bool(result["refused"]),
        "refusal_correct": bool(result["refused"]) == should_refuse,
        "answer_correct": None,
        "source_correct": None,
        "answer": " ".join(result["answer"].split()),
        "sources": sources,
        "confidence": result["confidence"],
        "error": result.get("error"),
        "latency_ms": latency_ms,
    }
    if not should_refuse:
        expected_sources = case.get("expect_source") or []
        expected_sources = expected_sources if isinstance(expected_sources, list) else [expected_sources]
        row["answer_correct"] = not result["refused"] and contains_all(result["answer"], case.get("expect_contains", []))
        row["source_correct"] = not expected_sources or any(s in sources for s in expected_sources)
    return row


def mark(value: bool | None) -> str:
    return "-" if value is None else ("yes" if value else "NO")


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [r for r in rows if not r["should_refuse"]]
    refusals = [r for r in rows if r["should_refuse"]]
    ratio = lambda n, d: n / d if d else 0.0  # noqa: E731
    return {
        "answerable": len(answerable),
        "refusal_cases": len(refusals),
        "answer_ok": sum(r["answer_correct"] for r in answerable),
        "source_ok": sum(r["source_correct"] for r in answerable),
        "refusal_ok": sum(r["refusal_correct"] for r in refusals),
        "answer_accuracy": ratio(sum(r["answer_correct"] for r in answerable), len(answerable)),
        "source_accuracy": ratio(sum(r["source_correct"] for r in answerable), len(answerable)),
        "refusal_accuracy": ratio(sum(r["refusal_correct"] for r in refusals), len(refusals)),
        "avg_latency_s": ratio(sum(r["latency_ms"] for r in rows), len(rows)) / 1000,
    }


def print_report(rows: list[dict[str, Any]], totals: dict[str, Any]) -> None:
    print(f"\n{'id':26} {'answer':6} {'source':6} {'refusal':7} {'conf':6} {'secs':>5}  answer")
    for r in rows:
        answer = r["answer"] if len(r["answer"]) <= 70 else r["answer"][:67] + "..."
        print(f"{r['id']:26} {mark(r['answer_correct']):6} {mark(r['source_correct']):6} "
              f"{mark(r['refusal_correct']):7} {r['confidence']:6} {r['latency_ms'] / 1000:5.1f}  {answer}")
    print(f"\nAnswer accuracy:  {totals['answer_ok']}/{totals['answerable']} = {totals['answer_accuracy']:.0%}"
          f"  (target {ANSWER_TARGET:.0%})")
    print(f"Source accuracy:  {totals['source_ok']}/{totals['answerable']} = {totals['source_accuracy']:.0%}")
    print(f"Correct refusals: {totals['refusal_ok']}/{totals['refusal_cases']} = {totals['refusal_accuracy']:.0%}"
          f"  (target {REFUSAL_TARGET:.0%})")
    print(f"Average latency:  {totals['avg_latency_s']:.1f}s")


def write_markdown(rows: list[dict[str, Any]], totals: dict[str, Any], path: Path, incomplete: str = "") -> None:
    met = totals["answer_accuracy"] >= ANSWER_TARGET and totals["refusal_accuracy"] >= REFUSAL_TARGET
    status = f"**Incomplete run:** {incomplete}." if incomplete else f"**Targets met:** {'yes' if met else 'no'}"
    lines = [
        "# OnboardIQ evaluation results",
        "",
        f"Generated by `scripts/run_eval.py` on {datetime.now().astimezone():%d %B %Y %H:%M %Z} with chat model "
        f"`{settings.groq_model}`, guard model `{settings.groq_guard_model}` and embeddings "
        f"`{settings.embedding_model}`. Questions: `tests/eval_questions.yaml`.",
        "",
        "| Metric | Result | Target |",
        "| --- | --- | --- |",
        f"| Answer accuracy | {totals['answer_ok']}/{totals['answerable']} ({totals['answer_accuracy']:.0%}) "
        f"| {ANSWER_TARGET:.0%} |",
        f"| Source accuracy | {totals['source_ok']}/{totals['answerable']} ({totals['source_accuracy']:.0%}) | - |",
        f"| Correct refusals | {totals['refusal_ok']}/{totals['refusal_cases']} ({totals['refusal_accuracy']:.0%}) "
        f"| {REFUSAL_TARGET:.0%} |",
        f"| Average latency | {totals['avg_latency_s']:.1f}s | - |",
        "",
        status,
        "",
        "## Per question",
        "",
        "| ID | Question | Answer correct | Source correct | Refusal correct | Confidence | Latency | Cited sources |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['question']} | {mark(r['answer_correct'])} | {mark(r['source_correct'])} "
            f"| {mark(r['refusal_correct'])} | {r['confidence']} | {r['latency_ms'] / 1000:.1f}s "
            f"| {', '.join(sorted(set(r['sources']))) or '-'} |"
        )
    lines += ["", "## Answers", ""]
    for r in rows:
        lines += [f"**{r['id']}**: {r['question']}", "", f"> {r['answer'].replace('|', '/')}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--output", type=Path, default=RESULTS)
    parser.add_argument("--sleep", type=float, default=3.0, help="pause between questions (Groq per-minute limits)")
    parser.add_argument("--only", action="append", help="run only these question ids (repeatable)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

    if not settings.groq_api_key.strip():
        raise SystemExit("GROQ_API_KEY is not set in .env; the evaluation needs the real LLM.")
    cases = yaml.safe_load(args.questions.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    ensure_index()

    rows: list[dict[str, Any]] = []
    stopped = ""
    try:
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case['id']}: {case['question']}")
            result, latency_ms = ask(case["question"])
            if result.get("error") == "rate_limit":
                stopped = f"Groq rate limit still reached after a {RATE_LIMIT_PAUSE_S}s pause (daily quota?)"
                break
            rows.append(score(case, result, latency_ms))
            r = rows[-1]
            print(f"    answer {mark(r['answer_correct'])}, source {mark(r['source_correct'])}, "
                  f"refusal {mark(r['refusal_correct'])}, {latency_ms / 1000:.1f}s")
            if i < len(cases):
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        stopped = "interrupted"

    if not rows:
        raise SystemExit(f"No questions completed ({stopped}).")
    if stopped:
        print(f"\nStopped early: {stopped}. Results cover {len(rows)} of {len(cases)} questions.")
    totals = summarise(rows)
    print_report(rows, totals)
    write_markdown(rows, totals, args.output, incomplete=f"{stopped}; {len(rows)} of {len(cases)} questions run"
                   if stopped else "")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
