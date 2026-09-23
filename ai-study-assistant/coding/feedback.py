# Progressive coding help: five levels, and the last one is the only one that shows a solution.
#
# The level is enforced here rather than trusted to the model: the prompt states one level, and
# the solution level is only reachable when the student asks for it explicitly.
from typing import Any
from coding.problems import CodingProblem
from coding.runner import ExecutionResult
from llm.model import NODE_API_KEYS, get_structured_llm, run_chain
from prompts.prompts import CODE_REVIEW_PROMPT, CODING_FAILURE_PROMPT, CODING_HINT_PROMPT
from schemas.models import CodeReview, CodingHint, FailureAnalysis
from utils.helpers import log_step
MAX_LEVEL = 5
SOLUTION_LEVEL = 5
# What each level of help is allowed to contain.
LEVELS = {
    1: "a small nudge about one specific line or condition, no approach, no code",
    2: "a conceptual hint naming the idea or data structure that applies, still no code",
    3: "a detailed approach in prose: the steps to take, still no code",
    4: "pseudocode of the approach, but not runnable code in the target language",
    5: "the full worked solution with a short explanation",
}
LEVEL_NAMES = {
    1: "Small hint",
    2: "Conceptual hint",
    3: "Detailed approach",
    4: "Pseudocode",
    5: "Full solution",
}
# A short description of what the last run did, for the coach.
def outcome_text(result: ExecutionResult | None) -> str:
    if result is None:
        return "The student has not run their code yet."
    if result.timed_out:
        return "The code did not finish in time."
    if result.error:
        return f"The code failed to run: {result.error.strip().splitlines()[-1][:200]}"
    if result.all_passed:
        return "All tests pass."
    failed = result.failures[:2]
    detail = "; ".join(
        f"input {case.get('input')} expected {case.get('expected')} but got {case.get('actual')}"
        for case in failed
    )
    return f"{result.passed} of {result.total} tests pass. Failing: {detail}"
# Ask for help at one level. Level 5 is the only one that may contain a solution, and the caller
# has to ask for it deliberately.
def hint(
    problem: CodingProblem, code: str, level: int, result: ExecutionResult | None = None
) -> str:
    level = max(1, min(MAX_LEVEL, int(level)))
    chain = CODING_HINT_PROMPT | get_structured_llm(CodingHint, NODE_API_KEYS["coding_hint"])
    answer: CodingHint = run_chain(
        chain,
        {
            "statement": problem.statement,
            "code": (code or "(nothing written yet)")[:6000],
            "outcome": outcome_text(result),
            "level": level,
            "level_meaning": LEVELS[level],
        },
        f"coding hint level {level}",
    )
    log_step("CODING", f"Gave help at level {level} ({LEVEL_NAMES[level]})")
    return answer.hint
# Diagnose a failing submission from its real test results.
def analyse_failure(problem: CodingProblem, code: str, result: ExecutionResult) -> FailureAnalysis:
    failures = "\n".join(
        f"- input {case.get('input')}: expected {case.get('expected')}, got {case.get('actual')}"
        for case in result.failures[:5]
    ) or (result.error[:500] or "No specific failing case was captured.")
    chain = CODING_FAILURE_PROMPT | get_structured_llm(
        FailureAnalysis, NODE_API_KEYS["coding_hint"]
    )
    analysis: FailureAnalysis = run_chain(
        chain,
        {
            "statement": problem.statement,
            "code": code[:6000],
            "passed": result.passed,
            "total": result.total,
            "failures": failures,
        },
        "coding failure analysis",
    )
    return analysis
# Analyse a solution that passes, from the code the student actually wrote.
def review_solution(problem: CodingProblem, code: str) -> CodeReview:
    chain = CODE_REVIEW_PROMPT | get_structured_llm(CodeReview, NODE_API_KEYS["coding_review"])
    review: CodeReview = run_chain(
        chain, {"statement": problem.statement, "code": code[:6000]}, "code review"
    )
    log_step("CODING", f"Reviewed a solution: {review.time_complexity} time")
    return review
# What the mastery engine suggests doing about a concept the student is weak at.
# Deterministic: a plan built from their numbers, not another LLM call.
def practice_plan(concept_name: str, mastery: float, mistakes: list[str]) -> list[str]:
    steps: list[str] = []
    if mistakes:
        steps.append(f"Review what keeps going wrong: {mistakes[0]}")
    if mastery < 40:
        steps.extend(
            [
                f"Re-read the core idea behind {concept_name}",
                "Solve 2 easy problems on it",
                "Explain the approach out loud before coding the next one",
                "Then try 1 medium problem",
            ]
        )
    elif mastery < 65:
        steps.extend(
            [
                f"Solve 1 easy {concept_name} problem to warm up",
                "Then 2 medium problems, writing the approach first",
            ]
        )
    elif mastery < 85:
        steps.extend([f"Solve 2 medium {concept_name} problems", "Then attempt 1 hard problem"])
    else:
        steps.extend(
            [f"Keep {concept_name} warm with 1 hard problem", "Try a challenge mixing it with another concept"]
        )
    return steps
