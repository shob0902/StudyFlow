# Shared StudyState passed between graph nodes, plus workflow settings.
import operator
from typing import Annotated, Any, TypedDict
from learning.mastery import MEDIUM as DEFAULT_DIFFICULTY
PASSING_SCORE = 70
MAX_RETRIES = 2
FIRST_QUIZ_SIZE = 5
RETRY_QUIZ_SIZE = 3
class StudyState(TypedDict):
    # Who this learning state belongs to. Set by the auth layer before the graph runs, never by a node.
    user_id: str
    user_name: str
    user_email: str
    topic: str
    topic_analysis: dict[str, Any]
    explanation: dict[str, Any]
    examples: list[dict[str, Any]]
    quiz: list[dict[str, Any]]
    user_answers: list[str]
    score: float
    feedback: str
    weak_concepts: list[str]
    attempts: Annotated[list[dict[str, Any]], operator.add]
    re_explanations: Annotated[list[dict[str, Any]], operator.add]
    retry_count: int
    recommendation: dict[str, Any]
    next_topic: str
    # The knowledge layer: which concepts this session touches, what the mastery engine made of
    # the last attempt, and what it says to do next. Written by update_knowledge, read by the
    # router, the quiz generator and the UI.
    concepts: list[dict[str, Any]]
    mastery: dict[str, Any]
    adaptive_action: str
    quiz_difficulty: str
    source: dict[str, Any]
# Build the starting StudyState for a new topic, scoped to the signed-in user.
def create_initial_state(
    topic: str, user: dict[str, Any] | None = None, source: dict[str, Any] | None = None
) -> StudyState:
    user = user or {}
    return StudyState(
        user_id=str(user.get("user_id", "")),
        user_name=str(user.get("user_name", "")),
        user_email=str(user.get("user_email", "")),
        topic=topic.strip(),
        topic_analysis={},
        explanation={},
        examples=[],
        quiz=[],
        user_answers=[],
        score=0.0,
        feedback="",
        weak_concepts=[],
        attempts=[],
        re_explanations=[],
        retry_count=0,
        recommendation={},
        next_topic="",
        concepts=[],
        mastery={},
        adaptive_action="",
        quiz_difficulty=DEFAULT_DIFFICULTY,
        source=source or {},
    )
