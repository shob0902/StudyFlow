# Session history: titles, transcripts, ordering, paging, deletion and per-user isolation.
from datetime import datetime, timedelta, timezone
import pytest
from auth.errors import UnauthorizedError
from auth.user_context import new_thread_id
from db import service
from db.repository import MessageRepository, StudySessionRepository
from db.transcript import build_messages, new_messages, title_for, truncate_title
from ui import history
# A study state part-way through: topic understood, explained, one graded attempt, not finished.
@pytest.fixture
def state_after_first_quiz() -> dict:
    return {
        "topic": "how do embeddings work in practice",
        "topic_analysis": {"clean_topic": "Embeddings", "difficulty": "beginner"},
        "explanation": {"definition": "A vector of numbers.", "why_it_matters": "Search."},
        "examples": [{"title": "Search", "description": "Find similar documents."}],
        "attempts": [
            {
                "attempt_number": 1,
                "score": 40.0,
                "correct_count": 2,
                "total_questions": 5,
                "passed": False,
                "overall_feedback": "A shaky start.",
                "weak_concepts": ["cosine similarity"],
                "study_tip": "Re-read the analogy.",
                "results": [
                    {
                        "question": "What is an embedding?",
                        "user_answer": "A picture",
                        "correct_answer": "A vector",
                        "is_correct": False,
                        "explanation": "It is a vector.",
                    }
                ],
            }
        ],
        "re_explanations": [{"definition": "Simpler: a list of numbers."}],
        "recommendation": {},
    }
# A user with one session, ready to record against.
@pytest.fixture
def owner(users, db_file):
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    thread_id = new_thread_id(user.id)
    record = service.start_study_session(user.id, thread_id, "how do embeddings work in practice")
    return user, thread_id, record
# --- titles -------------------------------------------------------------
# A new session starts with its topic as the title, cut to a sidebar-friendly length.
def test_new_session_title_comes_from_the_topic(owner):
    _, _, record = owner
    assert record.title == "how do embeddings work in practice"
    assert record.title_is_custom is False
# A long topic is truncated rather than filling the sidebar.
def test_long_titles_are_truncated():
    long_topic = "explain " + "very " * 30 + "long topic"
    assert len(truncate_title(long_topic)) <= 60
    assert truncate_title(long_topic).endswith("…")
    assert truncate_title("short") == "short"
# The title the tutor produced when it analysed the topic becomes the session name.
def test_title_upgrades_to_the_analysed_topic(owner, state_after_first_quiz):
    user, thread_id, record = owner
    assert title_for(state_after_first_quiz) == "Embeddings"
    service.record_session_state(user.id, thread_id, state_after_first_quiz)
    assert service.get_session(user.id, record.id).title == "Embeddings"
# A name the user chose is never replaced by a generated one.
def test_manual_rename_is_never_overwritten(owner, state_after_first_quiz):
    user, thread_id, record = owner
    service.rename_session(user.id, record.id, "My embeddings revision")
    service.record_session_state(user.id, thread_id, state_after_first_quiz)
    renamed = service.get_session(user.id, record.id)
    assert renamed.title == "My embeddings revision"
    assert renamed.title_is_custom is True
# An empty name is refused rather than leaving a session with no label.
def test_rename_requires_a_name(owner):
    user, _, record = owner
    with pytest.raises(Exception):
        service.rename_session(user.id, record.id, "   ")
# --- transcript ---------------------------------------------------------
# The transcript follows the order the session happened in.
def test_transcript_is_in_order(state_after_first_quiz):
    kinds = [message["kind"] for message in build_messages(state_after_first_quiz)]
    assert kinds == [
        "topic",
        "explanation",
        "examples",
        "quiz",
        "answers",
        "results",
        "re_explanation",
    ]
    roles = [message["role"] for message in build_messages(state_after_first_quiz)]
    assert roles[0] == "user"
    assert roles[1] == "assistant"
    assert roles[4] == "user"
# A state with no topic produces nothing to store.
def test_empty_state_has_no_transcript():
    assert build_messages({}) == []
    assert build_messages({"topic": "   "}) == []
# Saving twice does not duplicate anything, and later progress appends.
def test_recording_twice_adds_no_duplicates(owner, state_after_first_quiz):
    user, thread_id, record = owner
    first = service.record_session_state(user.id, thread_id, state_after_first_quiz)
    second = service.record_session_state(user.id, thread_id, state_after_first_quiz)
    assert first == 7
    assert second == 0
    messages = service.load_messages(user.id, record.id)
    assert len(messages) == 7
    assert [m.position for m in messages] == list(range(7))
    finished = dict(state_after_first_quiz)
    finished["recommendation"] = {"next_topic": "Vector Databases", "reason": "Natural next step."}
    assert service.record_session_state(user.id, thread_id, finished) == 1
    assert len(service.load_messages(user.id, record.id)) == 8
