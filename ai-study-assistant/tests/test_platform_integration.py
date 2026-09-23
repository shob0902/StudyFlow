# The whole loop, end to end: document -> quiz -> mastery -> weakness -> review -> coding ->
# plan. These are the tests that would fail if the four features drifted into separate silos.
from datetime import datetime, timedelta, timezone
import pytest
from auth.errors import UnauthorizedError
from coding import grading, problems
from coding.problems import CodingProblem
from db import learning_service, plan_service, review_service
from graph.knowledge import attempts_from_quiz, concepts_for_state, update_knowledge
from learning.mastery import ACTIVITY_CODING, ACTIVITY_QUIZ, ACTIVITY_REVIEW, Attempt
from learning.planner import StudyGoal
from rag import store
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
DP_NOTES = b"""# Dynamic Programming

Dynamic programming solves problems with overlapping subproblems by storing results.
Memoization caches results top down; tabulation fills a table bottom up.
"""
DP = "dsa::dynamic_programming"
# A signed-in learner.
@pytest.fixture
def learner(users, db_file):
    return users.upsert_from_google("google-1", "ada@example.com", "Ada")
# A second learner, for isolation checks.
@pytest.fixture
def other(users, db_file):
    return users.upsert_from_google("google-2", "bob@example.com", "Bob")
# A binary search problem tagged with one concept.
def _problem(user_id, concepts=(DP,)):
    return problems.store_problem(
        user_id,
        CodingProblem(
            id="", user_id=user_id, title="Fibonacci", statement="Return the nth Fibonacci number.",
            language="python", difficulty="easy", signature="def fib(n):", constraints="",
            examples=[],
            tests=[
                {"input": "(0,)", "expected": "0"},
                {"input": "(1,)", "expected": "1"},
                {"input": "(10,)", "expected": "55"},
            ],
            concepts=list(concepts),
        ),
    )
WORKING_FIB = "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n"
# --- one concept, four sources -----------------------------------------
# A quiz, a document quiz, a review and a coding submission all move the same row.
def test_every_activity_updates_one_mastery_score(learner):
    learning_service.register_names(["Dynamic Programming"], "DSA")
    for activity in (ACTIVITY_QUIZ, "document", ACTIVITY_REVIEW, ACTIVITY_CODING):
        learning_service.record_attempts(
            learner.id,
            [Attempt(DP, correct=True, difficulty="medium", activity=activity,
                     concept_name="Dynamic Programming", subject="DSA")],
            source=activity,
        )
    states = learning_service.mastery_for_user(learner.id)
    assert len(states) == 1, "the four activities must share one concept row, not create four"
    assert states[0].attempts == 4
    assert states[0].correct_attempts == 4
# The dashboard reports each activity separately while the mastery stays unified.
def test_accuracy_is_tracked_per_activity_but_mastery_is_shared(learner):
    learning_service.register_names(["Dynamic Programming"], "DSA")
    learning_service.record_attempts(
        learner.id, [Attempt(DP, correct=False, activity=ACTIVITY_QUIZ, concept_name="DP", subject="DSA")]
    )
    learning_service.record_attempts(
        learner.id, [Attempt(DP, correct=True, activity=ACTIVITY_CODING, concept_name="DP", subject="DSA")]
    )
    summary = learning_service.dashboard_summary(learner.id)
    assert summary["quiz_accuracy"] == 0.0
    assert summary["coding_accuracy"] == 100.0
    assert summary["concepts"] == 1
