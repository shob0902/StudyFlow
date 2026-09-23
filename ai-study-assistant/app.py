# Streamlit UI that starts, pauses and resumes the LangGraph study workflow for the signed-in user.
from typing import Any
import streamlit as st
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from auth.errors import UnauthorizedError
from auth.streamlit_auth import learning_data, render_user_panel, require_login
from auth.user_context import UserContext, new_thread_id, require_thread_owner
from db.learning_service import record_attempts, record_mistake
from learning.mastery import ACTIVITY_DOCUMENT, Attempt
from learning.misconceptions import classify_attempt
from rag.store import get_document
from db.service import (
    SIDEBAR_PAGE_SIZE,
    delete_session,
    get_session,
    list_sessions,
    load_messages,
    record_session_state,
    rename_session,
    save_progress,
    session_count,
    start_study_session,
)
from graph.state import MAX_RETRIES, PASSING_SCORE, create_initial_state
from graph.workflow import (
    NODE_LABELS,
    TEXT_DIAGRAM,
    WAIT_FOR_ANSWERS,
    build_workflow,
    get_mermaid_diagram,
)
from llm.model import MODEL, NODE_API_KEYS, missing_api_keys
from ui import cards, coding_ui, documents_ui, history, knowledge_ui, study_ui
from ui.auth_ui import learning_summary as learning_summary_card
from ui.theme import inject_styles
from ui.three_scenes import END_NODE, embed, hero_scene, rocket_scene, score_scene, thinking_scene, workflow_scene
from utils.helpers import StudyAssistantError, grade_quiz, log_error, log_step
MAX_TOPIC_LENGTH = 300
SUGGESTED_TOPICS = ["What is an embedding?", "How does photosynthesis work?", "What is recursion?"]
st.set_page_config(page_title="AI Study Assistant", layout="centered")
# Build the compiled graph once per server process.
@st.cache_resource
def get_graph() -> CompiledStateGraph:
    return build_workflow()
