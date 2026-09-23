# The history sidebar driven through the real page: listing, opening, renaming, deleting, isolation.
from pathlib import Path
import pytest
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
# A signed-in user plus a running app, with any given sessions already stored.
def _signed_in_app(monkeypatch, db_file, topics=(), google_id="google-1", name="Ada Lovelace"):
    from auth.google_oauth import GoogleProfile
    from auth.service import user_context_for_profile
    from auth.streamlit_auth import session_store
    from auth.user_context import new_thread_id
    from db import service
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    user = user_context_for_profile(
        GoogleProfile(google_id=google_id, email=f"{google_id}@example.com", name=name)
    )
    records = []
    for topic in topics:
        thread_id = new_thread_id(user.user_id)
        records.append(service.start_study_session(user.user_id, thread_id, topic))
    session = session_store().create(user)
    app = AppTest.from_file(APP_FILE, default_timeout=60)
    app.session_state["auth_session_id"] = session.session_id
    app.run()
    return app, user, records
# Every piece of HTML the page rendered.
def _html(app) -> str:
    return " ".join(element.value for element in app.get("html"))
# Find a widget by key, or None.
def _widget(collection, key):
    return next((widget for widget in collection if widget.key == key), None)
# A user with no sessions sees the New session button and an empty state, not an error.
def test_empty_history_is_handled(monkeypatch, db_file):
    app, _, _ = _signed_in_app(monkeypatch, db_file)
    assert not app.exception
    assert _widget(app.button, "new_session") is not None
    assert "No sessions yet." in _html(app)
# Stored sessions appear in the sidebar, grouped by when they were last touched.
def test_sessions_appear_in_the_sidebar(monkeypatch, db_file):
    app, _, records = _signed_in_app(monkeypatch, db_file, topics=["Recursion", "Embeddings"])
    assert not app.exception
    labels = [button.label for button in app.button]
    assert any("Recursion" in label for label in labels)
    assert any("Embeddings" in label for label in labels)
    assert "Today" in _html(app)
    for record in records:
        assert _widget(app.button, f"open_{record.id}") is not None
# The newest session is listed first.
def test_sessions_are_ordered_by_recent_activity(monkeypatch, db_file):
    from db import service
    app, user, records = _signed_in_app(monkeypatch, db_file, topics=["Older", "Newer"])
    service.save_progress(user.user_id, records[0].thread_id, "active", None, 1)
    app.run()
    open_labels = [b.label for b in app.button if b.key and b.key.startswith("open_")]
    assert open_labels[0].endswith("Older")
# Opening a stored session whose graph state is gone shows its saved transcript.
def test_opening_a_session_loads_its_transcript(monkeypatch, db_file):
    from db import service
    app, user, records = _signed_in_app(monkeypatch, db_file, topics=["Recursion"])
    service.record_session_state(
        user.user_id,
        records[0].thread_id,
        {
            "topic": "Recursion",
            "topic_analysis": {"clean_topic": "Recursion"},
            "explanation": {"definition": "A function that calls itself."},
            "attempts": [],
            "re_explanations": [],
        },
    )
    app.run()
    _widget(app.button, f"open_{records[0].id}").click().run()
    assert not app.exception
    html = _html(app)
    assert any("Saved session" in header.value for header in app.header)
    assert "A function that calls itself." in html
    assert "Explanation" in html
    assert app.session_state["thread_id"] == records[0].thread_id
# Starting a new session clears the workspace without deleting anything.
def test_new_session_clears_the_workspace(monkeypatch, db_file):
    app, user, records = _signed_in_app(monkeypatch, db_file, topics=["Recursion"])
    _widget(app.button, f"open_{records[0].id}").click().run()
    assert app.session_state["thread_id"] is not None
    _widget(app.button, "new_session").click().run()
    assert not app.exception
    assert app.session_state["thread_id"] is None
    assert app.session_state["study_state"] is None
    assert app.session_state["transcript"] is None
    from db import service
    assert service.session_count(user.user_id) == 1
    assert _widget(app.button, f"open_{records[0].id}") is not None
# Renaming updates the sidebar straight away, with no page refresh.
def test_renaming_updates_the_sidebar(monkeypatch, db_file):
    app, user, records = _signed_in_app(monkeypatch, db_file, topics=["Recursion"])
    _widget(app.text_input, f"rename_{records[0].id}").set_value("Recursion revision").run()
    _widget(app.button, f"save_{records[0].id}").click().run()
    assert not app.exception
    assert any("Recursion revision" in button.label for button in app.button)
    from db import service
    assert service.get_session(user.user_id, records[0].id).title == "Recursion revision"
# Deleting asks for confirmation first.
def test_delete_needs_confirmation(monkeypatch, db_file):
    from db import service
    app, user, records = _signed_in_app(monkeypatch, db_file, topics=["Recursion"])
    _widget(app.button, f"delete_{records[0].id}").click().run()
    assert not app.exception
    assert service.get_session(user.user_id, records[0].id) is not None
    assert any("cannot be undone" in warning.value for warning in app.warning)
# A confirmed delete removes the session from the sidebar immediately.
def test_confirmed_delete_removes_the_session(monkeypatch, db_file):
    from db import service
    app, user, records = _signed_in_app(monkeypatch, db_file, topics=["Recursion", "Embeddings"])
    target = records[0]
    _widget(app.checkbox, f"confirm_{target.id}").set_value(True).run()
    _widget(app.button, f"delete_{target.id}").click().run()
    assert not app.exception
    assert service.get_session(user.user_id, target.id) is None
    assert _widget(app.button, f"open_{target.id}") is None
    assert _widget(app.button, f"open_{records[1].id}") is not None
# Deleting the session that is open returns the workspace to an empty one.
def test_deleting_the_open_session_resets_the_workspace(monkeypatch, db_file):
    app, user, records = _signed_in_app(monkeypatch, db_file, topics=["Recursion"])
    target = records[0]
    _widget(app.button, f"open_{target.id}").click().run()
    assert app.session_state["thread_id"] == target.thread_id
    _widget(app.checkbox, f"confirm_{target.id}").set_value(True).run()
    _widget(app.button, f"delete_{target.id}").click().run()
    assert not app.exception
    assert app.session_state["thread_id"] is None
    assert "No sessions yet." in _html(app)
# One user's history is never visible to another.
def test_history_is_isolated_between_users(monkeypatch, db_file):
    ada_app, ada, ada_records = _signed_in_app(monkeypatch, db_file, topics=["Ada's topic"])
    grace_app, grace, _ = _signed_in_app(
        monkeypatch, db_file, topics=["Grace's topic"], google_id="google-2", name="Grace Hopper"
    )
    assert not grace_app.exception
    labels = [button.label for button in grace_app.button]
    assert any("Grace's topic" in label for label in labels)
    assert not any("Ada's topic" in label for label in labels)
    assert _widget(grace_app.button, f"open_{ada_records[0].id}") is None
    assert "Ada's topic" not in _html(grace_app)
