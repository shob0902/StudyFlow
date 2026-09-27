# Repositories: every query that touches user-owned data takes a user_id and filters on it.
import sqlite3
import uuid
from typing import Any
from auth.errors import DatabaseError, UnauthorizedError
from db.models import SessionMessage, StudySessionRecord, User, utc_now
from utils.helpers import log_error, log_step
MAX_TITLE_LENGTH = 60
# Read and write application users. Google's `sub` is the external identity; users.id is the internal one.
class UserRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # Look a user up by the stable Google identifier.
    def get_by_google_id(self, google_id: str) -> User | None:
        row = self._connection.execute(
            "SELECT * FROM users WHERE google_id = ?", (google_id,)
        ).fetchone()
        return User.from_row(row) if row else None
    # Look a user up by internal id.
    def get_by_id(self, user_id: str) -> User | None:
        row = self._connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User.from_row(row) if row else None
    # Look a user up by email. Used for reporting conflicts, never for authorization.
    def get_by_email(self, email: str) -> User | None:
        row = self._connection.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return User.from_row(row) if row else None
    # Create the user on first sign-in, or refresh the profile and last_login_at on a return visit.
    def upsert_from_google(
        self, google_id: str, email: str, name: str, profile_picture: str = ""
    ) -> User:
        google_id = str(google_id).strip()
        email = str(email).strip().lower()
        if not google_id or not email:
            raise DatabaseError("Google did not return a usable account. Please try signing in again.")
        now = utc_now()
        existing = self.get_by_google_id(google_id)
        try:
            if existing:
                with self._connection:
                    self._connection.execute(
                        "UPDATE users SET email = ?, name = ?, profile_picture = ?, last_login_at = ? WHERE id = ?",
                        (email, name, profile_picture, now, existing.id),
                    )
                log_step("DB", f"Existing user signed in: {existing.id}")
                return self.get_by_id(existing.id)  # type: ignore[return-value]
            user_id = str(uuid.uuid4())
            with self._connection:
                self._connection.execute(
                    "INSERT INTO users (id, google_id, email, name, profile_picture, created_at, last_login_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, google_id, email, name, profile_picture, now, now),
                )
            log_step("DB", f"Created user record {user_id}")
            return self.get_by_id(user_id)  # type: ignore[return-value]
        except sqlite3.IntegrityError:
            log_error("User upsert hit a uniqueness constraint")
            raise DatabaseError(
                "That email is already linked to a different Google account. "
                "Please sign in with the account you used before."
            )
        except sqlite3.Error:
            log_error("User upsert failed")
            raise DatabaseError("The app could not save your account. Please try again.")
    # How many users exist. Handy for tests and the sidebar.
    def count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
