# Coding practice: problem validation, sandboxed execution, failure classification and the
# mastery update that follows.
import pytest
from auth.errors import UnauthorizedError
from coding import grading, problems
from coding.feedback import LEVELS, MAX_LEVEL, SOLUTION_LEVEL, outcome_text, practice_plan
from coding.problems import CodingProblem, validate_tests
from coding.runner import ExecutionResult, SubprocessRunner, configured_mode, isolation_notice
from db import learning_service
from learning.misconceptions import (
    EDGE_CASE_FAILURE,
    RUNTIME_ERROR,
    SYNTAX_ERROR,
    TIMEOUT,
    WRONG_ANSWER,
    classify_code_failure,
)
SEARCH_TESTS = [
    {"input": "([1, 2, 3, 4, 5], 4)", "expected": "3"},
    {"input": "([1, 2, 3], 9)", "expected": "-1"},
    {"input": "([], 1)", "expected": "-1"},
]
GOOD_CODE = """
def search(nums, target):
    low, high = 0, len(nums) - 1
    while low <= high:
        mid = (low + high) // 2
        if nums[mid] == target:
            return mid
        if nums[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
"""
# A stored problem belonging to a signed-in user.
@pytest.fixture
def problem(users, db_file):
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    learning_service.register_names(["Binary Search"], "DSA")
    stored = problems.store_problem(
        user.id,
        CodingProblem(
            id="", user_id=user.id, title="Find the index", statement="Return the index or -1.",
            language="python", difficulty="medium", signature="def search(nums, target):",
            constraints="", examples=[], tests=SEARCH_TESTS, concepts=["dsa::binary_search"],
        ),
    )
    return user, stored
# --- generated problems -------------------------------------------------
# Test cases that are not valid literals are discarded rather than run.
def test_unparseable_tests_are_discarded():
    tests = validate_tests(["([1,2], 3)", "this is not python", "(4,)"], ["1", "2", "3"])
    assert len(tests) == 2
    assert tests[0]["input"] == "([1,2], 3)"
# A single argument is wrapped into a tuple so the call does not splat it.
def test_single_arguments_become_tuples():
    tests = validate_tests(["5", "[1, 2, 3]"], ["25", "6"])
    assert tests[0]["input"] == "(5,)"
    assert tests[1]["input"] == "([1, 2, 3],)"
# Mismatched inputs and outputs simply stop at the shorter list.
def test_mismatched_lengths_are_trimmed():
    assert len(validate_tests(["(1,)", "(2,)", "(3,)"], ["1"])) == 1
# A problem generated without usable tests is refused, so it cannot poison mastery.
def test_problem_without_tests_is_refused(users, db_file, monkeypatch):
    from langchain_core.runnables import RunnableLambda
    from schemas.models import CodingProblemSpec
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    spec = CodingProblemSpec(
        title="Bad", statement="x", signature="def f(x):", function_name="f",
        test_inputs=["not python"], test_outputs=["also not python"], concepts=["x"],
    )
    monkeypatch.setattr(problems, "get_structured_llm", lambda *a, **k: RunnableLambda(lambda v: v))
    monkeypatch.setattr(problems, "run_chain", lambda *a, **k: spec)
    with pytest.raises(problems.ProblemError):
        problems.generate_problem(user.id, "anything")
# Starter code matches the signature the tests will call.
def test_starter_code_matches_the_signature(problem):
    _user, stored = problem
    assert "def search(nums, target):" in problems.starter_code(stored)
    assert stored.function_name == "search"
# --- the sandbox --------------------------------------------------------
# Correct code passes every test.
def test_correct_code_passes():
    result = SubprocessRunner(timeout=10).run(GOOD_CODE, "python", SEARCH_TESTS, "search")
    assert result.all_passed
    assert result.passed == 3
    assert result.runtime_ms > 0
# Wrong code fails the cases it gets wrong and passes the rest.
def test_wrong_code_fails_some_cases():
    code = "def search(nums, target):\n    return nums.index(target) if target in nums else 0\n"
    result = SubprocessRunner(timeout=10).run(code, "python", SEARCH_TESTS, "search")
    assert not result.all_passed
    assert 0 < result.passed < 3
    assert len(result.failures) == 2
