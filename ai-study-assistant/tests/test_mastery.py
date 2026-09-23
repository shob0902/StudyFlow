# The mastery engine: how a score moves, what it decides, and how mistakes are classified.
from datetime import datetime, timedelta, timezone
import pytest
from learning.concepts import Concept, make_concept, make_concepts, slugify
from learning.mastery import (
    CHALLENGE,
    DEFAULT_CONFIG,
    EASY,
    HARD,
    LEARNING,
    MASTERED,
    MEDIUM,
    Attempt,
    MasteryConfig,
    WEAK,
    confidence_for,
    decayed_score,
    difficulty_for,
    new_state,
    next_action,
    overall_mastery,
    status_for,
    summarise,
    update_mastery,
    weakest,
    with_decay,
)
from learning import mastery as mastery_module
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
# A concept the learner has not met yet.
@pytest.fixture
def fresh():
    return new_state("dsa::binary_search", "Binary Search", "DSA")
# Apply a run of attempts and return the final state.
def _run(state, count, correct, difficulty=MEDIUM, now=NOW):
    for offset in range(count):
        state = update_mastery(
            state,
            Attempt(state.concept_slug, correct=correct, difficulty=difficulty),
            now=now + timedelta(minutes=offset),
        )
    return state
# --- concept identity ---------------------------------------------------
# The same idea written different ways lands on one concept.
def test_concept_names_normalise_to_one_slug():
    assert slugify("Binary Search", "DSA") == slugify("the binary search", "DSA")
    assert slugify("What is Binary Search?", "DSA") == "dsa::binary_search"
# Concepts carry a subject, guessed when it is not given.
def test_subject_is_inferred():
    assert make_concept("Dynamic Programming").subject == "DSA"
    assert make_concept("SQL Window Functions").subject == "SQL"
    assert make_concept("Python Decorators").subject == "Python"
    assert make_concept("Photosynthesis").subject == "Science"
# Duplicates collapse, order is kept, junk is dropped.
def test_concept_lists_are_deduplicated():
    concepts = make_concepts(["Recursion", "recursion", "", "a", "Trees"])
    assert [c.name for c in concepts] == ["Recursion", "Trees"]
# --- mastery movement ---------------------------------------------------
# A brand new concept has no score and no status.
def test_new_concept_is_unknown(fresh):
    assert fresh.mastery_score == 0
    assert fresh.learning_status == "unknown"
    assert not fresh.is_started
    assert next_action(fresh) == "continue"
# Mastery is not correct-over-total: the same ratio scores differently depending on when the
# right answers happened.
def test_mastery_is_not_a_simple_ratio(fresh):
    improving = _run(_run(fresh, 3, False), 3, True)
    declining = _run(_run(fresh, 3, True), 3, False)
    assert improving.correct_attempts == declining.correct_attempts == 3
    assert improving.attempts == declining.attempts == 6
    assert improving.mastery_score > declining.mastery_score + 20
# Recent performance dominates: a strong recent run recovers a bad start.
def test_recent_performance_dominates(fresh):
    state = _run(fresh, 4, False, EASY)
    assert state.mastery_score < 20
    state = _run(state, 4, True, MEDIUM)
    assert state.mastery_score > 60
# Correct answers on hard questions are worth more than on easy ones.
def test_difficulty_weights_the_evidence(fresh):
    easy = _run(fresh, 3, True, EASY)
    hard = _run(fresh, 3, True, HARD)
    assert hard.mastery_score > easy.mastery_score
# Easy questions alone cannot carry a concept to mastery, because of the difficulty ceiling.
def test_easy_questions_cannot_reach_mastery(fresh):
    state = _run(fresh, 10, True, EASY)
    assert state.mastery_score < 85
    assert state.learning_status != MASTERED
# A wrong easy question costs more than a wrong hard one.
def test_wrong_easy_costs_more_than_wrong_hard(fresh):
    started = _run(fresh, 2, True, MEDIUM)
    after_easy = update_mastery(started, Attempt(started.concept_slug, correct=False, difficulty=EASY), now=NOW)
    after_hard = update_mastery(started, Attempt(started.concept_slug, correct=False, difficulty=HARD), now=NOW)
    assert after_easy.mastery_score < after_hard.mastery_score
# Repeated mistakes hurt more than a single slip.
def test_repeated_mistakes_compound(fresh):
    started = _run(fresh, 3, True, MEDIUM)
    one = update_mastery(started, Attempt(started.concept_slug, correct=False), now=NOW)
    two = update_mastery(one, Attempt(started.concept_slug, correct=False), now=NOW)
    three = update_mastery(two, Attempt(started.concept_slug, correct=False), now=NOW)
    assert one.mastery_score - two.mastery_score > 0
    assert two.mastery_score - three.mastery_score > 0
    assert three.consecutive_incorrect == 3
# Partial credit counts: eight of ten coding tests is not the same as failing.
def test_partial_credit_is_used(fresh):
    partial = update_mastery(fresh, Attempt(fresh.concept_slug, correct=False, score=0.8), now=NOW)
    failed = update_mastery(fresh, Attempt(fresh.concept_slug, correct=False, score=0.0), now=NOW)
    assert partial.mastery_score > failed.mastery_score