# Only the lines beyond what is stored are handed to the database.
def test_new_messages_skips_what_is_stored(state_after_first_quiz):
    assert len(new_messages(state_after_first_quiz, 0)) == 7
    assert len(new_messages(state_after_first_quiz, 5)) == 2
    assert new_messages(state_after_first_quiz, 99) == []
# The saved transcript keeps what the student was told, so it reads back later.
def test_transcript_content_is_readable(owner, state_after_first_quiz):
    user, thread_id, record = owner
    service.record_session_state(user.id, thread_id, state_after_first_quiz)
    messages = service.load_messages(user.id, record.id)
    assert messages[0].content == "how do embeddings work in practice"
    assert "A vector of numbers." in messages[1].content
    assert "Search" in messages[2].content
    assert "40%" in messages[5].content
    assert "cosine similarity" in messages[5].content
# --- listing, ordering, paging -----------------------------------------
# The history is ordered by most recent activity.
def test_sessions_are_listed_most_recent_first(users, db_file):
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    first = service.start_study_session(user.id, new_thread_id(user.id), "Recursion")
    second = service.start_study_session(user.id, new_thread_id(user.id), "Embeddings")
    service.save_progress(user.id, first.thread_id, "active", None, 1)
    listed = [record.topic for record in service.list_sessions(user.id)]
    assert listed[0] == "Recursion"
    assert set(listed) == {"Recursion", "Embeddings"}
    assert service.session_count(user.id) == 2
# The sidebar asks for one page at a time instead of every session.
def test_listing_is_paged(users, db_file):
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    for number in range(5):
        service.start_study_session(user.id, new_thread_id(user.id), f"Topic {number}")
    assert len(service.list_sessions(user.id, limit=2)) == 2
    assert len(service.list_sessions(user.id, limit=2, offset=2)) == 2
    assert len(service.list_sessions(user.id, limit=2, offset=4)) == 1
    assert service.session_count(user.id) == 5
# --- deletion -----------------------------------------------------------
# Deleting a session takes its transcript with it.
def test_delete_removes_the_messages_too(owner, state_after_first_quiz, connection):
    user, thread_id, record = owner
    service.record_session_state(user.id, thread_id, state_after_first_quiz)
    assert service.delete_session(user.id, record.id) is True
    assert service.get_session(user.id, record.id) is None
    remaining = connection.execute(
        "SELECT COUNT(*) AS n FROM session_messages WHERE study_session_id = ?", (record.id,)
    ).fetchone()["n"]
    assert remaining == 0
# Deleting something already gone is reported, not crashed.
def test_deleting_twice_is_safe(owner):
    user, _, record = owner
    assert service.delete_session(user.id, record.id) is True
    assert service.delete_session(user.id, record.id) is False
# --- isolation ----------------------------------------------------------
# Two users, each with a session and a transcript.
@pytest.fixture
def two_owners(users, db_file, state_after_first_quiz):
    ada = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    grace = users.upsert_from_google("google-2", "grace@example.com", "Grace")
    ada_thread = new_thread_id(ada.id)
    ada_session = service.start_study_session(ada.id, ada_thread, "Recursion")
    service.record_session_state(ada.id, ada_thread, state_after_first_quiz)
    grace_session = service.start_study_session(grace.id, new_thread_id(grace.id), "Embeddings")
    return ada, grace, ada_session, grace_session
# The history only ever lists your own sessions.
def test_history_is_per_user(two_owners):
    ada, grace, ada_session, grace_session = two_owners
    assert [r.id for r in service.list_sessions(ada.id)] == [ada_session.id]
    assert [r.id for r in service.list_sessions(grace.id)] == [grace_session.id]
    assert service.session_count(grace.id) == 1
# One user cannot read another's transcript.
def test_cannot_read_another_users_messages(two_owners):
    ada, grace, ada_session, _ = two_owners
    assert service.load_messages(ada.id, ada_session.id)
    with pytest.raises(UnauthorizedError):
        service.load_messages(grace.id, ada_session.id)
# One user cannot rename or delete another's session.
def test_cannot_rename_or_delete_another_users_session(two_owners):
    ada, grace, ada_session, _ = two_owners
    with pytest.raises(UnauthorizedError):
        service.rename_session(grace.id, ada_session.id, "mine now")
    assert service.delete_session(grace.id, ada_session.id) is False
    still_there = service.get_session(ada.id, ada_session.id)
    assert still_there is not None
    assert still_there.title != "mine now"
