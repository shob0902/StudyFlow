# Streamlit glue for the auth layer: the login gate, the callback handler and logout.
from typing import Any
import streamlit as st
from auth import remember
from auth.avatar import fetch_avatar
from auth.config import is_configured, load_config, missing_settings
from auth.errors import AuthError, AuthConfigError
from auth.google_oauth import PendingLoginStore, build_authorization_url, raise_for_callback_error
from auth.service import load_user_learning_data, login_with_google, logout
from auth.session import SessionStore
from auth.user_context import UserContext
from ui.auth_ui import login_page, login_setup_needed, user_badge
from utils.helpers import StudyAssistantError, log_error, log_step
SESSION_ID_KEY = "auth_session_id"
USER_KEY = "user_context"
ERROR_KEY = "auth_error"
AUTH_URL_KEY = "auth_url"
LEARNING_DATA_KEY = "user_learning_data"
AVATAR_KEY = "user_avatar"
CLEAR_COOKIE_KEY = "clear_sign_in_cookie"
# Study keys that belong to one signed-in user and must never survive a logout.
USER_SCOPED_KEYS = [
    "thread_id",
    "study_state",
    "next_nodes",
    "execution_log",
    "error",
    "celebrated",
    "graph_png",
    "transcript",
    "read_only",
    "history_limit",
    # The platform sections keep their own working state; all of it belongs to one user.
    "section",
    "section_nav",
    "pending_section",
    "doc_quiz",
    "coding_prefill",
    "coding_problem_id",
    "coding_code",
    "coding_result",
    "coding_hint_level",
    "coding_notes",
    "coding_queue",
    "coding_confirm_solution",
    "review_queue",
    "review_index",
    "review_shown",
    "review_done",
    "plan_new",
    "last_upload",
    "attached_document_id",
    "attach_pick",
    "document_upload",
    LEARNING_DATA_KEY,
    AVATAR_KEY,
    USER_KEY,
    AUTH_URL_KEY,
]
# One store of in-flight logins per server process; it must outlive the page redirect.
@st.cache_resource
def pending_store() -> PendingLoginStore:
    return PendingLoginStore()
# One store of signed-in sessions per server process.
@st.cache_resource
def session_store() -> SessionStore:
    ttl = load_config().session_ttl_minutes if is_configured() else 720
    return SessionStore(ttl_minutes=ttl)
# Show an authentication message on the next render and drop the spent consent URL, so retrying works.
def _set_error(message: str) -> None:
    st.session_state[ERROR_KEY] = message
    st.session_state.pop(AUTH_URL_KEY, None)
# Forget everything tied to the previous user, then start fresh state for this one.
def _start_user_session(user: UserContext) -> None:
    for key in USER_SCOPED_KEYS:
        st.session_state.pop(key, None)
    st.session_state[USER_KEY] = user
    st.session_state[AVATAR_KEY] = fetch_avatar(user.profile_picture)
    try:
        st.session_state[LEARNING_DATA_KEY] = load_user_learning_data(user)
    except StudyAssistantError as error:
        log_error("Could not load the user's saved learning data")
        _set_error(str(error))
        st.session_state[LEARNING_DATA_KEY] = {"recent_sessions": [], "summary": {}}
    log_step("AUTH", f"User context ready for {user.user_id}")
# Handle the ?code=/?state= (or ?error=) Google adds to the redirect URI.
def _handle_callback() -> None:
    params = st.query_params
    error_code = params.get("error")
    code = params.get("code")
    state = params.get("state")
    if not error_code and not code:
        return
    st.query_params.clear()
    try:
        if error_code:
            raise_for_callback_error(str(error_code))
        session = login_with_google(
            load_config(), pending_store(), session_store(), str(code), str(state or "")
        )
    except AuthError as error:
        _set_error(str(error))
        st.rerun()
        return
    except StudyAssistantError as error:
        _set_error(str(error))
        st.rerun()
        return
    except Exception:
        log_error("Unexpected failure while completing the Google sign-in")
        _set_error("Sign-in failed unexpectedly. Please try again.")
        st.rerun()
        return
    st.session_state[SESSION_ID_KEY] = session.session_id
    _start_user_session(session.user)
    st.rerun()
