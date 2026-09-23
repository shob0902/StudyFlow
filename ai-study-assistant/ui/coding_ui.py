# Coding Practice: generate a problem, write code, run it, submit it, and get graded help.
from typing import Any
import streamlit as st
from coding import feedback, grading, problems
from coding.runner import SandboxError, available_languages, isolation_notice
from db import learning_service
from learning.mastery import DIFFICULTIES
from learning.misconceptions import CODE_FAILURE_LABELS
from ui import cards
from utils.helpers import StudyAssistantError
STATE_PROBLEM = "coding_problem_id"
EDITOR_PREFIX = "coding_editor_"
STATE_RESULT = "coding_result"
STATE_HINTS = "coding_hint_level"
STATE_NOTES = "coding_notes"
STATE_QUEUE = "coding_queue"
MAX_PROBLEMS = 5
# The coding practice page.
def render(user: Any) -> None:
    st.header("Coding practice")
    level, message = isolation_notice()
    st.html(cards.sandbox_notice(level, message))
    languages = available_languages()
    if not languages:
        st.warning("Code execution is switched off on this server, so problems cannot be graded.")
        return
    _render_generator(user, languages)
    problem = _current_problem(user)
    if problem is None:
        _render_history(user)
        return
    _render_problem(user, problem)
# The form that asks for a new problem.
def _render_generator(user: Any, languages: list[str]) -> None:
    weak = learning_service.mastery_for_user(user.user_id)[:5]
    suggestions = [state.concept_name for state in weak if state.is_started]
    with st.expander("New problem", expanded=_current_problem(user) is None):
        with st.form("new_coding_problem"):
            topic = st.text_input(
                "Topic",
                value=st.session_state.get("coding_prefill", ""),
                placeholder=suggestions[0] if suggestions else "Binary search",
            )
            columns = st.columns(3)
            language = columns[0].selectbox("Language", languages)
            difficulty = columns[1].selectbox("Difficulty", list(DIFFICULTIES), index=1)
            count = columns[2].number_input(
                "Problems", 1, MAX_PROBLEMS, 1,
                help="Generate a set to work through one after another.",
            )
            asked = st.form_submit_button("Generate", type="primary", width="stretch")
        if suggestions:
            st.caption("Your weakest concepts: " + ", ".join(suggestions))
    if not asked:
        return
    st.session_state["coding_prefill"] = ""
    chosen = topic.strip() or (suggestions[0] if suggestions else "")
    if not chosen:
        st.warning("Enter a topic to practise.")
        return
    _generate_set(user, chosen, difficulty, language, int(count))
# Generate a set of problems and queue them.
#
# Each one is a separate call, so a set that fails half way still leaves the student with the
# problems that did come back rather than nothing at all.
def _generate_set(user: Any, topic: str, difficulty: str, language: str, count: int) -> None:
    generated: list[str] = []
    failure = ""
    progress = st.progress(0.0, text=f"Writing a {difficulty} problem about {topic}...")
    for number in range(count):
        progress.progress(
            number / count, text=f"Writing problem {number + 1} of {count} about {topic}..."
        )
        try:
            problem = problems.generate_problem(user.user_id, topic, difficulty, language)
        except StudyAssistantError as error:
            failure = str(error)
            break
        generated.append(problem.id)
    progress.empty()
    if not generated:
        st.error(failure or "No problems could be generated. Please try again.")
        return
    if failure:
        st.warning(f"Made {len(generated)} of {count} problems. {failure}")
    first = problems.get_problem(user.user_id, generated[0])
    st.session_state[STATE_QUEUE] = generated[1:]
    _open_problem(first)
    st.rerun()
# Put a problem in the editor.
def _open_problem(problem: Any) -> None:
    st.session_state[STATE_PROBLEM] = problem.id
    st.session_state[STATE_RESULT] = None
    st.session_state[STATE_HINTS] = 0
    st.session_state[STATE_NOTES] = []
