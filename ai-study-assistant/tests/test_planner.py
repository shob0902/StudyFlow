# The study planner: how a plan is shaped by mastery, and how it changes as mastery moves.
from datetime import date, datetime, timedelta, timezone
import pytest
from learning.concepts import make_concepts
from learning.mastery import Attempt, new_state, update_mastery
from learning.planner import (
    DEFAULT_PLANNER_CONFIG,
    PlanItem,
    PlannerConfig,
    StudyGoal,
    activity_for,
    concept_weight,
    generate_plan,
    parse_date,
    replan,
    summarise,
    weeks_available,
)
TODAY = date(2026, 9, 23)
TOPICS = ["Statistics", "Regression", "Clustering", "Decision Trees"]
# A four-week goal.
@pytest.fixture
def goal():
    return StudyGoal(
        subject="Machine Learning",
        target_date=(TODAY + timedelta(days=28)).isoformat(),
        level="beginner",
        hours_per_day=2.0,
        topics=TOPICS,
    )
# A mastery state at a given score.
def _state(slug, score, attempts=5):
    state = new_state(slug, slug.split("::")[-1].title(), "Machine Learning")
    for _ in range(attempts):
        state = update_mastery(
            state, Attempt(slug, correct=score >= 60, score=score / 100.0, difficulty="medium")
        )
    return state
# --- dates and shape ----------------------------------------------------
# The plan covers the weeks the deadline allows.
def test_weeks_come_from_the_deadline():
    assert weeks_available((TODAY + timedelta(days=28)).isoformat(), TODAY) == 4
    assert weeks_available((TODAY + timedelta(days=10)).isoformat(), TODAY) == 2
    assert weeks_available("", TODAY) == DEFAULT_PLANNER_CONFIG.default_weeks
    assert weeks_available((TODAY - timedelta(days=1)).isoformat(), TODAY) == 1
# Dates are accepted in the formats a person might type.
def test_dates_are_parsed_flexibly():
    assert parse_date("2026-10-20") == date(2026, 10, 20)
    assert parse_date("20 October 2026") == date(2026, 10, 20)
    assert parse_date("20/10/2026") == date(2026, 10, 20)
    assert parse_date("nonsense") is None
# A plan covers every topic and reserves the last week for revision.
def test_plan_covers_the_topics(goal):
    plan = generate_plan(goal, make_concepts(TOPICS, goal.subject), {}, TODAY)
    learning = [item for item in plan.items if item.activity != "revision"]
    assert {item.concept_name for item in learning} == set(TOPICS)
    assert plan.weeks == 4
    assert any(item.activity == "revision" for item in plan.items)
    assert max(item.week for item in plan.items) == 4
# A goal with no topics produces an empty plan rather than a broken one.
def test_plan_without_topics_is_empty(goal):
    plan = generate_plan(goal, [], {}, TODAY)
    assert plan.items == []
    assert plan.weeks == 4
# --- mastery awareness --------------------------------------------------
# Weak concepts are worth more plan time than strong ones.
def test_weak_concepts_weigh_more():
    assert concept_weight(20.0, True) > concept_weight(80.0, True)
    assert concept_weight(0.0, False) == 1.0
    assert DEFAULT_PLANNER_CONFIG.min_weight <= concept_weight(100.0, True)
# What to do with a concept depends on how well it is known.
def test_activity_follows_mastery():
    assert activity_for(0.0, False) == "learn"
    assert activity_for(20.0, True) == "relearn"
    assert activity_for(50.0, True) == "practice"
    assert activity_for(75.0, True) == "review"
    assert activity_for(95.0, True) == "maintain"
# The plan puts what the student is worst at first, and mastered topics last.
def test_plan_is_ordered_by_weakness(goal):
    mastery = {
        "machine_learning::statistics": _state("machine_learning::statistics", 95),
        "machine_learning::clustering": _state("machine_learning::clustering", 20),
    }
    plan = generate_plan(goal, make_concepts(TOPICS, goal.subject), mastery, TODAY)
    learning = [item for item in plan.items if item.activity != "revision"]
    assert learning[0].concept_name == "Clustering"
    assert learning[-1].concept_name == "Statistics"
    assert learning[-1].activity == "maintain"
