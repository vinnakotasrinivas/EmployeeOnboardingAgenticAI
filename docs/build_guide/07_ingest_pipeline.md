# Step 7: Ingest pipeline

## Spec

**Goal:** a single function that takes an uploaded file through every check (validate, load, relevance, chunk, index) and returns one clear result per file. The API, UI and CLI all call this function.

**Files created**
- `app/ingestion/pipeline.py`
- `app/store/tables.py`: an in-memory registry of DataFrames for the Data Analyst agent, rebuilt from `uploads_dir` at startup
- `scripts/ingest_samples.py`
- `tests/test_pipeline.py`

**`pipeline.py`**
- `IngestResult(pydantic)` fields:
  - `doc_id: str | None`, `filename`
  - `status: "indexed" | "rejected" | "pending" | "error" | "duplicate"`
  - `message: str` (one sentence for the user)
  - `category`, `confidence`
  - `pages`, `rows`, `chunks`
  - `preview: str` (first about 800 characters, or the table head as markdown)
- `ingest_file(filename, data, force=False) -> IngestResult` runs these stages in order:
  1. Compute the hash. If it's already in the registry, return `duplicate` with the existing doc's status.
  2. `validate_file`. On failure, return `error` with the validator message (don't add it to the registry).
  3. `load_file`. On a loader error, record it in the registry as `error` and return.
  4. Relevance: `classify` then `decide`. `force=True` skips this and ingests directly (used when the user confirms a pending doc).
  5. If the decision is `reject`, record it as `rejected` with the reason. If `pending`, save the raw file and record it as `pending`.
  6. If `ingest`: chunk, `add_documents`, save the raw file, register the tables, then record it as `indexed` with the chunk count.
- `ingest_many(files: list[(name, bytes)]) -> list[IngestResult]`: each file runs in its own try/except, so one bad file never stops the batch.
- `confirm_pending(doc_id) -> IngestResult`: loads the saved raw file and runs ingestion with `force=True`.
- `discard_pending(doc_id)` and `delete_document(doc_id)`: remove the doc from FAISS, the tables, the registry and the uploads folder.
- Log each stage with timing to the `onboardiq.ingest` logger.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md and docs/build_guide/07_ingest_pipeline.md for the exact spec. This is STEP 7 ONLY: the ingest pipeline that ties steps 3-6 together.

Implement app/ingestion/pipeline.py and app/store/tables.py as specified. Reuse existing modules (validator, loaders, relevance, registry, chunker, vector_store); do not duplicate their logic. Each file in ingest_many must be isolated with try/except so one failure never blocks the others; unexpected exceptions become status "error" with message "Unexpected error while processing this file." and the traceback goes to the log only.

Create scripts/ingest_samples.py with flags --reset (clear data/faiss_index, data/registry.db, data/uploads), --include-invalid (also ingest docs/sample_data/irrelevant and docs/sample_data/invalid). By default it ingests docs/sample_data/{pdf,txt,csv,xlsx}/. Print a table: filename, status, category, confidence, pages/rows, chunks, message. Print vector_store.stats() at the end.

Create tests/test_pipeline.py using tmp data dirs (monkeypatch settings) and mocking the relevance classify call so tests run offline: relevant doc gets indexed with chunks > 0; irrelevant doc rejected; duplicate upload returns "duplicate"; jpg returns error with the image message; a batch with one corrupt file still indexes the others; confirm_pending indexes a pending doc; delete_document removes chunks.

Run pytest and `uv run python scripts/ingest_samples.py --reset --include-invalid`, and show outputs.
```

## Checkpoint

```powershell
uv run python scripts/ingest_samples.py --reset --include-invalid
uv run python scripts/ingest_samples.py
uv run pytest -q
```

**Expected output:** on the first run, the 9 Northwind files are `indexed`, the 3 irrelevant files are `rejected` with reasons, and the invalid files are `error` with their specific messages. On the second run (without `--reset`), every file is `duplicate`.

## Common problems

- **The second run re-indexes everything:** the duplicate check has to happen before validation, using the registry's sha256.
- **The tables are empty after a restart:** `tables.py` must rebuild from `uploads_dir` for every `indexed` CSV or Excel doc when it's first imported.
- **Tests are slow:** the embedding model loads once per session. Use a session-scoped pytest fixture, or mock the embeddings with a small fake that returns deterministic vectors.
