# Step 11: Self-explanatory Streamlit UI

## Spec

**Goal:** someone who has never seen the project can open the page and understand what it does, what to upload, and how to ask questions, with no instructions from you.

**Files created**
- `ui/streamlit_app.py`
- `ui/api_client.py`: a thin `httpx` wrapper around the FastAPI endpoints, with a 120-second timeout and friendly errors when the API is down
- `ui/assets/architecture.png` (or a Mermaid or Graphviz diagram rendered with `st.graphviz_chart`)
- `.streamlit/config.toml`

**`.streamlit/config.toml`**

```toml
[server]
port = 8765
maxUploadSize = 19

[theme]
base = "light"
primaryColor = "#2563eb"
```

**Layout (top to bottom)**
1. **Header:** "OnboardIQ - Your onboarding assistant", plus a one-paragraph description: "Ask questions about your company's onboarding documents. OnboardIQ reads PDFs, text files, CSVs and Excel sheets, keeps only onboarding-related documents, and answers with citations to the exact page or rows." Add a caption with the capstone context.
2. **Status bar** (one row of `st.metric` or badges): Groq connection (green or red), the model name, the embedding model, and chunks indexed. Data comes from `/health`. If the API is unreachable or the key is invalid, show an `st.error` banner explaining how to fix it ("Start the API with ...", "Add GROQ_API_KEY to .env").
3. **"How it works" expander:** the 5 numbered steps (Upload, Validate, Relevance check, Index, Ask with agents and guardrails) and the architecture diagram.
4. **Sidebar, "Step 1 - Upload onboarding documents":**
   - `st.file_uploader` with `accept_multiple_files=True`, `type=["pdf","txt","csv","xlsx","xls"]`, a label naming the allowed types and the "under 19 MB each" limit, and `help=` text explaining the relevance check.
   - An "Upload and process" button. It shows a spinner, then a per-file results table with status badges: Indexed (green), Rejected - not onboarding (orange), Pending review (blue), Error (red), and Duplicate (grey). Each row includes the message.
   - Pending docs show Confirm and Discard buttons per file.
   - A "Load sample documents" button ingests the 9 onboarding documents in `docs/sample_data/{pdf,txt,csv,xlsx}/` so evaluators can try it instantly.
   - A "Knowledge base" section lists the indexed docs with category and chunk count, plus a delete button for each.
   - A document preview: pick an indexed doc to see its preview text or table head, page or row counts, and category.
5. **Main area, "Step 2 - Ask a question":**
   - `st.chat_input` with the placeholder "e.g. When is the benefits enrollment deadline?"
   - 4 sample-question buttons above the input. Clicking one asks it.
   - Chat history is kept in `st.session_state`.
   - **Answer card:** the answer in markdown and a confidence badge (High green, Medium amber, Low grey). A "Sources used" expander shows each citation with its source, page or rows, score and snippet. An "Agent steps" expander shows the trace as a numbered list with the ms for each agent.
   - Refusals use `st.info` styling, not `st.error`.
6. **Footer limitations:** "No OCR for scanned PDFs. English only. Answers are limited to the uploaded documents. Not legal or HR advice."

**Rules**
- The UI only talks to the API through `ui/api_client.py`, which reads `API_URL` from settings or the environment. It doesn't import `app.agents` directly.
- Use `st.cache_data(ttl=10)` for `/health` and `/documents`, and clear that cache after an upload or delete.

## Prompt

```text
Read docs/build_guide/onboarding_agent_capstone.plan.md (section "6. Self-explanatory UI") and docs/build_guide/11_streamlit_ui.md for the exact spec. This is STEP 11 ONLY: the Streamlit UI.

Add dependency: `uv add streamlit`.

Implement .streamlit/config.toml, ui/api_client.py, and ui/streamlit_app.py exactly as specified. The UI must talk to the backend only via ui/api_client.py over HTTP (API_URL from env, default http://127.0.0.1:8766). Handle API-down gracefully with a clear banner, never a Python traceback. Render the architecture diagram with st.graphviz_chart (no image dependency needed) unless an image exists at ui/assets/architecture.png.

Add a "Load sample documents" sidebar button that posts every file in docs/sample_data/pdf, txt, csv and xlsx (not irrelevant/ or invalid/) to /upload. Use the example questions in docs/sample_data/README.md as the 4 sample-question buttons.

Keep the code organised into small functions: render_header, render_status, render_how_it_works, render_sidebar_upload, render_knowledge_base, render_chat, render_answer, render_footer.

When done, tell me the exact two commands to run (API and UI) in separate terminals. Do not start long-running processes yourself unless asked.
```

## Checkpoint

Terminal 1:

```powershell
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8766 --reload-dir app --reload
```

Terminal 2:

```powershell
uv run streamlit run ui/streamlit_app.py
```

Open http://localhost:8765 and work through this list:
- [ ] The description and the "How it works" section explain the app without you saying anything.
- [ ] The status bar is green and shows the chunk count.
- [ ] Uploading `invalid/photo.jpg`, `invalid/archive.zip`, `irrelevant/pasta_recipe.txt` and `pdf/code_of_conduct.pdf` together gives 4 rows, each with its own message (image error, archive error, rejected as not onboarding, indexed or duplicate).
- [ ] Clicking a sample question shows an answer, a confidence badge, sources and agent steps.
- [ ] Asking "What's the best pizza in Rome?" gives a polite scoped reply.
- [ ] Stopping the API (Ctrl+C in terminal 1) and refreshing shows a clear "API not running" banner, not a crash.

## Common problems

- **"File must be 19.0MB or smaller" appears before your own message:** that's Streamlit's built-in limit from `maxUploadSize`. Your validator handles files between 19 MB and the Streamlit limit, so set `maxUploadSize = 19` and accept that Streamlit's message shows for anything larger.
- **The whole page reruns on every click:** expected in Streamlit. Keep state in `st.session_state` and use `st.fragment` for the chat area if it feels slow.
- **Answers fail with "rate limit" even though Groq has plenty of tokens left:** check `logs/app.log` for `Request too large ... output tokens per minute (OTPM): Limit 1000`. The free tier caps output at 1000 tokens per minute, and a call without `max_tokens` asks for 2048. `GROQ_MAX_TOKENS` (default 800) sets the cap on every call.
- **Sample-question buttons don't trigger an answer:** store the clicked question in `st.session_state["pending_question"]` and process it on the next run.
