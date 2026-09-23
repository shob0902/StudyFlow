# The mastery algorithm and the difficulty strategy built on it.
# Deterministic and configurable: no LLM call is needed to score an attempt, so mastery updates
# are cheap, repeatable and testable. Every learning activity funnels through update_mastery().
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any
# What a learner can be doing when they practise a concept.
ACTIVITY_QUIZ = "quiz"
ACTIVITY_DOCUMENT = "document"
ACTIVITY_REVIEW = "review"
ACTIVITY_CODING = "coding"
ACTIVITIES = (ACTIVITY_QUIZ, ACTIVITY_DOCUMENT, ACTIVITY_REVIEW, ACTIVITY_CODING)
# Difficulty levels, easiest first.
EASY = "easy"
MEDIUM = "medium"
HARD = "hard"
CHALLENGE = "challenge"
DIFFICULTIES = (EASY, MEDIUM, HARD, CHALLENGE)
# Learning statuses, derived from the numeric score rather than tracked separately.
UNKNOWN = "unknown"
WEAK = "weak"
LEARNING = "learning"
PROFICIENT = "proficient"
MASTERED = "mastered"
# What the system should do next for a concept.
CONTINUE = "continue"
INCREASE_DIFFICULTY = "increase_difficulty"
DECREASE_DIFFICULTY = "decrease_difficulty"
RE_EXPLAIN = "re_explain"
TARGETED_PRACTICE = "targeted_practice"
PREREQUISITE_REVIEW = "prerequisite_review"
NEXT_CONCEPT = "next_concept"
# Every number the algorithm uses, in one place so it can be tuned without touching the logic.
@dataclass(frozen=True)
class MasteryConfig:
    # How strongly the newest attempt moves the score. Higher = recent performance dominates.
    learning_rate: float = 0.34
    # The first few attempts move the score faster, so a new concept finds its level quickly.
    warmup_attempts: int = 3
    warmup_multiplier: float = 1.5
    # A correct hard question is worth more than a correct easy one.
    difficulty_weight: dict[str, float] = field(
        default_factory=lambda: {EASY: 0.75, MEDIUM: 1.0, HARD: 1.25, CHALLENGE: 1.45}
    )
    # Losses are weighted the other way round: getting an easy question wrong says far more
    # about a gap than missing a hard one, which is expected while learning.
    wrong_difficulty_weight: dict[str, float] = field(
        default_factory=lambda: {EASY: 1.3, MEDIUM: 1.0, HARD: 0.75, CHALLENGE: 0.6}
    )
    # Ceiling an attempt at each difficulty can push mastery to: you cannot master a concept
    # on easy questions alone.
    difficulty_ceiling: dict[str, float] = field(
        default_factory=lambda: {EASY: 70.0, MEDIUM: 88.0, HARD: 97.0, CHALLENGE: 100.0}
    )
    # Repeated wrong answers on the same concept hurt more than a single slip.
    streak_penalty: float = 4.0
    streak_bonus: float = 3.0
    max_streak_effect: int = 3
    # Knowledge fades. Mastery decays towards a floor with this half-life, in days.
    decay_half_life_days: float = 45.0
    decay_floor_ratio: float = 0.55
    # Confidence rises with the number of attempts; this is the count at which it reaches ~63%.
    confidence_scale: float = 4.0
    # Where the status labels sit on the 0-100 scale.
    weak_below: float = 40.0
    learning_below: float = 65.0
    proficient_below: float = 85.0
    # A concept with too few attempts is not called mastered however well it scores.
    mastered_min_attempts: int = 4
    # Which difficulty to serve at each mastery band.
    difficulty_bands: tuple[tuple[float, str], ...] = (
        (40.0, EASY),
        (65.0, MEDIUM),
        (85.0, HARD),
        (101.0, CHALLENGE),
    )
    # Where a concept starts before anything is known about it.
    starting_score: float = 50.0
DEFAULT_CONFIG = MasteryConfig()
# One concept's state for one user. Mirrors the stored row, but carries no database concerns.
@dataclass(frozen=True)
class MasteryState:
    concept_slug: str
    concept_name: str = ""
    subject: str = ""
    mastery_score: float = 0.0
    confidence: float = 0.0
    attempts: int = 0
    correct_attempts: int = 0
    incorrect_attempts: int = 0
    consecutive_correct: int = 0
    consecutive_incorrect: int = 0
    current_difficulty: str = MEDIUM
    last_attempted_at: str = ""
    last_correct_at: str = ""
    learning_status: str = UNKNOWN
    # True once the learner has practised this at all.
    @property
    def is_started(self) -> bool:
        return self.attempts > 0
