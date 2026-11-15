# Step 1: Scaffold the project

## Spec

**Goal:** an empty but correctly structured Python project that loads its settings from `.env`.

**Files created**
- `pyproject.toml`, `uv.lock`, `.python-version` (3.11)
- `app/__init__.py`, `app/config.py`
- Empty packages, each with an `__init__.py`: `app/api/`, `app/ingestion/`, `app/store/`, `app/agents/`, `app/guardrails/`, `app/llm/`
- Folders: `ui/`, `scripts/`, `tests/`, `data/`, `logs/`, `docs/` (sample data lives in `docs/sample_data/`, see step 2)
- `.env`, `.env.example`, `.gitignore`

**Rules**
- Use Python 3.11, managed by uv.
- `app/config.py` uses `pydantic-settings` and exposes a single `settings` object. Fields:
  - `groq_api_key: str = ""`
  - `groq_model: str = "qwen/qwen3.8-27b"`
  - `groq_guard_model: str = "meta-llama/llama-guard-4-12b"`
  - `embedding_model: str = "BAAI/bge-small-en-v1.5"`
  - `max_file_mb: float = 19`
  - `top_k: int = 5`
  - `similarity_threshold: float = 0.35`
  - `relevance_threshold: float = 0.75`
  - `api_url: str = "http://127.0.0.1:8766"`
  - `data_dir: Path = Path("data")`, plus derived `faiss_dir`, `registry_db` and `uploads_dir` paths
  - `log_dir: Path = Path("logs")`
- `.env.example` has every variable with placeholder values. `.env` holds your real key.
- `.gitignore` ignores `.env`, `.venv/`, `data/`, `logs/`, `__pycache__/`, `*.zip` and `docs/sample_data/invalid/oversize.pdf`.
- Install only the dependencies listed below. Later steps add more.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md for full context. We are building it one step at a time. This is STEP 1 ONLY: project scaffold. Do not implement anything from later steps.

I am on Windows with PowerShell. My system Python is 3.14, but this project must use Python 3.11 via uv.

Do the following:
1. Run `uv init --app --name onboardiq` in the current folder (no nested folder), then `uv python pin 3.11`. Delete any generated hello.py or main.py.
2. Add dependencies: `uv add pydantic-settings python-dotenv`.
3. Create the package layout: app/__init__.py, app/config.py, and empty packages (each with __init__.py) app/api, app/ingestion, app/store, app/agents, app/guardrails, app/llm. Create folders ui/, scripts/, tests/, data/, logs/ (put a .gitkeep in empty folders).
4. app/config.py: a pydantic-settings `Settings` class reading from `.env`, with these fields and defaults: groq_api_key "", groq_model "qwen/qwen3.8-27b", groq_guard_model "meta-llama/llama-guard-4-12b", embedding_model "BAAI/bge-small-en-v1.5", max_file_mb 19.0, top_k 5, similarity_threshold 0.35, relevance_threshold 0.75, api_url "http://127.0.0.1:8766", data_dir Path("data"), log_dir Path("logs"). Add properties faiss_dir (data_dir/"faiss_index"), registry_db (data_dir/"registry.db"), uploads_dir (data_dir/"uploads"), and max_file_bytes. Create the data directories on import. Expose a module-level `settings = Settings()`.
5. Create .env.example with every variable and placeholder values. Create .env with the same variables; leave GROQ_API_KEY empty for me to fill in.
6. Create .gitignore covering .env, .venv/, data/ (but keep data/.gitkeep), logs/, __pycache__/, *.pyc, *.zip, .pytest_cache/, docs/sample_data/invalid/oversize.pdf.
7. Run `git init` if this is not already a git repo.
8. Run `uv sync`, then run `uv run python -c "from app.config import settings; print(settings.groq_model, settings.max_file_bytes)"` and show me the output.

Keep the code minimal and typed. Do not add README content yet.
```

## Checkpoint

1. Open `.env` and paste your Groq key after `GROQ_API_KEY=`.
2. Run:

```powershell
uv run python --version
uv run python -c "from app.config import settings; print(settings.groq_model, settings.max_file_bytes, bool(settings.groq_api_key))"
git status
```

**Expected output:** `Python 3.11.x`, then `qwen/qwen3.8-27b 19922944.0 True`. `git status` should not list `.env`.

## Common problems

- **`uv run python --version` shows 3.14:** delete `.venv`, then run `uv python pin 3.11` and `uv sync` again.
- **`ModuleNotFoundError: app`:** uv didn't install the project in editable mode. Make sure `pyproject.toml` has a build system, or run scripts from the project root so `app` is importable. Asking the agent to add `[tool.uv] package = true` with a hatchling build backend also fixes it.
- **`.env` shows up in `git status`:** check `.gitignore` is in the project root and that the line reads exactly `.env`.
