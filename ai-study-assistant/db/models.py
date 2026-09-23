# Plain data records stored in the database. No Streamlit, no LangGraph, no Google imports.
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
# Current UTC time as an ISO 8601 string. Milliseconds, so rows created in the same second
# still sort deterministically by when they happened.
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
# An application user. `id` is the internal key every user-scoped row points at.
@dataclass(frozen=True)
class User:
    id: str
    google_id: str
    email: str
    name: str
    profile_picture: str
    created_at: str
    last_login_at: str
    # Build a User from a database row.
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "User":
        return cls(
            id=row["id"],
            google_id=row["google_id"],
            email=row["email"],
            name=row["name"],
            profile_picture=row["profile_picture"] or "",
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )
# One study session: this app's conversation. Owned by exactly one user.
@dataclass(frozen=True)
class StudySessionRecord:
    id: str
    user_id: str
    thread_id: str
    topic: str
    status: str
    score: float | None
    attempts: int
    created_at: str
    updated_at: str
    title: str = ""
    title_is_custom: bool = False
    # What the sidebar shows: the title, falling back to the topic.
    @property
    def display_title(self) -> str:
        return self.title or self.topic
    # Build a StudySessionRecord from a database row.
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "StudySessionRecord":
        keys = row.keys()
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            thread_id=row["thread_id"],
            topic=row["topic"],
            status=row["status"],
            score=row["score"],
            attempts=row["attempts"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            title=(row["title"] if "title" in keys else "") or "",
            title_is_custom=bool(row["title_is_custom"]) if "title_is_custom" in keys else False,
        )
# One line of a study session's transcript: what the student asked and what the tutor produced.
@dataclass(frozen=True)
class SessionMessage:
    id: str
    study_session_id: str
    position: int
    role: str
    kind: str
    content: str
    created_at: str
    # Build a SessionMessage from a database row.
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "SessionMessage":
        return cls(
            id=row["id"],
            study_session_id=row["study_session_id"],
            position=row["position"],
            role=row["role"],
            kind=row["kind"],
            content=row["content"],
            created_at=row["created_at"],
        )
