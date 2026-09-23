# Graph node functions: each does one study step and returns a partial state update.
from typing import Any
from langgraph.types import interrupt
from learning.mastery import CHALLENGE, EASY, HARD, MEDIUM
from graph.state import (
    FIRST_QUIZ_SIZE,
    MAX_RETRIES,
    PASSING_SCORE,
    RETRY_QUIZ_SIZE,
    StudyState,
)
from llm.model import NODE_API_KEYS, get_structured_llm, run_chain
from prompts.prompts import (
    EVALUATION_PROMPT,
    EXAMPLES_PROMPT,
    EXPLANATION_PROMPT,
    QUIZ_PROMPT,
    RE_EXPLANATION_PROMPT,
    RECOMMENDATION_PROMPT,
    TOPIC_ANALYSIS_PROMPT,
)
from schemas.models import (
    Evaluation,
    ExampleSet,
    Explanation,
    Quiz,
    Recommendation,
    TopicAnalysis,
)
from utils.helpers import (
    InvalidStateError,
    LLMError,
    MissingAPIKeyError,
    QuizGenerationError,
    bullet_list,
    clean_quiz_questions,
    explanation_to_text,
    grade_quiz,
    latest_explanation,
    log_step,
    require_fields,
    results_to_text,
)
# How each difficulty should feel, given to the quiz writer alongside the level itself.
DIFFICULTY_GUIDANCE = {
    EASY: "Recall and recognition. Check the basic definitions and the single most important idea.",
    MEDIUM: "Understanding. Ask the student to apply the idea to a straightforward situation.",
    HARD: "Application. Use scenarios, edge cases and questions that need two steps of reasoning.",
    CHALLENGE: "Mastery. Mix this concept with related ones and ask which approach fits and why.",
}
# Return the clean topic title, or the raw user input if not analysed yet.
def _topic_title(state: StudyState) -> str:
    return state.get("topic_analysis", {}).get("clean_topic") or state["topic"]
# Node: analyse the topic into a title, difficulty, key concepts and prerequisites.
def understand_topic(state: StudyState) -> dict[str, Any]:
    log_step("NODE", "Understanding topic")
    topic = state.get("topic", "").strip()
    if not topic:
        raise InvalidStateError("Please enter a topic you want to learn about.")
    chain = TOPIC_ANALYSIS_PROMPT | get_structured_llm(
        TopicAnalysis, NODE_API_KEYS["understand_topic"]
    )
    analysis: TopicAnalysis = run_chain(chain, {"topic": topic}, "topic analysis")
    log_step("NODE", f"Topic understood as '{analysis.clean_topic}' ({analysis.difficulty})")
    return {"topic_analysis": analysis.model_dump()}
# Node: generate the first beginner-friendly explanation.
def generate_explanation(state: StudyState) -> dict[str, Any]:
    log_step("NODE", "Generating explanation")
    require_fields(state, ["topic_analysis"], "generate_explanation")
    chain = EXPLANATION_PROMPT | get_structured_llm(
        Explanation, NODE_API_KEYS["generate_explanation"]
    )
    explanation: Explanation = run_chain(
        chain,
        {
            "topic": _topic_title(state),
            "key_concepts": bullet_list(state["topic_analysis"]["key_concepts"]),
        },
        "explanation",
    )
    return {"explanation": explanation.model_dump()}
# Node: generate 2-4 concrete examples of the topic.
def generate_examples(state: StudyState) -> dict[str, Any]:
    log_step("NODE", "Generating examples")
    require_fields(state, ["explanation"], "generate_examples")
    chain = EXAMPLES_PROMPT | get_structured_llm(ExampleSet, NODE_API_KEYS["generate_examples"])
    example_set: ExampleSet = run_chain(
        chain,
        {
            "topic": _topic_title(state),
            "explanation": explanation_to_text(state["explanation"]),
        },
        "examples",
    )
    examples = [example.model_dump() for example in example_set.examples][:4]
    return {"examples": examples}
# Node: generate and validate a quiz, using the backup key only if the main key fails.
def generate_quiz(state: StudyState) -> dict[str, Any]:
    require_fields(state, ["topic_analysis", "explanation"], "generate_quiz")
    is_retry = state.get("retry_count", 0) > 0
    num_questions = RETRY_QUIZ_SIZE if is_retry else FIRST_QUIZ_SIZE
    attempts = state.get("attempts", [])
    log_step(
        "NODE",
        f"Generating quiz #{len(attempts) + 1} ({num_questions} questions, "
        f"{state.get('quiz_difficulty') or MEDIUM})",
    )
    if is_retry:
        focus = "The student struggled with these concepts, so test them:\n" + bullet_list(
            state.get("weak_concepts", [])
        )
    else:
        focus = "Cover these key concepts:\n" + bullet_list(
            state["topic_analysis"]["key_concepts"]
        )
    previous_questions = [
        result["question"] for attempt in attempts for result in attempt["results"]
    ]
    difficulty = state.get("quiz_difficulty") or MEDIUM
    inputs = {
        "topic": _topic_title(state),
        "explanation": explanation_to_text(latest_explanation(state)),
        "num_questions": num_questions,
        "focus": focus,
        "difficulty": difficulty,
        "difficulty_guidance": DIFFICULTY_GUIDANCE.get(difficulty, DIFFICULTY_GUIDANCE[MEDIUM]),
        "avoid_questions": bullet_list(previous_questions),
    }
    quiz_keys = [NODE_API_KEYS["generate_quiz"], NODE_API_KEYS["generate_quiz_backup"]]
    best_questions: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for key_name in quiz_keys:
        try:
            chain = QUIZ_PROMPT | get_structured_llm(Quiz, key_name)
            quiz: Quiz = run_chain(chain, inputs, "quiz generation")
        except (LLMError, MissingAPIKeyError) as error:
            last_error = error
            log_step("NODE", f"Quiz generation with {key_name} failed: {error}")
            continue
        questions = clean_quiz_questions([q.model_dump() for q in quiz.questions])
        if len(questions) >= num_questions:
            best_questions = questions[:num_questions]
            break
        if len(questions) > len(best_questions):
            best_questions = questions
        log_step("NODE", f"Only {len(questions)} valid questions from {key_name}")
    if not best_questions:
        if last_error is not None:
            raise last_error
        raise QuizGenerationError(
            "The AI could not create a valid quiz for this topic. Please try again."
        )
    return {"quiz": best_questions, "user_answers": []}