# Code that will not parse is reported as a syntax error, not a crash.
def test_syntax_error_is_caught():
    result = SubprocessRunner(timeout=10).run(
        "def search(nums, target)\n    return 1\n", "python", SEARCH_TESTS, "search"
    )
    assert result.passed == 0
    assert "SyntaxError" in result.error
    assert classify_code_failure(_as_dict(result)) == SYNTAX_ERROR
# An endless loop is stopped by the timeout rather than hanging the app.
def test_infinite_loop_times_out():
    result = SubprocessRunner(timeout=2).run(
        "def search(nums, target):\n    while True:\n        pass\n", "python", SEARCH_TESTS, "search"
    )
    assert result.timed_out
    assert result.passed == 0
    assert classify_code_failure(_as_dict(result)) == TIMEOUT
# Code that does not define the expected function says so plainly.
def test_missing_function_is_reported():
    result = SubprocessRunner(timeout=10).run(
        "def other(x):\n    return x\n", "python", SEARCH_TESTS, "search"
    )
    assert "does not define" in result.error
# An exception inside the student's function fails only that case.
def test_runtime_error_in_one_case():
    code = "def search(nums, target):\n    return 10 // len(nums)\n"
    result = SubprocessRunner(timeout=10).run(code, "python", SEARCH_TESTS, "search")
    assert not result.all_passed
    assert any("ZeroDivisionError" in str(case.get("error", "")) for case in result.cases)
# The app always states how the code was isolated.
def test_isolation_is_reported():
    level, message = isolation_notice()
    assert level in ("docker", "subprocess", "disabled", "unavailable")
    assert message
    assert configured_mode() in ("auto", "docker", "subprocess", "disabled")
# --- failure classification --------------------------------------------
# Nearly everything passing points at an edge case, not a wrong idea.
def test_almost_passing_is_an_edge_case():
    assert classify_code_failure({"passed": 9, "total": 10}) == EDGE_CASE_FAILURE
    assert classify_code_failure({"passed": 2, "total": 10}) == WRONG_ANSWER
    assert classify_code_failure({"passed": 10, "total": 10}) == ""
# A crash is a runtime error; running out of time or memory is named as such.
def test_other_failure_kinds():
    assert classify_code_failure({"error": "ZeroDivisionError: division by zero"}) == RUNTIME_ERROR
    assert classify_code_failure({"timed_out": True}) == TIMEOUT
    assert classify_code_failure({"memory_exceeded": True}) == "memory_limit"
# --- submitting and mastery --------------------------------------------
# A correct submission is accepted and raises mastery on the problem's concepts.
def test_accepted_submission_raises_mastery(problem):
    user, stored = problem
    outcome = grading.submit(user.id, stored, GOOD_CODE)
    assert outcome.status == "accepted"
    assert outcome.result.all_passed
    assert outcome.concepts["dsa::binary_search"]["mastery"] > 0
    state = learning_service.mastery_for_concept(user.id, "dsa::binary_search")
    assert state.attempts == 1
    assert state.correct_attempts == 1
# A failing submission records the failure against the concept.
def test_failing_submission_records_the_mistake(problem):
    user, stored = problem
    code = "def search(nums, target):\n    return 0\n"
    outcome = grading.submit(user.id, stored, code)
    assert outcome.status != "accepted"
    assert outcome.failure_kind
    mistakes = learning_service.mistakes_for_concept(user.id, "dsa::binary_search")
    assert mistakes
    state = learning_service.mastery_for_concept(user.id, "dsa::binary_search")
    assert state.incorrect_attempts == 1