# The problem currently open, if any.
def _current_problem(user: Any) -> Any:
    problem_id = st.session_state.get(STATE_PROBLEM)
    if not problem_id:
        return None
    return problems.get_problem(user.user_id, problem_id)
# The problem, the editor and everything that happens around them.
def _render_problem(user: Any, problem: Any) -> None:
    remaining = st.session_state.get(STATE_QUEUE) or []
    if remaining:
        st.caption(f"{len(remaining)} more problem{'s' if len(remaining) != 1 else ''} in this set")
    st.subheader(problem.title)
    st.caption(f"{problem.difficulty} · {problem.language} · {len(problem.tests)} test cases")
    st.markdown(problem.statement)
    if problem.constraints:
        st.caption(f"**Constraints:** {problem.constraints}")
    if problem.examples:
        with st.expander("Examples"):
            for example in problem.examples:
                st.code(example, language=None)
    if problem.concepts:
        st.caption("Concepts: " + ", ".join(c.split("::")[-1].replace("_", " ") for c in problem.concepts))
    # One editor per problem, so moving to the next one starts from its own signature instead
    # of inheriting the previous answer. A shared key would keep the old code on screen.
    code = st.text_area(
        "Your solution",
        value=problems.starter_code(problem),
        height=320,
        key=f"{EDITOR_PREFIX}{problem.id}",
        help="Write the function the problem asks for. Tab indents; the tests call your function directly.",
    )
    run, submit, hint, skip = st.columns(4)
    if run.button("Run", width="stretch"):
        _run(problem, code, record=False, user=user)
    if submit.button("Submit", type="primary", width="stretch"):
        _run(problem, code, record=True, user=user)
    if hint.button("Get a hint", width="stretch"):
        _hint(problem, code)
    label = "Next problem" if remaining else "Close"
    if skip.button(label, width="stretch"):
        _advance(user)
    _render_result(user, problem, code)
    _render_notes()
    _render_history(user)
# Open the next problem in the set, or clear the editor when the set is finished.
def _advance(user: Any) -> None:
    queue = list(st.session_state.get(STATE_QUEUE) or [])
    while queue:
        following = problems.get_problem(user.user_id, queue.pop(0))
        if following is not None:
            st.session_state[STATE_QUEUE] = queue
            _open_problem(following)
            st.rerun()
            return
    st.session_state[STATE_QUEUE] = []
    st.session_state[STATE_PROBLEM] = None
    st.rerun()
# Run or submit the code.
def _run(problem: Any, code: str, record: bool, user: Any) -> None:
    with st.spinner("Running your code..."):
        try:
            if record:
                outcome = grading.submit(
                    user.user_id, problem, code, hints_used=st.session_state.get(STATE_HINTS, 0)
                )
                st.session_state[STATE_RESULT] = outcome
            else:
                result = grading.run_submission(problem, code)
                st.session_state[STATE_RESULT] = grading.SubmissionOutcome(
                    submission_id="", result=result,
                    status="ran" if result.all_passed else "wrong_answer",
                    failure_kind="", concepts={},
                )
        except SandboxError as error:
            st.error(str(error))
            return
        except StudyAssistantError as error:
            st.error(str(error))
            return
    st.rerun()
