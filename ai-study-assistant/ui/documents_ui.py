# Study material: the attach popover next to the tutor's topic box, and the Documents page.
#
# Both are the same flow (add it, let the tutor read it, ask about it, get quizzed on it); the
# popover keeps it one click away while studying, the page lays the library out in full.
from typing import Any
import streamlit as st
from db import learning_service
from rag import store
from rag.extract import DocumentError
from rag.tutor import STYLES, answer_question, extract_concepts, quiz_from_document
from ui import cards, history
from utils.helpers import StudyAssistantError, log_error
SELECTED = "attached_document_id"
ASK_STYLES = {
    "Explain this": "explain",
    "Explain like I'm a beginner": "beginner",
    "Summarise it": "summary",
    "Give me examples": "examples",
    "Find the definitions": "definitions",
    "Compare these ideas": "compare",
    "Write revision notes": "notes",
}
# The attach control: a single button that opens everything to do with documents.
def render_attach(user: Any, on_quiz: Any = None) -> None:
    try:
        documents = store.list_documents(user.user_id)
    except StudyAssistantError as error:
        st.warning(f"Could not read your documents. {error}")
        return
    label = f"＋  Add study material ({len(documents)})" if documents else "＋  Add study material"
    with st.container(key="sa_attach"):
        with st.popover(label, width="stretch"):
            _render_panel(user, documents, on_quiz)
    selected = _selected(user, documents)
    if selected is not None:
        st.caption(
            f"Attached: **{selected.filename}** — the tutor will teach and quiz you from this."
        )
# Everything inside the popover: upload, pick, understand, quiz, ask, remove.
def _render_panel(user: Any, documents: list[Any], on_quiz: Any) -> None:
    st.caption(
        "Bring your own notes, slides or a textbook chapter. Answers and quizzes come only from "
        "what you upload, and every answer says which file it came from."
    )
    _render_upload(user)
    if not documents:
        st.info("Nothing uploaded yet. Add a PDF, TXT, Markdown or DOCX file above.")
        return
    names = {document.filename: document.id for document in documents}
    current = st.session_state.get(SELECTED)
    index = next(
        (position for position, document in enumerate(documents) if document.id == current), 0
    )
    chosen_name = st.selectbox("Study material", list(names), index=index, key="attach_pick")
    document = next(d for d in documents if d.id == names[chosen_name])
    st.session_state[SELECTED] = document.id
    pages = f"{document.pages} pages · " if document.pages else ""
    st.caption(f"{pages}{document.chunk_count} passages · {document.size_bytes // 1024} KB")
    if document.concepts:
        st.caption(
            "Covers: "
            + ", ".join(slug.split("::")[-1].replace("_", " ") for slug in document.concepts[:10])
        )
    _render_quiz_controls(user, document, on_quiz)
    st.divider()
    _render_ask(user, document)
    st.divider()
    _render_delete(user, document)
# The documents page: an upload area, the library as cards, and the chosen document's tools.
# It is the same flow as the attach popover in the tutor, laid out as a full page.
def render_library(user: Any, on_quiz: Any = None) -> None:
    try:
        documents = store.list_documents(user.user_id)
    except StudyAssistantError as error:
        st.warning(f"Could not read your documents. {error}")
        return
    with st.container(key="sa_panel_upload"):
        st.html(cards.section_head("Upload study material", "PDF, DOCX, TXT or Markdown · up to 20 MB"))
        _render_upload(user)
    if not documents:
        st.html(cards.empty_state(
            "file", "No documents yet",
            "Upload notes, slides or a textbook chapter. Answers and quizzes then come only from your material.",
        ))
        return
    selected = _selected(user, documents) or documents[0]
    st.html(cards.section_head("Your documents", f"{len(documents)} file{'s' if len(documents) != 1 else ''}"))
    for row in range(0, len(documents), 3):
        columns = st.columns(3)
        for column, document in zip(columns, documents[row:row + 3]):
            is_selected = document.id == selected.id
            key = f"sa_doc_sel_{document.id}" if is_selected else f"sa_doc_{document.id}"
            with column, st.container(key=key):
                pages = f"{document.pages} pages · " if document.pages else ""
                st.html(cards.document_card(
                    document.filename,
                    f"{pages}{document.chunk_count} passages · added {history.relative_time(document.created_at)}",
                    [slug.split("::")[-1].replace("_", " ") for slug in document.concepts],
                ))
                if st.button(
                    "Selected" if is_selected else "Open", key=f"docopen_{document.id}", width="stretch",
                    type="primary" if is_selected else "secondary", disabled=is_selected,
                    icon=":material/check:" if is_selected else ":material/open_in_new:",
                ):
                    st.session_state[SELECTED] = document.id
                    st.rerun()
    st.session_state[SELECTED] = selected.id
    with st.container(key="sa_panel_doc_tools"):
        st.html(cards.section_head(selected.filename, "Ask, summarise or get quizzed"))
        ask_tab, quiz_tab, manage_tab = st.tabs(["Ask & summarise", "Quiz me", "Manage"])
        with ask_tab:
            _render_ask(user, selected)
        with quiz_tab:
            _render_quiz_controls(user, selected, on_quiz)
        with manage_tab:
            _render_delete(user, selected)
