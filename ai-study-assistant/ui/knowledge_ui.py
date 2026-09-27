# Dashboard, Knowledge and Analytics: the three views onto the mastery engine.
import json
from datetime import datetime, timedelta, timezone
from typing import Any
import pandas as pd
import streamlit as st
from db import learning_service, plan_service, review_service
from db.service import list_sessions
from coding.grading import coding_stats
from learning.mastery import ACTION_LABELS, next_action
from learning.misconceptions import CATEGORY_LABELS, CODE_FAILURE_LABELS
from rag import store
from ui import cards, history
from utils.helpers import StudyAssistantError
CONTINUE_LIMIT = 4
# The personalised dashboard: where the student stands and what to do about it.
def render_dashboard(
    user: Any, on_review: Any = None, on_practice: Any = None, on_learn: Any = None,
    on_plan: Any = None, on_tutor: Any = None, on_documents: Any = None, on_open_session: Any = None,
) -> None:
    try:
        summary = learning_service.dashboard_summary(user.user_id)
        code = coding_stats(user.user_id)
        recent = list_sessions(user.user_id, limit=CONTINUE_LIMIT)
        events = learning_service.recent_events(user.user_id, 60)
        documents = store.list_documents(user.user_id, limit=3)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    _render_hero(user, summary, on_tutor, on_review, on_documents)
    st.html(cards.stat_cards(_stat_items(summary, code)))
    main, side = st.columns([1.75, 1], gap="large")
    with main:
        _render_continue(recent, on_open_session, on_tutor)
        _render_plan_block(user, on_learn, on_plan)
        _render_weakest(summary, on_practice)
    with side:
        _render_ai_card(on_tutor, on_documents)
        _render_due(user, on_review)
        _render_recent_documents(documents, on_documents)
        _render_activity(events)
# The greeting, a line that fits where the student is, and the main calls to action.
def _render_hero(user: Any, summary: dict[str, Any], on_tutor: Any, on_review: Any, on_documents: Any) -> None:
    due, streak = summary["reviews_due"], summary["streak"]
    if due:
        message = f"You have {due} concept{'s' if due != 1 else ''} due for review today — a few minutes keeps them fresh."
    elif streak:
        message = f"You're on a {streak}-day streak. Keep your momentum going — you are making progress."
    elif summary["concepts"]:
        message = "Keep your momentum going — every quiz sharpens your mastery map."
    else:
        message = "Pick any topic and StudyFlow will explain it, quiz you and track what you've mastered."
    with st.container(key="sa_hero"):
        st.html(cards.dashboard_hello(user.first_name, message))
        first, second = st.columns(2)
        if on_tutor and first.button("Start studying", key="hero_start", type="primary",
                                     icon=":material/play_arrow:", width="stretch"):
            on_tutor()
        if due and on_review:
            if second.button("Review now", key="hero_review", icon=":material/style:", width="stretch"):
                on_review()
        elif on_documents and second.button("Ask AI about my notes", key="hero_docs",
                                             icon=":material/auto_awesome:", width="stretch"):
            on_documents()
# The headline numbers, each with a short explanation and, where it means something, a bar.
def _stat_items(summary: dict[str, Any], code: dict[str, Any]) -> list[tuple]:
    mastery, quiz = summary["overall_mastery"], summary["quiz_accuracy"]
    streak = summary["streak"]
    return [
        ("target", "", "Overall mastery", f"{mastery:.0f}%" if mastery is not None else "—",
         f"{summary['concepts']} concept{'s' if summary['concepts'] != 1 else ''} tracked", mastery),
        ("check", "blue", "Quiz accuracy", f"{quiz:.0f}%" if quiz is not None else "—",
         f"{summary['quiz_answered']} answers graded", quiz),
        ("repeat", "green", "Reviews due", summary["reviews_due"],
         f"{summary['reviews_done']} reviews done so far", None),
        ("code", "blue", "Coding solved", code["solved"],
         f"{code['submissions']} submission{'s' if code['submissions'] != 1 else ''}", None),
        ("flame", "warm", "Study streak", f"{streak} day{'s' if streak != 1 else ''}",
         "Keep going!" if streak else "Study today to start one", None),
    ]
# Recent study sessions as cards, each with a Continue button.
def _render_continue(records: list[Any], on_open_session: Any, on_tutor: Any) -> None:
    with st.container(key="sa_panel_continue"):
        st.html(cards.section_head("Continue learning", "Your latest sessions"))
        if not records:
            st.html(cards.empty_state(
                "book", "No study sessions yet",
                "Start your first topic and StudyFlow will keep your place here.",
            ))
            if on_tutor and st.button("Start a topic", key="continue_empty", type="primary", width="stretch"):
                on_tutor()
            return
        for row in range(0, len(records), 2):
            columns = st.columns(2)
            for column, record in zip(columns, records[row:row + 2]):
                with column, st.container(key=f"sa_cont_{record.id}"):
                    st.html(cards.continue_card(
                        record.display_title, record.status, record.score,
                        history.relative_time(record.updated_at),
                    ))
                    if on_open_session and st.button(
                        "Continue", key=f"continue_{record.id}", icon=":material/arrow_forward:",
                        width="stretch",
                    ):
                        on_open_session(record)