# A mastered concept drops to maintenance instead of being taught again.
def test_mastered_concepts_go_to_maintenance(goal):
    mastery = {slug: _state(slug, 95) for slug in [c.slug for c in make_concepts(TOPICS, goal.subject)]}
    plan = generate_plan(goal, make_concepts(TOPICS, goal.subject), mastery, TODAY)
    learning = [item for item in plan.items if item.activity != "revision"]
    assert all(item.activity == "maintain" for item in learning)
# --- replanning ---------------------------------------------------------
# When mastery moves, the remaining plan is rebuilt around it.
def test_replanning_follows_new_mastery(goal):
    concepts = make_concepts(TOPICS, goal.subject)
    plan = generate_plan(goal, concepts, {}, TODAY)
    regression = next(c.slug for c in concepts if c.name == "Regression")
    clustering = next(c.slug for c in concepts if c.name == "Clustering")
    mastery = {regression: _state(regression, 92), clustering: _state(clustering, 25)}
    updated = replan(plan, mastery)
    pending = [item for item in updated.items if item.activity != "revision"]
    by_name = {item.concept_name: item for item in pending}
    assert by_name["Regression"].activity == "maintain"
    assert by_name["Clustering"].activity == "relearn"
    assert by_name["Clustering"].week <= by_name["Regression"].week
    assert by_name["Clustering"].minutes >= by_name["Regression"].minutes
# Work already done is kept exactly as it was.
def test_replanning_keeps_finished_work(goal):
    concepts = make_concepts(TOPICS, goal.subject)
    plan = generate_plan(goal, concepts, {}, TODAY)
    done = PlanItem(
        concept_slug=plan.items[0].concept_slug, concept_name=plan.items[0].concept_name,
        subject="Machine Learning", week=1, minutes=60, activity="learn", status="done",
    )
    with_done = type(plan)(
        subject=plan.subject, weeks=plan.weeks, created_at=plan.created_at,
        target_date=plan.target_date, items=[done] + plan.items[1:],
    )
    updated = replan(with_done, {})
    finished = [item for item in updated.items if item.status == "done"]
    assert len(finished) == 1
    assert finished[0].minutes == 60
# A plan with nothing left to do is returned unchanged.
def test_replanning_a_finished_plan_changes_nothing(goal):
    plan = generate_plan(goal, make_concepts(["Statistics"], goal.subject), {}, TODAY)
    finished = type(plan)(
        subject=plan.subject, weeks=plan.weeks, created_at=plan.created_at,
        target_date=plan.target_date,
        items=[
            PlanItem(
                concept_slug=item.concept_slug, concept_name=item.concept_name,
                subject=item.subject, week=item.week, minutes=item.minutes,
                activity=item.activity, status="done",
            )
            for item in plan.items
        ],
    )
    assert replan(finished, {}) == finished
# --- summary ------------------------------------------------------------
# The summary reports what the plan page shows.
def test_summary_shape(goal):
    plan = generate_plan(goal, make_concepts(TOPICS, goal.subject), {}, TODAY)
    summary = summarise(plan)
    assert summary["weeks"] == 4
    assert summary["items"] == len(plan.items)
    assert summary["total_minutes"] > 0
    assert summary["done"] == 0
    assert "learn" in summary["by_activity"]
# Everything is configurable rather than fixed in the logic.
def test_planner_is_configurable(goal):
    config = PlannerConfig(default_weeks=2, items_per_week_cap=1, min_minutes_per_item=10)
    assert weeks_available("", TODAY, config) == 2
    plan = generate_plan(
        StudyGoal(subject="X", topics=TOPICS), make_concepts(TOPICS, "X"), {}, TODAY, config
    )
    assert plan.weeks == 2
