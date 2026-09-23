# SQLite connection handling, the schema every user-scoped table hangs off, and its migrations.
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from dotenv import load_dotenv
from auth.errors import DatabaseError
from utils.helpers import log_error, log_step
load_dotenv()
DB_PATH_VAR = "STUDY_DB_PATH"
DEFAULT_DB_PATH = "study_assistant.db"
CHECKPOINT_PATH_VAR = "STUDY_CHECKPOINT_PATH"
DEFAULT_CHECKPOINT_PATH = "study_checkpoints.db"
SCHEMA_VERSION = 3
# Schema notes:
#   users.id is the internal identifier every other table references. google_id is the stable
#   external identity; email is unique but is never the identity key.
#   A study session is this app's conversation: one topic, its explanations, quizzes and transcript.
#   concepts is a shared vocabulary; user_concept_mastery is one row per user per concept and is
#   the single home of both mastery and review scheduling, so the two can never disagree.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    google_id       TEXT NOT NULL UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    profile_picture TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    last_login_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id       TEXT NOT NULL UNIQUE,
    topic           TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    title_is_custom INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',
    score           REAL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_messages (
    id               TEXT PRIMARY KEY,
    study_session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,
    role             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    content          TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    UNIQUE(study_session_id, position)
);
CREATE TABLE IF NOT EXISTS concepts (
    slug       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    subject    TEXT NOT NULL DEFAULT 'General',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_concept_mastery (
    user_id               TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_slug          TEXT NOT NULL REFERENCES concepts(slug) ON DELETE CASCADE,
    mastery_score         REAL NOT NULL DEFAULT 0,
    confidence            REAL NOT NULL DEFAULT 0,
    attempts              INTEGER NOT NULL DEFAULT 0,
    correct_attempts      INTEGER NOT NULL DEFAULT 0,
    incorrect_attempts    INTEGER NOT NULL DEFAULT 0,
    consecutive_correct   INTEGER NOT NULL DEFAULT 0,
    consecutive_incorrect INTEGER NOT NULL DEFAULT 0,
    current_difficulty    TEXT NOT NULL DEFAULT 'medium',
    learning_status       TEXT NOT NULL DEFAULT 'unknown',
    last_attempted_at     TEXT NOT NULL DEFAULT '',
    last_correct_at       TEXT NOT NULL DEFAULT '',
    interval_days         INTEGER NOT NULL DEFAULT 0,
    ease                  REAL NOT NULL DEFAULT 2.2,
    review_count          INTEGER NOT NULL DEFAULT 0,
    lapses                INTEGER NOT NULL DEFAULT 0,
    last_reviewed_at      TEXT NOT NULL DEFAULT '',
    next_review_at        TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    PRIMARY KEY (user_id, concept_slug)
);
CREATE TABLE IF NOT EXISTS concept_mistakes (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_slug TEXT NOT NULL,
    category     TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT 'quiz',
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    checksum     TEXT NOT NULL DEFAULT '',
    pages        INTEGER NOT NULL DEFAULT 0,
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'ready',
    error        TEXT NOT NULL DEFAULT '',
    concepts     TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL,
    UNIQUE(user_id, checksum)
);
CREATE TABLE IF NOT EXISTS document_chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    page        INTEGER,
    section     TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    word_count  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(document_id, position)
);
CREATE TABLE IF NOT EXISTS coding_problems (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    statement   TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT 'python',
    difficulty  TEXT NOT NULL DEFAULT 'medium',
    signature   TEXT NOT NULL DEFAULT '',
    constraints TEXT NOT NULL DEFAULT '',
    examples    TEXT NOT NULL DEFAULT '[]',
    tests       TEXT NOT NULL DEFAULT '[]',
    concepts    TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coding_submissions (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id   TEXT NOT NULL REFERENCES coding_problems(id) ON DELETE CASCADE,
    language     TEXT NOT NULL DEFAULT 'python',
    code         TEXT NOT NULL,
    passed       INTEGER NOT NULL DEFAULT 0,
    total        INTEGER NOT NULL DEFAULT 0,
    runtime_ms   REAL NOT NULL DEFAULT 0,
    memory_kb    INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'wrong_answer',
    failure_kind TEXT NOT NULL DEFAULT '',
    detail       TEXT NOT NULL DEFAULT '',
    hints_used   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_plans (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject     TEXT NOT NULL,
    target_date TEXT NOT NULL DEFAULT '',
    weeks       INTEGER NOT NULL DEFAULT 4,
    goal        TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_plan_items (
    id            TEXT PRIMARY KEY,
    plan_id       TEXT NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_slug  TEXT NOT NULL,
    concept_name  TEXT NOT NULL,
    subject       TEXT NOT NULL DEFAULT '',
    week          INTEGER NOT NULL DEFAULT 1,
    minutes       INTEGER NOT NULL DEFAULT 30,
    activity      TEXT NOT NULL DEFAULT 'learn',
    status        TEXT NOT NULL DEFAULT 'pending',
    mastery_score REAL NOT NULL DEFAULT 0,
    position      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS learning_events (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    concept_slug TEXT NOT NULL DEFAULT '',
    activity     TEXT NOT NULL DEFAULT '',
    correct      INTEGER,
    score        REAL,
    detail       TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_study_sessions_user ON study_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_study_sessions_thread ON study_sessions(user_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_study_sessions_recent ON study_sessions(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_messages_session ON session_messages(study_session_id, position);
CREATE INDEX IF NOT EXISTS idx_mastery_user ON user_concept_mastery(user_id, mastery_score);
CREATE INDEX IF NOT EXISTS idx_mastery_due ON user_concept_mastery(user_id, next_review_at);
CREATE INDEX IF NOT EXISTS idx_mistakes_user ON concept_mistakes(user_id, concept_slug, created_at);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON document_chunks(user_id, document_id, position);
CREATE INDEX IF NOT EXISTS idx_problems_user ON coding_problems(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_user ON coding_submissions(user_id, problem_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plans_user ON study_plans(user_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_plan_items ON study_plan_items(plan_id, week, position);
CREATE INDEX IF NOT EXISTS idx_events_user ON learning_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_concept ON learning_events(user_id, concept_slug, created_at DESC);
"""
_init_lock = threading.Lock()
_initialised: set[str] = set()
# Where the SQLite file lives; STUDY_DB_PATH overrides it (use ':memory:' in tests).
def db_path() -> str:
    return os.getenv(DB_PATH_VAR, "").strip() or DEFAULT_DB_PATH
# Where LangGraph keeps its checkpoints, so a paused quiz survives a restart.
def checkpoint_path() -> str:
    return os.getenv(CHECKPOINT_PATH_VAR, "").strip() or DEFAULT_CHECKPOINT_PATH
# Open a connection with foreign keys on and rows accessible by column name.
def connect(path: str | None = None) -> sqlite3.Connection:
    target = path or db_path()
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(target, check_same_thread=False)
    except sqlite3.Error:
        log_error(f"Could not open the database at {target!r}")
        raise DatabaseError("The app could not open its database. Please check the STUDY_DB_PATH setting.")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
# Column names already present on a table.
def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
# Bring a database created by an older version up to the current schema.
# CREATE TABLE IF NOT EXISTS cannot add columns, so column changes are applied here; the v3
# tables are new, so the schema script above creates them and this only stamps the version.
def migrate(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    columns = _columns(connection, "study_sessions")
    added = []
    if "title" not in columns:
        connection.execute("ALTER TABLE study_sessions ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        added.append("title")
    if "title_is_custom" not in columns:
        connection.execute(
            "ALTER TABLE study_sessions ADD COLUMN title_is_custom INTEGER NOT NULL DEFAULT 0"
        )
        added.append("title_is_custom")
    if added:
        # Existing rows get their topic as the starting title.
        connection.execute("UPDATE study_sessions SET title = topic WHERE title = ''")
        log_step("DB", f"Migrated study_sessions: added {', '.join(added)}")
    if version != SCHEMA_VERSION:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        log_step("DB", f"Schema version {version} -> {SCHEMA_VERSION}")
# Create the tables if they are not there yet, then apply any pending migration.
def init_db(connection: sqlite3.Connection) -> None:
    try:
        with connection:
            connection.executescript(SCHEMA)
            migrate(connection)
    except sqlite3.Error:
        log_error("Could not create or migrate the database schema")
        raise DatabaseError("The app could not prepare its database. Please try again.")
# Open a connection to the configured database, creating the schema on first use.
def get_connection() -> sqlite3.Connection:
    target = db_path()
    connection = connect(target)
    with _init_lock:
        if target not in _initialised or target == ":memory:":
            init_db(connection)
            _initialised.add(target)
            log_step("DB", f"Database ready at {target!r}")
    return connection
# Run a block against a fresh connection and always close it afterwards.
@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
