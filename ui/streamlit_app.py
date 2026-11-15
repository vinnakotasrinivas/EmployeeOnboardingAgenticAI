"""OnboardIQ Streamlit UI. Talks to the FastAPI backend only through api_client."""

from __future__ import annotations

from typing import Any

import streamlit as st

import api_client as api

SAMPLE_DIRS = ("pdf", "txt", "csv", "xlsx")
SAMPLE_QUESTIONS = [
    "Who is Siddharth Patel's onboarding buddy and manager?",
    "What is the benefits enrollment deadline for someone who started on 19 October 2026?",
    "When is the next Security Awareness session in IST?",
    "How many days of earned leave do employees in India get, and how much can be carried forward?",
]
STATUS_BADGES = {
    "indexed": ("green", "Indexed"),
    "rejected": ("orange", "Rejected - not onboarding"),
    "pending": ("blue", "Pending review"),
    "error": ("red", "Error"),
    "duplicate": ("gray", "Duplicate"),
}
CONFIDENCE_COLORS = {"High": "green", "Medium": "orange", "Low": "gray"}
ARCHITECTURE_IMAGE = api.PROJECT_ROOT / "ui" / "assets" / "architecture.png"
ARCHITECTURE_DOT = """
digraph {
  rankdir=LR; nodesep=0.3; ranksep=0.35;
  node [shape=box, style="rounded,filled", fillcolor="#eff6ff", color="#2563eb", fontname="Helvetica", fontsize=11];
  edge [color="#64748b", fontname="Helvetica", fontsize=9];
  subgraph cluster_ingest {
    label="1. Ingestion"; fontname="Helvetica"; color="#cbd5e1";
    upload [label="Upload"]; validate [label="Validate\\n(type, size, content)"];
    relevance [label="Relevance check\\n(LLM)"]; chunk [label="Chunk + embed"];
    upload -> validate -> relevance -> chunk;
  }
  faiss [label="FAISS index", shape=cylinder, fillcolor="#f1f5f9"];
  tables [label="Table store", shape=cylinder, fillcolor="#f1f5f9"];
  chunk -> faiss; chunk -> tables;
  subgraph cluster_ask {
    label="2. Question answering (LangGraph)"; fontname="Helvetica"; color="#cbd5e1";
    question [label="Question"]; inguard [label="Input guard"]; planner [label="Planner"];
    retriever [label="Retriever"]; analyst [label="Data analyst"]; reasoner [label="Reasoner"];
    validator [label="Validator"]; outguard [label="Output guard"];
    answer [label="Answer +\\ncitations", fillcolor="#dcfce7", color="#16a34a"];
    question -> inguard -> planner -> retriever -> analyst -> reasoner -> validator -> outguard -> answer;
    validator -> reasoner [label="retry", style=dashed];
  }
  faiss -> retriever; tables -> analyst;
}
"""


def init_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("upload_results", [])
    st.session_state.setdefault("uploader_key", 0)


@st.cache_data(ttl=10, show_spinner=False)
def get_health() -> dict[str, Any]:
    try:
        return {"data": api.health(), "error": None}
    except api.APIError as exc:
        return {"data": None, "error": exc.message}


@st.cache_data(ttl=10, show_spinner=False)
def get_documents() -> list[dict[str, Any]]:
    try:
        return api.documents()
    except api.APIError:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def get_preview(doc_id: str, updated_at: str) -> dict[str, Any]:
    try:
        return api.preview(doc_id)
    except api.APIError as exc:
        return {"error": exc.message}


def refresh() -> None:
    get_health.clear()
    get_documents.clear()


def escape_md(text: str) -> str:
    """Stop dollar amounts from being rendered as LaTeX."""
    return text.replace("$", "\\$")


def status_badge(status: str) -> str:
    color, label = STATUS_BADGES.get(status, ("gray", status))
    return f":{color}-badge[{label}]"


# ---------- actions (button callbacks) ----------

