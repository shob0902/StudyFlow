# Classifying *why* an answer was wrong, so the next explanation can target the real gap.
# Deterministic rules run first and cost nothing; an LLM is only asked when the rules cannot tell.
import re
from dataclasses import dataclass
CONCEPTUAL_ERROR = "conceptual_error"
CALCULATION_ERROR = "calculation_error"
SYNTAX_ERROR = "syntax_error"
MISUNDERSTANDING_QUESTION = "misunderstanding_question"
CARELESS_ERROR = "careless_error"
PREREQUISITE_GAP = "prerequisite_gap"
VOCABULARY_GAP = "vocabulary_gap"
CATEGORIES = (
    CONCEPTUAL_ERROR, CALCULATION_ERROR, SYNTAX_ERROR, MISUNDERSTANDING_QUESTION,
    CARELESS_ERROR, PREREQUISITE_GAP, VOCABULARY_GAP,
)
CATEGORY_LABELS = {
    CONCEPTUAL_ERROR: "Concept not understood",
    CALCULATION_ERROR: "Slip in the working",
    SYNTAX_ERROR: "Syntax problem",
    MISUNDERSTANDING_QUESTION: "Misread the question",
    CARELESS_ERROR: "Careless slip",
    PREREQUISITE_GAP: "Missing a prerequisite",
    VOCABULARY_GAP: "Unfamiliar terminology",
}
# Coding failure kinds, classified from what actually happened when the code ran.
RUNTIME_ERROR = "runtime_error"
WRONG_ANSWER = "wrong_answer"
TIMEOUT = "timeout"
MEMORY_LIMIT = "memory_limit"
EDGE_CASE_FAILURE = "edge_case_failure"
COMPLEXITY_ISSUE = "complexity_issue"
CODE_FAILURES = (
    SYNTAX_ERROR, RUNTIME_ERROR, WRONG_ANSWER, TIMEOUT, MEMORY_LIMIT,
    EDGE_CASE_FAILURE, COMPLEXITY_ISSUE,
)
CODE_FAILURE_LABELS = {
    SYNTAX_ERROR: "Syntax error",
    RUNTIME_ERROR: "Runtime error",
    WRONG_ANSWER: "Wrong answer",
    TIMEOUT: "Too slow — timed out",
    MEMORY_LIMIT: "Used too much memory",
    EDGE_CASE_FAILURE: "Fails an edge case",
    COMPLEXITY_ISSUE: "Works, but too slow for the limits",
}
# One recorded mistake against one concept.
@dataclass(frozen=True)
class Misconception:
    concept_slug: str
    category: str
    note: str = ""
    # A short line for the UI.
    def describe(self) -> str:
        label = CATEGORY_LABELS.get(self.category, CODE_FAILURE_LABELS.get(self.category, self.category))
        return f"{label}: {self.note}" if self.note else label
# Words in a question that signal it is testing vocabulary rather than reasoning.
_DEFINITION_WORDS = ("define", "definition", "term", "called", "known as", "stands for", "means")
_NEGATIVE_WORDS = ("not", "except", "false", "incorrect", "never")
_NUMERIC = re.compile(r"^[\s\d+\-*/().,%^]+$")
# Classify a wrong quiz answer from the question and the options alone.
# These are signals, not certainties: an LLM refines them when one is available.
def classify_quiz_error(
    question: str, user_answer: str, correct_answer: str, options: list[str] | None = None
) -> str:
    text = f"{question}".lower()
    chosen = str(user_answer).strip()
    right = str(correct_answer).strip()
    if not chosen:
        return CARELESS_ERROR
    # A question that hinges on "not"/"except" and a wrong answer usually means it was misread.
    if any(f" {word} " in f" {text} " for word in _NEGATIVE_WORDS):
        return MISUNDERSTANDING_QUESTION
    # Both answers numeric: the method may be right and the arithmetic wrong.
    if _NUMERIC.match(chosen) and _NUMERIC.match(right):
        return CALCULATION_ERROR
    # Asking what something is called is a vocabulary question.
    if any(word in text for word in _DEFINITION_WORDS):
        return VOCABULARY_GAP
    # Answers that differ only slightly are easy to pick by accident.
    if _close_strings(chosen, right):
        return CARELESS_ERROR
    return CONCEPTUAL_ERROR
# True when two answers are near-identical, differing by case, spacing or a word.
def _close_strings(first: str, second: str) -> bool:
    normalise = lambda value: set(re.findall(r"[a-z0-9]+", value.lower()))
    left, right = normalise(first), normalise(second)
    if not left or not right:
        return False
    overlap = len(left & right) / max(len(left | right), 1)
    return overlap >= 0.7
# Classify a whole graded attempt: one category per wrong question, plus the dominant pattern.
def classify_attempt(results: list[dict]) -> tuple[list[str], str]:
    categories = [
        classify_quiz_error(
            result.get("question", ""),
            result.get("user_answer", ""),
            result.get("correct_answer", ""),
            result.get("options"),
        )
        for result in results
        if not result.get("is_correct")
    ]
    if not categories:
        return [], ""
    dominant = max(set(categories), key=categories.count)
    return categories, dominant
# Classify a coding failure from the execution result. Fully deterministic: the runner already
# knows whether the code failed to parse, crashed, timed out or simply returned the wrong thing.
def classify_code_failure(result: dict) -> str:
    if result.get("timed_out"):
        return TIMEOUT
    if result.get("memory_exceeded"):
        return MEMORY_LIMIT
    error = str(result.get("error") or "").lower()
    if "syntaxerror" in error or "indentationerror" in error or "parse error" in error:
        return SYNTAX_ERROR
    if error:
        return RUNTIME_ERROR
    passed = int(result.get("passed", 0))
    total = int(result.get("total", 0))
    if total and passed == total:
        return ""
    # Nearly everything passing points at a specific case rather than a wrong idea.
    if total and passed >= max(1, total - 2) and passed / total >= 0.7:
        return EDGE_CASE_FAILURE
    return WRONG_ANSWER
# The mistakes a learner makes most often on a concept, newest first, deduplicated.
def common_mistakes(records: list[dict], limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for record in reversed(records):
        note = str(record.get("note") or "").strip()
        category = str(record.get("category") or "")
        line = note or CATEGORY_LABELS.get(category, CODE_FAILURE_LABELS.get(category, category))
        key = line.lower()
        if line and key not in seen:
            seen.add(key)
            out.append(line)
        if len(out) >= limit:
            break
    return out