# The concepts that need the most work.
def _render_weakest(summary: dict[str, Any], on_practice: Any) -> None:
    weakest = summary.get("weakest") or []
    with st.container(key="sa_panel_weakest"):
        st.html(cards.section_head("Weakest concepts", "Lowest mastery first"))
        if not weakest:
            st.html(cards.empty_state(
                "target", "Nothing looks weak yet",
                "As you take quizzes and solve problems, the concepts that need work show up here.",
            ))
            return
        st.html("".join(
            cards.mastery_bar(state.concept_name, state.mastery_score, state.learning_status)
            for state in weakest[:5]
        ))
        if on_practice and st.button(
            f"Practise {weakest[0].concept_name}", type="primary", width="stretch"
        ):
            on_practice(weakest[0])
# The AI assistant card: one tap to the tutor, the document tutor, or a quiz.
def _render_ai_card(on_tutor: Any, on_documents: Any) -> None:
    with st.container(key="sa_ai_card"):
        st.html(cards.ai_card_text())
        if on_tutor and st.button("Ask a question", key="ai_ask", icon=":material/chat:", width="stretch"):
            on_tutor()
        if on_documents and st.button("Summarize my notes", key="ai_summary",
                                      icon=":material/summarize:", width="stretch"):
            on_documents()
        if on_tutor and st.button("Generate a quiz", key="ai_quiz", icon=":material/quiz:", width="stretch"):
            on_tutor()
# What is due for spaced-repetition review.
def _render_due(user: Any, on_review: Any) -> None:
    with st.container(key="sa_panel_due"):
        st.html(cards.section_head("Due for review"))
        due = review_service.due_today(user.user_id, limit=5)
        if not due:
            st.caption("Nothing due right now. Concepts come back here when they start to fade.")
            return
        st.html("".join(
            cards.due_row(
                card["mark"], card["concept_name"],
                f"{card['mastery']:.0f}% · {'overdue' if card['overdue_days'] > 0 else 'due'}",
            )
            for card in due
        ))
        if on_review and st.button("Start today's review", type="primary", width="stretch"):
            on_review()
# The most recently uploaded study material.
def _render_recent_documents(documents: list[Any], on_documents: Any) -> None:
    with st.container(key="sa_panel_docs"):
        st.html(cards.section_head("Recent study material"))
        if not documents:
            st.caption("Upload notes, slides or a chapter to ask questions and get quizzed on them.")
        rows = []
        for document in documents:
            topics = ", ".join(slug.split("::")[-1].replace("_", " ") for slug in document.concepts[:4])
            pages = f"{document.pages} pages · " if document.pages else ""
            rows.append(cards.note_row(
                document.filename,
                topics or f"{pages}{document.chunk_count} passages",
                f"Added {history.relative_time(document.created_at)}",
            ))
        if rows:
            st.html("".join(rows))
        if on_documents and st.button("Open documents", key="dash_docs", width="stretch"):
            on_documents()
# Recent activity as a small timeline, grouped by day.
def _render_activity(events: list[dict[str, Any]]) -> None:
    with st.container(key="sa_panel_activity"):
        st.html(cards.section_head("Recent activity"))
        days = activity_days(events)
        if not days:
            st.caption("Your quizzes, reviews and uploads will appear here.")
            return
        st.html(cards.timeline(days))
# Turn raw learning events into timeline rows: one row per thing done, newest first.
# A quiz records one event per concept it touched; those collapse into a single row.
def activity_days(events: list[dict[str, Any]], limit: int = 7) -> list[tuple[str, list[tuple[str, str, str, str]]]]:
    rows: list[tuple[str, tuple[str, str, str, str]]] = []
    seen: set[tuple[str, str, str]] = set()
    for event in events:
        day = history.group_for(event.get("created_at", ""))
        described = _describe_event(event)
        if described is None:
            continue
        key = (day, event.get("kind", ""), described[2])
        if key in seen:
            continue
        seen.add(key)
        rows.append((day, described))
        if len(rows) >= limit:
            break
    grouped: dict[str, list[tuple[str, str, str, str]]] = {}
    for day, row in rows:
        grouped.setdefault(day, []).append(row)
    return list(grouped.items())
