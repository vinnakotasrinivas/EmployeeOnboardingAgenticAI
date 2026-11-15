# Step 13: Tests and evaluation

## Spec

**Goal:** a test suite that proves each requirement works, plus a small question set that measures answer quality with the real LLM.

**Files created or changed**
- `tests/conftest.py`: shared fixtures. These include a temporary data dir (monkeypatching `settings`), a fake embeddings fixture (deterministic hash vectors, for fast offline tests), a real embeddings fixture (session-scoped, marked `slow`), and `mock_llm`.
- Fill gaps in the existing tests so every row below is covered.
- `tests/eval_questions.yaml`: 20 questions
- `scripts/run_eval.py`
- `pyproject.toml`: pytest config with markers `slow` and `live` (needs network and a Groq key). The default run excludes `live`.

**Coverage checklist (offline unless marked)**

| Area | Cases |
| --- | --- |
| Validator | jpg, png, zip, docx, pptx, xlsm, exe, empty, 19 MB exactly, 20 MB, renamed jpg-as-pdf, valid pdf/txt/csv/xlsx |
| Loaders | multi-page PDF, corrupt PDF, encrypted PDF, scanned (no text) PDF, latin-1 TXT, malformed CSV, two-sheet XLSX |
| Relevance | decide() thresholds; fallback path on LLM error; JSON parsing fallback |
| Registry | add, dedupe, update, delete |
| Chunker | prose sizes, overlap, table row groups with headers, metadata |
| Vector store | add/search/delete, threshold, category filter, rebuild after corrupt index |
| Pipeline | batch isolation, duplicate, pending confirm/discard |
| Agents | analyst executor safety, routing, retry, empty-index short circuit |
| Guardrails | input codes, PII masking, output citation enforcement |
| API | all endpoints, 500 handler hides tracebacks |
| Live (`-m live`) | 3 real questions return cited answers; 1 off-topic refused |

**`tests/eval_questions.yaml` format**

```yaml
- id: pto_days_us
  question: How many PTO days do US employees get per year?
  expect_contains: ["20"]
  expect_source: employee_handbook.pdf
  should_refuse: false
- id: buddy_lookup
  question: Who is Siddharth Patel's manager and onboarding buddy?
  expect_contains: ["Nisha Chowdary", "Abhishek Banerjee"]
  expect_source: team_directory.csv
  should_refuse: false
- id: stock_price
  question: What is Northwind Labs' stock price?
  should_refuse: true
```

Include 15 answerable questions across all 9 sample docs and 5 that should be refused (out of scope, injection, unsafe or off-topic). Start from the reference facts table in [step 2](02_sample_data.md) and the example questions in `docs/sample_data/README.md`, and check every expected answer against the actual file before adding it.

**`scripts/run_eval.py`**
- Ingests the samples if the index is empty.
- Runs every question through `answer_question`.
- Scores each one:
  - **answer_correct:** every `expect_contains` string appears in the answer, case-insensitive.
  - **source_correct:** `expect_source` is among the citations.
  - **refusal_correct:** the `refused` result matches `should_refuse`.
- Prints a table plus totals and the average latency, and writes `docs/eval_results.md`.
- Target: at least 85% answer accuracy and 100% correct refusals.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md (section "Verification") and docs/build_guide/13_tests_eval.md for the exact spec. This is STEP 13 ONLY: complete the test suite and add the evaluation harness.

1. Create tests/conftest.py with the shared fixtures described in the spec, and refactor existing tests to use them where it reduces duplication (don't rewrite tests that already pass and are clear).
2. Go through the coverage checklist table; for every case not yet covered, add a test. Generate any extra fixture files (png, docx, exe, encrypted PDF via pypdf, scanned PDF with only an image, latin-1 txt, malformed csv) inside tmp_path in the tests, not in docs/sample_data.
3. Configure pytest in pyproject.toml: testpaths=["tests"], markers slow and live, addopts = "-m 'not live'".
4. Add live tests marked @pytest.mark.live that hit Groq for 3 answerable questions and 1 off-topic one.
5. Create tests/eval_questions.yaml with 20 questions (15 answerable across all 9 onboarding docs in docs/sample_data/, 5 that must be refused). Verify each expected answer by reading the source file (use pandas for the CSV and Excel files) rather than guessing.
6. Create scripts/run_eval.py as specified, writing docs/eval_results.md.

Run `uv run pytest -q`, then `uv run pytest -q -m live`, then `uv run python scripts/run_eval.py`, and show all outputs. If eval accuracy is below 85%, show me which questions failed and why before changing any prompts.
```

## Checkpoint

```powershell
uv run pytest -q
uv run pytest -q -m live
uv run python scripts/run_eval.py
```

**Expected output:** the offline suite passes in under about 60 seconds, the live tests pass, and the eval prints at least 85% answer accuracy with 100% correct refusals. `docs/eval_results.md` exists. You'll use it in your report.

## Common problems

- **The eval fails because the answer says "twenty" instead of "20":** add both to `expect_contains`, or normalise numbers in the scorer.
- **Live tests hit Groq rate limits:** the free tier has per-minute limits. Add `time.sleep(2)` between eval questions.
- **The eval stalls with "tokens per day (TPD)" in the log:** the free tier also allows only 200,000 tokens per day per model, and a full eval uses a large part of that (each question makes 4-6 LLM calls). `run_eval.py` stops and writes partial results when the limit persists. Run the eval on a fresh day's quota, or set `GROQ_MODEL` to another model for that run; each model has its own daily limit.
- **The eval stalls with "tokens per day (TPD)" in the log:** the free tier also allows only 200,000 tokens per day per model, and a full eval uses a large part of that (each question makes 4-6 LLM calls). `run_eval.py` stops and writes partial results when the limit persists. Run the eval on a fresh day's quota, or set `GROQ_MODEL` to another model for that run; each model has its own daily limit.
- **The encrypted PDF fixture won't build:** use `PdfWriter().encrypt("pw")` from pypdf.