def run_upload(files: list[tuple[str, bytes]]) -> None:
    try:
        with st.spinner(f"Processing {len(files)} file(s). Each one is validated, checked for relevance and indexed..."):
            st.session_state.upload_results = api.upload(files)
    except api.APIError as exc:
        st.session_state.upload_results = []
        st.toast(exc.message, icon=":material/error:")
    refresh()


def load_samples() -> None:
    root = api.PROJECT_ROOT / "docs" / "sample_data"
    files = [(p.name, p.read_bytes()) for d in SAMPLE_DIRS for p in sorted((root / d).glob("*")) if p.is_file()]
    if not files:
        st.toast(f"No sample documents found in {root}.", icon=":material/error:")
        return
    run_upload(files)


def _replace_result(doc_id: str, new: dict[str, Any] | None) -> None:
    """Swap the upload result row for `doc_id` with `new`, or drop it when `new` is None."""
    updated = []
    for r in st.session_state.upload_results:
        if r.get("doc_id") != doc_id:
            updated.append(r)
        elif new is not None:
            updated.append(new)
    st.session_state.upload_results = updated


def confirm_doc(doc_id: str) -> None:
    try:
        with st.spinner("Indexing..."):
            result = api.confirm(doc_id)
        _replace_result(doc_id, result)
        st.toast(f"{result['filename']}: {result['message']}")
    except api.APIError as exc:
        st.toast(exc.message, icon=":material/error:")
    refresh()


def discard_doc(doc_id: str, filename: str) -> None:
    try:
        api.discard(doc_id)
        _replace_result(doc_id, None)
        st.toast(f"Discarded {filename}.")
    except api.APIError as exc:
        st.toast(exc.message, icon=":material/error:")
    refresh()


def delete_doc(doc_id: str, filename: str) -> None:
    try:
        removed = api.delete(doc_id)["chunks_removed"]
        st.toast(f"Deleted {filename} ({removed} chunks removed).")
    except api.APIError as exc:
        st.toast(exc.message, icon=":material/error:")
    refresh()


def ask_sample(question: str) -> None:
    st.session_state.pending_question = question


# ---------- page sections ----------

def render_header() -> None:
    st.title("OnboardIQ - Your onboarding assistant")
    st.markdown(
        "Ask questions about your company's onboarding documents. OnboardIQ reads PDFs, text files, CSVs and "
        "Excel sheets, keeps only onboarding-related documents, and answers with citations to the exact page "
        "or rows."
    )
    st.caption(
        "Capstone project: an agentic RAG assistant built with LangGraph agents, Groq LLMs, FAISS search, "
        "FastAPI and Streamlit. The sample data is for a fictional company, Northwind Labs."
    )


def render_status(health: dict[str, Any]) -> bool:
    """Show the status bar. Returns True if the API is reachable."""
    if health["error"]:
        st.error(
            f"{health['error']} Start it in a separate terminal from the project folder:\n\n"
            f"```powershell\n{api.START_API}\n```\nThen refresh this page.",
            title="API not running",
            icon=":material/cloud_off:",
        )
        return False

    data = health["data"]
    groq = data["groq"]
    if not groq.get("key_ok"):
        st.error(
            f"{groq.get('message', '')} Add a valid GROQ_API_KEY to the .env file in the project folder, "
            "then restart the API.",
            title="Groq is not connected",
            icon=":material/key_off:",
        )
    elif not groq.get("chat_model_ok"):
        st.warning(groq.get("message", ""), title="Chat model unavailable")

    cols = st.columns(4)
    with cols[0].container(border=True, height="stretch"):
        st.caption("Groq")
        if groq.get("key_ok"):
            st.badge("Connected", color="green", icon=":material/check_circle:")
        else:
            st.badge("Not connected", color="red", icon=":material/error:")
    with cols[1].container(border=True, height="stretch"):
        st.caption("Chat model")
        st.markdown(f"`{data['chat_model']}`")
    with cols[2].container(border=True, height="stretch"):
        st.caption("Embedding model")
        st.markdown(f"`{data['embedding_model']}`")
    with cols[3].container(border=True, height="stretch"):
        st.caption("Chunks indexed")
        st.markdown(f"**{data['chunks']}** from {data['docs']} documents")
    return True


