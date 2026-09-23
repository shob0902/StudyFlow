# The knowledge node: turn a graded quiz attempt into concept-level mastery.
#
# This is where the tutoring loop meets the knowledge graph. It runs after evaluate_answers and
# before the router, so the decision about what to do next is made from mastery rather than from
# the raw score alone. It is one node, not four, because mapping concepts and recording them is
# a single logical step — splitting it would add graph boxes without adding meaning.
from typing import Any
from db import learning_service
from learning.concepts import make_concept, make_concepts
from learning.mastery import (
    ACTION_LABELS,
    ACTIVITY_QUIZ,
    Attempt,
    MEDIUM,
    difficulty_for,
    next_action,
)
from learning.misconceptions import CATEGORY_LABELS, classify_attempt
from utils.helpers import log_step
# The concepts a study session is about: its topic, plus the key concepts the tutor identified.
def concepts_for_state(state: dict[str, Any]) -> list:
    analysis = state.get("topic_analysis") or {}
    subject = analysis.get("subject_area", "")
    names = [analysis.get("clean_topic") or state.get("topic", "")]
    names.extend(analysis.get("key_concepts") or [])
    return make_concepts([name for name in names if name], subject)
# Build one attempt per concept from a graded quiz.
#
# The topic concept gets the attempt's actual score, so a 60% quiz is 60% evidence rather than a
# flat pass or fail. Concepts the tutor flagged as weak are recorded as incorrect; the others
# follow the overall result. This is deliberately deterministic — no extra LLM call.
def attempts_from_quiz(state: dict[str, Any], attempt: dict[str, Any]) -> list[Attempt]:
    concepts = concepts_for_state(state)
    if not concepts:
        return []
    analysis = state.get("topic_analysis") or {}
    subject = analysis.get("subject_area", "")
    difficulty = state.get("quiz_difficulty") or MEDIUM
    score = float(attempt.get("score", 0.0)) / 100.0
    passed = bool(attempt.get("passed"))
    weak = {c.slug for c in make_concepts(attempt.get("weak_concepts") or [], subject)}
    topic_concept = concepts[0]
    out = [
        Attempt(
            concept_slug=topic_concept.slug,
            correct=passed,
            score=score,
            difficulty=difficulty,
            activity=ACTIVITY_QUIZ,
            concept_name=topic_concept.name,
            subject=topic_concept.subject,
        )
    ]
    for concept in concepts[1:]:
        is_weak = concept.slug in weak
        out.append(
            Attempt(
                concept_slug=concept.slug,
                correct=passed and not is_weak,
                score=0.0 if is_weak else score,
                difficulty=difficulty,
                activity=ACTIVITY_QUIZ,
                concept_name=concept.name,
                subject=concept.subject,
            )
        )
    # A weak concept the analysis never listed still deserves a row.
    known = {c.slug for c in concepts}
    for concept in make_concepts(attempt.get("weak_concepts") or [], subject):
        if concept.slug not in known:
            out.append(
                Attempt(
                    concept_slug=concept.slug, correct=False, score=0.0, difficulty=difficulty,
                    activity=ACTIVITY_QUIZ, concept_name=concept.name, subject=concept.subject,
                )
            )
    return out
# Record why the wrong answers were wrong, against the concepts they belong to.
def record_misconceptions(user_id: str, state: dict[str, Any], attempt: dict[str, Any]) -> str:
    results = attempt.get("results") or []
    categories, dominant = classify_attempt(results)
    if not dominant:
        return ""
    analysis = state.get("topic_analysis") or {}
    subject = analysis.get("subject_area", "")
    weak_names = attempt.get("weak_concepts") or [analysis.get("clean_topic") or state.get("topic", "")]
    note = attempt.get("study_tip") or ""
    for concept in make_concepts(weak_names, subject):
        learning_service.record_mistake(user_id, concept.slug, dominant, note, source="quiz")
    log_step("NODE", f"Recorded misconception: {CATEGORY_LABELS.get(dominant, dominant)}")
    return dominant
# Node: map the latest attempt onto concepts, update mastery and decide what to do next.
def update_knowledge(state: dict[str, Any]) -> dict[str, Any]:
    attempts = state.get("attempts") or []
    if not attempts:
        return {}
    latest = attempts[-1]
    user_id = state.get("user_id", "")
    concept_attempts = attempts_from_quiz(state, latest)
    if not concept_attempts:
        return {}
    log_step("NODE", f"Updating mastery for {len(concept_attempts)} concept(s)")
    # The terminal demo runs without a signed-in user; scoring still happens, storage does not.
    if not user_id:
        log_step("NODE", "No signed-in user, so mastery is not stored")
        return {"concepts": [_concept_row(a) for a in concept_attempts]}
    updated = learning_service.record_attempts(user_id, concept_attempts, source="quiz")
    misconception = record_misconceptions(user_id, state, latest)
    topic_slug = concept_attempts[0].concept_slug
    topic_state = updated.get(topic_slug)
    action = next_action(topic_state) if topic_state else ""
    difficulty = difficulty_for(topic_state.mastery_score) if topic_state else MEDIUM
    if topic_state:
        log_step(
            "MASTERY",
            f"{topic_state.concept_name}: {topic_state.mastery_score:.0f}% "
            f"({topic_state.learning_status}) -> {ACTION_LABELS.get(action, action)}",
        )
    return {
        "concepts": [
            _concept_row(attempt, updated.get(attempt.concept_slug)) for attempt in concept_attempts
        ],
        "mastery": {
            "topic_slug": topic_slug,
            "score": topic_state.mastery_score if topic_state else 0.0,
            "status": topic_state.learning_status if topic_state else "unknown",
            "confidence": topic_state.confidence if topic_state else 0.0,
            "misconception": misconception,
            "mistakes": learning_service.mistakes_for_concept(user_id, topic_slug),
        },
        "adaptive_action": action,
        "quiz_difficulty": difficulty,
    }
# A concept row for the state, carrying the new score when there is one.
def _concept_row(attempt: Attempt, state: Any = None) -> dict[str, Any]:
    return {
        "slug": attempt.concept_slug,
        "name": attempt.concept_name,
        "subject": attempt.subject,
        "mastery": round(state.mastery_score, 1) if state else None,
        "status": state.learning_status if state else "unknown",
    }
# Register the concepts of a topic before teaching it, and report what the learner already knows.
# Used by the tutor UI to show prior knowledge, and by document and coding practice alike.
def prior_knowledge(user_id: str, names: list[str], subject: str = "") -> dict[str, Any]:
    concepts = learning_service.register_names(names, subject)
    known = learning_service.mastery_map(user_id) if user_id else {}
    return {
        concept.slug: {
            "name": concept.name,
            "subject": concept.subject,
            "mastery": known[concept.slug].mastery_score if concept.slug in known else None,
            "status": known[concept.slug].learning_status if concept.slug in known else "unknown",
        }
        for concept in concepts
    }
