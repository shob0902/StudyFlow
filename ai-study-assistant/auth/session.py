# Server-side login sessions: creation, lookup, expiry and logout. No Streamlit imports.
import secrets
import threading
import time
from dataclasses import dataclass
from auth.errors import SessionExpiredError
from auth.user_context import UserContext
from utils.helpers import log_step
# One signed-in session. The browser only ever holds the opaque session_id.
@dataclass(frozen=True)
class AuthSession:
    session_id: str
    user: UserContext
    created_at: float
    expires_at: float
    # True once the session has outlived its TTL.
    def is_expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at
# Tracks which session ids are currently signed in, so logout and expiry are enforced server-side.
class SessionStore:
    def __init__(self, ttl_minutes: int = 720) -> None:
        self._ttl_seconds = max(int(ttl_minutes), 1) * 60
        self._lock = threading.Lock()
        self._sessions: dict[str, AuthSession] = {}
    # Start a session for a verified user and return it.
    def create(self, user: UserContext) -> AuthSession:
        now = time.time()
        session = AuthSession(
            session_id=secrets.token_urlsafe(32),
            user=user,
            created_at=now,
            expires_at=now + self._ttl_seconds,
        )
        with self._lock:
            self._prune(now)
            self._sessions[session.session_id] = session
        log_step("AUTH", f"Session started for user {user.user_id}")
        return session
    # Return a live session, or None when it is unknown or expired.
    def get(self, session_id: str | None) -> AuthSession | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired():
                del self._sessions[session_id]
                return None
            return session
    # Return a live session or explain that it expired.
    def require(self, session_id: str | None) -> AuthSession:
        session = self.get(session_id)
        if session is None:
            raise SessionExpiredError("Your session has expired. Please sign in again.")
        return session
    # End a session. Safe to call for an id that is already gone.
    def revoke(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            if self._sessions.pop(session_id, None) is not None:
                log_step("AUTH", "Session ended")
    # Drop every session that has expired.
    def _prune(self, now: float) -> None:
        for session_id in [sid for sid, s in self._sessions.items() if s.is_expired(now)]:
            del self._sessions[session_id]
    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)
