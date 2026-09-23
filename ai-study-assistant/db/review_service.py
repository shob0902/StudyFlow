# Today's review: what is due, and what answering a review card does to mastery and the schedule.
#
# A review is just another activity, so it goes through learning_service.record_attempts() like
# everything else. The only difference is that the review activity advances the SM-2 interval.
from datetime import datetime, timezone
from typing import Any
from db import learning_service
from learning.mastery import ACTIVITY_REVIEW, Attempt
from learning.scheduling import URGENCY_MARKS, days_overdue, urgency
from utils.helpers import log_step
# One concept waiting to be reviewed.
def _card(state: Any, review: Any) -> dict[str, Any]:
    band = urgency(state.mastery_score)
    return {
        "concept_slug": state.concept_slug,
        "concept_name": state.concept_name,
        "subject": state.subject,
        "mastery": state.mastery_score,
        "status": state.learning_status,
        "urgency": band,
        "mark": URGENCY_MARKS[band],
        "overdue_days": days_overdue(review),
        "interval_days": review.interval_days,
        "review_count": review.review_count,
        "mistakes": [],
    }
# Everything due right now, most urgent first.
def due_today(user_id: str, now: datetime | None = None, limit: int = 20) -> list[dict[str, Any]]:
    moment = now or datetime.now(timezone.utc)
    cards = [_card(state, review) for state, review in learning_service.due_reviews(user_id, moment, limit)]
    for card in cards:
        card["mistakes"] = learning_service.mistakes_for_concept(user_id, card["concept_slug"], 2)
    return cards
# What is coming in the next week, for the plan view.
def upcoming(user_id: str, days: int = 7, now: datetime | None = None) -> list[dict[str, Any]]:
    moment = now or datetime.now(timezone.utc)
    return [
        _card(state, review)
        for state, review in learning_service.upcoming_reviews(user_id, days, moment)
    ]
# Record the outcome of reviewing one concept.
#
# quality is 0-1: a flashcard the student got right is 1, a half-remembered one is 0.5, a blank
# is 0. That feeds both the mastery score and the next interval.
def record_review(
    user_id: str, concept_slug: str, quality: float, concept_name: str = "", subject: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    quality = max(0.0, min(1.0, float(quality)))
    attempt = Attempt(
        concept_slug=concept_slug,
        correct=quality >= 0.6,
        score=quality,
        difficulty=_difficulty_for_review(user_id, concept_slug),
        activity=ACTIVITY_REVIEW,
        concept_name=concept_name,
        subject=subject,
    )
    updated = learning_service.record_attempts(user_id, [attempt], source="review", now=now)
    state = updated.get(concept_slug)
    log_step("REVIEW", f"{concept_name or concept_slug}: quality {quality:.1f}")
    if state is None:
        return {}
    return {
        "concept_slug": concept_slug,
        "mastery": state.mastery_score,
        "status": state.learning_status,
        "next_review_at": _next_review(user_id, concept_slug),
    }
# Review at the difficulty the concept currently sits at.
def _difficulty_for_review(user_id: str, concept_slug: str) -> str:
    state = learning_service.mastery_for_concept(user_id, concept_slug)
    return state.current_difficulty if state else "medium"
# When this concept comes back.
def _next_review(user_id: str, concept_slug: str) -> str:
    from db.database import session
    from db.mastery_repository import MasteryRepository
    with session() as connection:
        review = MasteryRepository(connection).get_review(user_id, concept_slug)
    return review.next_review_at if review else ""
# A review session: the cards to work through, with the questions already chosen.
#
# Flashcard-style recall for concepts with little history, multiple choice when there is a stored
# quiz question to reuse, and a coding prompt for concepts practised through code.
def build_session(user_id: str, limit: int = 8, now: datetime | None = None) -> list[dict[str, Any]]:
    cards = due_today(user_id, now, limit)
    for card in cards:
        card["mode"] = _mode_for(card)
    return cards
# Which kind of review suits this concept.
def _mode_for(card: dict[str, Any]) -> str:
    if card["mastery"] < 40:
        return "flashcard"
    if card["review_count"] >= 3 and card["mastery"] >= 70:
        return "recall"
    return "flashcard"
# How many reviews this user has done, for the dashboard.
def review_stats(user_id: str, now: datetime | None = None) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    due = learning_service.due_reviews(user_id, moment, limit=100)
    soon = learning_service.upcoming_reviews(user_id, 7, moment)
    return {
        "due_now": len(due),
        "due_this_week": len(soon),
        "weakest_due": due[0][0].concept_name if due else "",
    }
