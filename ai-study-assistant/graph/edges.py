# Routing function for the conditional edge that runs after quiz evaluation.
from typing import Literal
from graph.state import MAX_RETRIES, PASSING_SCORE, StudyState
from learning.mastery import NEXT_CONCEPT, PREREQUISITE_REVIEW, RE_EXPLAIN as MASTERY_RE_EXPLAIN
from utils.helpers import log_step
RE_EXPLAIN = "re_explain"
RECOMMEND = "recommend"
# Router: choose re_explain or recommend from the score and retry count.
def route_after_evaluation(state: StudyState) -> Literal["re_explain", "recommend"]:
    score = state.get("score", 0.0)
    retry_count = state.get("retry_count", 0)
    log_step("ROUTER", f"Score = {score:.0f}, retries used = {retry_count}/{MAX_RETRIES}")
    action = state.get("adaptive_action", "")
    if action:
        log_step("ROUTER", f"Mastery engine says: {action}")
    # The mastery engine can override a bare pass: a concept it considers weak, or one the
    # student keeps failing, is worth re-explaining even when this quiz scraped through.
    if score >= PASSING_SCORE:
        if action in (MASTERY_RE_EXPLAIN, PREREQUISITE_REVIEW) and retry_count < MAX_RETRIES:
            log_step("ROUTER", f"Passed, but mastery is still weak -> going to {RE_EXPLAIN}")
            return RE_EXPLAIN
        log_step("ROUTER", f"Passed -> going to {RECOMMEND}")
        return RECOMMEND
    if action == NEXT_CONCEPT:
        log_step("ROUTER", f"Concept already mastered -> going to {RECOMMEND}")
        return RECOMMEND
    if retry_count >= MAX_RETRIES:
        log_step("ROUTER", f"Max retries reached -> going to {RECOMMEND} with extra guidance")
        return RECOMMEND
    log_step("ROUTER", f"Below {PASSING_SCORE}% -> going to {RE_EXPLAIN}")
    return RE_EXPLAIN
