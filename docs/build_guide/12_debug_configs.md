# Step 12: Debug and launch configurations

## Spec

**Goal:** press F5 in Cursor and debug any part of the app (API, UI, the CLIs or the tests) with breakpoints that work inside the agents.

**Files created or changed**
- `pyproject.toml`: add `debugpy` to the dev dependency group
- `.vscode/settings.json`
- `.vscode/launch.json`
- `README.md`: a "Debugging" section (create a minimal README if it doesn't exist yet; step 14a fills in the rest)

**`.vscode/settings.json`**

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": ["tests"],
  "python.envFile": "${workspaceFolder}/.env"
}
```

**`.vscode/launch.json`**: every configuration uses `"type": "debugpy"`, `"request": "launch"` (except attach), `"envFile": "${workspaceFolder}/.env"`, `"justMyCode": false` and `"cwd": "${workspaceFolder}"`.

| Name | How it runs |
| --- | --- |
| API: FastAPI (uvicorn) | `"module": "uvicorn"`, args `app.api.main:app --host 127.0.0.1 --port 8766 --reload --reload-dir app` |
| UI: Streamlit | `"module": "streamlit"`, args `run ui/streamlit_app.py --server.port 8765` |
| Ingest sample data (CLI) | `"program": "${workspaceFolder}/scripts/ingest_samples.py"`, args `--reset --include-invalid` |
| Ask a question (CLI) | `"program": "${workspaceFolder}/scripts/ask.py"`, args `["${input:question}"]` |
| Pytest: current file | `"module": "pytest"`, args `${file} -q` |
| Pytest: all tests | `"module": "pytest"`, args `tests -q` |
| Attach to process (port 5678) | `"request": "attach"`, `"connect": {"host": "localhost", "port": 5678}` |

- **Compound "Full stack: API + UI":** runs the API and UI configs together, with `"stopAll": true`.
- **Inputs:** `question` is a `promptString` with the default "Who is Siddharth Patel's onboarding buddy?".

**README "Debugging" section**
- How to use the F5 configs above.
- Terminal equivalents:
  - `uv run uvicorn ...`
  - `uv run streamlit run ...`
  - `uv run python -m debugpy --listen 5678 --wait-for-client scripts/ask.py "question"`, then run the "Attach" config
- Good breakpoint spots: `pipeline.ingest_file`, `relevance.classify`, `graph.answer_question`, each agent node, and `input_guard.check`.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md (section "7. Debugging and launch configs") and docs/build_guide/12_debug_configs.md for the exact spec. This is STEP 12 ONLY: debug configs.

Run `uv add --dev debugpy`. Create .vscode/settings.json and .vscode/launch.json exactly as the spec describes (Windows interpreter path .venv\Scripts\python.exe). Validate that launch.json is valid JSON (comments are allowed by VS Code but keep it comment-free).

Add a "Debugging" section to README.md (create a minimal README with a title and one-line description if none exists) covering F5 usage, the terminal equivalents including the debugpy --listen/attach flow, and suggested breakpoint locations with file paths.

Make sure .vscode/ is NOT ignored by .gitignore so evaluators get the configs.
```

## Checkpoint

1. In Cursor, open Run and Debug (Ctrl+Shift+D). All 7 configs and "Full stack: API + UI" should be listed.
2. Set a breakpoint in `app/agents/planner.py` inside the planner node.
3. Run "Ask a question (CLI)", accept the default question, and check that execution stops at your breakpoint. Inspect `state`.
4. Run "Full stack: API + UI", open http://localhost:8765, ask a question, and check that the same breakpoint hits inside the API process.
5. Run "Pytest: all tests" and check it passes.

## Common problems

- **"Debugger type debugpy is not supported":** install or enable the Python Debugger extension (`ms-python.debugpy`) in Cursor.
- **Breakpoints are greyed out inside the API:** `--reload` runs the app in a child process. Remove `--reload` from the debug config if breakpoints don't bind, and keep it only for the terminal command.
- **The wrong interpreter is picked:** press Ctrl+Shift+P, choose "Python: Select Interpreter", and select `.venv\Scripts\python.exe`.