# The signed-in user for this browser session, or None. Validated server-side on every rerun.
#
# A page refresh starts a fresh browser connection with empty session state, so the session id
# is taken from the cookie instead. It still has to name a live session in the store, which is
# what makes a server restart require a new sign-in.
def current_user() -> UserContext | None:
    session_id = st.session_state.get(SESSION_ID_KEY)
    from_cookie = False
    if not session_id:
        session_id = remember.read_cookie()
        from_cookie = bool(session_id)
    if not session_id:
        return None
    session = session_store().get(session_id)
    if session is None:
        _clear_session_state()
        # A cookie left over from an earlier run of the server is not an expired visit worth
        # reporting; it is just stale, so drop it quietly.
        if from_cookie:
            st.session_state[CLEAR_COOKIE_KEY] = True
            log_step("AUTH", "Ignoring a sign-in cookie from an earlier run of the server")
        else:
            _set_error("Your session has expired. Please sign in again.")
        return None
    if from_cookie:
        st.session_state[SESSION_ID_KEY] = session_id
        log_step("AUTH", "Restored the sign-in from its cookie")
    stored = st.session_state.get(USER_KEY)
    # The session store is the source of truth: if it names anyone else, start that user's state from scratch.
    if not isinstance(stored, UserContext) or stored.user_id != session.user.user_id:
        _start_user_session(session.user)
    return session.user
# Keys created one per item, which cannot be listed ahead of time.
USER_SCOPED_PREFIXES = ("coding_editor_",)
# Drop every key tied to the signed-in user, including the session id.
def _clear_session_state() -> None:
    st.session_state.pop(SESSION_ID_KEY, None)
    for key in USER_SCOPED_KEYS:
        st.session_state.pop(key, None)
    for key in [k for k in list(st.session_state) if str(k).startswith(USER_SCOPED_PREFIXES)]:
        st.session_state.pop(key, None)
# Sign the user out: revoke the session server-side and wipe their state from this browser session.
def sign_out() -> None:
    logout(session_store(), st.session_state.get(SESSION_ID_KEY))
    _clear_session_state()
    # The session is already dead server-side, so the cookie is harmless; this removes it too.
    st.session_state[CLEAR_COOKIE_KEY] = True
    st.query_params.clear()
    log_step("AUTH", "User signed out")
# The Google consent URL for this browser session, built once so one state is reused per visitor.
def _auth_url() -> str:
    if AUTH_URL_KEY not in st.session_state:
        st.session_state[AUTH_URL_KEY] = build_authorization_url(load_config(), pending_store())
    return str(st.session_state[AUTH_URL_KEY])
# Draw the landing page for visitors who are not signed in.
def _render_login() -> None:
    if not is_configured():
        st.html(login_setup_needed(missing_settings()))
    else:
        try:
            st.html(login_page(_auth_url()))
        except AuthConfigError as error:
            st.html(login_setup_needed(missing_settings()))
            st.error(str(error))
    if st.session_state.get(ERROR_KEY):
        st.warning(st.session_state.pop(ERROR_KEY))
# Write or remove the sign-in cookie. Called once per run, while the page is rendering, because
# a script queued immediately before st.rerun() would never reach the browser.
def _sync_cookie() -> None:
    session_id = st.session_state.get(SESSION_ID_KEY)
    if session_id:
        ttl = load_config().session_ttl_minutes if is_configured() else 720
        remember.write_cookie(session_id, ttl * 60)
    elif st.session_state.pop(CLEAR_COOKIE_KEY, False):
        remember.clear_cookie()
# The login gate: returns the signed-in user, or renders the landing page and stops the script.
def require_login() -> UserContext:
    _handle_callback()
    user = current_user()
    _sync_cookie()
    if user is None:
        _render_login()
        st.stop()
    if st.session_state.get(ERROR_KEY):
        st.warning(st.session_state.pop(ERROR_KEY))
    return user
# Sidebar block: who is signed in, plus the logout button.
def render_user_panel(user: UserContext) -> None:
    st.html(user_badge(user, str(st.session_state.get(AVATAR_KEY, ""))))
    if st.button("Logout", key="logout_button", width="stretch"):
        sign_out()
        st.rerun()
# The saved learning data loaded at login, refreshed on demand.
def learning_data(user: UserContext, refresh: bool = False) -> dict[str, Any]:
    if refresh or LEARNING_DATA_KEY not in st.session_state:
        try:
            st.session_state[LEARNING_DATA_KEY] = load_user_learning_data(user)
        except StudyAssistantError:
            log_error("Could not refresh the user's saved learning data")
            st.session_state[LEARNING_DATA_KEY] = {"recent_sessions": [], "summary": {}}
    return dict(st.session_state[LEARNING_DATA_KEY])
