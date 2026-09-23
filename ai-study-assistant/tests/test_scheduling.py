# Spaced repetition: how intervals grow, how they collapse after a lapse, and what is due.
from datetime import datetime, timedelta, timezone
import pytest
from learning.scheduling import (
    DEFAULT_REVIEW_CONFIG,
    ReviewConfig,
    ReviewState,
    days_overdue,
    due_now,
    interval_cap,
    is_due,
    next_interval,
    parse,
    reschedule_for_mastery,
    review,
    schedule_new,
    urgency,
)
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
STRONG = 90.0
# A concept just learnt.
@pytest.fixture
def new_card():
    return schedule_new("dsa::binary_search", mastery_score=STRONG, now=NOW)
# Review a card repeatedly with the given quality.
def _reviews(state, count, quality, mastery=STRONG, now=NOW):
    for step in range(count):
        state = review(state, quality, mastery, now=now + timedelta(days=step))
    return state
# A newly learnt concept comes back tomorrow.
def test_new_concept_is_due_tomorrow(new_card):
    assert new_card.interval_days == 1
    assert parse(new_card.next_review_at) == NOW + timedelta(days=1)
    assert new_card.review_count == 0
    assert not is_due(new_card, NOW)
    assert is_due(new_card, NOW + timedelta(days=1, minutes=1))
# Learning then reviewing walks the ladder: due after 1 day, then 3, 7, 14, 30.
def test_intervals_grow_on_success(new_card):
    state = new_card
    seen = [state.interval_days]
    for _ in range(4):
        state = review(state, 1.0, STRONG, now=NOW)
        seen.append(state.interval_days)
    assert seen == [1, 3, 7, 14, 30]
# Past the ladder, the interval multiplies by the ease factor.
def test_intervals_keep_growing_past_the_ladder(new_card):
    state = _reviews(new_card, 7, 1.0)
    assert state.interval_days > 30
    assert state.ease > DEFAULT_REVIEW_CONFIG.initial_ease
# Failing a review collapses the interval: 7 days becomes about 2.
def test_failure_shortens_the_interval():
    state = ReviewState(concept_slug="c", interval_days=7, ease=2.2, review_count=3)
    after = review(state, 0.0, STRONG, now=NOW)
    assert after.interval_days == 2
    assert after.lapses == 1
    assert after.ease < state.ease
    assert parse(after.next_review_at) == NOW + timedelta(days=2)
# Passing a review at 7 days roughly doubles it.
def test_success_lengthens_the_interval():
    state = ReviewState(concept_slug="c", interval_days=7, ease=2.0, review_count=5)
    after = review(state, 1.0, STRONG, now=NOW)
    assert after.interval_days == 14
    assert after.review_count == 6
    assert after.lapses == 0
# A half-remembered card counts as a failure, since recall was not solid.
def test_shaky_recall_counts_as_a_lapse():
    state = ReviewState(concept_slug="c", interval_days=10, ease=2.2, review_count=4)
    assert review(state, 0.5, STRONG, now=NOW).lapses == 1
    assert review(state, 0.9, STRONG, now=NOW).lapses == 0
# Ease is bounded, so a run of failures cannot drive it to nothing.
def test_ease_stays_within_bounds(new_card):
    collapsed = _reviews(new_card, 12, 0.0)
    assert collapsed.ease == DEFAULT_REVIEW_CONFIG.min_ease
    soaring = _reviews(new_card, 20, 1.0)
    assert soaring.ease <= DEFAULT_REVIEW_CONFIG.max_ease
# Mastery caps the interval: a weak concept never gets a month off.
def test_mastery_caps_the_interval():
    assert interval_cap(20.0) == 2
    assert interval_cap(50.0) == 5
    assert interval_cap(75.0) == 14
    assert interval_cap(95.0) == DEFAULT_REVIEW_CONFIG.max_interval_days
    state = ReviewState(concept_slug="c", interval_days=30, ease=2.5, review_count=6)
    assert review(state, 1.0, 30.0, now=NOW).interval_days == 2
# A concept whose mastery has dropped is pulled forward without waiting for its next review.
def test_dropping_mastery_brings_a_review_forward():
    state = ReviewState(
        concept_slug="c", interval_days=30, ease=2.2, review_count=5,
        last_reviewed_at=NOW.isoformat(),
        next_review_at=(NOW + timedelta(days=30)).isoformat(),
    )
    pulled = reschedule_for_mastery(state, 25.0, now=NOW)
    assert pulled.interval_days == 2
    assert parse(pulled.next_review_at) == NOW + timedelta(days=2)
    # A concept that is still strong is left alone.
    assert reschedule_for_mastery(state, 95.0, now=NOW) == state
# Nothing is hard-coded: a different configuration gives different intervals.
def test_schedule_is_configurable():
    config = ReviewConfig(first_intervals=(2, 5), lapse_ratio=0.5, min_interval_days=1)
    state = schedule_new("c", STRONG, NOW, config)
    assert state.interval_days == 2
    assert review(state, 1.0, STRONG, NOW, config).interval_days == 5
    lapsed = ReviewState(concept_slug="c", interval_days=10)
    assert next_interval(lapsed, False, STRONG, config) == 5
# Due cards are ordered weakest first, then most overdue.
def test_due_ordering_puts_the_weakest_first():
    overdue = ReviewState(concept_slug="a", next_review_at=(NOW - timedelta(days=5)).isoformat())
    just_due = ReviewState(concept_slug="b", next_review_at=(NOW - timedelta(hours=1)).isoformat())
    later = ReviewState(concept_slug="c", next_review_at=(NOW + timedelta(days=3)).isoformat())
    ordered = due_now([(overdue, 70.0), (just_due, 20.0), (later, 10.0)], NOW)
    assert [state.concept_slug for state, _ in ordered] == ["b", "a"]
    assert days_overdue(overdue, NOW) == 5.0
    assert days_overdue(later, NOW) < 0
# A card with no schedule yet counts as due.
def test_unscheduled_card_is_due():
    assert is_due(ReviewState(concept_slug="c"), NOW)
# Urgency bands follow mastery.
def test_urgency_bands():
    assert urgency(20) == "critical"
    assert urgency(50) == "high"
    assert urgency(75) == "medium"
    assert urgency(95) == "low"