# What happened last time the code ran.
def _render_result(user: Any, problem: Any, code: str) -> None:
    outcome = st.session_state.get(STATE_RESULT)
    if outcome is None:
        return
    result = outcome.result
    st.html(
        cards.metrics(
            [
                ("Passed", f"{result.passed}/{result.total}", ""),
                ("Time", f"{result.runtime_ms:.0f} ms", ""),
                ("Isolation", result.isolation, ""),
                (
                    "Result",
                    "Accepted" if result.all_passed else CODE_FAILURE_LABELS.get(outcome.failure_kind, "Not yet"),
                    "",
                ),
            ]
        )
    )
    if result.error:
        st.code(result.error, language=None)
    if result.failures:
        with st.expander(f"{len(result.failures)} failing case(s)", expanded=not result.all_passed):
            for case in result.failures[:6]:
                st.caption(
                    f"input `{case.get('input')}` → expected `{case.get('expected')}`, "
                    f"got `{case.get('actual')}`"
                )
                if case.get("error"):
                    st.code(str(case["error"]).strip().splitlines()[-1], language=None)
    if outcome.concepts:
        st.caption(
            "Mastery updated: "
            + ", ".join(
                f"{slug.split('::')[-1].replace('_', ' ')} {data['mastery']:.0f}%"
                for slug, data in outcome.concepts.items()
            )
        )
    if outcome.submission_id and result.all_passed:
        if st.session_state.get(STATE_QUEUE):
            if st.button("On to the next problem", type="primary", width="stretch"):
                _advance(user)
        _render_review(problem, code)
    elif outcome.submission_id and not result.all_passed:
        _render_diagnosis(problem, code, result)
# Complexity analysis of a solution that passes.
def _render_review(problem: Any, code: str) -> None:
    if st.button("Analyse my solution", width="stretch"):
        with st.spinner("Reading your code..."):
            try:
                review = feedback.review_solution(problem, code)
            except StudyAssistantError as error:
                st.error(str(error))
                return
        st.success(
            f"**Time:** {review.time_complexity}  ·  **Space:** {review.space_complexity}\n\n"
            f"{review.reasoning}"
        )
        if review.improvement:
            st.info(f"**Possible improvement:** {review.improvement}")
        if review.edge_cases:
            st.caption("Edge cases worth checking: " + "; ".join(review.edge_cases))
# Why a failing submission failed.
def _render_diagnosis(problem: Any, code: str, result: Any) -> None:
    if st.button("Why did it fail?", width="stretch"):
        with st.spinner("Looking at what went wrong..."):
            try:
                analysis = feedback.analyse_failure(problem, code, result)
            except StudyAssistantError as error:
                st.error(str(error))
                return
        st.warning(f"**Likely issue:** {analysis.likely_issue}\n\n{analysis.hint}")
# Ask for the next level of help.
def _hint(problem: Any, code: str) -> None:
    level = min(feedback.MAX_LEVEL, st.session_state.get(STATE_HINTS, 0) + 1)
    if level >= feedback.SOLUTION_LEVEL and not st.session_state.get("coding_confirm_solution"):
        st.session_state["coding_confirm_solution"] = True
        st.warning("The next step shows the full solution. Press the hint button again to see it.")
        return
    outcome = st.session_state.get(STATE_RESULT)
    with st.spinner(f"Thinking of a {feedback.LEVEL_NAMES[level].lower()}..."):
        try:
            text = feedback.hint(problem, code, level, outcome.result if outcome else None)
        except StudyAssistantError as error:
            st.error(str(error))
            return
    st.session_state[STATE_HINTS] = level
    st.session_state.setdefault(STATE_NOTES, []).append((feedback.LEVEL_NAMES[level], text))
    st.rerun()
# The hints given so far.
def _render_notes() -> None:
    notes = st.session_state.get(STATE_NOTES) or []
    if not notes:
        return
    st.subheader("Help so far")
    for label, text in notes:
        st.info(f"**{label}.** {text}")
    st.caption(
        f"Hints used: {len(notes)} of {feedback.MAX_LEVEL}. Hints reduce how much a solved "
        "problem raises your mastery."
    )
# Problems this user has generated before.
def _render_history(user: Any) -> None:
    try:
        history = problems.list_problems(user.user_id, 10)
    except StudyAssistantError:
        return
    if not history:
        return
    with st.expander("Your problems"):
        for problem in history:
            columns = st.columns([5, 1], vertical_alignment="center")
            columns[0].caption(f"**{problem.title}** · {problem.difficulty} · {problem.language}")
            if columns[1].button("Open", key=f"open_problem_{problem.id}", width="stretch"):
                st.session_state[STATE_QUEUE] = []
                _open_problem(problem)
                st.rerun()
