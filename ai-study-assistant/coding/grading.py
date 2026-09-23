# Grading a submission and feeding the result into the same mastery engine the quizzes use.
#
# Coding gives partial credit: 8 of 10 tests passing is 0.8 of an attempt, not a flat failure.
# That is why Attempt carries a score as well as a correct flag.
import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any
from auth.errors import DatabaseError, UnauthorizedError
from coding.problems import CodingProblem
from coding.runner import ExecutionResult, SandboxError, select_runner
from db import learning_service
from db.database import session
from db.models import utc_now
from learning.mastery import ACTIVITY_CODING, Attempt
from learning.misconceptions import (
    CODE_FAILURE_LABELS,
    COMPLEXITY_ISSUE,
    TIMEOUT,
    classify_code_failure,
)
from utils.helpers import log_error, log_step
STATUS_ACCEPTED = "accepted"
# What the student sees after submitting, and what the mastery engine recorded.
@dataclass(frozen=True)
class SubmissionOutcome:
    submission_id: str
    result: ExecutionResult
    status: str
    failure_kind: str
    concepts: dict[str, Any]
    # A readable headline.
    @property
    def headline(self) -> str:
        if self.status == STATUS_ACCEPTED:
            return f"Accepted — {self.result.passed}/{self.result.total} tests passed"
        return f"{CODE_FAILURE_LABELS.get(self.failure_kind, 'Not accepted')} — " \
               f"{self.result.passed}/{self.result.total} tests passed"
# Run a submission against the problem's tests, without recording anything.
# Used by the Run button, so a student can experiment without it counting.
def run_submission(problem: CodingProblem, code: str, language: str = "") -> ExecutionResult:
    if not code.strip():
        raise SandboxError("Write some code first.")
    runner = select_runner()
    return runner.run(code, language or problem.language, problem.tests, problem.function_name)
# Run a submission, store it, and update mastery for every concept the problem exercises.
def submit(user_id: str, problem: CodingProblem, code: str, hints_used: int = 0) -> SubmissionOutcome:
    if not user_id:
        raise UnauthorizedError("Please sign in before submitting code.")
    if problem.user_id != user_id:
        raise UnauthorizedError("That problem does not belong to your account.")
    result = run_submission(problem, code)
    failure_kind = "" if result.all_passed else (classify_code_failure(_result_dict(result)) or "wrong_answer")
    # Passing every test but timing out on the way means the approach is too slow, not wrong.
    if result.timed_out and result.passed:
        failure_kind = COMPLEXITY_ISSUE
    status = STATUS_ACCEPTED if result.all_passed else failure_kind
    submission_id = _store(user_id, problem, code, result, status, failure_kind, hints_used)
    concepts = _update_mastery(user_id, problem, result, failure_kind, hints_used)
    log_step(
        "CODING",
        f"Submission {result.passed}/{result.total} -> {status} "
        f"({'accepted' if result.all_passed else failure_kind})",
    )
    return SubmissionOutcome(
        submission_id=submission_id, result=result, status=status,
        failure_kind=failure_kind, concepts=concepts,
    )
# The execution result as the plain dict the classifier expects.
def _result_dict(result: ExecutionResult) -> dict[str, Any]:
    return {
        "passed": result.passed, "total": result.total, "error": result.error,
        "timed_out": result.timed_out, "memory_exceeded": result.memory_exceeded,
    }
# Record the submission itself.
def _store(
    user_id: str, problem: CodingProblem, code: str, result: ExecutionResult,
    status: str, failure_kind: str, hints_used: int,
) -> str:
    submission_id = str(uuid.uuid4())
    detail = {
        "isolation": result.isolation,
        "error": result.error[:500],
        "failures": [
            {"input": case.get("input"), "expected": case.get("expected"), "actual": case.get("actual")}
            for case in result.failures[:5]
        ],
    }
    try:
        with session() as connection:
            with connection:
                connection.execute(
                    "INSERT INTO coding_submissions (id, user_id, problem_id, language, code,"
                    " passed, total, runtime_ms, memory_kb, status, failure_kind, detail,"
                    " hints_used, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        submission_id, user_id, problem.id, problem.language, code[:20000],
                        result.passed, result.total, result.runtime_ms, result.memory_kb,
                        status, failure_kind, json.dumps(detail), hints_used, utc_now(),
                    ),
                )
    except sqlite3.Error:
        log_error("Could not store a coding submission")
        raise DatabaseError("Your code ran, but the result could not be saved. Please try again.")
    return submission_id
# Feed the result into the shared mastery engine, one attempt per concept the problem tags.
#
# Hints reduce the credit: solving a problem after being walked through it is weaker evidence
# than solving it unaided.
def _update_mastery(
    user_id: str, problem: CodingProblem, result: ExecutionResult, failure_kind: str, hints_used: int
) -> dict[str, Any]:
    if not problem.concepts:
        return {}
    ratio = result.passed / result.total if result.total else 0.0
    penalty = max(0.55, 1.0 - 0.12 * max(0, hints_used))
    score = round(ratio * penalty, 4)
    attempts = [
        Attempt(
            concept_slug=slug,
            correct=result.all_passed,
            score=score,
            difficulty=problem.difficulty,
            activity=ACTIVITY_CODING,
            concept_name=slug.split("::")[-1].replace("_", " ").title(),
            subject=slug.split("::")[0].replace("_", " ").title(),
        )
        for slug in problem.concepts
    ]
    updated = learning_service.record_attempts(user_id, attempts, source="coding")
    if failure_kind:
        note = _failure_note(result, failure_kind)
        for slug in problem.concepts:
            learning_service.record_mistake(user_id, slug, failure_kind, note, source="coding")
    return {
        slug: {"mastery": state.mastery_score, "status": state.learning_status}
        for slug, state in updated.items()
    }
# A short, factual note about what went wrong, taken from the run rather than guessed.
def _failure_note(result: ExecutionResult, failure_kind: str) -> str:
    if failure_kind == TIMEOUT:
        return "Ran out of time on the given limits."
    if result.error:
        return result.error.strip().splitlines()[-1][:200]
    failed = result.failures
    if failed:
        case = failed[0]
        return f"Failed on input {case.get('input')}: expected {case.get('expected')}, got {case.get('actual')}"[:200]
    return ""
# This user's submissions for a problem, newest first.
def submissions_for(user_id: str, problem_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with session() as connection:
        rows = connection.execute(
            "SELECT * FROM coding_submissions WHERE user_id = ? AND problem_id = ?"
            " ORDER BY created_at DESC LIMIT ?",
            (user_id, problem_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
# How this user is doing at coding overall.
def coding_stats(user_id: str) -> dict[str, Any]:
    with session() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS submissions,"
            " SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) AS accepted,"
            " COUNT(DISTINCT CASE WHEN status = 'accepted' THEN problem_id END) AS solved"
            " FROM coding_submissions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    submissions = int(row["submissions"] or 0)
    accepted = int(row["accepted"] or 0)
    return {
        "submissions": submissions,
        "accepted": accepted,
        "solved": int(row["solved"] or 0),
        "accuracy": round(accepted / submissions * 100, 1) if submissions else None,
    }