def render_how_it_works() -> None:
    with st.expander("How it works", icon=":material/info:"):
        st.markdown(
            "1. **Upload**: add PDF, TXT, CSV or Excel files in the sidebar (or load the sample documents).\n"
            "2. **Validate**: each file is checked for type, size and readable content. Images, archives, "
            "Word files, macros and corrupt or scanned PDFs are rejected with a clear message.\n"
            "3. **Relevance check**: an LLM decides whether the document is about onboarding. Unrelated files "
            "are rejected; borderline ones wait for you to confirm.\n"
            "4. **Index**: text is split into chunks and embedded into a FAISS index; spreadsheets are also "
            "kept as tables so they can be filtered and sorted exactly.\n"
            "5. **Ask**: a team of agents answers your question. Guardrails check the question, a planner breaks "
            "it down, a retriever finds passages, a data analyst queries tables, a reasoner writes a cited "
            "answer and a validator checks every claim against the sources."
        )
        if ARCHITECTURE_IMAGE.exists():
            st.image(str(ARCHITECTURE_IMAGE), caption="Architecture")
        else:
            st.graphviz_chart(ARCHITECTURE_DOT, width="stretch", alt="OnboardIQ architecture diagram")


def render_upload_results() -> None:
    results = st.session_state.upload_results
    if not results:
        return
    st.markdown("**Results**")
    for r in results:
        with st.container(border=True):
            st.markdown(f"{status_badge(r['status'])} **{r['filename']}**")
            st.caption(escape_md(r["message"]))
            if r["status"] == "pending" and r.get("doc_id"):
                render_review_buttons(r["doc_id"], r["filename"], key_prefix="result")


def render_review_buttons(doc_id: str, filename: str, key_prefix: str) -> None:
    with st.container(horizontal=True):
        st.button("Confirm", key=f"{key_prefix}_confirm_{doc_id}", icon=":material/check:", type="primary",
                  on_click=confirm_doc, args=(doc_id,))
        st.button("Discard", key=f"{key_prefix}_discard_{doc_id}", icon=":material/close:",
                  on_click=discard_doc, args=(doc_id, filename))