# Partial passes give partial credit rather than nothing.
def test_partial_passes_give_partial_credit(problem, users, db_file):
    user, stored = problem
    partial = "def search(nums, target):\n    return nums.index(target) if target in nums else 0\n"
    nothing = "def search(nums, target):\n    return 99\n"
    outcome_partial = grading.submit(user.id, stored, partial)
    other = users.upsert_from_google("google-2", "bob@example.com", "Bob")
    stored_other = problems.store_problem(
        other.id,
        CodingProblem(
            id="", user_id=other.id, title="t", statement="s", language="python",
            difficulty="medium", signature="def search(nums, target):", constraints="",
            examples=[], tests=SEARCH_TESTS, concepts=["dsa::binary_search"],
        ),
    )
    outcome_nothing = grading.submit(other.id, stored_other, nothing)
    assert (
        outcome_partial.concepts["dsa::binary_search"]["mastery"]
        > outcome_nothing.concepts["dsa::binary_search"]["mastery"]
    )
# Submissions are stored and counted.
def test_submissions_are_recorded(problem):
    user, stored = problem
    grading.submit(user.id, stored, GOOD_CODE)
    history = grading.submissions_for(user.id, stored.id)
    assert len(history) == 1
    assert history[0]["status"] == "accepted"
    stats = grading.coding_stats(user.id)
    assert stats["submissions"] == 1 and stats["solved"] == 1 and stats["accuracy"] == 100.0
# Hints reduce the credit a solved problem earns.
def test_hints_reduce_the_credit(problem, users, db_file):
    user, stored = problem
    unaided = grading.submit(user.id, stored, GOOD_CODE)
    other = users.upsert_from_google("google-3", "cat@example.com", "Cat")
    stored_other = problems.store_problem(
        other.id,
        CodingProblem(
            id="", user_id=other.id, title="t", statement="s", language="python",
            difficulty="medium", signature="def search(nums, target):", constraints="",
            examples=[], tests=SEARCH_TESTS, concepts=["dsa::binary_search"],
        ),
    )
    helped = grading.submit(other.id, stored_other, GOOD_CODE, hints_used=4)
    assert (
        unaided.concepts["dsa::binary_search"]["mastery"]
        > helped.concepts["dsa::binary_search"]["mastery"]
    )
# --- isolation ----------------------------------------------------------
# One user cannot see, open or submit against another's problem.
def test_problems_are_private(problem, users):
    user, stored = problem
    other = users.upsert_from_google("google-2", "bob@example.com", "Bob")
    assert problems.get_problem(other.id, stored.id) is None
    assert problems.list_problems(other.id) == []
    assert problems.delete_problem(other.id, stored.id) is False
    with pytest.raises(UnauthorizedError):
        grading.submit(other.id, stored, GOOD_CODE)
    assert grading.submissions_for(other.id, stored.id) == []
# --- progressive help ---------------------------------------------------
# There are five levels and only the last one is allowed to show a solution.
def test_help_levels_are_progressive():
    assert set(LEVELS) == {1, 2, 3, 4, 5}
    assert MAX_LEVEL == SOLUTION_LEVEL == 5
    assert "no code" in LEVELS[1]
    assert "pseudocode" in LEVELS[4].lower()
    assert "solution" in LEVELS[5]
# The coach is told what actually happened, not asked to guess.
def test_outcome_text_describes_the_run():
    assert "not run" in outcome_text(None)
    assert "All tests pass" in outcome_text(ExecutionResult(passed=3, total=3))
    timed_out = ExecutionResult(passed=0, total=3, timed_out=True)
    assert "did not finish" in outcome_text(timed_out)
    failing = ExecutionResult(
        passed=1, total=2, cases=[{"input": "(1,)", "expected": "2", "actual": "3", "passed": False}]
    )
    assert "1 of 2" in outcome_text(failing)
# The practice plan for a weak concept is concrete and ordered.
def test_practice_plan_scales_with_mastery():
    weak = practice_plan("Dynamic Programming", 31.0, ["Confuses memoization with tabulation"])
    strong = practice_plan("Dynamic Programming", 90.0, [])
    assert "Confuses memoization with tabulation" in weak[0]
    assert any("easy" in step for step in weak)
    assert any("hard" in step or "challenge" in step for step in strong)
# The execution result as the plain dict the classifier takes.
def _as_dict(result):
    return {
        "passed": result.passed, "total": result.total, "error": result.error,
        "timed_out": result.timed_out, "memory_exceeded": result.memory_exceeded,
    }
