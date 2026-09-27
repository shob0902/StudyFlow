# The application shell: grouped sidebar navigation, the top header with search, and the search
# results. Section names are the app's internal keys; the labels are what the student sees.
from typing import Any, Callable
import streamlit as st
from ui import cards
from utils.helpers import StudyAssistantError
SEARCH_KEY = "sa_search"
SEARCH_CLEAR = "sa_search_clear"
# (group, [(section key, label, Material icon)]).
NAV_GROUPS = [
    ("Main", [
        ("Dashboard", "Dashboard", ":material/space_dashboard:"),
        ("Learn", "AI Tutor", ":material/auto_awesome:"),
        ("Today's Review", "Review", ":material/style:"),
        ("Coding Practice", "Coding Practice", ":material/code:"),
    ]),
    ("Study", [
        ("Documents", "Documents", ":material/description:"),
        ("Study Plan", "Study Planner", ":material/calendar_month:"),
        ("Knowledge", "Knowledge Map", ":material/hub:"),
        ("Analytics", "Progress", ":material/insights:"),
    ]),
]
# The title and subtitle the header shows for each section.
PAGE_META = {
    "Dashboard": ("Dashboard", "Your learning at a glance"),
    "Learn": ("AI Tutor", "Explanations, examples and an adaptive quiz on any topic"),
    "Today's Review": ("Today's Review", "Spaced repetition keeps what you've learned"),
    "Coding Practice": ("Coding Practice", "Generated problems, run and graded in a sandbox"),
    "Documents": ("Documents", "Ask, summarise and get quizzed on your own material"),
    "Study Plan": ("Study Planner", "A week-by-week plan built from your mastery"),
    "Knowledge": ("Knowledge Map", "Mastery for every concept you've practised"),
    "Analytics": ("Progress", "How your mastery and practice are trending"),
}
# Every section, in navigation order.
SECTIONS = [key for _, items in NAV_GROUPS for key, _, _ in items]
# The widget key of a section's navigation button.
def nav_key(section: str) -> str:
    return "nav_" + "".join(ch if ch.isalnum() else "_" for ch in section.lower())
# The sidebar navigation. Returns the section that was clicked on this run, if any.
def render_nav(current: str) -> str | None:
    st.html(cards.brand())
    chosen = None
    for group, items in NAV_GROUPS:
        st.html(f"<div class='sa-nav-label'>{cards.esc(group)}</div>")
        with st.container(key=f"sa_navgroup_{group.lower()}", gap="small"):
            for section, label, icon in items:
                active = section == current
                if st.button(
                    label, key=nav_key(section), icon=icon, width="stretch",
                    type="primary" if active else "tertiary",
                    help=None if active else f"Go to {label}",
                ):
                    chosen = section
    return chosen
# The top header: page title on the left, search in the middle, avatar on the right.
# Returns what is typed in the search box.
def render_header(section: str, name: str, picture: str = "") -> str:
    if st.session_state.pop(SEARCH_CLEAR, False):
        st.session_state[SEARCH_KEY] = ""
    title, subtitle = PAGE_META.get(section, (section, ""))
    with st.container(key="sa_header"):
        left, middle, right = st.columns([5, 5, 1], vertical_alignment="center")
        with left:
            st.html(cards.page_title(title, subtitle))
        with middle:
            query = st.text_input(
                "Search", key=SEARCH_KEY, placeholder="Search sessions, documents, topics...",
                icon=":material/search:", label_visibility="collapsed",
            )
        with right:
            st.html(f"<div class='sa-head-avatar'>{cards.avatar(name, picture)}</div>")
    return (query or "").strip()
# Search what the student already has, and offer to start learning the query itself.
def render_search_results(
    query: str,
    sessions: Callable[[], list[Any]],
    documents: Callable[[], list[Any]],
    concepts: Callable[[], list[Any]],
    on_open_session: Callable[[Any], None],
    on_open_document: Callable[[Any], None],
    on_learn: Callable[[str], None],
) -> None:
    needle = query.lower()
    try:
        found_sessions = [r for r in sessions() if needle in r.display_title.lower()][:5]
        found_documents = [d for d in documents() if needle in d.filename.lower()][:5]
        found_concepts = [c for c in concepts() if needle in c.concept_name.lower()][:5]
    except StudyAssistantError as error:
        st.warning(f"Search is unavailable right now. {error}")
        return
    with st.container(key="sa_search_results"):
        st.html(cards.section_head(f"Results for “{query}”"))
        if st.button(f"Learn “{query[:60]}” with the AI tutor", key="search_learn",
                     icon=":material/auto_awesome:", type="primary", width="stretch"):
            _clear_search()
            on_learn(query)
        for record in found_sessions:
            if st.button(record.display_title, key=f"search_session_{record.id}",
                         icon=":material/history:", width="stretch", help="Open this study session"):
                _clear_search()
                on_open_session(record)
        for document in found_documents:
            if st.button(document.filename, key=f"search_doc_{document.id}",
                         icon=":material/description:", width="stretch", help="Open this document"):
                _clear_search()
                on_open_document(document)
        for state in found_concepts:
            if st.button(f"{state.concept_name} · {state.mastery_score:.0f}% mastery",
                         key=f"search_concept_{state.concept_slug}", icon=":material/hub:",
                         width="stretch", help="Study this concept with the AI tutor"):
                _clear_search()
                on_learn(state.concept_name)
        if not (found_sessions or found_documents or found_concepts):
            st.caption("Nothing in your sessions, documents or concepts matches yet.")
# Empty the search box on the next run (a widget's value cannot change once it is drawn).
def _clear_search() -> None:
    st.session_state[SEARCH_CLEAR] = True
