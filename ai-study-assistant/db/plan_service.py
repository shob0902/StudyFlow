# Study plans and review sessions: the two things that decide what the student does next.
#
# Plan shape is computed in learning/planner.py from mastery; the LLM is only asked to propose a
# topic list for a subject, and only when the student has not supplied one.
import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Any
from auth.errors import DatabaseError, UnauthorizedError
from db import learning_service
from db.database import session
from db.models import utc_now
from learning.concepts import Concept, make_concepts
from learning.planner import (
    PlanItem,
    StudyGoal,
    StudyPlan,
    generate_plan,
    replan,
    summarise,
    weeks_available,
)
from llm.model import NODE_API_KEYS, get_structured_llm, run_chain
from prompts.prompts import STUDY_PLAN_PROMPT
from schemas.models import StudyPlanTopics
from utils.helpers import LLMError, StudyAssistantError, log_error, log_step
# Ask the model for an ordered topic list, steered by what the student already knows.
def propose_topics(user_id: str, goal: StudyGoal) -> list[Concept]:
    if goal.topics:
        return make_concepts(goal.topics, goal.subject)
    states = learning_service.mastery_for_user(user_id) if user_id else []
    strong = [s.concept_name for s in states if s.mastery_score >= 75][:8]
    weak = [s.concept_name for s in states if s.mastery_score < 50][:8]
    chain = STUDY_PLAN_PROMPT | get_structured_llm(
        StudyPlanTopics, NODE_API_KEYS["study_planner"]
    )
    try:
        proposed: StudyPlanTopics = run_chain(
            chain,
            {
                "subject": goal.subject,
                "level": goal.level,
                "weeks": weeks_available(goal.target_date),
                "hours_per_day": goal.hours_per_day,
                "wanted": ", ".join(goal.topics) or "no specific topics",
                "strong": ", ".join(strong) or "nothing yet",
                "weak": ", ".join(weak) or "nothing yet",
            },
            "study plan topics",
        )
    except LLMError:
        log_step("PLANNER", "Topic generation failed; using the subject as a single topic")
        return make_concepts([goal.subject], goal.subject)
    return make_concepts(proposed.topics, proposed.subject or goal.subject)
# Build a plan and store it, retiring whichever plan was active before.
def create_plan(user_id: str, goal: StudyGoal) -> tuple[str, StudyPlan]:
    if not user_id:
        raise UnauthorizedError("Please sign in to make a study plan.")
    concepts = propose_topics(user_id, goal)
    learning_service.ensure_concepts(concepts)
    mastery = learning_service.mastery_map(user_id)
    plan = generate_plan(goal, concepts, mastery)
    plan_id = _store(user_id, goal, plan)
    learning_service.record_event(
        user_id, kind="plan_created", detail={"subject": goal.subject, "weeks": plan.weeks}
    )
    log_step("PLANNER", f"Created a {plan.weeks}-week plan for {goal.subject!r} with {len(plan.items)} items")
    return plan_id, plan
# Write a plan and its items.
def _store(user_id: str, goal: StudyGoal, plan: StudyPlan) -> str:
    plan_id = str(uuid.uuid4())
    now = utc_now()
    try:
        with session() as connection:
            with connection:
                # Exactly one plan is active at a time: a new one takes over, and the others
                # stay in the history where they can be reopened.
                connection.execute(
                    "UPDATE study_plans SET status = 'archived', updated_at = ?"
                    " WHERE user_id = ? AND status = 'active'",
                    (now, user_id),
                )
                connection.execute(
                    "INSERT INTO study_plans (id, user_id, subject, target_date, weeks, goal,"
                    " status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
                    (
                        plan_id, user_id, goal.subject, goal.target_date, plan.weeks,
                        json.dumps(
                            {
                                "level": goal.level, "hours_per_day": goal.hours_per_day,
                                "session_minutes": goal.session_minutes,
                                "target_score": goal.target_score, "topics": goal.topics,
                            }
                        ),
                        now, now,
                    ),
                )
                connection.executemany(
                    "INSERT INTO study_plan_items (id, plan_id, user_id, concept_slug,"
                    " concept_name, subject, week, minutes, activity, status, mastery_score, position)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            str(uuid.uuid4()), plan_id, user_id, item.concept_slug,
                            item.concept_name, item.subject, item.week, item.minutes,
                            item.activity, item.status, item.mastery_score, position,
                        )
                        for position, item in enumerate(plan.items)
                    ],
                )
    except sqlite3.Error:
        log_error("Could not store a study plan")
        raise DatabaseError("Could not save that study plan. Please try again.")
    return plan_id
