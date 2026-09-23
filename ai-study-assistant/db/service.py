# Thin service over the repositories so the UI never builds SQL or holds a connection open.
from typing import Any
from db.database import session
from db.models import SessionMessage, StudySessionRecord
from db.repository import MessageRepository, StudySessionRepository, user_learning_summary
from db.transcript import new_messages, title_for, truncate_title
SIDEBAR_PAGE_SIZE = 15
# Record that this user started a study session on a graph thread they own.
def start_study_session(user_id: str, thread_id: str, topic: str) -> StudySessionRecord:
    with session() as connection:
        return StudySessionRepository(connection).create(
            user_id, thread_id, topic, truncate_title(topic)
        )
# Save the latest status, score and attempt count for one of this user's sessions.
def save_progress(
    user_id: str, thread_id: str, status: str, score: float | None, attempts: int
) -> None:
    with session() as connection:
        StudySessionRepository(connection).update_progress(
            user_id, thread_id, status, score, attempts
        )
# Save everything new about a session in one place: its title and the transcript lines it gained.
# Called after each graph run, and safe to call repeatedly: nothing already stored is written twice.
def record_session_state(user_id: str, thread_id: str, state: dict[str, Any]) -> int:
    with session() as connection:
        sessions = StudySessionRepository(connection)
        record = sessions.get_by_thread(user_id, thread_id)
        if record is None:
            return 0
        sessions.set_auto_title(user_id, thread_id, title_for(state, record.topic))
        messages = MessageRepository(connection)
        stored = messages.count_for_session(user_id, record.id)
        pending = new_messages(state, stored)
        return messages.append(user_id, record.id, pending)
# One page of this user's sessions, most recently updated first.
def list_sessions(
    user_id: str, limit: int = SIDEBAR_PAGE_SIZE, offset: int = 0
) -> list[StudySessionRecord]:
    with session() as connection:
        return StudySessionRepository(connection).list_for_user(user_id, limit, offset)
# This user's most recent study sessions, newest first.
def recent_sessions(user_id: str, limit: int = 10) -> list[StudySessionRecord]:
    return list_sessions(user_id, limit)
# How many sessions this user has in total.
def session_count(user_id: str) -> int:
    with session() as connection:
        return StudySessionRepository(connection).count_for_user(user_id)
# Fetch one of this user's sessions, or None when it is not theirs.
def get_session(user_id: str, session_id: str) -> StudySessionRecord | None:
    with session() as connection:
        return StudySessionRepository(connection).get(user_id, session_id)
# Fetch one of this user's sessions by graph thread, or None when it is not theirs.
def get_session_by_thread(user_id: str, thread_id: str) -> StudySessionRecord | None:
    with session() as connection:
        return StudySessionRepository(connection).get_by_thread(user_id, thread_id)
# Rename one of this user's sessions.
def rename_session(user_id: str, session_id: str, title: str) -> StudySessionRecord:
    with session() as connection:
        return StudySessionRepository(connection).rename(user_id, session_id, title)
# Delete one of this user's sessions and its transcript.
def delete_session(user_id: str, session_id: str) -> bool:
    with session() as connection:
        return StudySessionRepository(connection).delete(user_id, session_id)
# The transcript of one of this user's sessions. Loaded only when a session is opened.
def load_messages(user_id: str, session_id: str, limit: int = 500) -> list[SessionMessage]:
    with session() as connection:
        return MessageRepository(connection).list_for_session(user_id, session_id, limit)
# Aggregate learning numbers for this user.
def learning_summary(user_id: str) -> dict:
    with session() as connection:
        return user_learning_summary(connection, user_id)