# The outcome of one piece of practice, whatever produced it.
@dataclass(frozen=True)
class Attempt:
    concept_slug: str
    correct: bool
    difficulty: str = MEDIUM
    activity: str = ACTIVITY_QUIZ
    # 0.0-1.0 for partial credit, such as 8 of 10 coding tests passing. Defaults to correctness.
    score: float | None = None
    concept_name: str = ""
    subject: str = ""
    # How well this attempt went, on 0-1.
    @property
    def quality(self) -> float:
        if self.score is not None:
            return max(0.0, min(1.0, float(self.score)))
        return 1.0 if self.correct else 0.0
# Current UTC time as an ISO string.
def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
# Parse a stored timestamp, treating a naive value as UTC.
def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
# The status label for a score. Labels are a view of the number, never a separate truth.
def status_for(score: float, attempts: int, config: MasteryConfig = DEFAULT_CONFIG) -> str:
    if attempts <= 0:
        return UNKNOWN
    if score < config.weak_below:
        return WEAK
    if score < config.learning_below:
        return LEARNING
    if score < config.proficient_below:
        return PROFICIENT
    return MASTERED if attempts >= config.mastered_min_attempts else PROFICIENT
# The difficulty to serve next for a given mastery score.
def difficulty_for(score: float, config: MasteryConfig = DEFAULT_CONFIG) -> str:
    for ceiling, level in config.difficulty_bands:
        if score < ceiling:
            return level
    return CHALLENGE
# Confidence in the score itself: how much evidence is behind it, on 0-1.
def confidence_for(attempts: int, config: MasteryConfig = DEFAULT_CONFIG) -> float:
    if attempts <= 0:
        return 0.0
    return round(1.0 - math.exp(-attempts / max(config.confidence_scale, 0.1)), 4)
# What a score decays to after time away from a concept. Knowledge fades, but not to nothing:
# it settles at a floor, because having learnt something once still counts for something.
def decayed_score(
    score: float, last_attempted_at: str, now: datetime | None = None,
    config: MasteryConfig = DEFAULT_CONFIG,
) -> float:
    moment = _parse(last_attempted_at)
    if moment is None or score <= 0:
        return score
    days = max((now or datetime.now(timezone.utc)) - moment, timedelta(0)).total_seconds() / 86400
    if days <= 0 or config.decay_half_life_days <= 0:
        return score
    floor = score * config.decay_floor_ratio
    decayed = floor + (score - floor) * math.pow(0.5, days / config.decay_half_life_days)
    return round(max(0.0, min(100.0, decayed)), 2)
# Apply one attempt to a concept's state and return the new state.
#
# The score is an exponential moving average of attempt quality, not correct/total, so recent
# work counts for much more than old work. On top of that:
#   - the target an attempt pulls towards is capped by its difficulty, so easy questions cannot
#     carry a concept to mastery;
#   - difficulty weights how far the score moves;
#   - runs of right or wrong answers add a consistency bonus or penalty;
#   - time since the last attempt is applied as decay before the update.
def update_mastery(
    state: MasteryState,
    attempt: Attempt,
    now: datetime | None = None,
    config: MasteryConfig = DEFAULT_CONFIG,
) -> MasteryState:
    now = now or datetime.now(timezone.utc)
    difficulty = attempt.difficulty if attempt.difficulty in config.difficulty_weight else MEDIUM
    quality = attempt.quality
    correct = attempt.correct
    # Start from the decayed score so a long gap is accounted for before new evidence lands.
    base = decayed_score(state.mastery_score, state.last_attempted_at, now, config) if state.is_started else config.starting_score
    ceiling = config.difficulty_ceiling.get(difficulty, 88.0)
    target = quality * ceiling if quality > 0 else 0.0
    weights = config.difficulty_weight if quality >= 0.5 else config.wrong_difficulty_weight
    rate = config.learning_rate * weights.get(difficulty, 1.0)
    if state.attempts < config.warmup_attempts:
        rate *= config.warmup_multiplier
    rate = max(0.05, min(0.9, rate))
    score = base + (target - base) * rate
    # Consistency: a run of correct answers is evidence of real mastery, a run of wrong answers
    # is evidence the concept is not there at all.
    consecutive_correct = state.consecutive_correct + 1 if correct else 0
    consecutive_incorrect = 0 if correct else state.consecutive_incorrect + 1
    if consecutive_correct > 1:
        bonus = config.streak_bonus * min(consecutive_correct - 1, config.max_streak_effect)
        # The bonus may not push a concept past what this difficulty can prove, unless the
        # learner was already above that from harder work. Without this cap the bonus would
        # compound on every attempt and easy questions alone would reach 100%.
        score = min(score + bonus, max(ceiling, base))
    if consecutive_incorrect > 1:
        score -= config.streak_penalty * min(consecutive_incorrect - 1, config.max_streak_effect)
    score = round(max(0.0, min(100.0, score)), 2)
    attempts = state.attempts + 1
    return MasteryState(
        concept_slug=state.concept_slug,
        concept_name=attempt.concept_name or state.concept_name,
        subject=attempt.subject or state.subject,
        mastery_score=score,
        confidence=confidence_for(attempts, config),
        attempts=attempts,
        correct_attempts=state.correct_attempts + (1 if correct else 0),
        incorrect_attempts=state.incorrect_attempts + (0 if correct else 1),
        consecutive_correct=consecutive_correct,
        consecutive_incorrect=consecutive_incorrect,
        current_difficulty=difficulty_for(score, config),
        last_attempted_at=_now_iso(now),
        last_correct_at=_now_iso(now) if correct else state.last_correct_at,
        learning_status=status_for(score, attempts, config),
    )
