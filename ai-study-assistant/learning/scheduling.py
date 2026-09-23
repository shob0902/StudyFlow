# Spaced repetition: when a concept should next be reviewed.
# An SM-2 style algorithm, adapted so mastery has a say: a shaky concept comes back sooner than
# its interval alone would suggest. Every number lives in ReviewConfig.
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from learning import mastery as mastery_module
# Every knob the scheduler uses.
@dataclass(frozen=True)
class ReviewConfig:
    # The ladder a concept climbs while it keeps being recalled correctly.
    first_intervals: tuple[int, ...] = (1, 3, 7, 14, 30)
    # Beyond the ladder, the interval is multiplied by the ease factor.
    initial_ease: float = 2.2
    min_ease: float = 1.3
    max_ease: float = 2.8
    ease_gain: float = 0.12
    ease_loss: float = 0.22
    # A failed review does not reset to zero, it drops back sharply.
    lapse_ratio: float = 0.3
    min_interval_days: int = 1
    max_interval_days: int = 180
    # Mastery caps the interval: you do not get a month off a concept you are weak at.
    mastery_caps: tuple[tuple[float, int], ...] = (
        (40.0, 2),
        (65.0, 5),
        (85.0, 14),
        (101.0, 180),
    )
    # How good an attempt has to be to count as a successful review.
    pass_quality: float = 0.6
DEFAULT_REVIEW_CONFIG = ReviewConfig()
# When a concept is due, and the history behind that decision.
@dataclass(frozen=True)
class ReviewState:
    concept_slug: str
    interval_days: int = 0
    ease: float = DEFAULT_REVIEW_CONFIG.initial_ease
    review_count: int = 0
    lapses: int = 0
    last_reviewed_at: str = ""
    next_review_at: str = ""
# Current UTC time.
def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)
# Parse a stored timestamp, treating a naive value as UTC.
def parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
# The longest interval allowed at a given mastery score.
def interval_cap(mastery_score: float, config: ReviewConfig = DEFAULT_REVIEW_CONFIG) -> int:
    for ceiling, cap in config.mastery_caps:
        if mastery_score < ceiling:
            return cap
    return config.max_interval_days
# Work out the next interval after a review.
# Success climbs the ladder, then multiplies by ease. Failure drops to a fraction of the current
# interval, which is why a failed 7-day concept comes back in about 2 days rather than a month.
def next_interval(
    state: ReviewState, passed: bool, mastery_score: float = 50.0,
    config: ReviewConfig = DEFAULT_REVIEW_CONFIG,
) -> int:
    if not passed:
        dropped = int(round(max(state.interval_days, 1) * config.lapse_ratio))
        return max(config.min_interval_days, min(dropped, interval_cap(mastery_score, config)))
    # schedule_new already placed the concept on the first rung, so a successful review moves
    # to the next one: learn -> 1 day, then 3, 7, 14, 30, then ease-multiplied.
    step = state.review_count + 1 if state.interval_days else 0
    if step < len(config.first_intervals):
        interval = config.first_intervals[step]
    else:
        interval = int(round(max(state.interval_days, 1) * state.ease))
    interval = max(config.min_interval_days, min(interval, config.max_interval_days))
    return min(interval, interval_cap(mastery_score, config))
# Record a review and return the concept's new schedule.
def review(
    state: ReviewState, quality: float, mastery_score: float = 50.0,
    now: datetime | None = None, config: ReviewConfig = DEFAULT_REVIEW_CONFIG,
) -> ReviewState:
    moment = _now(now)
    passed = quality >= config.pass_quality
    ease = state.ease + (config.ease_gain if passed else -config.ease_loss)
    ease = round(max(config.min_ease, min(config.max_ease, ease)), 3)
    interval = next_interval(state, passed, mastery_score, config)
    return ReviewState(
        concept_slug=state.concept_slug,
        interval_days=interval,
        ease=ease,
        review_count=state.review_count + 1 if passed else state.review_count,
        lapses=state.lapses + (0 if passed else 1),
        last_reviewed_at=moment.isoformat(timespec="seconds"),
        next_review_at=(moment + timedelta(days=interval)).isoformat(timespec="seconds"),
    )
# The first schedule for a concept that has just been learnt.
def schedule_new(
    concept_slug: str, mastery_score: float = 50.0, now: datetime | None = None,
    config: ReviewConfig = DEFAULT_REVIEW_CONFIG,
) -> ReviewState:
    moment = _now(now)
    interval = min(config.first_intervals[0], interval_cap(mastery_score, config))
    return ReviewState(
        concept_slug=concept_slug,
        interval_days=interval,
        ease=config.initial_ease,
        review_count=0,
        last_reviewed_at=moment.isoformat(timespec="seconds"),
        next_review_at=(moment + timedelta(days=interval)).isoformat(timespec="seconds"),
    )
# Bring a review forward when mastery has dropped below what its interval assumes.
def reschedule_for_mastery(
    state: ReviewState, mastery_score: float, now: datetime | None = None,
    config: ReviewConfig = DEFAULT_REVIEW_CONFIG,
) -> ReviewState:
    cap = interval_cap(mastery_score, config)
    if state.interval_days <= cap:
        return state
    anchor = parse(state.last_reviewed_at) or _now(now)
    return ReviewState(
        concept_slug=state.concept_slug,
        interval_days=cap,
        ease=state.ease,
        review_count=state.review_count,
        lapses=state.lapses,
        last_reviewed_at=state.last_reviewed_at,
        next_review_at=(anchor + timedelta(days=cap)).isoformat(timespec="seconds"),
    )
# True when a concept is due now.
def is_due(state: ReviewState, now: datetime | None = None) -> bool:
    moment = parse(state.next_review_at)
    return moment is None or moment <= _now(now)
# How overdue a concept is, in days. Negative means it is not due yet.
def days_overdue(state: ReviewState, now: datetime | None = None) -> float:
    moment = parse(state.next_review_at)
    if moment is None:
        return 0.0
    return round((_now(now) - moment).total_seconds() / 86400, 2)
# Everything due now, most urgent first: weakest concepts and most overdue come first.
def due_now(
    states: list[tuple[ReviewState, float]], now: datetime | None = None, limit: int = 20
) -> list[tuple[ReviewState, float]]:
    due = [(state, score) for state, score in states if is_due(state, now)]
    due.sort(key=lambda pair: (pair[1], -days_overdue(pair[0], now)))
    return due[:limit]
# The urgency band shown next to a due concept.
def urgency(mastery_score: float) -> str:
    if mastery_score < mastery_module.DEFAULT_CONFIG.weak_below:
        return "critical"
    if mastery_score < mastery_module.DEFAULT_CONFIG.learning_below:
        return "high"
    if mastery_score < mastery_module.DEFAULT_CONFIG.proficient_below:
        return "medium"
    return "low"
# Short words rather than coloured dots; the UI styles them by band.
URGENCY_MARKS = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
