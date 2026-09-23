# Generating and storing coding problems.
#
# A generated problem is only accepted once its test cases parse as real literals and line up,
# because a problem whose tests are nonsense would poison the mastery engine with false failures.
import ast
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Any
from auth.errors import DatabaseError, UnauthorizedError
from db.database import session
from db.models import utc_now
from db import learning_service
from learning.concepts import make_concepts
from learning.mastery import DIFFICULTIES, MEDIUM
from llm.model import NODE_API_KEYS, get_structured_llm, run_chain
from prompts.prompts import CODING_PROBLEM_PROMPT
from schemas.models import CodingProblemSpec
from utils.helpers import StudyAssistantError, log_error, log_step
MIN_TESTS = 2
MAX_TESTS = 12
# What each difficulty should ask of the student.
DIFFICULTY_GUIDANCE = {
    "easy": "A single idea, short input sizes, no tricky edge cases beyond empty input.",
    "medium": "Requires choosing the right approach; include at least one awkward edge case.",
    "hard": "Needs an efficient algorithm; naive solutions should be too slow for the constraints.",
    "challenge": "Combines two ideas and requires reasoning about complexity.",
}
# A problem generated that cannot be trusted.
class ProblemError(StudyAssistantError):
    pass
# A stored coding problem.
@dataclass(frozen=True)
class CodingProblem:
    id: str
    user_id: str
    title: str
    statement: str
    language: str
    difficulty: str
    signature: str
    constraints: str
    examples: list[str] = field(default_factory=list)
    tests: list[dict[str, str]] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    created_at: str = ""
    # The function the tests call, taken from the signature.
    @property
    def function_name(self) -> str:
        head = self.signature.split("(")[0]
        return head.replace("def", "").replace("function", "").strip() or "solve"
    # Build from a database row.
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CodingProblem":
        loads = lambda value, default: json.loads(value) if value else default
        return cls(
            id=row["id"], user_id=row["user_id"], title=row["title"], statement=row["statement"],
            language=row["language"], difficulty=row["difficulty"], signature=row["signature"],
            constraints=row["constraints"], examples=loads(row["examples"], []),
            tests=loads(row["tests"], []), concepts=loads(row["concepts"], []),
            created_at=row["created_at"],
        )
# Check a generated test pair really is a pair of Python literals that can be run.
def validate_tests(inputs: list[str], outputs: list[str]) -> list[dict[str, str]]:
    tests: list[dict[str, str]] = []
    for raw_input, raw_output in zip(inputs, outputs):
        argument = str(raw_input).strip()
        expected = str(raw_output).strip()
        if not argument or not expected:
            continue
        # A single argument still has to be a tuple, or calling the function would splat a list.
        if not (argument.startswith("(") and argument.endswith(")")):
            argument = f"({argument},)"
        try:
            parsed = ast.literal_eval(argument)
            ast.literal_eval(expected)
        except (ValueError, SyntaxError):
            log_step("CODING", f"Discarding an unparseable test case: {raw_input!r}")
            continue
        if not isinstance(parsed, tuple):
            argument = f"({argument},)"
        tests.append({"input": argument, "expected": expected})
        if len(tests) >= MAX_TESTS:
            break
    return tests
# Ask the model for a problem, then keep only what survives validation.
def generate_problem(
    user_id: str, topic: str, difficulty: str = MEDIUM, language: str = "python"
) -> CodingProblem:
    if not user_id:
        raise UnauthorizedError("Please sign in before practising code.")
    difficulty = difficulty if difficulty in DIFFICULTIES else MEDIUM
    chain = CODING_PROBLEM_PROMPT | get_structured_llm(
        CodingProblemSpec, NODE_API_KEYS["coding_problem"]
    )
    spec: CodingProblemSpec = run_chain(
        chain,
        {
            "topic": topic,
            "difficulty": difficulty,
            "language": language,
            "difficulty_guidance": DIFFICULTY_GUIDANCE.get(difficulty, ""),
        },
        "coding problem",
    )
    tests = validate_tests(spec.test_inputs, spec.test_outputs)
    if len(tests) < MIN_TESTS:
        raise ProblemError(
            "The generated problem did not come with usable test cases. Please try again."
        )
    signature = spec.signature.strip() or f"def {spec.function_name}(...):"
    concepts = make_concepts(spec.concepts or [topic])
    learning_service.ensure_concepts(concepts)
    problem = store_problem(
        user_id,
        CodingProblem(
            id="", user_id=user_id, title=spec.title.strip()[:120],
            statement=spec.statement.strip(), language=language, difficulty=difficulty,
            signature=signature, constraints=spec.constraints.strip(),
            examples=[str(example) for example in spec.examples][:6],
            tests=tests, concepts=[concept.slug for concept in concepts],
        ),
    )
    log_step(
        "CODING",
        f"Generated {difficulty} problem {problem.title!r} with {len(tests)} tests "
        f"for {len(concepts)} concept(s)",
    )
    return problem
# Save a problem for this user.
def store_problem(user_id: str, problem: CodingProblem) -> CodingProblem:
    problem_id = str(uuid.uuid4())
    try:
        with session() as connection:
            with connection:
                connection.execute(
                    "INSERT INTO coding_problems (id, user_id, title, statement, language,"
                    " difficulty, signature, constraints, examples, tests, concepts, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        problem_id, user_id, problem.title, problem.statement, problem.language,
                        problem.difficulty, problem.signature, problem.constraints,
                        json.dumps(problem.examples), json.dumps(problem.tests),
                        json.dumps(problem.concepts), utc_now(),
                    ),
                )
    except sqlite3.Error:
        log_error("Could not store a coding problem")
        raise DatabaseError("Could not save that problem. Please try again.")
    return get_problem(user_id, problem_id)  # type: ignore[return-value]
# One of this user's problems, or None when it is not theirs.
def get_problem(user_id: str, problem_id: str) -> CodingProblem | None:
    with session() as connection:
        row = connection.execute(
            "SELECT * FROM coding_problems WHERE id = ? AND user_id = ?", (problem_id, user_id)
        ).fetchone()
    return CodingProblem.from_row(row) if row else None
# This user's problems, newest first.
def list_problems(user_id: str, limit: int = 20) -> list[CodingProblem]:
    with session() as connection:
        rows = connection.execute(
            "SELECT * FROM coding_problems WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [CodingProblem.from_row(row) for row in rows]
# Delete one of this user's problems and its submissions.
def delete_problem(user_id: str, problem_id: str) -> bool:
    with session() as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM coding_problems WHERE id = ? AND user_id = ?", (problem_id, user_id)
            )
    return cursor.rowcount > 0
# A starting file for the editor: the signature and a place to write.
def starter_code(problem: CodingProblem) -> str:
    if problem.language == "javascript":
        name = problem.function_name
        return (
            f"// {problem.title}\n"
            f"function {name}(/* arguments */) {{\n    // your code here\n}}\n\n"
            f"module.exports = {{ {name} }};\n"
        )
    signature = problem.signature.rstrip(":")
    if not signature.startswith("def "):
        signature = f"def {problem.function_name}(*args)"
    return f"{signature}:\n    # your code here\n    pass\n"