def render_sidebar_upload(api_ok: bool) -> None:
    st.header("Step 1 - Upload onboarding documents")
    files = st.file_uploader(
        "PDF, TXT, CSV or Excel files, under 19 MB each",
        type=["pdf", "txt", "csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.uploader_key}",
        help="Every file is checked before indexing. Documents that aren't about employee onboarding (policies, "
             "benefits, IT setup, training, team info...) are rejected, and borderline ones wait for your review.",
    )
    if st.button("Upload and process", type="primary", icon=":material/upload:", width="stretch",
                 disabled=not files or not api_ok):
        run_upload([(f.name, f.getvalue()) for f in files])
        st.session_state.uploader_key += 1
        st.rerun()
    st.button("Load sample documents", icon=":material/folder_open:", width="stretch", disabled=not api_ok,
              on_click=load_samples,
              help="Uploads the 9 Northwind Labs sample onboarding documents from docs/sample_data so you can "
                   "try questions straight away.")
    render_upload_results()


def render_knowledge_base(docs: list[dict[str, Any]]) -> None:
    st.divider()
    st.header("Knowledge base")
    shown = {r.get("doc_id") for r in st.session_state.upload_results}
    waiting = [d for d in docs if d["status"] == "pending" and d["id"] not in shown]
    if waiting:
        st.markdown("**Waiting for your review**")
        for d in waiting:
            with st.container(border=True):
                st.markdown(f"{status_badge('pending')} **{d['filename']}**")
                st.caption(escape_md(d.get("reason") or ""))
                render_review_buttons(d["id"], d["filename"], key_prefix="kb")

    indexed = [d for d in docs if d["status"] == "indexed"]
    if not indexed:
        st.caption("No documents indexed yet. Upload files above or load the sample documents.")
        return
    for d in indexed:
        name_col, button_col = st.columns([5, 1], vertical_alignment="center")
        name_col.markdown(f"**{d['filename']}**  \n:gray[{d['category'] or 'unknown'} · {d['chunks']} chunks]")
        button_col.button("", key=f"delete_{d['id']}", icon=":material/delete:", help=f"Delete {d['filename']}",
                          on_click=delete_doc, args=(d["id"], d["filename"]))
    render_preview(indexed + [d for d in docs if d["status"] == "pending"])


def render_preview(docs: list[dict[str, Any]]) -> None:
    by_id = {d["id"]: d for d in docs}
    doc_id = st.selectbox("Preview a document", list(by_id), index=None, placeholder="Choose a document",
                          format_func=lambda i: by_id[i]["filename"])
    if not doc_id:
        return
    result = get_preview(doc_id, by_id[doc_id]["updated_at"])
    if result.get("error"):
        st.warning(result["error"])
        return
    facts = [result.get("category") or "unknown"]
    if result.get("pages"):
        facts.append(f"{result['pages']} pages")
    if result.get("rows"):
        facts.append(f"{result['rows']} rows")
    facts.append(f"{result.get('chunks', 0)} chunks")
    st.caption(" · ".join(facts))
    with st.container(height=300, border=True):
        if not result.get("preview"):
            st.caption(escape_md(result.get("message") or "No preview available."))
        elif result.get("rows") is not None:
            st.markdown(escape_md(result["preview"]))
        else:
            st.text(result["preview"])


def render_answer(result: dict[str, Any]) -> None:
    if result.get("error"):
        st.warning(result["error"], icon=":material/error:")
        return
    if result["refused"]:
        st.info(escape_md(result["answer"]), icon=":material/info:")
    else:
        st.markdown(escape_md(result["answer"]))
    with st.container(horizontal=True, vertical_alignment="center"):
        confidence = result["confidence"]
        st.badge(f"{confidence} confidence", color=CONFIDENCE_COLORS.get(confidence, "gray"))
        st.caption(f"{result['latency_ms'] / 1000:.1f}s")
    if result["citations"]:
        with st.expander(f"Sources used ({len(result['citations'])})", icon=":material/description:"):
            for i, c in enumerate(result["citations"], 1):
                st.markdown(f"**{i}. {c['source']}**, {c['location']} :gray[(score {c['score']:.2f})]")
                st.caption(escape_md(c["snippet"]))
    with st.expander("Agent steps", icon=":material/account_tree:"):
        st.markdown("\n".join(
            f"{i}. **{s['agent']}**: {escape_md(s['summary'])} :gray[({s['ms']} ms)]"
            for i, s in enumerate(result["trace"], 1)
        ))


def render_chat(api_ok: bool) -> None:
    st.header("Step 2 - Ask a question")
    st.caption("Try one of these, or type your own question below.")
    with st.container(horizontal=True):
        for i, q in enumerate(SAMPLE_QUESTIONS):
            st.button(q, key=f"sample_{i}", disabled=not api_ok, on_click=ask_sample, args=(q,))

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(escape_md(msg["content"]))
            else:
                render_answer(msg["result"])

    typed = st.chat_input("e.g. When is the benefits enrollment deadline?", disabled=not api_ok,
                          submit_mode="disable")
    question = typed or st.session_state.pop("pending_question", None)
    if not question:
        return
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(escape_md(question))
    with st.chat_message("assistant"):
        with st.spinner("The agents are reading your documents..."):
            try:
                result = api.ask(question)
            except api.APIError as exc:
                result = {"error": exc.message}
        render_answer(result)
    st.session_state.messages.append({"role": "assistant", "result": result})


def render_footer() -> None:
    st.divider()
    st.caption(
        "Limitations: No OCR for scanned PDFs. English only. Answers are limited to the uploaded documents. "
        "Not legal or HR advice."
    )


st.set_page_config(page_title="OnboardIQ", page_icon=":material/school:", layout="wide")
init_state()
render_header()
health = get_health()
api_ok = render_status(health)
render_how_it_works()
with st.sidebar:
    render_sidebar_upload(api_ok)
    if api_ok:
        render_knowledge_base(get_documents())
render_chat(api_ok)
render_footer()
