# Today's Review and the Study Plan: what to revise now, and what to learn over the coming weeks.
from datetime import date, datetime, timedelta, timezone
from typing import Any
import streamlit as st
from db import learning_service, plan_service, review_service
from learning.planner import StudyGoal
from ui import cards
from utils.helpers import StudyAssistantError
REVIEW_QUEUE = "review_queue"
REVIEW_INDEX = "review_index"
REVIEW_SHOWN = "review_shown"
REVIEW_DONE = "review_done"
# How well the student says they recalled a concept, and what that is worth.
GRADES = [
    ("Forgot it", 0.0),
    ("Shaky", 0.4),
    ("Got it", 0.8),
    ("Easy", 1.0),
]
# Today's review page.
def render_review(user: Any) -> None:
    st.header("Today's review")
    if st.session_state.get(REVIEW_QUEUE):
        _render_session(user)
        return
    try:
        due = review_service.due_today(user.user_id, limit=20)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    done = st.session_state.get(REVIEW_DONE) or []
    if done:
        st.success(f"Reviewed {len(done)} concept(s). " + ", ".join(
            f"{name} → {score:.0f}%" for name, score in done
        ))
        st.session_state[REVIEW_DONE] = []
    if not due:
        upcoming = review_service.upcoming(user.user_id, 7)
        st.info("Nothing is due right now.")
        if upcoming:
            st.caption("Coming up this week:")
            for card in upcoming[:8]:
                st.html(cards.due_row(card["mark"], card["concept_name"], f"{card['mastery']:.0f}%"))
        return
    st.caption(f"{len(due)} concept{'s' if len(due) != 1 else ''} due")
    for card in due:
        detail = f"{card['mastery']:.0f}%"
        if card["overdue_days"] > 0:
            detail += f" · {card['overdue_days']:.0f} days overdue"
        st.html(cards.due_row(card["mark"], card["concept_name"], detail))
        if card["mistakes"]:
            st.caption("Last time: " + card["mistakes"][0])
    if st.button("Start review session", type="primary", width="stretch"):
        st.session_state[REVIEW_QUEUE] = due
        st.session_state[REVIEW_INDEX] = 0
        st.session_state[REVIEW_SHOWN] = False
        st.session_state[REVIEW_DONE] = []
        st.rerun()
# One card at a time: recall it, then grade yourself.
def _render_session(user: Any) -> None:
    queue = st.session_state[REVIEW_QUEUE]
    index = st.session_state.get(REVIEW_INDEX, 0)
    if index >= len(queue):
        st.session_state[REVIEW_QUEUE] = []
        st.rerun()
        return
    card = queue[index]
    st.caption(f"Card {index + 1} of {len(queue)}")
    st.progress((index) / len(queue))
    st.subheader(card["concept_name"])
    st.caption(f"{card['subject']} · currently {card['mastery']:.0f}%")
    if not st.session_state.get(REVIEW_SHOWN):
        st.info("Recall everything you can about this, out loud or on paper. Then reveal.")
        if st.button("I've tried — show me", type="primary", width="stretch"):
            st.session_state[REVIEW_SHOWN] = True
            st.rerun()
        return
    if card["mistakes"]:
        st.warning("What caught you out before: " + "; ".join(card["mistakes"]))
    st.caption("How well did you recall it?")
    columns = st.columns(len(GRADES))
    for column, (label, quality) in zip(columns, GRADES):
        if column.button(label, key=f"grade_{index}_{label}", width="stretch"):
            _grade(user, card, quality)
    if st.button("End session", width="stretch"):
        st.session_state[REVIEW_QUEUE] = []
        st.rerun()
# Record one graded card and move on.
def _grade(user: Any, card: dict[str, Any], quality: float) -> None:
    try:
        result = review_service.record_review(
            user.user_id, card["concept_slug"], quality, card["concept_name"], card["subject"]
        )
    except StudyAssistantError as error:
        st.error(str(error))
        return
    st.session_state.setdefault(REVIEW_DONE, []).append(
        (card["concept_name"], result.get("mastery", card["mastery"]))
    )
    st.session_state[REVIEW_INDEX] = st.session_state.get(REVIEW_INDEX, 0) + 1
    st.session_state[REVIEW_SHOWN] = False
    st.rerun()
# The study plan page.
def render_plan(user: Any, on_learn: Any = None) -> None:
    st.header("Study plan")
    try:
        found = plan_service.active_plan(user.user_id)
    except StudyAssistantError as error:
        st.error(str(error))
        return
    if found is None:
        _render_goal_form(user)
        _render_history(user)
        return
    plan_id, plan = found
    summary = plan_service.plan_summary(plan)
    st.subheader(plan.subject)
    st.html(
        cards.metrics(
            [
                ("Weeks", summary["weeks"], plan.target_date or "no deadline"),
                ("Items", summary["items"], f"{summary['done']} done"),
                ("Planned time", f"{summary['total_minutes'] // 60} h", ""),
                ("Focus", max(summary["by_activity"], key=summary["by_activity"].get, default="—"), ""),
            ]
        )
    )
    columns = st.columns(3)
    if columns[0].button("Update against my mastery", type="primary", width="stretch"):
        with st.spinner("Rebalancing the weeks ahead..."):
            plan_service.refresh_plan(user.user_id, plan_id)
        st.rerun()
    if columns[1].button("New plan", width="stretch"):
        st.session_state["plan_new"] = True
        st.rerun()
    if columns[2].button("Delete this plan", key="delete_active_plan", width="stretch"):
        plan_service.delete_plan(user.user_id, plan_id)
        st.rerun()
    if st.session_state.get("plan_new"):
        _render_goal_form(user)
        _render_history(user)
        return
    today = date.today()
    for week, items in plan.by_week():
        start = today + timedelta(days=7 * (week - 1))
        st.markdown(f"**Week {week}** — from {start.strftime('%d %b')}")
        for item in items:
            _render_item(user, plan_id, item, on_learn)
    _render_history(user)