# Node: pause the graph with interrupt() until the UI resumes it with answers.
def wait_for_answers(state: StudyState) -> dict[str, Any]:
    log_step("NODE", "Waiting for user answers")
    require_fields(state, ["quiz"], "wait_for_answers")
    answers = interrupt({"message": "Please answer the quiz", "num_questions": len(state["quiz"])})
    if not isinstance(answers, list) or len(answers) != len(state["quiz"]):
        raise InvalidStateError("The submitted answers don't match the quiz. Please try again.")
    log_step("GRAPH", f"Resumed with {len(answers)} answers")
    return {"user_answers": [str(answer) for answer in answers]}
# Node: grade the answers in Python and add LLM feedback to the attempt history.
def evaluate_answers(state: StudyState) -> dict[str, Any]:
    log_step("NODE", "Evaluating answers")
    require_fields(state, ["quiz", "user_answers"], "evaluate_answers")
    quiz, user_answers = state["quiz"], state["user_answers"]
    if len(quiz) != len(user_answers):
        raise InvalidStateError("The number of answers does not match the number of questions.")
    results, correct_count, score = grade_quiz(quiz, user_answers)
    log_step("NODE", f"Correct: {correct_count}/{len(quiz)} -> score {score:.0f}%")
    try:
        chain = EVALUATION_PROMPT | get_structured_llm(
            Evaluation, NODE_API_KEYS["evaluate_answers"]
        )
        evaluation: Evaluation = run_chain(
            chain,
            {
                "topic": _topic_title(state),
                "score": f"{score:.0f}",
                "results": results_to_text(results),
            },
            "answer evaluation",
        )
        feedback_data = evaluation.model_dump()
    except LLMError:
        log_step("NODE", "Feedback generation failed, using simple fallback feedback")
        missed = [result["question"] for result in results if not result["is_correct"]]
        feedback_data = {
            "overall_feedback": f"You answered {correct_count} of {len(quiz)} questions correctly.",
            "strengths": [],
            "weak_concepts": missed,
            "study_tip": "Review the explanations for the questions you missed.",
        }
    attempt_record = {
        "attempt_number": len(state.get("attempts", [])) + 1,
        "score": score,
        "correct_count": correct_count,
        "total_questions": len(quiz),
        "passed": score >= PASSING_SCORE,
        "results": results,
        **feedback_data,
    }
    return {
        "score": score,
        "feedback": feedback_data["overall_feedback"],
        "weak_concepts": feedback_data["weak_concepts"],
        "attempts": [attempt_record],
    }
# Node: generate a simpler explanation and increase the retry count.
def re_explain_topic(state: StudyState) -> dict[str, Any]:
    retry_count = state.get("retry_count", 0) + 1
    log_step("NODE", f"Re-explaining topic (retry {retry_count}/{MAX_RETRIES})")
    require_fields(state, ["explanation"], "re_explain_topic")
    weak_concepts = state.get("weak_concepts") or state["topic_analysis"]["key_concepts"]
    chain = RE_EXPLANATION_PROMPT | get_structured_llm(
        Explanation, NODE_API_KEYS["re_explain_topic"]
    )
    simpler: Explanation = run_chain(
        chain,
        {
            "topic": _topic_title(state),
            "previous_explanation": explanation_to_text(latest_explanation(state)),
            "weak_concepts": bullet_list(weak_concepts),
            "attempt": retry_count,
        },
        "re-explanation",
    )
    return {
        "re_explanations": [simpler.model_dump()],
        "retry_count": retry_count,
    }
# Node: recommend the next topic, with extra guidance if the student did not pass.
def recommend_next_topic(state: StudyState) -> dict[str, Any]:
    score = state.get("score", 0.0)
    passed = score >= PASSING_SCORE
    log_step("NODE", f"Recommending next topic (passed={passed})")
    last_attempt = state["attempts"][-1] if state.get("attempts") else {}
    chain = RECOMMENDATION_PROMPT | get_structured_llm(
        Recommendation, NODE_API_KEYS["recommend_next_topic"]
    )
    recommendation: Recommendation = run_chain(
        chain,
        {
            "topic": _topic_title(state),
            "score": f"{score:.0f}",
            "passed": "yes" if passed else "no",
            "strengths": bullet_list(last_attempt.get("strengths", [])),
            "weak_concepts": bullet_list(state.get("weak_concepts", [])),
            "prerequisites": bullet_list(state.get("topic_analysis", {}).get("prerequisites", [])),
        },
        "recommendation",
    )
    log_step("NODE", f"Next topic: {recommendation.next_topic}")
    return {
        "recommendation": recommendation.model_dump(),
        "next_topic": recommendation.next_topic,
    }