ACTIVITY_NAMES = {"quiz": "Quiz", "coding": "Coding", "review": "Review", "document": "Document quiz"}
# One event as (icon, tone, text, detail), or None for events not worth showing.
def _describe_event(event: dict[str, Any]) -> tuple[str, str, str, str] | None:
    kind = event.get("kind", "")
    try:
        detail = json.loads(event.get("detail") or "{}")
    except (TypeError, ValueError):
        detail = {}
    concept = str(event.get("concept_slug") or "").split("::")[-1].replace("_", " ").title()
    when = history.relative_time(event.get("created_at", ""))
    if kind == "attempt":
        activity = ACTIVITY_NAMES.get(event.get("activity", ""), "Practice")
        correct = event.get("correct")
        tone = "good" if correct else ("bad" if correct is not None else "")
        return ("check" if correct else "target", tone, f"{activity}: {concept}", when)
    if kind == "document_uploaded":
        return ("upload", "blue", f"Added {detail.get('filename', 'a document')}", when)
    if kind == "plan_created":
        return ("calendar", "", f"Created a plan for {detail.get('subject', 'a subject')}", when)
    if kind == "plan_item_done":
        return ("check", "good", f"Finished a plan item: {concept}", when)
    if kind == "plan_updated":
        return ("calendar", "", "Updated the study plan", when)
    return None
# What the study plan says to do now: which week it is, the topic to be on, and what follows.
def _render_plan_block(user: Any, on_learn: Any = None, on_plan: Any = None) -> None:
    try:
        focus = plan_service.plan_focus(user.user_id)
    except StudyAssistantError as error:
        st.warning(f"Could not read your study plan. {error}")
        return
    with st.container(key="sa_plan_card"):
        _render_plan_focus(focus, on_learn, on_plan)
# The plan block's contents.
def _render_plan_focus(focus: dict[str, Any], on_learn: Any = None, on_plan: Any = None) -> None:
    if not focus:
        st.html(cards.section_head("Study plan"))
        st.caption("No plan yet. Set a subject and a date and the planner builds one around what you already know.")
        if on_plan and st.button("Make a study plan", width="stretch"):
            on_plan()
        return
    st.html(cards.section_head(f"Your plan: {focus['subject']}"))
    deadline = f" · until {focus['target_date']}" if focus["target_date"] else ""
    st.caption(
        f"Week {focus['week']} of {focus['weeks']}{deadline} · "
        f"{focus['done']} of {focus['total']} items done"
        + (" · you are behind the plan" if focus["behind"] else "")
    )
    if focus["total"]:
        st.progress(focus["done"] / focus["total"])
    current = focus["current"]
    if current is None:
        st.success("Everything in this plan is done. Time for a new one.")
        if on_plan and st.button("Plan what's next", width="stretch"):
            on_plan()
        return
    st.html(
        cards.metrics(
            [
                ("Study now", current.concept_name, f"{current.activity} · {current.minutes} min"),
                (
                    "Mastery",
                    f"{current.mastery_score:.0f}%" if current.mastery_score else "new",
                    "week " + str(current.week),
                ),
                ("This week", len(focus["this_week"]) or "clear", "items left"),
            ]
        )
    )
    columns = st.columns(2)
    if on_learn and columns[0].button(
        f"Learn {current.concept_name}", type="primary", width="stretch"
    ):
        on_learn(current.concept_name)
    if on_plan and columns[1].button("Open the full plan", width="stretch"):
        on_plan()
    if focus["upcoming"]:
        st.caption(
            "Coming up: "
            + " · ".join(f"{item.concept_name} ({item.activity})" for item in focus["upcoming"])
        )
# The knowledge dashboard: mastery by subject, with a drill-down per concept.
def render_knowledge(user: Any, on_practice: Any = None) -> None:
    try:
        grouped = learning_service.mastery_by_subject(user.user_id)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    if not grouped:
        st.html(cards.empty_state(
            "layers", "Your knowledge map is empty",
            "Study something and this map of what you know starts building itself.",
        ))
        return
    with st.container(key="sa_panel_subjects"):
        st.html(cards.section_head("Mastery by subject", f"{len(grouped)} subject{'s' if len(grouped) != 1 else ''}"))
        st.html(_subject_bars(grouped))
    for subject, states in grouped.items():
        with st.expander(f"{subject} — {len(states)} concept{'s' if len(states) != 1 else ''}"):
            for state in states:
                _render_concept(user, state, on_practice)
# One mastery bar per subject, averaged over its concepts.
def _subject_bars(grouped: dict[str, list[Any]]) -> str:
    return "".join(
        cards.mastery_bar(subject, sum(state.mastery_score for state in states) / len(states))
        for subject, states in grouped.items()
    )