# One user cannot write into another's transcript.
def test_cannot_append_to_another_users_transcript(two_owners, connection, state_after_first_quiz):
    ada, grace, ada_session, _ = two_owners
    messages = MessageRepository(connection)
    with pytest.raises(UnauthorizedError):
        messages.append(grace.id, ada_session.id, [{"role": "user", "kind": "topic", "content": "x"}])
    with pytest.raises(UnauthorizedError):
        messages.count_for_session(grace.id, ada_session.id)
# Recording against a thread the user does not own stores nothing.
def test_recording_another_users_thread_stores_nothing(two_owners, state_after_first_quiz):
    ada, grace, ada_session, _ = two_owners
    assert service.record_session_state(grace.id, ada_session.thread_id, state_after_first_quiz) == 0
# --- grouping and times -------------------------------------------------
# A stored session, with a chosen last-updated time.
class _Record:
    def __init__(self, updated_at: str, score=None, status="active"):
        self.updated_at = updated_at
        self.score = score
        self.status = status
# Sessions fall into the Today / Yesterday / Previous 7 days / Older buckets, in that order.
def test_sessions_are_grouped_by_age():
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    records = [
        _Record((now - timedelta(hours=2)).isoformat()),
        _Record((now - timedelta(days=1)).isoformat()),
        _Record((now - timedelta(days=4)).isoformat()),
        _Record((now - timedelta(days=40)).isoformat()),
    ]
    groups = history.group_sessions(records, now)
    assert [label for label, _ in groups] == [
        history.TODAY,
        history.YESTERDAY,
        history.PREVIOUS_7_DAYS,
        history.OLDER,
    ]
    assert all(len(items) == 1 for _, items in groups)
# Empty groups are left out rather than shown as empty headings.
def test_empty_groups_are_dropped():
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    groups = history.group_sessions([_Record(now.isoformat())], now)
    assert [label for label, _ in groups] == [history.TODAY]
# Times read the way a person would say them.
def test_relative_times_are_readable():
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    assert history.relative_time((now - timedelta(seconds=10)).isoformat(), now) == "just now"
    assert history.relative_time((now - timedelta(minutes=5)).isoformat(), now) == "5 min ago"
    assert history.relative_time((now - timedelta(hours=3)).isoformat(), now) == "3 hr ago"
    assert history.relative_time((now - timedelta(days=1)).isoformat(), now) == "Yesterday"
    assert "Aug" in history.relative_time((now - timedelta(days=30)).isoformat(), now)
    assert history.relative_time("not-a-date", now) == ""
# A session's meta line says when it changed and how it went.
def test_item_meta_shows_time_and_score():
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
    done = _Record((now - timedelta(minutes=5)).isoformat(), score=80.0, status="finished")
    assert "5 min ago" in history.item_meta(done, now)
    assert "80%" in history.item_meta(done, now)
    ongoing = _Record((now - timedelta(minutes=5)).isoformat())
    assert "in progress" in history.item_meta(ongoing, now)
# --- migration ----------------------------------------------------------
# A database written by the previous version gains the history columns and table without losing data.
def test_v1_database_migrates_to_v2(tmp_path, monkeypatch):
    import sqlite3
    from db.database import SCHEMA_VERSION, connect, init_db
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE users (id TEXT PRIMARY KEY, google_id TEXT NOT NULL UNIQUE,"
        " email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, profile_picture TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL, last_login_at TEXT NOT NULL);"
        "CREATE TABLE study_sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),"
        " thread_id TEXT NOT NULL UNIQUE, topic TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',"
        " score REAL, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL);"
        "PRAGMA user_version = 1;"
    )
    old.execute(
        "INSERT INTO users VALUES ('u1','g1','ada@example.com','Ada','','2026-01-01','2026-01-01')"
    )
    old.execute(
        "INSERT INTO study_sessions (id, user_id, thread_id, topic, status, score, attempts,"
        " created_at, updated_at) VALUES ('s1','u1','u1::t','Recursion','finished',90.0,1,"
        " '2026-01-01','2026-01-01')"
    )
    old.commit()
    old.close()
    connection = connect(str(path))
    init_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(study_sessions)")}
    assert {"title", "title_is_custom"} <= columns
    row = connection.execute("SELECT * FROM study_sessions WHERE id = 's1'").fetchone()
    assert row["topic"] == "Recursion"
    assert row["title"] == "Recursion"
    assert row["score"] == 90.0
    tables = {r["name"] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "session_messages" in tables
    repo = StudySessionRepository(connection)
    assert repo.list_for_user("u1")[0].display_title == "Recursion"
    connection.close()
# Migrating an already-current database changes nothing.
def test_migration_is_idempotent(connection, owner):
    from db.database import SCHEMA_VERSION, init_db
    user, _, record = owner
    init_db(connection)
    init_db(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert service.get_session(user.id, record.id) is not None
