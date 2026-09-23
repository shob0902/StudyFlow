# Keeping a sign-in across a page refresh.
#
# st.session_state lives only as long as one browser connection, so a refresh loses it. The
# opaque session id is therefore also kept in a cookie: the browser hands it back after a
# refresh, and the server checks it against the in-memory session store as usual.
#
# That store is deliberately in memory, which gives exactly the behaviour asked for:
#   refresh the page  -> cookie is returned, the session is still in the store, you stay in
#   restart the server -> the store is empty, the cookie means nothing, you sign in again
#
# The cookie holds the session id and nothing else: no tokens, no profile, no secrets.
import json
import streamlit as st
from utils.helpers import log_step
COOKIE_NAME = "sa_session"
MAX_AGE_CAP = 60 * 60 * 24 * 30
# The session id the browser is offering, if any.
def read_cookie() -> str:
    try:
        cookies = st.context.cookies or {}
    except Exception:
        return ""
    value = cookies.get(COOKIE_NAME, "")
    return str(value).strip()
# Run a snippet of JavaScript in a zero-height frame. Streamlit's frames run with
# allow-same-origin, so a cookie set here belongs to the app's own origin.
def _run_script(script: str) -> None:
    markup = f"<script>{script}</script>"
    # A frame needs a positive height, so it is one pixel tall inside a container the stylesheet
    # collapses. It stays rendered rather than hidden, because a display:none frame is not
    # guaranteed to run its script.
    with st.container(key="sa_cookie"):
        if hasattr(st, "iframe"):
            st.iframe(markup, height=1)
        else:
            import streamlit.components.v1 as components
            components.html(markup, height=0, width=0)
# Store the session id in the browser, refreshing its lifetime on every run.
def write_cookie(session_id: str, max_age_seconds: int) -> None:
    if not session_id:
        return
    max_age = max(60, min(int(max_age_seconds), MAX_AGE_CAP))
    _run_script(
        "const secure = location.protocol === 'https:' ? '; Secure' : '';"
        f"document.cookie = {json.dumps(COOKIE_NAME)} + '=' + {json.dumps(session_id)}"
        f" + '; path=/; max-age={max_age}; SameSite=Lax' + secure;"
    )
# Remove the cookie. Logout already revokes the session server-side, so this is tidying up:
# a cookie left behind would be refused on the next visit anyway.
def clear_cookie() -> None:
    _run_script(
        f"document.cookie = {json.dumps(COOKIE_NAME)} + '=; path=/; max-age=0; SameSite=Lax';"
    )
    log_step("AUTH", "Cleared the sign-in cookie")
