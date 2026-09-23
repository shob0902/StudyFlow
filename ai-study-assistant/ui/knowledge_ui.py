# Dashboard, Knowledge and Analytics: the three views onto the mastery engine.
from typing import Any
import streamlit as st
from db import learning_service, plan_service, review_service
from coding.grading import coding_stats
from learning.mastery import ACTION_LABELS, next_action
from learning.misconceptions import CATEGORY_LABELS, CODE_FAILURE_LABELS
from ui import cards
from utils.helpers import StudyAssistantError
# The personalised dashboard: where the student stands and what to do about it.
def render_dashboard(
    user: Any, on_review: Any = None, on_practice: Any = None, on_learn: Any = None,
    on_plan: Any = None,
) -> None:
    st.header(f"Welcome back, {user.first_name}")
    try:
        summary = learning_service.dashboard_summary(user.user_id)
        code = coding_stats(user.user_id)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    if not summary["concepts"]:
        st.info(
            "Nothing tracked yet. Study a topic, upload a document or solve a coding problem, and "
            "your knowledge profile starts filling in."
        )
        _render_plan_block(user, on_learn, on_plan)
        return
    percent = lambda value: f"{value:.0f}%" if value is not None else "—"
    st.html(
        cards.metrics(
            [
                ("Overall mastery", percent(summary["overall_mastery"]), f"{summary['concepts']} concepts"),
                ("Quiz accuracy", percent(summary["quiz_accuracy"]), f"{summary['quiz_answered']} answered"),
                ("Coding accuracy", percent(code["accuracy"]), f"{code['solved']} solved"),
                ("Reviews due", str(summary["reviews_due"]), "today"),
                ("Streak", f"{summary['streak']} day{'s' if summary['streak'] != 1 else ''}", ""),
            ]
        )
    )
    _render_plan_block(user, on_learn, on_plan)
    weakest = summary.get("weakest") or []
    left, right = st.columns(2)
    with left:
        st.subheader("Weakest concepts")
        if not weakest:
            st.caption("Nothing looks weak yet.")
        for state in weakest[:5]:
            st.html(cards.mastery_bar(state.concept_name, state.mastery_score, state.learning_status))
        if weakest and on_practice and st.button(
            f"Practise {weakest[0].concept_name}", type="primary", width="stretch"
        ):
            on_practice(weakest[0])
    with right:
        st.subheader("Due for review")
        due = review_service.due_today(user.user_id, limit=5)
        if not due:
            st.caption("Nothing due right now.")
        for card in due:
            st.html(
                cards.due_row(
                    card["mark"], card["concept_name"],
                    f"{card['mastery']:.0f}% · {'overdue' if card['overdue_days'] > 0 else 'due'}",
                )
            )
        if due and on_review and st.button("Start today's review", type="primary", width="stretch"):
            on_review()
# What the study plan says to do now: which week it is, the topic to be on, and what follows.
def _render_plan_block(user: Any, on_learn: Any = None, on_plan: Any = None) -> None:
    try:
        focus = plan_service.plan_focus(user.user_id)
    except StudyAssistantError as error:
        st.warning(f"Could not read your study plan. {error}")
        return
    if not focus:
        st.subheader("Study plan")
        st.caption("No plan yet. Set a subject and a date and the planner builds one around what you already know.")
        if on_plan and st.button("Make a study plan", width="stretch"):
            on_plan()
        return
    st.subheader(f"Your plan: {focus['subject']}")
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
    st.header("Your knowledge")
    try:
        grouped = learning_service.mastery_by_subject(user.user_id)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    if not grouped:
        st.info("Study something and this map of what you know starts building itself.")
        return
    for subject, states in grouped.items():
        average = sum(state.mastery_score for state in states) / len(states)
        st.html(cards.mastery_bar(subject, average))
        with st.expander(f"{subject} — {len(states)} concept{'s' if len(states) != 1 else ''}"):
            for state in states:
                _render_concept(user, state, on_practice)
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
    st.header("Analytics")
    try:
        summary = learning_service.dashboard_summary(user.user_id)
        events = learning_service.recent_mistakes(user.user_id, 30)
        grouped = learning_service.mastery_by_subject(user.user_id)
        code = coding_stats(user.user_id)
        reviews = review_service.review_stats(user.user_id)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    if not summary["concepts"]:
        st.info("Analytics appear once you have practised something.")
        return
    st.html(
        cards.metrics(
            [
                ("Concepts tracked", summary["concepts"], ""),
                ("Total attempts", summary["attempts"], f"{summary['correct']} correct"),
                ("Coding submissions", code["submissions"], f"{code['accepted']} accepted"),
                ("Reviews done", summary["reviews_done"], f"{reviews['due_this_week']} due this week"),
            ]
        )
    )
    st.subheader("Mastery by subject")
    for subject, states in grouped.items():
        average = sum(state.mastery_score for state in states) / len(states)
        st.html(cards.mastery_bar(subject, average))
    st.subheader("Where you go wrong")
    if not events:
        st.caption("No mistakes recorded yet.")
    else:
        tally: dict[str, int] = {}
        for record in events:
            tally[record["category"]] = tally.get(record["category"], 0) + 1
        for category, count in sorted(tally.items(), key=lambda pair: -pair[1]):
            label = CATEGORY_LABELS.get(category, CODE_FAILURE_LABELS.get(category, category))
            st.html(cards.mastery_bar(label, min(100, count * 100 / max(len(events), 1))))
        with st.expander("Recent mistakes"):
            for record in events[:12]:
                label = CATEGORY_LABELS.get(
                    record["category"], CODE_FAILURE_LABELS.get(record["category"], record["category"])
                )
                st.caption(
                    f"{record['created_at'][:10]} · {record['concept_slug'].split('::')[-1]} · "
                    f"{label}{' — ' + record['note'] if record['note'] else ''}"
                )
    st.subheader("By status")
    by_status = summary.get("by_status", {})
    if by_status:
        st.html(
            cards.metrics(
                [(status.title(), count, "") for status, count in sorted(by_status.items())]
            )
        )
