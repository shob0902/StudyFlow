# End-to-end checks of the Streamlit page: what an unauthenticated visitor can and cannot see.
from pathlib import Path
import pytest
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
# Run app.py in Streamlit's test harness with fake OAuth credentials and a throwaway database.
def _run_app(monkeypatch, db_file, configured: bool = True):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com" if configured else "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret" if configured else "")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
    app = AppTest.from_file(APP_FILE, default_timeout=30)
    app.run()
    return app
# All the HTML the page rendered, as one string.
def _page_html(app) -> str:
    return " ".join(element.value for element in app.get("html"))
# A visitor who is not signed in sees the landing page with the Google button.
def test_unauthenticated_visitor_sees_the_login_screen(monkeypatch, db_file):
    app = _run_app(monkeypatch, db_file)
    assert not app.exception
    html = _page_html(app)
    assert "Continue with Google" in html
    assert "Your personalized AI learning companion." in html
    assert "accounts.google.com" in html
# The login screen never renders the study workflow or its forms.
def test_unauthenticated_visitor_gets_no_study_ui(monkeypatch, db_file):
    app = _run_app(monkeypatch, db_file)
    assert not app.exception
    html = _page_html(app)
    assert "What do you want to learn?" not in html
    assert len(app.text_input) == 0
    assert len(app.button) == 0
# The client secret is never rendered into the page.
def test_login_screen_does_not_leak_the_secret(monkeypatch, db_file):
    app = _run_app(monkeypatch, db_file)
    assert "test-secret" not in _page_html(app)
# Without credentials the page explains the setup instead of showing a broken button.
def test_missing_credentials_show_setup_instructions(monkeypatch, db_file):
    app = _run_app(monkeypatch, db_file, configured=False)
    assert not app.exception
    html = _page_html(app)
    assert "Google sign-in is not configured" in html
    assert "GOOGLE_CLIENT_ID" in html
    assert "Continue with Google" not in html
# Sign a fake user in through the real session store and return the running app.
def _run_signed_in(monkeypatch, db_file, name: str = "Ada Lovelace", google_id: str = "google-1"):
    from auth.service import user_context_for_profile
    from auth.google_oauth import GoogleProfile
    from auth.streamlit_auth import session_store
    user = user_context_for_profile(
        GoogleProfile(google_id=google_id, email=f"{name.split()[0].lower()}@example.com", name=name)
    )
    session = session_store().create(user)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    app = AppTest.from_file(APP_FILE, default_timeout=30)
    app.session_state["auth_session_id"] = session.session_id
    app.run()
    return app, user
# A signed-in user is greeted by name and reaches the study UI.
def test_signed_in_user_sees_the_app(monkeypatch, db_file):
    app, user = _run_signed_in(monkeypatch, db_file)
    assert not app.exception
    html = _page_html(app)
    assert "Welcome, Ada" in html
    assert "ada@example.com" in html
    assert "Continue with Google" not in html
    assert any(button.label == "Logout" for button in app.button)
# Logging out clears the previous user's study state and returns to the login screen.
def test_logout_returns_to_login_and_clears_state(monkeypatch, db_file):
    app, user = _run_signed_in(monkeypatch, db_file)
    app.session_state["study_state"] = {"topic": "Recursion", "explanation": {"definition": "secret"}}
    app.session_state["thread_id"] = f"{user.user_id}::thread"
    logout_button = next(button for button in app.button if button.label == "Logout")
    logout_button.click().run()
    assert not app.exception
    html = _page_html(app)
    assert "Continue with Google" in html
    assert "Recursion" not in html
    assert "study_state" not in app.session_state
    assert "auth_session_id" not in app.session_state
    assert "user_context" not in app.session_state
# A different session id must never inherit the previous user's study state.
def test_second_user_never_sees_the_first_users_state(monkeypatch, db_file):
    from auth.google_oauth import GoogleProfile
    from auth.service import user_context_for_profile
    from auth.streamlit_auth import session_store
    app, ada = _run_signed_in(monkeypatch, db_file)
    app.session_state["study_state"] = {"topic": "Recursion", "explanation": {"definition": "ada-only"}}
    app.session_state["thread_id"] = f"{ada.user_id}::thread"
    grace = user_context_for_profile(
        GoogleProfile(google_id="google-2", email="grace@example.com", name="Grace Hopper")
    )
    app.session_state["auth_session_id"] = session_store().create(grace).session_id
    app.run()
    assert not app.exception
    html = _page_html(app)
    assert "Welcome, Grace" in html
    assert "Welcome, Ada" not in html
    assert "ada-only" not in html
    assert "Recursion" not in html
    assert app.session_state["user_context"].user_id == grace.user_id
    assert app.session_state["study_state"] is None
    assert app.session_state["thread_id"] is None