# Turn a stored plan row and its items into a StudyPlan.
def _to_plan(row: Any, items: list[Any]) -> StudyPlan:
    return StudyPlan(
        subject=row["subject"], weeks=row["weeks"], created_at=row["created_at"],
        target_date=row["target_date"],
        items=[
            PlanItem(
                concept_slug=item["concept_slug"], concept_name=item["concept_name"],
                subject=item["subject"], week=item["week"], minutes=item["minutes"],
                activity=item["activity"], mastery_score=item["mastery_score"],
                status=item["status"],
            )
            for item in items
        ],
    )
# Any one of this user's plans, active or not. Returns None for a plan that is not theirs.
def load_plan(user_id: str, plan_id: str) -> tuple[str, StudyPlan] | None:
    with session() as connection:
        row = connection.execute(
            "SELECT * FROM study_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
        ).fetchone()
        if row is None:
            return None
        items = connection.execute(
            "SELECT * FROM study_plan_items WHERE plan_id = ? AND user_id = ? ORDER BY week, position",
            (plan_id, user_id),
        ).fetchall()
    return row["id"], _to_plan(row, items)
# Make one of this user's plans the active one, archiving whichever was active before.
def activate_plan(user_id: str, plan_id: str) -> bool:
    now = utc_now()
    with session() as connection:
        owned = connection.execute(
            "SELECT 1 FROM study_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
        ).fetchone()
        if owned is None:
            raise UnauthorizedError("That study plan does not belong to your account.")
        with connection:
            connection.execute(
                "UPDATE study_plans SET status = 'archived', updated_at = ?"
                " WHERE user_id = ? AND status = 'active'",
                (now, user_id),
            )
            connection.execute(
                "UPDATE study_plans SET status = 'active', updated_at = ? WHERE id = ? AND user_id = ?",
                (now, plan_id, user_id),
            )
    log_step("PLANNER", f"Switched to plan {plan_id}")
    return True
# Delete every plan this user has. Returns how many went.
def delete_all_plans(user_id: str) -> int:
    with session() as connection:
        with connection:
            cursor = connection.execute("DELETE FROM study_plans WHERE user_id = ?", (user_id,))
    if cursor.rowcount:
        learning_service.record_event(
            user_id, kind="plans_cleared", detail={"count": cursor.rowcount}
        )
        log_step("PLANNER", f"Deleted {cursor.rowcount} plan(s)")
    return cursor.rowcount
# This user's active plan, if they have one.
def active_plan(user_id: str, subject: str = "") -> tuple[str, StudyPlan] | None:
    with session() as connection:
        if subject:
            row = connection.execute(
                "SELECT * FROM study_plans WHERE user_id = ? AND subject = ? AND status = 'active'"
                " ORDER BY updated_at DESC LIMIT 1",
                (user_id, subject),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM study_plans WHERE user_id = ? AND status = 'active'"
                " ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        items = connection.execute(
            "SELECT * FROM study_plan_items WHERE plan_id = ? AND user_id = ?"
            " ORDER BY week, position",
            (row["id"], user_id),
        ).fetchall()
    return row["id"], _to_plan(row, items)