# Delete a document, behind a confirmation tick.
def _render_delete(user: Any, document: Any) -> None:
    confirm = st.checkbox("Yes, delete it", key=f"docconfirm_{document.id}")
    if st.button("Delete this document", key=f"docdel_{document.id}", width="stretch"):
        if not confirm:
            st.warning("Tick the box first — this also deletes its passages.")
        else:
            store.delete_document(user.user_id, document.id)
            st.session_state.pop(SELECTED, None)
            st.rerun()
# Ask the tutor to read the document and set a quiz on it.
def _render_quiz_controls(user: Any, document: Any, on_quiz: Any) -> None:
    columns = st.columns(2)
    difficulty = columns[0].selectbox(
        "Difficulty", ["easy", "medium", "hard"], index=1, key=f"docdiff_{document.id}"
    )
    count = columns[1].number_input("Questions", 3, 10, 5, key=f"doccount_{document.id}")
    focus = st.text_input(
        "Focus on (optional)", key=f"docfocus_{document.id}",
        placeholder="a chapter, a section, or a single idea",
    )
    if st.button("Understand this and quiz me", type="primary", width="stretch", key=f"docquiz_{document.id}"):
        _start_quiz(user, document, int(count), difficulty, focus.strip(), on_quiz)
# Read the document, register what it covers, then build the quiz.
def _start_quiz(
    user: Any, document: Any, count: int, difficulty: str, focus: str, on_quiz: Any
) -> None:
    if on_quiz is None:
        st.warning("Quizzes are not available from here.")
        return
    if not document.concepts:
        _extract_concepts(user, document)
    with st.spinner("Reading your material and writing questions..."):
        try:
            questions, _hits = quiz_from_document(
                user.user_id, document.id, document.filename, topic=focus,
                num_questions=count, difficulty=difficulty,
            )
        except StudyAssistantError as error:
            st.error(str(error))
            return
    if not questions:
        st.warning("There was not enough readable material to build a quiz from.")
        return
    on_quiz(document, questions, difficulty)
# The upload control.
def _render_upload(user: Any) -> None:
    uploaded = st.file_uploader(
        "Upload a file",
        type=["pdf", "txt", "md", "docx"],
        key="document_upload",
        help="Up to 20 MB. Scanned PDFs without text cannot be read.",
    )
    if uploaded is None:
        return
    if st.session_state.get("last_upload") == uploaded.file_id:
        return
    with st.spinner(f"Reading {uploaded.name}..."):
        try:
            document = store.ingest(
                user.user_id, uploaded.name, uploaded.getvalue(), uploaded.type or ""
            )
        except DocumentError as error:
            st.session_state["last_upload"] = uploaded.file_id
            st.warning(str(error))
            return
        except StudyAssistantError as error:
            st.session_state["last_upload"] = uploaded.file_id
            st.error(str(error))
            return
    st.session_state["last_upload"] = uploaded.file_id
    st.session_state[SELECTED] = document.id
    learning_service.record_event(
        user.user_id, kind="document_uploaded", detail={"filename": document.filename}
    )
    _extract_concepts(user, document)
    st.success(f"Added {document.filename} — {document.chunk_count} passages indexed.")
    st.rerun()
# Work out what the document teaches and put those concepts in the knowledge graph.
def _extract_concepts(user: Any, document: Any) -> None:
    with st.spinner("Working out what it covers..."):
        try:
            found = extract_concepts(user.user_id, document.id, document.filename)
        except StudyAssistantError:
            log_error("Concept extraction failed")
            return
    concepts = learning_service.register_names(found.concepts, found.subject)
    if concepts:
        store.set_document_concepts(user.user_id, document.id, [c.slug for c in concepts])
        st.caption(f"Concepts found: {', '.join(c.name for c in concepts[:8])}")
# Ask a question about the attached document.
def _render_ask(user: Any, document: Any) -> None:
    question = st.text_input(
        "Ask about this document", key=f"docask_{document.id}",
        placeholder="Explain overlapping subproblems",
    )
    style = st.selectbox("How should I answer?", list(ASK_STYLES), key=f"docstyle_{document.id}")
    if not st.button("Ask", key=f"docaskgo_{document.id}", width="stretch"):
        return
    if not question.strip():
        st.warning("Type a question first.")
        return
    with st.spinner("Reading your material..."):
        try:
            answer = answer_question(
                user.user_id, question.strip(), document.id, ASK_STYLES[style]
            )
        except StudyAssistantError as error:
            st.error(str(error))
            return
    if answer.is_empty:
        st.warning(answer.answer)
        return
    if not answer.confident:
        st.caption("Your material only partly covers this.")
    st.markdown(answer.answer)
    for reference in answer.citations:
        st.html(cards.citation(reference.describe()))
# The document currently attached, if it still exists.
def _selected(user: Any, documents: list[Any]) -> Any:
    document_id = st.session_state.get(SELECTED)
    if not document_id:
        return None
    return next((document for document in documents if document.id == document_id), None)