# Read and write study sessions. Every method is scoped to one user_id.
class StudySessionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # Record a new study session for this user.
    def create(
        self, user_id: str, thread_id: str, topic: str, title: str = ""
    ) -> StudySessionRecord:
        now = utc_now()
        session_id = str(uuid.uuid4())
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO study_sessions"
                    " (id, user_id, thread_id, topic, title, title_is_custom, status, score, attempts,"
                    "  created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, 0, 'active', NULL, 0, ?, ?)",
                    (session_id, user_id, thread_id, topic, title or topic, now, now),
                )
        except sqlite3.IntegrityError:
            log_error("Study session insert hit a constraint")
            raise DatabaseError("Could not start that study session. Please try again.")
        except sqlite3.Error:
            log_error("Study session insert failed")
            raise DatabaseError("Could not save your study session. Please try again.")
        return self.get(user_id, session_id)  # type: ignore[return-value]
    # Fetch one of this user's sessions by id. Returns None for anyone else's session.
    def get(self, user_id: str, session_id: str) -> StudySessionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM study_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
        ).fetchone()
        return StudySessionRecord.from_row(row) if row else None
    # Fetch one of this user's sessions by graph thread id. Returns None for anyone else's thread.
    def get_by_thread(self, user_id: str, thread_id: str) -> StudySessionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM study_sessions WHERE thread_id = ? AND user_id = ?", (thread_id, user_id)
        ).fetchone()
        return StudySessionRecord.from_row(row) if row else None
    # List this user's sessions, most recently updated first.
    # Paged, so the sidebar never loads every session the user has.
    def list_for_user(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> list[StudySessionRecord]:
        rows = self._connection.execute(
            "SELECT * FROM study_sessions WHERE user_id = ?"
            " ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, max(offset, 0)),
        ).fetchall()
        return [StudySessionRecord.from_row(row) for row in rows]
    # How many sessions this user has, for the 'show more' control.
    def count_for_user(self, user_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM study_sessions WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row["n"])
    # Rename one of this user's sessions. A manual title is never overwritten afterwards.
    def rename(self, user_id: str, session_id: str, title: str) -> StudySessionRecord:
        title = title.strip()
        if not title:
            raise DatabaseError("Please enter a name for this session.")
        if self.get(user_id, session_id) is None:
            raise UnauthorizedError("That study session does not belong to your account.")
        try:
            with self._connection:
                self._connection.execute(
                    "UPDATE study_sessions SET title = ?, title_is_custom = 1"
                    " WHERE id = ? AND user_id = ?",
                    (title[:MAX_TITLE_LENGTH], session_id, user_id),
                )
        except sqlite3.Error:
            log_error("Study session rename failed")
            raise DatabaseError("Could not rename that session. Please try again.")
        log_step("DB", f"Renamed session {session_id}")
        return self.get(user_id, session_id)  # type: ignore[return-value]
    # Give a session a better automatic title, leaving a manually chosen one alone.
    def set_auto_title(self, user_id: str, thread_id: str, title: str) -> None:
        title = title.strip()[:MAX_TITLE_LENGTH]
        if not title:
            return
        record = self.get_by_thread(user_id, thread_id)
        if record is None:
            raise UnauthorizedError("That study session does not belong to your account.")
        if record.title_is_custom or record.title == title:
            return
        try:
            with self._connection:
                self._connection.execute(
                    "UPDATE study_sessions SET title = ?"
                    " WHERE thread_id = ? AND user_id = ? AND title_is_custom = 0",
                    (title, thread_id, user_id),
                )
        except sqlite3.Error:
            log_error("Study session auto-title failed")
    # Save progress for one of this user's sessions; a thread the user does not own is rejected.
    def update_progress(
        self, user_id: str, thread_id: str, status: str, score: float | None, attempts: int
    ) -> None:
        if self.get_by_thread(user_id, thread_id) is None:
            raise UnauthorizedError("That study session does not belong to your account.")
        try:
            with self._connection:
                self._connection.execute(
                    "UPDATE study_sessions SET status = ?, score = ?, attempts = ?, updated_at = ?"
                    " WHERE thread_id = ? AND user_id = ?",
                    (status, score, attempts, utc_now(), thread_id, user_id),
                )
        except sqlite3.Error:
            log_error("Study session update failed")
            raise DatabaseError("Could not save your progress. Please try again.")
    # Delete one of this user's sessions and, by cascade, its transcript.
    # Returns False when the session is not theirs.
    def delete(self, user_id: str, session_id: str) -> bool:
        try:
            with self._connection:
                cursor = self._connection.execute(
                    "DELETE FROM study_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
                )
        except sqlite3.Error:
            log_error("Study session delete failed")
            raise DatabaseError("Could not delete that session. Please try again.")
        if cursor.rowcount:
            log_step("DB", f"Deleted session {session_id} and its messages")
        return cursor.rowcount > 0
# Read and write a session's transcript. Ownership is always checked through the parent session.
class MessageRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # Raise unless this session belongs to the user.
    def _require_owned(self, user_id: str, session_id: str) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM study_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
        ).fetchone()
        if row is None:
            raise UnauthorizedError("That study session does not belong to your account.")
    # How many transcript lines this session already has.
    def count_for_session(self, user_id: str, session_id: str) -> int:
        self._require_owned(user_id, session_id)
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM session_messages WHERE study_session_id = ?", (session_id,)
        ).fetchone()
        return int(row["n"])
    # Append transcript lines, numbered on from what is already stored. UNIQUE(session, position)
    # turns a repeated write into a no-op instead of a duplicate message.
    def append(self, user_id: str, session_id: str, messages: list[dict[str, str]]) -> int:
        if not messages:
            return 0
        start = self.count_for_session(user_id, session_id)
        now = utc_now()
        rows = [
            (
                str(uuid.uuid4()),
                session_id,
                start + offset,
                message["role"],
                message["kind"],
                message["content"],
                now,
            )
            for offset, message in enumerate(messages)
        ]
        try:
            with self._connection:
                self._connection.executemany(
                    "INSERT INTO session_messages"
                    " (id, study_session_id, position, role, kind, content, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    rows,
                )
        except sqlite3.Error:
            log_error("Transcript append failed")
            raise DatabaseError("Could not save this part of your session. Please try again.")
        return len(rows)
    # This session's transcript, in the order it happened.
    def list_for_session(
        self, user_id: str, session_id: str, limit: int = 500, offset: int = 0
    ) -> list[SessionMessage]:
        self._require_owned(user_id, session_id)
        rows = self._connection.execute(
            "SELECT * FROM session_messages WHERE study_session_id = ?"
            " ORDER BY position ASC LIMIT ? OFFSET ?",
            (session_id, limit, max(offset, 0)),
        ).fetchall()
        return [SessionMessage.from_row(row) for row in rows]
# Summary counts for one user, ready for a future analytics view.
def user_learning_summary(connection: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT COUNT(*) AS sessions, AVG(score) AS average_score, SUM(attempts) AS attempts"
        " FROM study_sessions WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return {
        "sessions": int(row["sessions"] or 0),
        "average_score": float(row["average_score"]) if row["average_score"] is not None else None,
        "quiz_attempts": int(row["attempts"] or 0),
    }