# One concept in the drill-down: score, status, mistakes and what to do next.
def _render_concept(user: Any, state: Any, on_practice: Any = None) -> None:
    with st.container(key=f"concept_{state.concept_slug}"):
        st.html(
            cards.mastery_bar(state.concept_name, state.mastery_score, state.learning_status)
            + f"<div style='margin:-.2rem 0 .4rem 9.6rem'>{cards.status_pill(state.learning_status)}"
            f"<span style='font-size:.78rem;opacity:.7;margin-left:.5rem'>"
            f"{state.attempts} attempt{'s' if state.attempts != 1 else ''} · "
            f"{state.correct_attempts} correct · confidence {state.confidence:.0%} · "
            f"next at {state.current_difficulty}</span></div>"
        )
        mistakes = learning_service.mistakes_for_concept(user.user_id, state.concept_slug, 3)
        if mistakes:
            st.caption("Common mistakes: " + "; ".join(mistakes))
        action = next_action(state)
        st.caption(f"Recommended: {ACTION_LABELS.get(action, action)}")
        if on_practice and st.button(
            "Practise this", key=f"practise_{state.concept_slug}", width="stretch"
        ):
            on_practice(state)
# Analytics: how the numbers have moved and where the mistakes cluster.
def render_analytics(user: Any) -> None:
    try:
        summary = learning_service.dashboard_summary(user.user_id)
        events = learning_service.recent_mistakes(user.user_id, 30)
        grouped = learning_service.mastery_by_subject(user.user_id)
        code = coding_stats(user.user_id)
        reviews = review_service.review_stats(user.user_id)
        activity = learning_service.recent_events(user.user_id, 500)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    if not summary["concepts"]:
        st.html(cards.empty_state(
            "chart", "No progress to show yet",
            "Analytics appear once you have practised something: take a quiz, review a concept or solve a problem.",
        ))
        return
    streak = summary["streak"]
    st.html(
        cards.stat_cards(
            [
                ("layers", "", "Concepts tracked", summary["concepts"], f"{len(grouped)} subjects", None),
                ("target", "blue", "Total attempts", summary["attempts"], f"{summary['correct']} correct", None),
                ("code", "blue", "Coding submissions", code["submissions"], f"{code['accepted']} accepted", None),
                ("repeat", "green", "Reviews done", summary["reviews_done"], f"{reviews['due_this_week']} due this week", None),
                ("flame", "warm", "Study streak", f"{streak} day{'s' if streak != 1 else ''}", "consecutive days", None),
            ]
        )
    )
    left, right = st.columns([1.4, 1], gap="large")
    with left, st.container(key="sa_panel_activity_chart"):
        st.html(cards.section_head("Study activity", "Last 14 days"))
        st.bar_chart(daily_activity(activity), color="#6D4AFF", height=240, x_label="", y_label="Actions")
    with right, st.container(key="sa_panel_mastery"):
        st.html(cards.section_head("Mastery by subject"))
        st.html(_subject_bars(grouped))
        by_status = summary.get("by_status", {})
        if by_status:
            st.html(cards.section_head("By status"))
            st.html(
                cards.metrics(
                    [(status.title(), count, "") for status, count in sorted(by_status.items())]
                )
            )
    with st.container(key="sa_panel_mistakes"):
        st.html(cards.section_head("Where you go wrong", "Last 30 mistakes"))
        if not events:
            st.caption("No mistakes recorded yet.")
        else:
            tally: dict[str, int] = {}
            for record in events:
                tally[record["category"]] = tally.get(record["category"], 0) + 1
            st.html("".join(
                cards.mastery_bar(
                    CATEGORY_LABELS.get(category, CODE_FAILURE_LABELS.get(category, category)),
                    min(100, count * 100 / max(len(events), 1)),
                )
                for category, count in sorted(tally.items(), key=lambda pair: -pair[1])
            ))
            with st.expander("Recent mistakes"):
                for record in events[:12]:
                    label = CATEGORY_LABELS.get(
                        record["category"], CODE_FAILURE_LABELS.get(record["category"], record["category"])
                    )
                    st.caption(
                        f"{record['created_at'][:10]} · {record['concept_slug'].split('::')[-1]} · "
                        f"{label}{' — ' + record['note'] if record['note'] else ''}"
                    )
# How many learning actions happened on each of the last `days` days, oldest first.
# Real dates on the index, so the chart keeps them in calendar order.
def daily_activity(events: list[dict[str, Any]], days: int = 14, now: datetime | None = None) -> pd.DataFrame:
    today = (now or datetime.now(timezone.utc)).date()
    counts = {today - timedelta(days=offset): 0 for offset in range(days - 1, -1, -1)}
    for event in events:
        moment = history.parse_time(event.get("created_at", ""))
        if moment is not None and moment.date() in counts:
            counts[moment.date()] += 1
    return pd.DataFrame({"Actions": list(counts.values())}, index=pd.to_datetime(list(counts)))
