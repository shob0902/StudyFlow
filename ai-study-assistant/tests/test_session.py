# Session creation, expiry, logout and the login-to-session path through the service layer.
import time
import pytest
from auth.errors import SessionExpiredError
from auth.google_oauth import PendingLoginStore, build_authorization_url
from auth.service import login_with_google, logout, user_context_for_profile
from auth.session import SessionStore
from auth.user_context import UserContext
from db.database import get_connection
from db.repository import UserRepository
from urllib.parse import parse_qs, urlparse
# A user context built from a stored record.
def _context() -> UserContext:
    return UserContext(
        user_id="user-1", google_id="google-1", email="ada@example.com", name="Ada Lovelace"
    )
# A new session gets an opaque id and a future expiry.
def test_session_is_created_with_an_opaque_id():
    store = SessionStore(ttl_minutes=60)
    session = store.create(_context())
    assert len(session.session_id) > 30
    assert session.expires_at > time.time()
    assert store.get(session.session_id).user.user_id == "user-1"
# An unknown session id is never accepted.
def test_unknown_session_is_not_accepted():
    store = SessionStore()
    assert store.get("made-up") is None
    assert store.get(None) is None
    with pytest.raises(SessionExpiredError):
        store.require("made-up")
# An expired session stops working and is forgotten.
def test_expired_session_is_rejected(monkeypatch):
    store = SessionStore(ttl_minutes=1)
    session = store.create(_context())
    monkeypatch.setattr(time, "time", lambda: session.expires_at + 1)
    assert store.get(session.session_id) is None
    assert len(store) == 0
# Logging out revokes the session server-side, so the old id is dead.
def test_logout_revokes_the_session():
    store = SessionStore()
    session = store.create(_context())
    logout(store, session.session_id)
    assert store.get(session.session_id) is None
    logout(store, session.session_id)  # revoking twice is harmless
# Signing in creates the user record and a session for that user.
def test_login_creates_user_and_session(db_file, oauth_config, google_claims, monkeypatch):
    pending = PendingLoginStore()
    state = parse_qs(urlparse(build_authorization_url(oauth_config, pending)).query)["state"][0]
    monkeypatch.setattr("auth.google_oauth.exchange_code", lambda *a, **k: {"id_token": "tok"})
    monkeypatch.setattr("auth.google_oauth.verify_id_token", lambda config, token: google_claims)
    sessions = SessionStore()
    session = login_with_google(oauth_config, pending, sessions, code="code", state=state)
    assert session.user.email == "ada@example.com"
    assert session.user.user_id
    connection = get_connection()
    try:
        stored = UserRepository(connection).get_by_google_id(google_claims["sub"])
    finally:
        connection.close()
    assert stored is not None and stored.id == session.user.user_id
# Signing in a second time reuses the same application user.
def test_second_login_reuses_the_same_user(db_file, google_claims):
    from auth.google_oauth import GoogleProfile
    profile = GoogleProfile(
        google_id=google_claims["sub"], email="ada@example.com", name="Ada", picture=""
    )
    first = user_context_for_profile(profile)
    second = user_context_for_profile(profile)
    assert first.user_id == second.user_id
# Each session carries its own user, so two logins never share identity.
def test_sessions_do_not_share_identity():
    store = SessionStore()
    ada = store.create(_context())
    grace = store.create(
        UserContext(user_id="user-2", google_id="google-2", email="grace@example.com", name="Grace")
    )
    assert store.get(ada.session_id).user.user_id == "user-1"
    assert store.get(grace.session_id).user.user_id == "user-2"
    logout(store, ada.session_id)
    assert store.get(grace.session_id) is not None