# Confidence grows with evidence and never exceeds one.
def test_confidence_grows_with_attempts():
    assert confidence_for(0) == 0.0
    assert confidence_for(1) < confidence_for(5) < confidence_for(20) <= 1.0
# --- decay --------------------------------------------------------------
# Knowledge fades with time away, but settles at a floor rather than vanishing.
def test_mastery_decays_towards_a_floor():
    long_ago = (NOW - timedelta(days=180)).isoformat()
    faded = decayed_score(80.0, long_ago, NOW)
    assert 40 < faded < 60
    assert decayed_score(80.0, NOW.isoformat(), NOW) == 80.0
# Decay is applied before new evidence, so a long gap shows up in the next attempt.
def test_decay_applies_before_an_attempt(fresh):
    strong = _run(fresh, 4, True, HARD)
    stale = update_mastery(
        strong, Attempt(strong.concept_slug, correct=True, difficulty=HARD), now=NOW + timedelta(days=200)
    )
    fresh_again = update_mastery(
        strong, Attempt(strong.concept_slug, correct=True, difficulty=HARD), now=NOW
    )
    assert stale.mastery_score < fresh_again.mastery_score
# Viewing a state applies decay without inventing an attempt.
def test_with_decay_does_not_record_an_attempt(fresh):
    state = _run(fresh, 4, True, HARD)
    later = with_decay(state, NOW + timedelta(days=120))
    assert later.attempts == state.attempts
    assert later.mastery_score < state.mastery_score
# --- statuses and difficulty -------------------------------------------
# Labels follow the number, and mastery needs evidence as well as a high score.
def test_status_follows_score_and_evidence():
    assert status_for(0, 0) == "unknown"
    assert status_for(20, 3) == WEAK
    assert status_for(50, 3) == LEARNING
    assert status_for(95, 2) == "proficient"
    assert status_for(95, 8) == MASTERED
# Difficulty rises with mastery.
def test_difficulty_follows_mastery():
    assert difficulty_for(10) == EASY
    assert difficulty_for(50) == MEDIUM
    assert difficulty_for(75) == HARD
    assert difficulty_for(95) == CHALLENGE
# The whole policy is configurable rather than hard-coded at each site.
def test_thresholds_are_configurable(fresh):
    strict = MasteryConfig(weak_below=60.0, learning_below=80.0, difficulty_bands=((60.0, EASY), (101.0, HARD)))
    assert status_for(50, 3, strict) == WEAK
    assert difficulty_for(50, strict) == EASY
    assert status_for(50, 3) == LEARNING
# --- next action --------------------------------------------------------
# A weak concept with repeated failures is sent back to prerequisites.
def test_repeated_failure_asks_for_prerequisites(fresh):
    state = _run(fresh, 3, False)
    assert next_action(state) == "prerequisite_review"
# A weak concept gets targeted practice or a re-explanation.
def test_weak_concept_gets_practice(fresh):
    state = update_mastery(fresh, Attempt(fresh.concept_slug, correct=False, score=0.1), now=NOW)
    assert state.learning_status == WEAK
    assert next_action(state) in ("targeted_practice", "re_explain")
# A consistently right learner is moved up.
def test_success_increases_difficulty(fresh):
    state = _run(fresh, 3, True, MEDIUM)
    assert next_action(state) in ("increase_difficulty", "next_concept")
# A mastered concept is left alone.
def test_mastered_concept_moves_on(fresh):
    state = _run(fresh, 8, True, CHALLENGE)
    assert state.learning_status == MASTERED
    assert next_action(state) == "next_concept"
# --- aggregates ---------------------------------------------------------
# The headline number weights by confidence, so one lucky answer cannot swing it.
def test_overall_mastery_weights_by_confidence(fresh):
    solid = _run(new_state("a", "A", "S"), 8, True, HARD)
    lucky = update_mastery(new_state("b", "B", "S"), Attempt("b", correct=True), now=NOW)
    combined = overall_mastery([solid, lucky])
    assert solid.mastery_score > combined > lucky.mastery_score - 30
# The weakest concepts come first, and unstarted ones are left out.
def test_weakest_lists_started_concepts_only(fresh):
    strong = _run(new_state("a", "A", "S"), 5, True, HARD)
    weak_state = _run(new_state("b", "B", "S"), 3, False)
    untouched = new_state("c", "C", "S")
    assert [s.concept_slug for s in weakest([strong, weak_state, untouched])] == ["b", "a"]
# The summary reports what the dashboard needs.
def test_summary_shape(fresh):
    states = [_run(new_state("a", "A", "S"), 4, True, HARD), _run(new_state("b", "B", "S"), 2, False)]
    summary = summarise(states)
    assert summary["concepts"] == 2
    assert summary["attempts"] == 6
    assert set(summary["by_status"]) <= {WEAK, LEARNING, "proficient", MASTERED}
    assert len(summary["weakest"]) == 2
