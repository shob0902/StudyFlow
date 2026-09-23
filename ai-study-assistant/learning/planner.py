# The study planner: turn a goal plus what the learner already knows into a week-by-week plan,
# and keep adjusting it as mastery moves. The allocation logic is deterministic; an LLM is only
# used to propose the topic list for a subject, and never to do arithmetic.
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from learning import mastery as mastery_module
from learning.concepts import Concept, make_concepts
# How much of the plan goes to new learning versus revision, by how the learner is doing.
@dataclass(frozen=True)
class PlannerConfig:
    default_weeks: int = 4
    max_weeks: int = 16
    min_minutes_per_item: int = 20
    # The last slice of the plan is kept for revision and mock practice.
    revision_share: float = 0.25
    # Weak concepts are worth more plan time than strong ones; this is the spread.
    min_weight: float = 0.4
    max_weight: float = 3.0
    # A concept at or above this mastery moves to light maintenance instead of active study.
    maintenance_above: float = 85.0
    items_per_week_cap: int = 8
DEFAULT_PLANNER_CONFIG = PlannerConfig()
# What the learner asked for.
@dataclass(frozen=True)
class StudyGoal:
    subject: str
    target_date: str = ""
    level: str = "beginner"
    hours_per_day: float = 1.0
    session_minutes: int = 45
    target_score: int | None = None
    topics: list[str] = field(default_factory=list)
# One thing to study in one week of the plan.
@dataclass(frozen=True)
class PlanItem:
    concept_slug: str
    concept_name: str
    subject: str
    week: int
    minutes: int
    activity: str
    mastery_score: float = 0.0
    status: str = "pending"
# The whole plan.
@dataclass(frozen=True)
class StudyPlan:
    subject: str
    weeks: int
    created_at: str
    target_date: str = ""
    items: list[PlanItem] = field(default_factory=list)
    # The plan grouped by week number, in order.
    def by_week(self) -> list[tuple[int, list[PlanItem]]]:
        weeks: dict[int, list[PlanItem]] = {}
        for item in self.items:
            weeks.setdefault(item.week, []).append(item)
        return [(week, weeks[week]) for week in sorted(weeks)]
    # Total minutes the plan asks for.
    @property
    def total_minutes(self) -> int:
        return sum(item.minutes for item in self.items)