# --- the loop -----------------------------------------------------------
# The full journey the product is built around, in one test.
def test_learning_loop_end_to_end(learner):
    # A document is uploaded and its concepts join the knowledge graph.
    document = store.ingest(learner.id, "dp.md", DP_NOTES)
    concepts = learning_service.register_names(["Dynamic Programming"], "DSA")
    store.set_document_concepts(learner.id, document.id, [c.slug for c in concepts])
    assert store.get_document(learner.id, document.id).concepts == [DP]
    # The student does badly on a quiz about it.
    learning_service.record_attempts(
        learner.id,
        [Attempt(DP, correct=False, score=0.3, difficulty="medium", activity=ACTIVITY_QUIZ,
                 concept_name="Dynamic Programming", subject="DSA")],
        now=NOW,
    )
    learning_service.record_mistake(learner.id, DP, "conceptual_error", "Confuses memoization with tabulation")
    weak = learning_service.mastery_for_concept(learner.id, DP)
    assert weak.learning_status == "weak"
    # The system knows what to do about it, and remembers why.
    recommendation = learning_service.recommendation_for(learner.id, DP)
    assert recommendation["action"] in ("targeted_practice", "re_explain", "prerequisite_review")
    assert "memoization" in recommendation["mistakes"][0]
    # A review is scheduled, and soon, because the concept is weak.
    upcoming = review_service.upcoming(learner.id, days=30, now=NOW)
    assert [card["concept_slug"] for card in upcoming] == [DP]
    assert upcoming[0]["interval_days"] <= 2
    assert upcoming[0]["urgency"] == "critical"
    # Coding practice on the same concept raises it.
    outcome = grading.submit(learner.id, _problem(learner.id), WORKING_FIB)
    assert outcome.status == "accepted"
    after_coding = learning_service.mastery_for_concept(learner.id, DP)
    assert after_coding.mastery_score > weak.mastery_score
    # Reviewing it successfully raises it further and pushes the next review out.
    result = review_service.record_review(learner.id, DP, 1.0, "Dynamic Programming", "DSA")
    assert result["mastery"] > after_coding.mastery_score
    assert result["next_review_at"]
    # The plan reflects all of it: DP is no longer something to learn from scratch.
    goal = StudyGoal(
        subject="DSA", target_date=(NOW + timedelta(days=21)).date().isoformat(),
        hours_per_day=1.5, topics=["Dynamic Programming", "Binary Search", "Graphs"],
    )
    _plan_id, plan = plan_service.create_plan(learner.id, goal)
    dp_items = [item for item in plan.items if item.concept_slug == DP and item.activity != "revision"]
    assert dp_items
    assert dp_items[0].activity != "learn"
    assert dp_items[0].mastery_score > 0
# A concept that has since been mastered is demoted when the plan is refreshed.
def test_plan_reacts_to_mastery_changes(learner):
    goal = StudyGoal(subject="DSA", topics=["Dynamic Programming", "Graphs"], hours_per_day=1.0)
    plan_id, plan = plan_service.create_plan(learner.id, goal)
    before = {item.concept_slug: item.activity for item in plan.items if item.activity != "revision"}
    assert before[DP] == "learn"
    for _ in range(6):
        learning_service.record_attempts(
            learner.id,
            [Attempt(DP, correct=True, difficulty="challenge", activity=ACTIVITY_CODING,
                     concept_name="Dynamic Programming", subject="DSA")],
        )
    updated = plan_service.refresh_plan(learner.id, plan_id)
    after = {item.concept_slug: item.activity for item in updated.items if item.activity != "revision"}
    assert after[DP] == "maintain"
# --- the graph node -----------------------------------------------------
# The knowledge node turns a graded quiz into concept attempts.
def test_quiz_state_becomes_concept_attempts():
    state = {
        "topic": "dynamic programming",
        "topic_analysis": {
            "clean_topic": "Dynamic Programming", "subject_area": "DSA",
            "key_concepts": ["Memoization", "Optimal Substructure"],
        },
        "quiz_difficulty": "medium",
    }
    attempt = {"score": 40.0, "passed": False, "weak_concepts": ["Memoization"], "results": []}
    assert [c.name for c in concepts_for_state(state)] == [
        "Dynamic Programming", "Memoization", "Optimal Substructure"
    ]
    attempts = attempts_from_quiz(state, attempt)
    by_slug = {a.concept_slug: a for a in attempts}
    assert by_slug["dsa::dynamic_programming"].score == 0.4
    assert by_slug["dsa::memoization"].correct is False
    assert by_slug["dsa::memoization"].score == 0.0
    assert all(a.activity == ACTIVITY_QUIZ for a in attempts)
