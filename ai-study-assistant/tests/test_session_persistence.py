# Staying signed in across a page refresh, and being asked to sign in again after a restart.
from pathlib import Path
import pytest
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP_FILE = str(Path(__file__).resolve().parents[1] / "app.py")
# A user with a live session in the store.
@pytest.fixture
def signed_in(monkeypatch, db_file):
    from auth.google_oauth import GoogleProfile
    from auth.service import user_context_for_profile
    from auth.streamlit_auth import session_store
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    user = user_context_for_profile(
        GoogleProfile(google_id="google-1", email="ada@example.com", name="Ada Lovelace")
    )
    return user, session_store().create(user)
# Open the app the way a browser would, handing back whatever cookie it holds.
def _open(monkeypatch, cookie: str = ""):
    import auth.remember as remember
    monkeypatch.setattr(remember, "read_cookie", lambda: cookie)
    app = AppTest.from_file(APP_FILE, default_timeout=120)
    app.run()
    return app
# All the HTML the page rendered.
def _html(app) -> str:
    return " ".join(element.value for element in app.get("html"))
# A refresh keeps the user signed in: the cookie names a session the store still has.
def test_refresh_keeps_you_signed_in(monkeypatch, signed_in, db_file):
    _user, session = signed_in
    app = _open(monkeypatch, cookie=session.session_id)
    assert not app.exception
    assert "Continue with Google" not in _html(app)
    assert "Welcome, Ada" in _html(app)
    assert app.session_state["auth_session_id"] == session.session_id
# The session id is adopted into session state, so the rest of the run behaves normally.
def test_refresh_restores_the_user_context(monkeypatch, signed_in, db_file):
    from auth.user_context import UserContext
    user, session = signed_in
    app = _open(monkeypatch, cookie=session.session_id)
    restored = app.session_state["user_context"]
    assert isinstance(restored, UserContext)
    assert restored.user_id == user.user_id
    assert restored.email == "ada@example.com"
# Restarting the server empties the in-memory store, so the cookie no longer signs anyone in.
def test_restarting_the_server_requires_a_new_sign_in(monkeypatch, signed_in, db_file):
    from auth.streamlit_auth import session_store
    _user, session = signed_in
    # A restart is a fresh session store, which is what clearing the cached resource simulates.
    session_store.clear()
    app = _open(monkeypatch, cookie=session.session_id)
    assert not app.exception
    assert "Continue with Google" in _html(app)
    assert "auth_session_id" not in app.session_state
# A stale cookie is removed from the browser, and quietly: it is not an expired visit.
def test_a_stale_cookie_is_cleared_quietly(monkeypatch, signed_in, db_file):
    import auth.remember as remember
    from auth.streamlit_auth import session_store
    _user, session = signed_in
    session_store.clear()
    cleared = []
    monkeypatch.setattr(remember, "clear_cookie", lambda: cleared.append(True))
    app = _open(monkeypatch, cookie=session.session_id)
    assert cleared == [True]
    assert not any("expired" in warning.value.lower() for warning in app.warning)
    assert "Continue with Google" in _html(app)
# While signed in, the cookie is refreshed on every run so it does not lapse mid-session.
def test_the_cookie_is_refreshed_while_signed_in(monkeypatch, signed_in, db_file):
    import auth.remember as remember
    _user, session = signed_in
    written = []
    monkeypatch.setattr(
        remember, "write_cookie", lambda value, max_age: written.append((value, max_age))
    )
    _open(monkeypatch, cookie=session.session_id)
    assert written
    assert written[-1][0] == session.session_id
    assert written[-1][1] > 0
# A cookie naming nothing at all is ignored.
def test_an_unknown_cookie_is_ignored(monkeypatch, signed_in, db_file):
    app = _open(monkeypatch, cookie="not-a-real-session")
    assert not app.exception
    assert "Continue with Google" in _html(app)
# With no cookie the visitor simply sees the login screen.
def test_no_cookie_means_the_login_screen(monkeypatch, signed_in, db_file):
    app = _open(monkeypatch, cookie="")
    assert "Continue with Google" in _html(app)
# Logging out revokes the session, so the cookie cannot sign that user back in.
def test_logout_beats_the_cookie(monkeypatch, signed_in, db_file):
    _user, session = signed_in
    app = _open(monkeypatch, cookie=session.session_id)
    next(button for button in app.button if button.label == "Logout").click().run()
    assert "Continue with Google" in _html(app)
    # The same cookie on a later visit is refused, because the session is gone server-side.
    again = _open(monkeypatch, cookie=session.session_id)
    assert "Continue with Google" in _html(again)
    assert "auth_session_id" not in again.session_state
# An expired session is refused even though the cookie is still held.
def test_an_expired_session_is_refused(monkeypatch, signed_in, db_file):
    import time
    from auth.streamlit_auth import session_store
    _user, session = signed_in
    monkeypatch.setattr(time, "time", lambda: session.expires_at + 1)
    app = _open(monkeypatch, cookie=session.session_id)
    assert "Continue with Google" in _html(app)
# One user's cookie never restores another user's session.
def test_a_cookie_only_restores_its_own_user(monkeypatch, signed_in, db_file, users):
    from auth.google_oauth import GoogleProfile
    from auth.service import user_context_for_profile
    from auth.streamlit_auth import session_store
    _ada, ada_session = signed_in
    grace = user_context_for_profile(
        GoogleProfile(google_id="google-2", email="grace@example.com", name="Grace Hopper")
    )
    grace_session = session_store().create(grace)
    app = _open(monkeypatch, cookie=grace_session.session_id)
    assert "Welcome, Grace" in _html(app)
    assert "Ada" not in _html(app)
    assert app.session_state["user_context"].user_id == grace.user_id
    assert app.session_state["auth_session_id"] == grace_session.session_id
    assert ada_session.session_id != grace_session.session_id
