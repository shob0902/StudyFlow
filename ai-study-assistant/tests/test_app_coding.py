# The coding page driven through the real app: working a set of problems one after another.
from pathlib import Path
import pytest
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
# Move to a section by clicking its sidebar navigation button.
def _nav(app, section):
    from ui.shell import nav_key
    next(button for button in app.button if button.key == nav_key(section)).click().run()
    return app
GOOD_CODE = "def solve(n):\n    return n * 2\n"
# A signed-in user on the coding page, with the given problems already stored and queued.
def _coding_app(monkeypatch, db_file, titles=("First", "Second", "Third")):
    from auth.google_oauth import GoogleProfile
    from auth.service import user_context_for_profile
    from auth.streamlit_auth import session_store
    from coding.problems import CodingProblem, store_problem
    from db import learning_service
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("CODE_EXECUTION_MODE", "subprocess")
    user = user_context_for_profile(
        GoogleProfile(google_id="google-1", email="ada@example.com", name="Ada")
    )
    learning_service.register_names(["Doubling"], "Python")
    stored = [
        store_problem(
            user.user_id,
            CodingProblem(
                id="", user_id=user.user_id, title=title, statement="Return twice n.",
                language="python", difficulty="easy", signature="def solve(n):",
                constraints="", examples=[],
                tests=[{"input": "(2,)", "expected": "4"}, {"input": "(0,)", "expected": "0"}],
                concepts=["python::doubling"],
            ),
        )
        for title in titles
    ]
    app = AppTest.from_file(APP_FILE, default_timeout=120)
    app.session_state["auth_session_id"] = session_store().create(user).session_id
    app.run()
    _nav(app, "Coding Practice")
    return app, user, stored
# Put a set in the editor the way generating one does.
def _open_set(app, stored):
    app.session_state["coding_problem_id"] = stored[0].id
    app.session_state["coding_queue"] = [problem.id for problem in stored[1:]]
    app.run()
    return app
# Find a widget by key.
def _widget(collection, key):
    return next((widget for widget in collection if widget.key == key), None)
# The number of problems is a real control, not a disabled placeholder.
def test_problem_count_is_usable(monkeypatch, db_file):
    from ui.coding_ui import MAX_PROBLEMS
    app, _user, _stored = _coding_app(monkeypatch, db_file)
    assert not app.exception
    counter = _widget(app.number_input, None) or app.number_input[0]
    assert counter.label == "Problems"
    assert counter.disabled is False
    assert counter.max == MAX_PROBLEMS
    assert counter.min == 1
# A queued set says how much is left and offers the next problem.
def test_a_set_shows_what_is_left(monkeypatch, db_file):
    app, _user, stored = _coding_app(monkeypatch, db_file)
    _open_set(app, stored)
    assert not app.exception
    captions = " ".join(caption.value for caption in app.caption)
    assert "2 more problems in this set" in captions
    assert any(button.label == "Next problem" for button in app.button)
    assert any(subheader.value == "First" for subheader in app.subheader)
# Next problem walks the set, and the last one closes the editor.
def test_next_problem_walks_the_set(monkeypatch, db_file):
    app, _user, stored = _coding_app(monkeypatch, db_file)
    _open_set(app, stored)
    next(b for b in app.button if b.label == "Next problem").click().run()
    assert not app.exception
    assert app.session_state["coding_problem_id"] == stored[1].id
    assert app.session_state["coding_queue"] == [stored[2].id]
    assert any(subheader.value == "Second" for subheader in app.subheader)
    next(b for b in app.button if b.label == "Next problem").click().run()
    assert app.session_state["coding_problem_id"] == stored[2].id
    assert app.session_state["coding_queue"] == []
    # The last problem offers Close instead, which clears the editor.
    assert any(button.label == "Close" for button in app.button)
    next(b for b in app.button if b.label == "Close").click().run()
    assert app.session_state["coding_problem_id"] is None
# Moving on gives the next problem its own starter code and clears the previous result.
def test_advancing_resets_the_editor(monkeypatch, db_file):
    app, _user, stored = _coding_app(monkeypatch, db_file)
    _open_set(app, stored)
    app.session_state["coding_hint_level"] = 3
    app.session_state["coding_notes"] = [("Small hint", "look again")]
    next(b for b in app.button if b.label == "Next problem").click().run()
    assert app.session_state["coding_hint_level"] == 0
    assert app.session_state["coding_notes"] == []
    editor = _widget(app.text_area, f"coding_editor_{stored[1].id}")
    assert editor is not None
    assert "your code here" in editor.value
    assert "return n * 2" not in editor.value
    assert app.session_state["coding_result"] is None
# A problem that has been deleted is skipped rather than breaking the set.
def test_deleted_problems_are_skipped(monkeypatch, db_file):
    from coding.problems import delete_problem
    app, user, stored = _coding_app(monkeypatch, db_file)
    _open_set(app, stored)
    delete_problem(user.user_id, stored[1].id)
    next(b for b in app.button if b.label == "Next problem").click().run()
    assert not app.exception
    assert app.session_state["coding_problem_id"] == stored[2].id
# Submitting the last problem of a set still records mastery.
def test_submitting_within_a_set_records_mastery(monkeypatch, db_file):
    from db import learning_service
    app, user, stored = _coding_app(monkeypatch, db_file)
    _open_set(app, stored)
    _widget(app.text_area, f"coding_editor_{stored[0].id}").set_value(GOOD_CODE).run()
    next(b for b in app.button if b.label == "Submit").click().run()
    assert not app.exception
    state = learning_service.mastery_for_concept(user.user_id, "python::doubling")
    assert state is not None and state.attempts == 1
    assert any("On to the next problem" == button.label for button in app.button)
# Opening an old problem from the history starts a set of one.
def test_opening_from_history_clears_the_queue(monkeypatch, db_file):
    app, _user, stored = _coding_app(monkeypatch, db_file)
    _open_set(app, stored)
    opener = _widget(app.button, f"open_problem_{stored[2].id}")
    assert opener is not None
    opener.click().run()
    assert app.session_state["coding_queue"] == []
    assert app.session_state["coding_problem_id"] == stored[2].id
    assert any(button.label == "Close" for button in app.button)