# Create the st.session_state keys for the signed-in user. Runs after the login gate, so a logout wipes them first.
def init_session_state() -> None:
    defaults: dict[str, Any] = {
        "thread_id": None,
        "study_state": None,
        "next_nodes": (),
        "execution_log": [],
        "error": None,
        "graph_png": None,
        "celebrated": set(),
        "transcript": None,
        "read_only": False,
        "history_limit": SIDEBAR_PAGE_SIZE,
        "section": SECTIONS[0],
        PENDING_NAV: None,
        "doc_quiz": None,
        "coding_prefill": "",
        "attached_document_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
# The signed-in user for this browser session. require_login() puts it there before anything else runs.
def current_user() -> UserContext:
    user = st.session_state.get("user_context")
    if not isinstance(user, UserContext):
        raise UnauthorizedError("Please sign in again to continue.")
    return user
# Return the LangGraph config for this session's thread, after checking the user owns that thread.
def graph_config() -> dict[str, Any]:
    thread_id = require_thread_owner(current_user().user_id, st.session_state.thread_id)
    return {"configurable": {"thread_id": thread_id}}
# Copy the checkpointed graph state into st.session_state.
def sync_state_from_graph() -> None:
    snapshot = get_graph().get_state(graph_config())
    st.session_state.study_state = dict(snapshot.values)
    st.session_state.next_nodes = tuple(snapshot.next)
# Run or resume the graph with a 3D thinking animation and live progress, then rerun the page.
def run_graph(graph_input: Any) -> None:
    st.session_state.error = None
    embed(thinking_scene(), 170)
    with st.status("LangGraph is working...", expanded=True) as status:
        try:
            for update in get_graph().stream(graph_input, graph_config(), stream_mode="updates"):
                for node_name in update:
                    if node_name == "__interrupt__":
                        st.write("Paused — waiting for your quiz answers")
                        st.session_state.execution_log.append("interrupt (waiting for user)")
                    else:
                        st.write(NODE_LABELS.get(node_name, node_name))
                        st.session_state.execution_log.append(node_name)
            status.update(label="Done!", state="complete", expanded=False)
        except StudyAssistantError as error:
            log_error("Graph stopped with a known error")
            st.session_state.error = str(error)
            status.update(label="Something went wrong", state="error")
        except Exception:
            log_error("Graph stopped with an unexpected error")
            st.session_state.error = (
                "An unexpected error occurred. Check the terminal for details, then try again."
            )
            status.update(label="Something went wrong", state="error")
    sync_state_from_graph()
    persist_progress()
    st.rerun()
# Start a new study session for a topic, on a thread inside the signed-in user's namespace.
def start_session(topic: str) -> None:
    user = current_user()
    thread_id = new_thread_id(user.user_id)
    try:
        start_study_session(user.user_id, thread_id, topic)
    except StudyAssistantError as error:
        log_error("Could not record the new study session")
        st.session_state.error = str(error)
        return
    st.session_state.thread_id = thread_id
    st.session_state.execution_log = []
    st.session_state.transcript = None
    st.session_state.read_only = False
    log_step("UI", f"New study session for: {topic!r} (user {user.user_id})")
    log_step("GRAPH", "Starting workflow")
    run_graph(create_initial_state(topic, user.for_graph()))
# Save where this user's session got to, so it survives a restart and feeds future features.
def persist_progress() -> None:
    state = st.session_state.study_state
    if not state or not st.session_state.thread_id:
        return
    try:
        save_progress(
            current_user().user_id,
            st.session_state.thread_id,
            "finished" if session_status() == "finished" else "active",
            float(state.get("score", 0.0)) if state.get("attempts") else None,
            len(state.get("attempts", [])),
        )
        record_session_state(current_user().user_id, st.session_state.thread_id, state)
        learning_data(current_user(), refresh=True)
    except StudyAssistantError:
        log_error("Could not save the study session progress")
# Clear the workspace so the topic form appears. Nothing stored is deleted.
def new_session() -> None:
    for key in ["thread_id", "study_state", "next_nodes", "transcript", "read_only"]:
        st.session_state[key] = None
    st.session_state.next_nodes = ()
    st.session_state.execution_log = []
    st.session_state.error = None
    st.session_state[PENDING_NAV] = "Learn"
    log_step("UI", "Started a new, empty session")
# Open a stored session: restore its graph state so it can be continued, or fall back to the
# saved transcript when its checkpoint is gone (for example a session from before restarts persisted).
def open_session(record: Any) -> None:
    user = current_user()
    st.session_state.error = None
    with st.spinner("Loading that session..."):
        try:
            owned = get_session(user.user_id, record.id)
            if owned is None:
                raise UnauthorizedError("That study session does not belong to your account.")
            st.session_state.thread_id = owned.thread_id
            st.session_state.execution_log = []
            snapshot = get_graph().get_state(graph_config())
            if snapshot.values:
                st.session_state.study_state = dict(snapshot.values)
                st.session_state.next_nodes = tuple(snapshot.next)
                st.session_state.transcript = None
                st.session_state.read_only = False
            else:
                st.session_state.study_state = None
                st.session_state.next_nodes = ()
                st.session_state.transcript = load_messages(user.user_id, owned.id)
                st.session_state.read_only = True
        except StudyAssistantError as error:
            log_error("Could not open the stored session")
            st.session_state.error = str(error)
            st.rerun()
            return
    st.session_state[PENDING_NAV] = "Learn"
    log_step("UI", f"Opened session {record.id}")
    st.rerun()
# Rename a session from its menu.
def rename_current(record: Any, title: str) -> None:
    try:
        rename_session(current_user().user_id, record.id, title)
    except StudyAssistantError as error:
        st.session_state.error = str(error)
    st.rerun()
# Delete a session. If it was the open one, the workspace goes back to a new session.
def delete_current(record: Any) -> None:
    try:
        deleted = delete_session(current_user().user_id, record.id)
    except StudyAssistantError as error:
        st.session_state.error = str(error)
        st.rerun()
        return
    if deleted and record.thread_id == st.session_state.thread_id:
        new_session()
    if not deleted:
        st.session_state.error = "That session could not be found. It may already be deleted."
    log_step("UI", f"Deleted session {record.id}")
    st.rerun()
# Resume the paused graph with the student's quiz answers.
def submit_answers(answers: list[str]) -> None:
    log_step("GRAPH", "Resuming workflow with the student's answers")
    run_graph(Command(resume=answers))
# Clear the current study session from st.session_state.
def reset_session() -> None:
    for key in ["thread_id", "study_state", "next_nodes", "execution_log", "error"]:
        del st.session_state[key]
    init_session_state()
# Return where the workflow is: idle, quiz, finished or stopped.
def session_status() -> str:
    state = st.session_state.study_state
    next_nodes = st.session_state.next_nodes
    if not state:
        return "idle"
    if WAIT_FOR_ANSWERS in next_nodes:
        return "quiz"
    if next_nodes:
        return "stopped"
    if state.get("recommendation"):
        return "finished"
    return "stopped"
# Work out which study stages are done, active or still to come for the progress stepper.
def study_steps(state: dict[str, Any], status: str) -> list[tuple[str, str, str]]:
    stages = [
        ("1", "Understand", bool(state.get("topic_analysis"))),
        ("2", "Learn", bool(state.get("explanation"))),
        ("3", "Examples", bool(state.get("examples"))),
        ("4", "Quiz", bool(state.get("attempts")) and status != "quiz"),
        ("5", "Results", bool(state.get("attempts")) and status != "quiz"),
        ("6", "Next", bool(state.get("recommendation"))),
    ]
    active = next((index for index, (_, _, done) in enumerate(stages) if not done), None)
    return [
        (icon, label, "done" if done else ("active" if index == active else ""))
        for index, (icon, label, done) in enumerate(stages)
    ]
# Return the workflow node to highlight as current in the 3D map.
def current_workflow_node() -> str | None:
    status = session_status()
    if status == "quiz":
        return WAIT_FOR_ANSWERS
    if status == "finished":
        return END_NODE
    if status == "stopped" and st.session_state.next_nodes:
        return st.session_state.next_nodes[0]
    return None
# Draw the session history: a New session button, then this user's sessions grouped by date.
# Only one page of sessions is fetched, and a session's transcript is loaded only when opened.
def render_history(user: UserContext) -> None:
    if st.button("New session", key="new_session", type="primary", width="stretch"):
        new_session()
        st.rerun()
    try:
        limit = st.session_state.history_limit
        records = list_sessions(user.user_id, limit=limit)
        total = session_count(user.user_id)
    except StudyAssistantError as error:
        st.warning(f"Could not load your history. {error}")
        return
    st.markdown("###### History")
    if not records:
        st.html(history.empty_state())
        return
    for label, group in history.group_sessions(records):
        st.html(history.group_header(label))
        for record in group:
            render_history_item(record)
    if len(records) < total:
        if st.button(f"Show more ({total - len(records)} older)", key="history_more", width="stretch"):
            st.session_state.history_limit = limit + SIDEBAR_PAGE_SIZE
            st.rerun()
# One session in the history: open it, or use the menu to rename or delete it.
def render_history_item(record: Any) -> None:
    is_active = record.thread_id == st.session_state.thread_id
    with st.container(key=f"histitem_{record.id}"):
        open_column, menu_column = st.columns([6, 1], vertical_alignment="center")
        label = record.display_title
        if open_column.button(
            label,
            key=f"open_{record.id}",
            width="stretch",
            type="primary" if is_active else "secondary",
            help="Currently open" if is_active else "Open this session",
        ):
            open_session(record)
        with menu_column.popover("⋯", width="stretch"):
            st.caption(record.display_title)
            new_title = st.text_input(
                "Rename", value=record.display_title, key=f"rename_{record.id}", max_chars=60
            )
            if st.button("Save name", key=f"save_{record.id}", width="stretch"):
                rename_current(record, new_title)
            st.divider()
            confirm = st.checkbox("Yes, delete it", key=f"confirm_{record.id}")
            if st.button("Delete session", key=f"delete_{record.id}", width="stretch"):
                if not confirm:
                    st.warning("Tick the box first — this cannot be undone.")
                else:
                    delete_current(record)
        st.html(history.item_meta(record))
# Draw the sidebar with settings, API key mapping and session details.
def render_sidebar() -> None:
    with st.sidebar:
        user = current_user()
        render_user_panel(user)
        st.html(cards.sidebar_header(MODEL, PASSING_SCORE, MAX_RETRIES))
        render_history(user)
        data = learning_data(user)
        st.html(learning_summary_card(data.get("summary", {})))
        with st.expander("API key per node"):
            st.code("\n".join(f"{node:<22} {key}" for node, key in NODE_API_KEYS.items()))
            st.caption("wait_for_answers doesn't call Groq, so it needs no key.")
        state = st.session_state.study_state
        if not state:
            return
        st.subheader("Current session")
        title = state.get("topic_analysis", {}).get("clean_topic") or state.get("topic", "")
        rows = [
            ("Topic", title),
            ("Quiz attempts", str(len(state.get("attempts", [])))),
            ("Retries used", f"{state.get('retry_count', 0)}/{MAX_RETRIES}"),
            ("Status", session_status()),
        ]
        if state.get("attempts"):
            rows.insert(3, ("Latest score", f"{state.get('score', 0):.0f}%"))
        st.html(cards.sidebar_session(rows))
        with st.expander("Graph execution log"):
            st.code("\n".join(f"→ {step}" for step in st.session_state.execution_log) or "(empty)")
        with st.expander("Raw graph state"):
            st.json(state_for_display(state), expanded=False)
        if st.button("Reset session", width="stretch"):
            reset_session()
            st.rerun()
# Copy the state with correct answers hidden while a quiz is open.
def state_for_display(state: dict[str, Any]) -> dict[str, Any]:
    display = dict(state)
    if session_status() == "quiz":
        display["quiz"] = [
            {"question": q["question"], "options": q["options"], "correct_answer": "hidden"}
            for q in state.get("quiz", [])
        ]
    return display
# Draw the hero: animated title on the left and the 3D knowledge crystal on the right.
def render_hero() -> None:
    text_col, scene_col = st.columns([3, 2], vertical_alignment="center")
    with text_col:
        st.html(cards.hero_intro())
    with scene_col:
        embed(hero_scene(), 250)
# Draw the explanation tiles, marked as simpler for re-explanations.
def render_explanation(explanation: dict[str, Any], simpler: bool = False) -> None:
    st.html(cards.explanation_cards(explanation, simpler))
# Draw the examples as 3D flip cards.
def render_examples(examples: list[dict[str, Any]]) -> None:
    st.header("Examples")
    st.html(cards.example_cards(examples))
# Draw the quiz form with animated question cards and submit the answers when complete.
def render_quiz_form(state: dict[str, Any]) -> None:
    quiz = state["quiz"]
    attempt_number = len(state.get("attempts", [])) + 1
    st.header("Quiz" if attempt_number == 1 else f"Quiz — Attempt {attempt_number}")
    st.html(cards.quiz_intro(len(quiz), PASSING_SCORE, attempt_number > 1))
    form_id = f"{st.session_state.thread_id}_{attempt_number}"
    with st.form(f"quiz_form_{form_id}"):
        answers = []
        for index, question in enumerate(quiz):
            with st.container(key=f"qcard_{form_id}_{index}"):
                answer = st.radio(
                    f"**Q{index + 1}. {question['question']}**",
                    options=question["options"],
                    index=None,
                    key=f"answer_{form_id}_{index}",
                )
            answers.append(answer)
        submitted = st.form_submit_button("Submit Quiz", type="primary", width="stretch")
    if submitted:
        if any(answer is None for answer in answers):
            st.warning("Please answer every question before submitting.")
        else:
            submit_answers(answers)
# Draw one attempt: 3D score scene for the latest attempt, summary cards and per-question results.
def render_attempt_result(attempt: dict[str, Any], is_latest: bool) -> None:
    number = attempt["attempt_number"]
    st.header(f"Quiz Results — Attempt {number}")
    if is_latest:
        embed(score_scene(attempt["score"], attempt["passed"]), 240)
        celebration_key = f"{st.session_state.thread_id}_{number}"
        if attempt["passed"] and celebration_key not in st.session_state.celebrated:
            st.session_state.celebrated.add(celebration_key)
            st.balloons()
    st.html(cards.result_summary(attempt, MAX_RETRIES))
    with st.expander("See every question with explanations", expanded=is_latest):
        st.html(cards.question_results(attempt["results"]))
# Draw the next-topic recommendation with the 3D rocket and its start button.
def render_recommendation(state: dict[str, Any]) -> None:
    recommendation = state["recommendation"]
    passed = state.get("score", 0) >= PASSING_SCORE
    st.header("What's Next?")
    scene_col, card_col = st.columns([2, 3], vertical_alignment="center")
    with scene_col:
        embed(rocket_scene(), 260)
    with card_col:
        st.html(cards.recommendation_card(recommendation, passed))
    if st.button(f"Start learning: {recommendation['next_topic']}", type="primary", width="stretch"):
        start_session(recommendation["next_topic"])
# Draw the whole study session from the saved state.
def render_session() -> None:
    state = st.session_state.study_state
    status = session_status()
    st.html(cards.stepper(study_steps(state, status)))
    analysis = state.get("topic_analysis")
    if analysis:
        st.html(cards.topic_card(analysis))
    if state.get("explanation"):
        st.header("Explanation")
        render_explanation(state["explanation"])
    if state.get("examples"):
        render_examples(state["examples"])
    attempts = state.get("attempts", [])
    re_explanations = state.get("re_explanations", [])
    for index, attempt in enumerate(attempts):
        render_attempt_result(attempt, is_latest=index == len(attempts) - 1)
        if index < len(re_explanations):
            st.header("Let's Try a Simpler Explanation")
            render_explanation(re_explanations[index], simpler=True)
    if status == "quiz":
        render_quiz_form(state)
    elif status == "finished":
        render_recommendation(state)
    elif status == "stopped":
        next_nodes = st.session_state.next_nodes
        if next_nodes:
            st.warning(f"The workflow stopped before finishing. Next step: `{next_nodes[0]}`")
            if st.button("Retry this step", type="primary"):
                log_step("GRAPH", f"Retrying from checkpoint at '{next_nodes[0]}'")
                run_graph(None)
        else:
            st.error("The study session is in an unexpected state. Please reset the session.")
# Draw a stored session that can no longer be continued, from its saved transcript.
def render_transcript() -> None:
    messages = st.session_state.transcript
    st.header("Saved session")
    if not messages:
        st.info("This session was saved before it produced anything. Start a new one on this topic.")
    else:
        st.caption(
            "This session finished in an earlier run of the app, so it is shown from its saved "
            "transcript and cannot be continued."
        )
        st.html(cards.transcript(messages))
    topic = messages[0].content if messages else ""
    if topic and st.button(f"Study this topic again: {topic[:60]}", type="primary"):
        start_session(topic)
# Draw the workflow as an interactive 3D map, text, Mermaid source and an optional image.
def render_graph_section() -> None:
    with st.expander("View LangGraph Workflow"):
        map_tab, text_tab, mermaid_tab = st.tabs(["3D map", "Text", "Mermaid"])
        with map_tab:
            visited = {step for step in st.session_state.execution_log if step in NODE_LABELS}
            embed(workflow_scene(visited, current_workflow_node()), 400)
            st.caption("Green nodes already ran in this session, the glowing amber node is where the graph is now.")
        with text_tab:
            st.code(TEXT_DIAGRAM, language=None)
        with mermaid_tab:
            graph = get_graph()
            st.markdown("Generated by `graph.get_graph().draw_mermaid()`")
            st.code(get_mermaid_diagram(graph), language=None)
            st.caption("Tip: paste this into https://mermaid.live to see it drawn.")
            if st.button("Render graph image"):
                try:
                    st.session_state.graph_png = graph.get_graph().draw_mermaid_png()
                except Exception:
                    log_error("Could not render graph image")
                    st.warning(
                        "Could not render the image (it needs internet access to mermaid.ink). "
                        "The 3D map and Mermaid source show the same graph."
                    )
            if st.session_state.graph_png:
                st.image(st.session_state.graph_png)
# Build the page: styles, sidebar, hero, API key check, topic form, session and graph view.
# The sections of the app. Learn is the original tutor flow, untouched; the rest are the
# platform views built on the same mastery engine.
NAV_KEY = "section_nav"
PENDING_NAV = "pending_section"
SECTIONS = [
    "Dashboard",
    "Learn",
    "Knowledge",
    "Coding Practice",
    "Today's Review",
    "Study Plan",
    "Analytics",
]
# Ask for a different section on the next run.
#
# The request is parked rather than written to the nav widget directly: these calls come from
# buttons inside a section, which render after the nav, and Streamlit refuses to let a widget's
# value be changed once it exists in the same run.
def go_to(section: str) -> None:
    st.session_state[PENDING_NAV] = section
    st.rerun()
# The section selector: a centred bar across the top of the page rather than a sidebar list.
def render_nav() -> None:
    pending = st.session_state.pop(PENDING_NAV, None)
    if pending in SECTIONS:
        st.session_state.section = pending
        # Dropping the widget's stored value before it is created lets `default` take effect.
        st.session_state.pop(NAV_KEY, None)
    with st.container(key="sa_nav"):
        chosen = st.segmented_control(
            "Go to",
            SECTIONS,
            default=st.session_state.section,
            key=NAV_KEY,
            label_visibility="collapsed",
        )
    # Clicking the active segment deselects it; stay where we are rather than blanking the page.
    if chosen:
        st.session_state.section = chosen
# Start learning a topic from anywhere in the app.
def learn_topic(topic: str) -> None:
    st.session_state[PENDING_NAV] = "Learn"
    start_session(topic)
# Practise a weak concept: open coding practice with the concept already chosen.
def practise_concept(state: Any) -> None:
    st.session_state.coding_prefill = state.concept_name
    go_to("Coding Practice")
# Run a quiz built from one of the user's documents through the normal quiz machinery.
def start_document_quiz(document: Any, questions: list[dict[str, Any]], difficulty: str) -> None:
    user = current_user()
    thread_id = new_thread_id(user.user_id)
    topic = f"{document.filename}"
    try:
        start_study_session(user.user_id, thread_id, topic)
    except StudyAssistantError as error:
        st.session_state.error = str(error)
        return
    st.session_state.thread_id = thread_id
    st.session_state.transcript = None
    st.session_state.read_only = False
    st.session_state.execution_log = []
    st.session_state.doc_quiz = {
        "document_id": document.id,
        "filename": document.filename,
        "questions": questions,
        "difficulty": difficulty,
    }
    st.session_state[PENDING_NAV] = "Learn"
    log_step("UI", f"Document quiz from {document.filename!r} ({len(questions)} questions)")
    st.rerun()
# A quiz built from one of the user's documents.
#
# It does not go through the LangGraph tutor, which is topic-driven, but it grades with the same
# helper and records the result through the same mastery service, so a document quiz moves the
# same concept scores a topic quiz does.
def render_document_quiz() -> None:
    quiz = st.session_state.doc_quiz
    user = current_user()
    st.header(f"Quiz — {quiz['filename']}")
    st.caption(f"{len(quiz['questions'])} questions · {quiz['difficulty']} · from your document")
    graded = quiz.get("graded")
    if graded is None:
        with st.form("doc_quiz_form"):
            answers = []
            for index, question in enumerate(quiz["questions"]):
                with st.container(key=f"docq_{index}"):
                    answers.append(
                        st.radio(
                            f"**Q{index + 1}. {question['question']}**",
                            options=question["options"], index=None, key=f"docans_{index}",
                        )
                    )
            submitted = st.form_submit_button("Submit Quiz", type="primary", width="stretch")
        if submitted:
            if any(answer is None for answer in answers):
                st.warning("Please answer every question before submitting.")
            else:
                _grade_document_quiz(user, quiz, answers)
    else:
        _render_document_results(graded)
    if st.button("Back to my documents", width="stretch"):
        st.session_state.doc_quiz = None
        go_to("Learn")
# Grade a document quiz and push the result into the mastery engine.
def _grade_document_quiz(user: UserContext, quiz: dict[str, Any], answers: list[str]) -> None:
    results, correct_count, score = grade_quiz(quiz["questions"], answers)
    document = get_document(user.user_id, quiz["document_id"])
    concept_slugs = document.concepts if document else []
    passed = score >= PASSING_SCORE
    categories, dominant = classify_attempt(results)
    if concept_slugs:
        attempts = [
            Attempt(
                concept_slug=slug, correct=passed, score=score / 100.0,
                difficulty=quiz["difficulty"], activity=ACTIVITY_DOCUMENT,
                concept_name=slug.split("::")[-1].replace("_", " ").title(),
                subject=slug.split("::")[0].replace("_", " ").title(),
            )
            for slug in concept_slugs
        ]
        updated = record_attempts(user.user_id, attempts, source="document")
        if dominant:
            for slug in concept_slugs:
                record_mistake(user.user_id, slug, dominant, "", source="document")
    else:
        updated = {}
    quiz["graded"] = {
        "results": results, "score": score, "correct": correct_count,
        "total": len(results), "passed": passed,
        "mastery": {
            slug: {"name": state.concept_name, "score": state.mastery_score, "status": state.learning_status}
            for slug, state in updated.items()
        },
    }
    st.session_state.doc_quiz = quiz
    log_step("UI", f"Document quiz graded: {score:.0f}% over {len(concept_slugs)} concept(s)")
    st.rerun()
# The results of a document quiz, with what it did to mastery.
def _render_document_results(graded: dict[str, Any]) -> None:
    st.html(cards.result_summary(
        {
            "attempt_number": 1, "score": graded["score"], "correct_count": graded["correct"],
            "total_questions": graded["total"], "passed": graded["passed"],
            "overall_feedback": "Graded from your own document.",
            "strengths": [], "weak_concepts": [], "study_tip": "",
        },
        MAX_RETRIES,
    ))
    if graded["mastery"]:
        st.subheader("Mastery updated")
        for data in graded["mastery"].values():
            st.html(cards.mastery_bar(data["name"], data["score"], data["status"]))
    with st.expander("See every question", expanded=True):
        st.html(cards.question_results(graded["results"]))
# The Learn section: the original topic form, session view and graph view.
def render_learn() -> None:
    render_hero()
    missing_keys = missing_api_keys()
    if missing_keys:
        st.error(
            f"**Missing Groq API keys:** {', '.join(missing_keys)}  \n"
            "Copy `.env.example` to `.env`, paste your Groq API keys, then restart the app."
        )
        render_graph_section()
        st.stop()
    if st.session_state.get("doc_quiz"):
        render_document_quiz()
        return
    documents_ui.render_attach(current_user(), on_quiz=start_document_quiz)
    with st.form("topic_form"):
        topic = st.text_input("What do you want to learn?", placeholder="What is an embedding?")
        start_clicked = st.form_submit_button("Start Learning", type="primary", width="stretch")
    if start_clicked:
        if not topic.strip():
            st.warning("Please enter a topic first.")
        elif len(topic) > MAX_TOPIC_LENGTH:
            st.warning(f"Please keep the topic under {MAX_TOPIC_LENGTH} characters.")
        else:
            start_session(topic.strip())
    if not st.session_state.study_state:
        st.caption("Need an idea? Try one of these:")
        for column, suggestion in zip(st.columns(len(SUGGESTED_TOPICS)), SUGGESTED_TOPICS):
            if column.button(suggestion, key=f"suggest_{suggestion}", width="stretch"):
                start_session(suggestion)
    if st.session_state.error:
        st.error(st.session_state.error)
    if st.session_state.transcript is not None:
        render_transcript()
    elif st.session_state.study_state:
        render_session()
    st.divider()
    render_graph_section()
# Build the page: styles, login gate, sidebar, then the chosen section.
def main() -> None:
    inject_styles()
    require_login()
    init_session_state()
    user = current_user()
    render_nav()
    render_sidebar()
    section = st.session_state.section
    if section == "Dashboard":
        knowledge_ui.render_dashboard(
            user,
            on_review=lambda: go_to("Today's Review"),
            on_practice=practise_concept,
            on_learn=learn_topic,
            on_plan=lambda: go_to("Study Plan"),
        )
    elif section == "Knowledge":
        knowledge_ui.render_knowledge(user, on_practice=practise_concept)
    elif section == "Coding Practice":
        coding_ui.render(user)
    elif section == "Today's Review":
        study_ui.render_review(user)
    elif section == "Study Plan":
        study_ui.render_plan(user, on_learn=learn_topic)
    elif section == "Analytics":
        knowledge_ui.render_analytics(user)
    else:
        render_learn()
main()
