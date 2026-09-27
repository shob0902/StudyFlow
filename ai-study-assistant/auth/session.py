# Login sessions: creation, lookup, expiry and logout, in memory or in the database. No Streamlit imports.
import hashlib
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
    # A fresh session for this user, not yet stored anywhere.
    def _new_session(self, user: UserContext) -> AuthSession:
        now = time.time()
        return AuthSession(
            session_id=secrets.token_urlsafe(32),
            user=user,
            created_at=now,
            expires_at=now + self._ttl_seconds,
        )
    # Start a session for a verified user and return it.
    def create(self, user: UserContext) -> AuthSession:
        session = self._new_session(user)
        now = session.created_at
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
# The same store kept in the database, so a server restart or redeploy does not sign everyone
# out: the cookie's session id still names a stored row afterwards. Only a SHA-256 hash of the id
# is stored, so a leaked database row cannot be replayed as a cookie.
class DatabaseSessionStore(SessionStore):
    # The key a session id is stored under.
    @staticmethod
    def _hash(session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    # Start a session for a verified user, store it and drop any that have expired.
    def create(self, user: UserContext) -> AuthSession:
        from db.database import session as db_session
        session = self._new_session(user)
        with db_session() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM auth_sessions WHERE expires_at <= ?", (session.created_at,)
                )
                connection.execute(
                    "INSERT INTO auth_sessions (id_hash, user_id, created_at, expires_at)"
                    " VALUES (?, ?, ?, ?)",
                    (self._hash(session.session_id), user.user_id, session.created_at, session.expires_at),
                )
        log_step("AUTH", f"Session started for user {user.user_id}")
        return session
    # Return a live session with its user as currently stored, or None when unknown or expired.
    def get(self, session_id: str | None) -> AuthSession | None:
        if not session_id:
            return None
        from db.database import session as db_session
        from db.models import User
        with db_session() as connection:
            row = connection.execute(
                "SELECT u.*, s.created_at AS session_created_at, s.expires_at AS session_expires_at"
                " FROM auth_sessions s JOIN users u ON u.id = s.user_id WHERE s.id_hash = ?",
                (self._hash(session_id),),
            ).fetchone()
            if row is None:
                return None
            session = AuthSession(
                session_id=session_id,
                user=UserContext.from_user(User.from_row(row)),
                created_at=row["session_created_at"],
                expires_at=row["session_expires_at"],
            )
            if session.is_expired():
                with connection:
                    connection.execute(
                        "DELETE FROM auth_sessions WHERE id_hash = ?", (self._hash(session_id),)
                    )
                return None
        return session
    # End a session. Safe to call for an id that is already gone.
    def revoke(self, session_id: str | None) -> None:
        if not session_id:
            return
        from db.database import session as db_session
        with db_session() as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM auth_sessions WHERE id_hash = ?", (self._hash(session_id),)
                )
        if cursor.rowcount:
            log_step("AUTH", "Session ended")
    # How many sessions are still live.
    def __len__(self) -> int:
        from db.database import session as db_session
        with db_session() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM auth_sessions WHERE expires_at > ?", (time.time(),)
            ).fetchone()
        return int(row["n"])
