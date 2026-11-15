# Step 14a: README

## Spec

**Goal:** an evaluator can set up and run the app from the README alone, with uv, and find their way around the project.

**Files created or changed**
- `README.md` (full version; keep the Debugging section from step 12)

**`README.md` sections**
1. What OnboardIQ is (3 sentences) and a screenshot (`docs/screenshot.png`, which you'll take in step 15).
2. Features list: supported formats, the relevance gate, the five agents, guardrails and citations.
3. Quick start with uv: `uv sync`, copy `.env.example` to `.env` and add `GROQ_API_KEY`, start the API and the UI in two terminals, then open http://localhost:8765 and click "Load sample documents".
4. Local setup details on Windows, macOS and Linux (installing uv and Python 3.11, the CPU-only torch index, the first-run embedding model download).
5. Configuration: a table of every `.env` variable.
6. Usage walkthrough with 4 example questions.
7. Testing: `pytest`, live tests and the eval script, plus a link to `docs/eval_results.md`.
8. Debugging (from step 12).
9. Project structure tree.
10. Limitations.
11. Capstone task mapping table (tasks 1 to 10, linking each to its files).

Link to `ARCHITECTURE.md` (step 14b) from the features or project structure section.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md and docs/build_guide/14a_readme.md for the exact spec. This is STEP 14a ONLY: the README. Do not create ARCHITECTURE.md yet, and do not add Docker files; the app is run locally with uv.

Write the full README.md with all 11 sections from the spec, keeping the existing Debugging section. Use real commands and real file paths from this repo, and list every variable in .env.example in the configuration table. Verify every path you mention exists (docs/screenshot.png and ARCHITECTURE.md come in later steps; mention them anyway).

When done, list any path in README.md that doesn't exist yet.
```

## Checkpoint

Follow the README quick start from a fresh terminal:

```powershell
uv sync
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8766
```

In a second terminal:

```powershell
uv run streamlit run ui/streamlit_app.py
```

Open http://localhost:8765, click "Load sample documents", and ask a question.

**Expected output:** the quick start works exactly as written. The only missing paths are `docs/screenshot.png` (step 15) and `ARCHITECTURE.md` (step 14b).

## Common problems

- **`uv sync` downloads a 2+ GB torch:** that's the CUDA build. Check that `pyproject.toml` still has the CPU-only `pytorch-cpu` index from step 6.
- **The first start is slow:** the embedding model (about 130 MB) downloads on the first run and is cached afterwards. Say so in the README.
- **The configuration table drifts from `.env.example`:** generate it from `.env.example` and `app/config.py`, not from memory.
- **The README mentions a path that doesn't exist:** check every path with `Test-Path` before you finish.