# A fresh state for a concept nobody has practised yet.
def new_state(concept_slug: str, concept_name: str = "", subject: str = "") -> MasteryState:
    return MasteryState(
        concept_slug=concept_slug, concept_name=concept_name, subject=subject,
        mastery_score=0.0, learning_status=UNKNOWN, current_difficulty=MEDIUM,
    )
# What the app should do next for one concept, given where the learner is.
# Kept as one function so the policy lives in a single place rather than as thresholds sprinkled
# through the graph and the UI.
def next_action(state: MasteryState, config: MasteryConfig = DEFAULT_CONFIG) -> str:
    if not state.is_started:
        return CONTINUE
    if state.consecutive_incorrect >= 3:
        return PREREQUISITE_REVIEW
    if state.mastery_score < config.weak_below:
        return RE_EXPLAIN if state.consecutive_incorrect >= 2 else TARGETED_PRACTICE
    if state.mastery_score < config.learning_below:
        return DECREASE_DIFFICULTY if state.consecutive_incorrect >= 1 else CONTINUE
    if state.learning_status == MASTERED:
        return NEXT_CONCEPT
    if state.consecutive_correct >= 2:
        return INCREASE_DIFFICULTY
    return CONTINUE
# A short, human explanation of a next action, for the UI.
ACTION_LABELS = {
    CONTINUE: "Keep going at this level",
    INCREASE_DIFFICULTY: "Ready for harder questions",
    DECREASE_DIFFICULTY: "Step back to easier questions",
    RE_EXPLAIN: "Needs explaining again, more simply",
    TARGETED_PRACTICE: "Needs focused practice",
    PREREQUISITE_REVIEW: "Check the prerequisites first",
    NEXT_CONCEPT: "Mastered — move on",
}
# The overall picture across many concepts, for the dashboard.
def overall_mastery(states: list[MasteryState]) -> float:
    started = [state for state in states if state.is_started]
    if not started:
        return 0.0
    # Weight by confidence so a concept with one lucky answer does not swing the headline number.
    total_weight = sum(max(state.confidence, 0.15) for state in started)
    weighted = sum(state.mastery_score * max(state.confidence, 0.15) for state in started)
    return round(weighted / total_weight, 1) if total_weight else 0.0
# The concepts most worth working on: low mastery first, but only ones with real evidence.
def weakest(states: list[MasteryState], limit: int = 5) -> list[MasteryState]:
    started = [state for state in states if state.is_started]
    return sorted(started, key=lambda state: (state.mastery_score, -state.attempts))[:limit]
# Apply time decay to a stored state without recording an attempt, for display.
def with_decay(
    state: MasteryState, now: datetime | None = None, config: MasteryConfig = DEFAULT_CONFIG
) -> MasteryState:
    if not state.is_started:
        return state
    score = decayed_score(state.mastery_score, state.last_attempted_at, now, config)
    return replace(
        state,
        mastery_score=score,
        learning_status=status_for(score, state.attempts, config),
        current_difficulty=difficulty_for(score, config),
    )
# Summarise a set of states for the dashboard.
def summarise(states: list[MasteryState]) -> dict[str, Any]:
    started = [state for state in states if state.is_started]
    by_status: dict[str, int] = {}
    for state in started:
        by_status[state.learning_status] = by_status.get(state.learning_status, 0) + 1
    return {
        "concepts": len(started),
        "overall_mastery": overall_mastery(started),
        "attempts": sum(state.attempts for state in started),
        "correct": sum(state.correct_attempts for state in started),
        "by_status": by_status,
        "weakest": weakest(started, 5),
    }