# Every plan this user has made, with the active one marked.
#
# Plans are kept rather than replaced: a finished one is a record of what was studied, and an
# older one can be made active again.
def _render_history(user: Any) -> None:
    try:
        plans = plan_service.list_plans(user.user_id)
    except StudyAssistantError as error:
        st.warning(f"Could not load your plans. {error}")
        return
    if not plans:
        return
    st.divider()
    with st.expander(f"All your plans ({len(plans)})"):
        for record in plans:
            _render_history_row(user, record)
        st.divider()
        confirm = st.checkbox("Yes, delete every plan", key="confirm_reset_plans")
        if st.button("Reset — delete all plans", key="reset_plans", width="stretch"):
            if not confirm:
                st.warning("Tick the box first. This removes every plan and cannot be undone.")
            else:
                removed = plan_service.delete_all_plans(user.user_id)
                st.session_state["plan_new"] = False
                st.success(f"Deleted {removed} plan(s).")
                st.rerun()
# One plan in the history, with its progress and its own controls.
def _render_history_row(user: Any, record: dict[str, Any]) -> None:
    with st.container(key=f"planrow_{record['id']}"):
        columns = st.columns([5, 1, 1], vertical_alignment="center")
        active = record["status"] == "active"
        items = record.get("items") or 0
        done = record.get("done") or 0
        progress = f"{done}/{items} done" if items else "empty"
        when = str(record.get("created_at", ""))[:10]
        columns[0].markdown(
            f"{'**' if active else ''}{record['subject']}{'**' if active else ''}"
            f"{' · active' if active else ''}  \n"
            f"<span style='font-size:.76rem;opacity:.7'>{when} · {record['weeks']} weeks · "
            f"{progress}{' · until ' + record['target_date'] if record['target_date'] else ''}</span>",
            unsafe_allow_html=True,
        )
        if not active and columns[1].button("Open", key=f"openplan_{record['id']}", width="stretch"):
            plan_service.activate_plan(user.user_id, record["id"])
            st.rerun()
        if columns[2].button("Delete", key=f"delplan_{record['id']}", width="stretch"):
            plan_service.delete_plan(user.user_id, record["id"])
            st.rerun()
# One line of the plan.
def _render_item(user: Any, plan_id: str, item: Any, on_learn: Any = None) -> None:
    with st.container(key=f"plan_{plan_id}_{item.week}_{item.concept_slug}"):
        columns = st.columns([4, 1, 1], vertical_alignment="center")
        done = item.status == "done"
        label = f"**{item.concept_name}**" if not done else f"{item.concept_name} (done)"
        columns[0].markdown(
            f"{label}  \n<span style='font-size:.76rem;opacity:.7'>{item.activity} · "
            f"{item.minutes} min · mastery {item.mastery_score:.0f}%</span>",
            unsafe_allow_html=True,
        )
        if on_learn and columns[1].button("Learn", key=f"learn_{plan_id}_{item.week}_{item.concept_slug}", width="stretch"):
            on_learn(item.concept_name)
        if not done and columns[2].button(
            "Done", key=f"done_{plan_id}_{item.week}_{item.concept_slug}", width="stretch"
        ):
            plan_service.complete_item(user.user_id, plan_id, item.concept_slug, item.week)
            st.rerun()
# The form that creates a plan.
def _render_goal_form(user: Any) -> None:
    st.caption("Tell the planner what you are working towards. It weights the plan by what you already know.")
    with st.form("study_goal"):
        subject = st.text_input("Subject", placeholder="Machine Learning")
        columns = st.columns(3)
        target = columns[0].date_input(
            "Target date", value=date.today() + timedelta(days=28), min_value=date.today()
        )
        hours = columns[1].number_input("Hours per day", 0.5, 12.0, 2.0, step=0.5)
        level = columns[2].selectbox("Current level", ["beginner", "intermediate", "advanced"])
        columns = st.columns(2)
        session_minutes = columns[0].number_input("Session length (min)", 15, 180, 45, step=15)
        target_score = columns[1].number_input("Target score (optional)", 0, 100, 0)
        topics = st.text_area(
            "Topics you want covered (one per line, optional)",
            placeholder="Regression\nClustering\nDecision trees",
            help="Leave empty and the planner will propose a syllabus for the subject.",
        )
        created = st.form_submit_button("Create plan", type="primary", width="stretch")
    if not created:
        return
    if not subject.strip():
        st.warning("Enter a subject first.")
        return
    goal = StudyGoal(
        subject=subject.strip(),
        target_date=target.isoformat(),
        level=level,
        hours_per_day=float(hours),
        session_minutes=int(session_minutes),
        target_score=int(target_score) or None,
        topics=[line.strip() for line in topics.splitlines() if line.strip()],
    )
    with st.spinner("Building your plan..."):
        try:
            plan_service.create_plan(user.user_id, goal)
        except StudyAssistantError as error:
            st.error(str(error))
            return
    st.session_state["plan_new"] = False
    st.rerun()
