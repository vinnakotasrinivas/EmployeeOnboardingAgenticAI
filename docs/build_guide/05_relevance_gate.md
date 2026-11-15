# Step 5: Document relevance gate and registry

## Spec

**Goal:** before a valid file is indexed, decide whether it's actually an onboarding document, and record every decision.

**Files created**
- `app/ingestion/relevance.py`
- `app/ingestion/registry.py`
- `scripts/check_relevance.py`
- `tests/test_registry.py`

**Relevance agent (`relevance.py`)**
- `build_profile(filename, load_result) -> str` is capped at about 3,000 characters. For PDF and TXT it uses the filename plus the text of the first 2 pages. For CSV and Excel it uses the filename, sheet names, column headers and the first 5 rows.
- `ONBOARDING_CATEGORIES`: `hr_policy`, `benefits`, `it_setup_security`, `code_of_conduct`, `team_directory`, `training_schedule`, `onboarding_checklist`, `payroll_leave`, `facilities_faq`, plus `other` for irrelevant docs. Each category has a one-line description.
- `RelevanceDecision(pydantic)`: `relevant: bool`, `category: str`, `confidence: float (0-1)`, `reason: str`.
- `classify(profile) -> RelevanceDecision` uses `invoke_json` from step 4, temperature 0, and a system prompt listing the categories.
- `decide(decision) -> "ingest" | "reject" | "pending"`:
  - **ingest:** relevant and confidence >= `settings.relevance_threshold` (0.75).
  - **reject:** not relevant and confidence >= 0.75.
  - **pending:** everything else.
- **No-key or LLM-failure fallback:** `classify_by_embedding(profile)` compares the cosine similarity of the profile to each category description. It uses the embedding model, which is added in step 6, so for now implement a keyword-overlap stub behind the same function name and leave a TODO for step 6. The decision's `reason` must say "fallback" so the UI can show it.

**Registry (`registry.py`, SQLite at `settings.registry_db`)**
- Table `documents` with columns `id` (uuid), `filename`, `sha256` (unique), `file_type`, `size_bytes`, `status` (`indexed` / `rejected` / `pending` / `error`), `category`, `confidence`, `reason`, `chunks` (int), `created_at` and `updated_at`.
- Functions:
  - `file_hash(data)`
  - `find_by_hash(sha)`
  - `add(...)`
  - `update_status(id, status, chunks=None, reason=None)`
  - `list_documents()`
  - `get(id)`
  - `delete(id)`
- Pending documents need the raw file kept so they can be indexed after confirmation. Save it under `settings.uploads_dir / f"{id}_{filename}"`.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md (section "2. Document relevance gate") and docs/build_guide/05_relevance_gate.md for the exact spec. This is STEP 5 ONLY: relevance agent and SQLite registry. No chunking or FAISS yet.

Implement app/ingestion/relevance.py and app/ingestion/registry.py as specified. Use invoke_json from app/llm/groq_client.py for classification (temperature 0). Use the standard library sqlite3 module for the registry (no ORM). Make registry functions safe to call from multiple threads (new connection per call is fine).

The embedding-based fallback depends on step 6, so implement classify_by_embedding as a keyword-overlap stub for now with a clear TODO(step 6) comment. If GROQ_API_KEY is empty or the LLM raises, use the fallback and make the reason start with "fallback:".

Create scripts/check_relevance.py that runs validate_file + load_file + build_profile + classify + decide on every file in docs/sample_data/{pdf,txt,csv,xlsx}/ and docs/sample_data/irrelevant/, and prints a table: filename, decision, category, confidence, reason (truncated to 60 chars).

Create tests/test_registry.py using a temporary database path (monkeypatch settings or pass a path) covering add, dedupe by hash, update_status, list, delete.

Run pytest and the check script, and show both outputs.
```

## Checkpoint

```powershell
uv run python scripts/check_relevance.py
uv run pytest -q
```

**Expected output:** all 9 Northwind files are `ingest` with sensible categories (for example, `team_directory.csv` gets `team_directory` and `it_security_policy.pdf` gets `it_setup_security`), and all 3 irrelevant files are `reject`. A file showing `pending` now and then is acceptable. Tests pass.

## Common problems

- **`quarterly_sales.csv` comes back as `pending`:** make the prompt explicit that general business data without onboarding content is not relevant. Few-shot examples in the system prompt help.
- **Confidence is always 1.0:** ask the model to calibrate. "Use 0.5-0.75 when unsure" works well.
- **`sqlite3.OperationalError: database is locked`:** open a new connection per call and close it with `with closing(...)`.
