# Turns the LangGraph study state into a plain-text transcript, so a past session can be read back
# without replaying the graph. Deterministic and append-only: the same state always produces the
# same lines in the same order, and only the lines beyond what is stored are ever written.
from typing import Any
from utils.helpers import bullet_list, explanation_to_text
MAX_TITLE_LENGTH = 60
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
# One transcript line.
def _message(role: str, kind: str, content: str) -> dict[str, str]:
    return {"role": role, "kind": kind, "content": content.strip()}
# The examples as readable text.
def _examples_text(examples: list[dict[str, Any]]) -> str:
    parts = []
    for number, example in enumerate(examples, start=1):
        parts.append(
            f"Example {number}: {example.get('title', '')}\n{example.get('description', '')}".strip()
        )
    return "\n\n".join(parts)
# The questions of one graded attempt, without giving away the answers.
def _quiz_text(results: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"Q{number}. {result.get('question', '')}" for number, result in enumerate(results, start=1)
    )
# What the student answered in one attempt.
def _answers_text(results: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"Q{number}. {result.get('user_answer', '')}"
        for number, result in enumerate(results, start=1)
    )
# The graded outcome of one attempt, with per-question detail.
def _results_text(attempt: dict[str, Any]) -> str:
    lines = [
        f"Score: {attempt.get('score', 0):.0f}% "
        f"({attempt.get('correct_count', 0)}/{attempt.get('total_questions', 0)} correct)",
        attempt.get("overall_feedback", ""),
    ]
    for number, result in enumerate(attempt.get("results", []), start=1):
        mark = "correct" if result.get("is_correct") else "wrong"
        lines.append(
            f"Q{number} [{mark}] {result.get('question', '')}\n"
            f"   Your answer: {result.get('user_answer', '')}\n"
            f"   Correct answer: {result.get('correct_answer', '')}"
        )
    weak = attempt.get("weak_concepts") or []
    if weak:
        lines.append(f"Concepts to revisit:\n{bullet_list(weak)}")
    tip = attempt.get("study_tip")
    if tip:
        lines.append(f"Study tip: {tip}")
    return "\n".join(part for part in lines if part)
# The recommendation that closes a session.
def _recommendation_text(recommendation: dict[str, Any]) -> str:
    parts = [
        f"Next topic: {recommendation.get('next_topic', '')}",
        recommendation.get("summary", ""),
        f"Why: {recommendation.get('reason', '')}" if recommendation.get("reason") else "",
    ]
    guidance = recommendation.get("extra_guidance") or []
    if guidance:
        parts.append(f"Extra guidance:\n{bullet_list(guidance)}")
    return "\n".join(part for part in parts if part)
# The full transcript for a study state, in the order it happened.
# Only completed quiz attempts are included: a quiz still waiting for answers lives in the
# checkpoint, and recording it early would duplicate it once the attempt is graded.
def build_messages(state: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    topic = (state.get("topic") or "").strip()
    if not topic:
        return messages
    messages.append(_message(ROLE_USER, "topic", topic))
    explanation = state.get("explanation") or {}
    if explanation:
        messages.append(_message(ROLE_ASSISTANT, "explanation", explanation_to_text(explanation)))
    examples = state.get("examples") or []
    if examples:
        messages.append(_message(ROLE_ASSISTANT, "examples", _examples_text(examples)))
    re_explanations = state.get("re_explanations") or []
    for index, attempt in enumerate(state.get("attempts") or []):
        results = attempt.get("results", [])
        messages.append(_message(ROLE_ASSISTANT, "quiz", _quiz_text(results)))
        messages.append(_message(ROLE_USER, "answers", _answers_text(results)))
        messages.append(_message(ROLE_ASSISTANT, "results", _results_text(attempt)))
        if index < len(re_explanations):
            messages.append(
                _message(
                    ROLE_ASSISTANT,
                    "re_explanation",
                    explanation_to_text(re_explanations[index]),
                )
            )
    recommendation = state.get("recommendation") or {}
    if recommendation:
        messages.append(
            _message(ROLE_ASSISTANT, "recommendation", _recommendation_text(recommendation))
        )
    return messages
# The lines that are not stored yet, given how many are already saved.
def new_messages(state: dict[str, Any], already_stored: int) -> list[dict[str, str]]:
    return build_messages(state)[max(already_stored, 0) :]
# A short title for a session. The topic analysis is written by the LLM that already ran, so its
# clean topic is the generated title; the raw topic, truncated, is the fallback.
def title_for(state: dict[str, Any], fallback: str = "") -> str:
    analysis = state.get("topic_analysis") or {}
    title = (analysis.get("clean_topic") or "").strip()
    if not title:
        title = (state.get("topic") or fallback or "").strip()
    return truncate_title(title)
# Keep a title to a length that fits the sidebar.
def truncate_title(title: str) -> str:
    title = " ".join(title.split())
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    return title[: MAX_TITLE_LENGTH - 1].rstrip() + "…"
