# The one way anything in the app records practice.
#
# Quizzes, document quizzes, reviews and coding submissions all call record_attempts(). That is
# what makes the knowledge graph unified: there is no second mastery score anywhere, and every
# activity moves the same row, its review schedule and the analytics together.
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from db.database import session
from db.mastery_repository import (
    ConceptRepository,
    EventRepository,
    MasteryRepository,
    MistakeRepository,
)
from learning import scheduling
from learning.concepts import Concept, make_concept
from learning.mastery import (
    Attempt,
    MasteryConfig,
    MasteryState,
    DEFAULT_CONFIG,
    new_state,
    next_action,
    summarise,
    update_mastery,
    with_decay,
)
from learning.misconceptions import common_mistakes
from utils.helpers import log_step
# Make sure a concept exists in the shared vocabulary, and return its slug.
def ensure_concept(concept: Concept) -> str:
    with session() as connection:
        return ConceptRepository(connection).ensure(concept.slug, concept.name, concept.subject)
# Register several concepts at once.
def ensure_concepts(concepts: Iterable[Concept]) -> list[str]:
    with session() as connection:
        repository = ConceptRepository(connection)
        return [repository.ensure(c.slug, c.name, c.subject) for c in concepts]
# Record practice against one or more concepts.
#
# For each attempt this updates mastery, moves the review schedule (bringing a review forward when
# mastery has dropped), and writes a learning event. Returns the new state of each concept so the
# caller can react — re-explain, change difficulty, or move on.
def record_attempts(
    user_id: str,
    attempts: list[Attempt],
    source: str = "quiz",
    now: datetime | None = None,
    config: MasteryConfig = DEFAULT_CONFIG,
) -> dict[str, MasteryState]:
    if not user_id or not attempts:
        return {}
    now = now or datetime.now(timezone.utc)
    updated: dict[str, MasteryState] = {}
    with session() as connection:
        concepts = ConceptRepository(connection)
        mastery = MasteryRepository(connection)
        events = EventRepository(connection)
        for attempt in attempts:
            concepts.ensure(
                attempt.concept_slug, attempt.concept_name or attempt.concept_slug, attempt.subject or "General"
            )
            state = mastery.get(user_id, attempt.concept_slug) or new_state(
                attempt.concept_slug, attempt.concept_name, attempt.subject
            )
            review = mastery.get_review(user_id, attempt.concept_slug)
            new = update_mastery(state, attempt, now, config)
            # Reviews move the schedule on; other practice starts one, or pulls it forward when
            # the concept has slipped.
            if attempt.activity == "review" and review is not None:
                review = scheduling.review(review, attempt.quality, new.mastery_score, now)
            elif review is None or not review.next_review_at:
                review = scheduling.schedule_new(attempt.concept_slug, new.mastery_score, now)
            else:
                review = scheduling.reschedule_for_mastery(review, new.mastery_score, now)
            mastery.save(user_id, new, review)
            events.add(
                user_id, kind="attempt", concept_slug=attempt.concept_slug,
                activity=attempt.activity, correct=attempt.correct, score=attempt.quality * 100,
                detail={"difficulty": attempt.difficulty, "source": source},
            )
            updated[attempt.concept_slug] = new
    log_step("MASTERY", f"{len(attempts)} attempt(s) from {source} updated {len(updated)} concept(s)")
    return updated
# Record a mistake against a concept, so the next explanation can address it.
def record_mistake(user_id: str, concept_slug: str, category: str, note: str = "", source: str = "quiz") -> None:
    with session() as connection:
        MistakeRepository(connection).add(user_id, concept_slug, category, note, source)
# What this user knows, with time decay applied so the numbers are honest about fading knowledge.
def mastery_for_user(user_id: str, subject: str = "", now: datetime | None = None) -> list[MasteryState]:
    with session() as connection:
        states = MasteryRepository(connection).list_for_user(user_id, subject)
    return [with_decay(state, now) for state in states]
# One concept's state for this user.
def mastery_for_concept(user_id: str, concept_slug: str, now: datetime | None = None) -> MasteryState | None:
    with session() as connection:
        state = MasteryRepository(connection).get(user_id, concept_slug)
    return with_decay(state, now) if state else None
# Mastery keyed by slug, which is what the planner wants.
def mastery_map(user_id: str, now: datetime | None = None) -> dict[str, MasteryState]:
    return {state.concept_slug: state for state in mastery_for_user(user_id, now=now)}