# Parse a target date, accepting a plain date or a full timestamp.
def parse_date(value: str) -> date | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None
# How many weeks the plan should cover: what the deadline allows, else the default.
def weeks_available(
    target_date: str, today: date | None = None, config: PlannerConfig = DEFAULT_PLANNER_CONFIG
) -> int:
    today = today or datetime.now(timezone.utc).date()
    deadline = parse_date(target_date)
    if deadline is None:
        return config.default_weeks
    days = (deadline - today).days
    if days <= 0:
        return 1
    return max(1, min(config.max_weeks, -(-days // 7)))
# How much attention a concept deserves: weak concepts are weighted up, mastered ones down.
# This is what makes the plan adapt — nothing else needs to know about mastery.
def concept_weight(
    mastery_score: float, started: bool, config: PlannerConfig = DEFAULT_PLANNER_CONFIG
) -> float:
    if not started:
        return 1.0
    weight = config.max_weight - (mastery_score / 100.0) * (config.max_weight - config.min_weight)
    return round(max(config.min_weight, min(config.max_weight, weight)), 3)
# What the learner should actually do with a concept at their current level.
def activity_for(mastery_score: float, started: bool, config: PlannerConfig = DEFAULT_PLANNER_CONFIG) -> str:
    if not started:
        return "learn"
    if mastery_score >= config.maintenance_above:
        return "maintain"
    if mastery_score < mastery_module.DEFAULT_CONFIG.weak_below:
        return "relearn"
    if mastery_score < mastery_module.DEFAULT_CONFIG.learning_below:
        return "practice"
    return "review"
# Build a plan from a goal, the topics to cover and what the learner already knows.
#
# Weak and unstarted concepts land earliest and get the most minutes; mastered ones drop to
# maintenance at the back. The final stretch of the plan is reserved for revision.
def generate_plan(
    goal: StudyGoal,
    concepts: list[Concept],
    mastery: dict[str, mastery_module.MasteryState] | None = None,
    today: date | None = None,
    config: PlannerConfig = DEFAULT_PLANNER_CONFIG,
) -> StudyPlan:
    today = today or datetime.now(timezone.utc).date()
    mastery = mastery or {}
    weeks = weeks_available(goal.target_date, today, config)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not concepts:
        return StudyPlan(
            subject=goal.subject, weeks=weeks, created_at=created, target_date=goal.target_date
        )
    minutes_per_week = max(
        config.min_minutes_per_item,
        int(goal.hours_per_day * 60 * 7),
    )
    # Order by how much attention each concept deserves. Weight already encodes all of it: a
    # concept the learner is demonstrably weak at outranks one they have never started, and a
    # mastered concept sinks to the end.
    scored = []
    for concept in concepts:
        state = mastery.get(concept.slug)
        score = state.mastery_score if state and state.is_started else 0.0
        started = bool(state and state.is_started)
        scored.append((concept, score, started, concept_weight(score, started, config)))
    scored.sort(key=lambda row: (-row[3], row[1]))
    # Weeks reserved for revision at the end of the plan.
    study_weeks = max(1, weeks - 1) if weeks > 2 else weeks
    per_week = max(1, min(config.items_per_week_cap, -(-len(scored) // study_weeks)))
    items: list[PlanItem] = []
    for index, (concept, score, started, weight) in enumerate(scored):
        week = min(study_weeks, index // per_week + 1)
        same_week = [row for row in scored[week_start(index, per_week) : week_start(index, per_week) + per_week]]
        week_weight = sum(row[3] for row in same_week) or 1.0
        minutes = max(
            config.min_minutes_per_item,
            int(minutes_per_week * (weight / week_weight)),
        )
        items.append(
            PlanItem(
                concept_slug=concept.slug,
                concept_name=concept.name,
                subject=concept.subject or goal.subject,
                week=week,
                minutes=minutes,
                activity=activity_for(score, started, config),
                mastery_score=score,
            )
        )
    if weeks > 2:
        items.extend(_revision_items(scored, weeks, goal, config))
    return StudyPlan(
        subject=goal.subject,
        weeks=weeks,
        created_at=created,
        target_date=goal.target_date,
        items=items,
    )
# The index the current week's block starts at.
def week_start(index: int, per_week: int) -> int:
    return (index // per_week) * per_week
# The revision week: the weakest concepts come back for another pass.
def _revision_items(
    scored: list[tuple[Concept, float, bool, float]],
    weeks: int,
    goal: StudyGoal,
    config: PlannerConfig,
) -> list[PlanItem]:
    weakest = sorted(scored, key=lambda row: row[1])[: config.items_per_week_cap]
    minutes = max(config.min_minutes_per_item, int(goal.session_minutes))
    return [
        PlanItem(
            concept_slug=concept.slug,
            concept_name=concept.name,
            subject=concept.subject or goal.subject,
            week=weeks,
            minutes=minutes,
            activity="revision",
            mastery_score=score,
        )
        for concept, score, _started, _weight in weakest
    ]
# Rebuild the un-started part of a plan against current mastery.
#
# Anything already done stays as it is. What is left is re-weighted, so a concept that has since
# been mastered drops to maintenance and one that has slipped gets more time and moves earlier.
def replan(
    plan: StudyPlan,
    mastery: dict[str, mastery_module.MasteryState],
    goal: StudyGoal | None = None,
    today: date | None = None,
    config: PlannerConfig = DEFAULT_PLANNER_CONFIG,
) -> StudyPlan:
    done = [item for item in plan.items if item.status == "done"]
    remaining = [item for item in plan.items if item.status != "done"]
    if not remaining:
        return plan
    goal = goal or StudyGoal(subject=plan.subject, target_date=plan.target_date)
    updated: list[PlanItem] = []
    for item in remaining:
        state = mastery.get(item.concept_slug)
        score = state.mastery_score if state and state.is_started else item.mastery_score
        started = bool(state and state.is_started)
        weight = concept_weight(score, started, config)
        updated.append(
            PlanItem(
                concept_slug=item.concept_slug,
                concept_name=item.concept_name,
                subject=item.subject,
                week=item.week,
                minutes=item.minutes,
                activity=activity_for(score, started, config),
                mastery_score=score,
                status=item.status,
            )
        )
    # Re-order the remaining work so the weakest concepts come first, then re-assign weeks.
    first_week = min(item.week for item in updated)
    last_week = max(plan.weeks, first_week)
    updated.sort(key=lambda item: (item.activity == "maintain", item.mastery_score))
    per_week = max(1, -(-len(updated) // max(1, last_week - first_week + 1)))
    rescheduled = [
        PlanItem(
            concept_slug=item.concept_slug,
            concept_name=item.concept_name,
            subject=item.subject,
            week=min(last_week, first_week + index // per_week),
            minutes=_minutes_for(item, config),
            activity=item.activity,
            mastery_score=item.mastery_score,
            status=item.status,
        )
        for index, item in enumerate(updated)
    ]
    return StudyPlan(
        subject=plan.subject,
        weeks=plan.weeks,
        created_at=plan.created_at,
        target_date=plan.target_date,
        items=done + rescheduled,
    )
# Minutes for an item after replanning: weak concepts get more, maintenance gets less.
def _minutes_for(item: PlanItem, config: PlannerConfig) -> int:
    weight = concept_weight(item.mastery_score, item.mastery_score > 0, config)
    scaled = int(config.min_minutes_per_item * max(1.0, weight))
    if item.activity == "maintain":
        return config.min_minutes_per_item
    return max(config.min_minutes_per_item, scaled)
# A short description of how the plan is shaped, for the UI.
def summarise(plan: StudyPlan) -> dict[str, Any]:
    by_activity: dict[str, int] = {}
    for item in plan.items:
        by_activity[item.activity] = by_activity.get(item.activity, 0) + 1
    return {
        "weeks": plan.weeks,
        "items": len(plan.items),
        "total_minutes": plan.total_minutes,
        "by_activity": by_activity,
        "done": sum(1 for item in plan.items if item.status == "done"),
    }
# Fall back to a sensible topic list when no LLM is available to propose one.
def fallback_topics(goal: StudyGoal) -> list[Concept]:
    return make_concepts(goal.topics, goal.subject)
