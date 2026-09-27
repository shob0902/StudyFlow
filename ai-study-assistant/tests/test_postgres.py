# The Postgres backend: statement translation always, and a real round trip when a test database
# is available. Set TEST_DATABASE_URL to a throwaway Postgres database (never the production one)
# to run the round trip; every table it creates is dropped again afterwards.
import os
import sqlite3
import pytest
from db.database import _postgres_schema, _to_postgres
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
# '?' placeholders become psycopg's '%s', and a literal '%' is escaped rather than read as one.
def test_placeholders_are_translated():
    assert _to_postgres("SELECT * FROM t WHERE a = ? AND b LIKE '10%'") == (
        "SELECT * FROM t WHERE a = %s AND b LIKE '10%%'"
    )
# REAL columns become DOUBLE PRECISION, so scores keep SQLite's precision.
def test_schema_uses_double_precision():
    schema = _postgres_schema()
    assert "DOUBLE PRECISION" in schema
    assert " REAL" not in schema
# Point the app at the test Postgres database, and drop everything it created afterwards.
@pytest.fixture
def postgres(monkeypatch):
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    import db.database as database
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    database._initialised.discard(database.POSTGRES_TARGET)
    yield database
    with database.session() as connection:
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
        ).fetchall()
        for row in tables:
            connection.execute(f'DROP TABLE IF EXISTS "{row["tablename"]}" CASCADE')
    database._initialised.discard(database.POSTGRES_TARGET)
    for pool in database._pools.values():
        pool.close()
    database._pools.clear()
# Users, study sessions, transcripts and mastery all round-trip through Postgres.
def test_data_round_trips_through_postgres(postgres):
    from db.learning_service import mastery_for_user, record_attempts
    from db.repository import MessageRepository, StudySessionRepository, UserRepository
    from learning.mastery import Attempt
    with postgres.session() as connection:
        users = UserRepository(connection)
        user = users.upsert_from_google("g-1", "Ada@Example.com", "Ada")
        again = users.upsert_from_google("g-1", "ada@example.com", "Ada L")
        assert again.id == user.id and again.name == "Ada L"
        sessions = StudySessionRepository(connection)
        record = sessions.create(user.id, f"{user.id}::t1", "Recursion")
        messages = MessageRepository(connection)
        line = [{"role": "user", "kind": "topic", "content": "100% recursion"}]
        messages.append(user.id, record.id, line)
        assert [m.content for m in messages.list_for_session(user.id, record.id)] == ["100% recursion"]
        assert sessions.list_for_user(user.id)[0].title == "Recursion"
    record_attempts(
        user.id,
        [Attempt(concept_slug="cs::recursion", correct=True, score=0.9, concept_name="Recursion", subject="CS")],
    )
    record_attempts(user.id, [Attempt(concept_slug="cs::recursion", correct=False, concept_name="Recursion")])
    states = mastery_for_user(user.id)
    assert [s.concept_slug for s in states] == ["cs::recursion"]
    assert states[0].attempts == 2
    with postgres.session() as connection:
        assert StudySessionRepository(connection).delete(user.id, record.id) is True
        assert connection.execute(
            "SELECT COUNT(*) AS n FROM session_messages"
        ).fetchone()["n"] == 0
# A constraint violation surfaces as sqlite3.IntegrityError and rolls the transaction back.
def test_constraint_errors_match_sqlite(postgres):
    from db.repository import UserRepository
    with postgres.session() as connection:
        UserRepository(connection).upsert_from_google("g-1", "ada@example.com", "Ada")
        with pytest.raises(sqlite3.IntegrityError):
            with connection:
                connection.execute(
                    "INSERT INTO users (id, google_id, email, name, created_at, last_login_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    ("other", "g-2", "ada@example.com", "Dup", "now", "now"),
                )
        assert UserRepository(connection).count() == 1
# A sign-in stored in Postgres survives a new store object and is gone after logout.
def test_sign_in_survives_a_restart_in_postgres(postgres):
    from auth.session import DatabaseSessionStore
    from auth.user_context import UserContext
    from db.repository import UserRepository
    with postgres.session() as connection:
        user = UserContext.from_user(UserRepository(connection).upsert_from_google("g-1", "ada@example.com", "Ada"))
    session = DatabaseSessionStore().create(user)
    restored = DatabaseSessionStore().get(session.session_id)
    assert restored is not None and restored.user == user
    DatabaseSessionStore().revoke(session.session_id)
    assert DatabaseSessionStore().get(session.session_id) is None
# A paused graph checkpoint is stored in Postgres and read back by a fresh saver.
def test_checkpoints_persist_in_postgres(postgres):
    from graph.workflow import postgres_checkpointer
    from langgraph.checkpoint.base import empty_checkpoint
    saver = postgres_checkpointer()
    config = {"configurable": {"thread_id": "user::thread", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    saver.put(config, checkpoint, {"source": "input", "step": -1}, {})
    assert postgres_checkpointer().get_tuple(config).checkpoint["id"] == checkpoint["id"]