# The node writes mastery and tells the router what to do next.
def test_knowledge_node_updates_mastery(learner):
    state = {
        "user_id": learner.id,
        "topic": "dynamic programming",
        "topic_analysis": {
            "clean_topic": "Dynamic Programming", "subject_area": "DSA", "key_concepts": [],
        },
        "quiz_difficulty": "medium",
        "attempts": [
            {
                "score": 20.0, "passed": False, "weak_concepts": ["Dynamic Programming"],
                "study_tip": "Revisit overlapping subproblems.",
                "results": [
                    {"question": "Which is not true?", "user_answer": "a", "correct_answer": "b",
                     "is_correct": False},
                ],
            }
        ],
    }
    update = update_knowledge(state)
    assert update["mastery"]["score"] > 0
    assert update["mastery"]["status"] == "weak"
    assert update["adaptive_action"] in ("targeted_practice", "re_explain", "prerequisite_review")
    assert update["quiz_difficulty"] == "easy"
    assert update["mastery"]["misconception"]
    assert learning_service.mastery_for_concept(learner.id, DP) is not None
# Without a signed-in user the node scores but stores nothing.
def test_knowledge_node_without_a_user_stores_nothing(db_file):
    state = {
        "user_id": "",
        "topic": "dynamic programming",
        "topic_analysis": {"clean_topic": "Dynamic Programming", "subject_area": "DSA", "key_concepts": []},
        "attempts": [{"score": 20.0, "passed": False, "weak_concepts": [], "results": []}],
    }
    update = update_knowledge(state)
    assert update["concepts"]
    assert "mastery" not in update
# --- isolation across every feature ------------------------------------
# Nothing one learner does is visible to another, in any of the four features.
def test_all_platform_data_is_isolated(learner, other):
    document = store.ingest(learner.id, "dp.md", DP_NOTES)
    learning_service.register_names(["Dynamic Programming"], "DSA")
    learning_service.record_attempts(
        learner.id, [Attempt(DP, correct=True, concept_name="Dynamic Programming", subject="DSA")]
    )
    learning_service.record_mistake(learner.id, DP, "conceptual_error", "private note")
    problem = _problem(learner.id)
    grading.submit(learner.id, problem, WORKING_FIB)
    plan_id, _plan = plan_service.create_plan(
        learner.id, StudyGoal(subject="DSA", topics=["Dynamic Programming"])
    )
    # Documents
    assert store.list_documents(other.id) == []
    assert store.get_document(other.id, document.id) is None
    # Mastery and mistakes
    assert learning_service.mastery_for_user(other.id) == []
    assert learning_service.mastery_for_concept(other.id, DP) is None
    assert learning_service.mistakes_for_concept(other.id, DP) == []
    assert learning_service.dashboard_summary(other.id)["concepts"] == 0
    # Coding
    assert problems.get_problem(other.id, problem.id) is None
    assert grading.submissions_for(other.id, problem.id) == []
    assert grading.coding_stats(other.id)["submissions"] == 0
    with pytest.raises(UnauthorizedError):
        grading.submit(other.id, problem, WORKING_FIB)
    # Reviews
    assert review_service.due_today(other.id) == []
    assert review_service.upcoming(other.id, 60) == []
    # Plans
    assert plan_service.active_plan(other.id) is None
    assert plan_service.list_plans(other.id) == []
    assert plan_service.delete_plan(other.id, plan_id) is False
    with pytest.raises(UnauthorizedError):
        plan_service.refresh_plan(other.id, plan_id)
    # And the owner still has everything.
    assert len(store.list_documents(learner.id)) == 1
    assert plan_service.active_plan(learner.id) is not None
# Recording a review for a concept a user has never met does not leak another user's state.
def test_review_of_an_unknown_concept_starts_fresh(learner, other):
    learning_service.register_names(["Dynamic Programming"], "DSA")
    learning_service.record_attempts(
        learner.id,
        [Attempt(DP, correct=True, difficulty="hard", concept_name="Dynamic Programming", subject="DSA")],
    )
    strong = learning_service.mastery_for_concept(learner.id, DP)
    result = review_service.record_review(other.id, DP, 0.0, "Dynamic Programming", "DSA")
    assert result["mastery"] < strong.mastery_score
    assert learning_service.mastery_for_concept(learner.id, DP).mastery_score == strong.mastery_score
