# Step 10: FastAPI backend

## Spec

**Goal:** an HTTP API over the pipeline and the agents, so the UI can talk to it.

**Files created**
- `app/api/main.py`: the app, startup hooks and routers
- `app/api/schemas.py`: request and response models
- `app/logging_setup.py`: structured logging to `logs/app.log`
- `tests/test_api.py`

**Endpoints**

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| GET | `/health` | none | `{status, groq: check_models(), embedding_model, chunks, docs}` |
| POST | `/upload` | multipart, one or more `files` | `list[IngestResult]` |
| GET | `/documents` | none | registry rows |
| DELETE | `/documents/{id}` | none | `{deleted: true, chunks_removed}` |
| POST | `/documents/{id}/confirm` | none | `IngestResult` |
| POST | `/documents/{id}/discard` | none | `{discarded: true}` |
| POST | `/ask` | `{question: str}` | `{answer, confidence, refused, citations, trace, latency_ms}` |

**Rules**
- **Startup (lifespan):** set up logging, warm up the embedding model, load FAISS (or rebuild from the registry if it fails), rebuild the tables, and run `check_models()`. A missing key should not crash the app; `/health` reports it instead.
- **Upload size:** reject requests with a total `Content-Length` over 19 MB per file times the file count, with a 413 and a friendly message. Per-file checks still happen in `validate_file`.
- **Errors:** a global exception handler returns `{"error": "Something went wrong. Please try again."}` with a 500 and logs the traceback. Stack traces never go to the client. LLM rate limits map to a 503 with the friendly message from step 4.
- **CORS:** allow `http://localhost:8765`.
- **Logging:** JSON lines with time, level, logger, message and request_id. Use a rotating file handler (5 MB, 3 backups) plus the console. Questions are logged through `mask_pii`.
- Run with `uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8766 --reload`.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md and docs/build_guide/10_fastapi.md for the exact spec. This is STEP 10 ONLY: FastAPI backend and logging. No Streamlit yet.

Add dependencies: `uv add fastapi "uvicorn[standard]" python-multipart` and `uv add --dev httpx`.

Implement app/logging_setup.py, app/api/schemas.py, and app/api/main.py exactly as specified, reusing app/ingestion/pipeline.py and app/agents/graph.answer_question. Use a FastAPI lifespan handler for startup work. Add a request-id middleware that puts the id in logs and in an X-Request-ID response header. Run blocking work (ingest, ask) in a threadpool (FastAPI sync endpoints are fine).

Create tests/test_api.py with TestClient (mock answer_question and the relevance classifier so tests are offline): /health returns 200 with fields; upload of a txt returns a result; upload of photo.jpg returns status "error" with the image message; /documents lists; delete works; /ask returns the mocked answer; an exception inside /ask returns 500 with the friendly error and no traceback.

Run pytest, then start the server in the background and show me the output of:
curl.exe -s http://127.0.0.1:8766/health
curl.exe -s -F "files=@docs/sample_data/txt/first_week_faq.txt" -F "files=@docs/sample_data/invalid/photo.jpg" http://127.0.0.1:8766/upload
curl.exe -s -X POST http://127.0.0.1:8766/ask -H "Content-Type: application/json" -d "{\"question\": \"When do I get paid in India?\"}"
```

## Checkpoint

Terminal 1:

```powershell
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8766 --reload
```

Terminal 2:

```powershell
curl.exe -s http://127.0.0.1:8766/health
curl.exe -s -F "files=@docs/sample_data/pdf/employee_handbook.pdf" -F "files=@docs/sample_data/invalid/archive.zip" http://127.0.0.1:8766/upload
curl.exe -s -X POST http://127.0.0.1:8766/ask -H "Content-Type: application/json" -d '{\"question\": \"What is the 401k match?\"}'
uv run pytest -q
```

Then open http://127.0.0.1:8766/docs and try the endpoints in the browser.

**Expected output:** `/health` shows the chunk count and `key_ok: true`. The upload returns `duplicate` or `indexed` for the PDF and `error` with the archive message for the zip. `/ask` answers "100% match on the first 4% of salary" with a citation. `logs\app.log` contains JSON lines.

## Common problems

- **PowerShell mangles the JSON body:** use the `/docs` page instead, or save the body to `q.json` and pass `-d "@q.json"`.
- **The first request is slow:** the embedding model loads at startup. The lifespan warm-up handles this; check it actually runs.
- **`--reload` keeps restarting:** it watches `data/` and `logs/`. Add `--reload-dir app`.