# Everything due for review right now, most urgent first.
def due_reviews(user_id: str, now: datetime | None = None, limit: int = 20) -> list[tuple[MasteryState, Any]]:
    moment = now or datetime.now(timezone.utc)
    with session() as connection:
        rows = MasteryRepository(connection).due(user_id, moment.isoformat(timespec="seconds"), limit)
    return [(with_decay(state, moment), review) for state, review in rows]
# What is coming up, so the planner can see the week ahead.
def upcoming_reviews(user_id: str, days: int = 7, now: datetime | None = None) -> list[tuple[MasteryState, Any]]:
    moment = now or datetime.now(timezone.utc)
    horizon = (moment + timedelta(days=days)).isoformat(timespec="seconds")
    with session() as connection:
        rows = MasteryRepository(connection).due(user_id, horizon, 200)
    return [(with_decay(state, moment), review) for state, review in rows]
# The mistakes this user keeps making on a concept, as readable lines.
def mistakes_for_concept(user_id: str, concept_slug: str, limit: int = 5) -> list[str]:
    with session() as connection:
        records = MistakeRepository(connection).for_concept(user_id, concept_slug, limit * 2)
    return common_mistakes(records, limit)
# The recent mistakes across everything, for the dashboard.
def recent_mistakes(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with session() as connection:
        return MistakeRepository(connection).recent(user_id, limit)
# Record something that is not an attempt, such as uploading a document or finishing a plan item.
def record_event(user_id: str, kind: str, **fields: Any) -> None:
    with session() as connection:
        EventRepository(connection).add(user_id, kind, **fields)
# How many consecutive days up to today this user has studied.
def study_streak(user_id: str, now: datetime | None = None) -> int:
    today = (now or datetime.now(timezone.utc)).date()
    with session() as connection:
        days = EventRepository(connection).active_days(user_id)
    streak = 0
    for offset, day in enumerate(days):
        try:
            parsed = datetime.fromisoformat(day).date()
        except ValueError:
            break
        expected = today - timedelta(days=streak)
        # Allow the run to start either today or yesterday, then require consecutive days.
        if offset == 0 and (today - parsed).days > 1:
            break
        if parsed == expected or (offset == 0 and (today - parsed).days == 1):
            streak += 1
        else:
            break
    return streak
# The headline numbers for the dashboard, in one pass over this user's data.
def dashboard_summary(user_id: str, now: datetime | None = None) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    states = mastery_for_user(user_id, now=moment)
    summary = summarise(states)
    with session() as connection:
        events = EventRepository(connection)
        quiz_correct, quiz_total = events.accuracy(user_id, "quiz")
        code_correct, code_total = events.accuracy(user_id, "coding")
        review_correct, review_total = events.accuracy(user_id, "review")
    summary.update(
        {
            "quiz_accuracy": round(quiz_correct / quiz_total * 100, 1) if quiz_total else None,
            "coding_accuracy": round(code_correct / code_total * 100, 1) if code_total else None,
            "review_accuracy": round(review_correct / review_total * 100, 1) if review_total else None,
            "quiz_answered": quiz_total,
            "coding_solved": code_correct,
            "coding_attempted": code_total,
            "reviews_done": review_total,
            "reviews_due": len(due_reviews(user_id, moment, limit=100)),
            "streak": study_streak(user_id, moment),
        }
    )
    return summary
# Mastery grouped by subject, for the knowledge dashboard.
def mastery_by_subject(user_id: str, now: datetime | None = None) -> dict[str, list[MasteryState]]:
    grouped: dict[str, list[MasteryState]] = {}
    for state in mastery_for_user(user_id, now=now):
        grouped.setdefault(state.subject or "General", []).append(state)
    for states in grouped.values():
        states.sort(key=lambda state: state.mastery_score)
    return dict(sorted(grouped.items()))
# What the app recommends doing about a concept right now.
def recommendation_for(user_id: str, concept_slug: str) -> dict[str, Any]:
    state = mastery_for_concept(user_id, concept_slug)
    if state is None:
        return {"action": "continue", "mastery": 0.0, "mistakes": []}
    return {
        "action": next_action(state),
        "mastery": state.mastery_score,
        "difficulty": state.current_difficulty,
        "status": state.learning_status,
        "mistakes": mistakes_for_concept(user_id, concept_slug),
    }
# Turn raw concept names from anywhere into registered concepts.
def register_names(names: list[str], subject: str = "") -> list[Concept]:
    concepts = [c for c in (make_concept(name, subject) for name in names) if c]
    if concepts:
        ensure_concepts(concepts)
    return concepts