# Every plan this user has made, newest first, with how far through each one they are.
def list_plans(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with session() as connection:
        rows = connection.execute(
            "SELECT p.*,"
            " (SELECT COUNT(*) FROM study_plan_items i WHERE i.plan_id = p.id) AS items,"
            " (SELECT COUNT(*) FROM study_plan_items i WHERE i.plan_id = p.id AND i.status = 'done')"
            "   AS done"
            " FROM study_plans p WHERE p.user_id = ? ORDER BY p.updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
# What the plan says to do now, for the dashboard.
#
# The current week is worked out from when the plan was made, so the dashboard can say "week 2 of
# 4" without storing a schedule; whatever is still pending in the earliest unfinished week is
# what the student should be on.
def plan_focus(user_id: str, today: date | None = None) -> dict[str, Any]:
    found = active_plan(user_id)
    if found is None:
        return {}
    plan_id, plan = found
    today = today or datetime.now(timezone.utc).date()
    started = _plan_start(plan, today)
    elapsed_weeks = max(0, (today - started).days // 7)
    current_week = min(plan.weeks, elapsed_weeks + 1)
    pending = [item for item in plan.items if item.status != "done"]
    done = [item for item in plan.items if item.status == "done"]
    this_week = [item for item in pending if item.week == current_week]
    # If this week's work is finished, point at whatever is next rather than at nothing.
    queue = this_week or pending
    return {
        "plan_id": plan_id,
        "subject": plan.subject,
        "target_date": plan.target_date,
        "week": current_week,
        "weeks": plan.weeks,
        "behind": bool(pending and pending[0].week < current_week),
        "current": queue[0] if queue else None,
        "this_week": this_week,
        "upcoming": [item for item in queue[1:4]],
        "done": len(done),
        "total": len(plan.items),
    }
# The day a plan started, falling back to today when its timestamp cannot be read.
def _plan_start(plan: StudyPlan, today: date) -> date:
    try:
        return datetime.fromisoformat(plan.created_at).date()
    except (TypeError, ValueError):
        return today
# Mark one item of this user's plan as done, and record it as a learning event.
def complete_item(user_id: str, plan_id: str, concept_slug: str, week: int) -> bool:
    with session() as connection:
        with connection:
            cursor = connection.execute(
                "UPDATE study_plan_items SET status = 'done'"
                " WHERE plan_id = ? AND user_id = ? AND concept_slug = ? AND week = ?",
                (plan_id, user_id, concept_slug, week),
            )
    if cursor.rowcount:
        learning_service.record_event(
            user_id, kind="plan_item_done", concept_slug=concept_slug, detail={"plan": plan_id}
        )
    return cursor.rowcount > 0
# Rebuild the unfinished part of a plan against current mastery.
#
# This is the "dynamic" in dynamic replanning: a concept that has since been mastered drops to
# maintenance, one that has slipped moves earlier and gets more time.
def refresh_plan(user_id: str, plan_id: str) -> StudyPlan | None:
    found = active_plan(user_id)
    if found is None or found[0] != plan_id:
        with session() as connection:
            owned = connection.execute(
                "SELECT 1 FROM study_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
            ).fetchone()
        if owned is None:
            raise UnauthorizedError("That study plan does not belong to your account.")
    plan = found[1] if found else None
    if plan is None:
        return None
    mastery = learning_service.mastery_map(user_id)
    updated = replan(plan, mastery)
    _replace_items(user_id, plan_id, updated)
    learning_service.record_event(user_id, kind="plan_updated", detail={"plan": plan_id})
    log_step("PLANNER", f"Replanned {len(updated.items)} item(s) against current mastery")
    return updated
# Swap a plan's pending items for the recomputed ones, keeping what is already done.
def _replace_items(user_id: str, plan_id: str, plan: StudyPlan) -> None:
    now = utc_now()
    try:
        with session() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM study_plan_items WHERE plan_id = ? AND user_id = ? AND status != 'done'",
                    (plan_id, user_id),
                )
                connection.executemany(
                    "INSERT INTO study_plan_items (id, plan_id, user_id, concept_slug,"
                    " concept_name, subject, week, minutes, activity, status, mastery_score, position)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            str(uuid.uuid4()), plan_id, user_id, item.concept_slug,
                            item.concept_name, item.subject, item.week, item.minutes,
                            item.activity, item.status, item.mastery_score, position,
                        )
                        for position, item in enumerate(plan.items)
                        if item.status != "done"
                    ],
                )
                connection.execute(
                    "UPDATE study_plans SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (now, plan_id, user_id),
                )
    except sqlite3.Error:
        log_error("Could not replan")
        raise DatabaseError("Could not update that study plan. Please try again.")
# Delete one of this user's plans.
def delete_plan(user_id: str, plan_id: str) -> bool:
    with session() as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM study_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
            )
    return cursor.rowcount > 0
# A one-line description of a plan's shape.
def plan_summary(plan: StudyPlan) -> dict[str, Any]:
    return summarise(plan)
