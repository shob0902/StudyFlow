# Connection handling, the schema every user-scoped table hangs off, and its migrations.
#
# Two backends sit behind the same sqlite3-style API:
#   DATABASE_URL set   -> hosted Postgres (e.g. Neon). Survives restarts and redeploys, which is
#                         what a host with a throwaway disk (Render, Railway, HF Spaces) needs.
#   DATABASE_URL unset -> a local SQLite file, for development and tests.
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from dotenv import load_dotenv
from auth.errors import DatabaseError
from utils.helpers import log_error, log_step
load_dotenv()
DB_PATH_VAR = "STUDY_DB_PATH"
DEFAULT_DB_PATH = "study_assistant.db"
CHECKPOINT_PATH_VAR = "STUDY_CHECKPOINT_PATH"
DEFAULT_CHECKPOINT_PATH = "study_checkpoints.db"
DATABASE_URL_VAR = "DATABASE_URL"
POOL_SIZE_VAR = "DB_POOL_SIZE"
POSTGRES_TARGET = "postgres"
SCHEMA_VERSION = 4
# Schema notes:
#   users.id is the internal identifier every other table references. google_id is the stable
#   external identity; email is unique but is never the identity key.
#   A study session is this app's conversation: one topic, its explanations, quizzes and transcript.
#   concepts is a shared vocabulary; user_concept_mastery is one row per user per concept and is
#   the single home of both mastery and review scheduling, so the two can never disagree.
#   auth_sessions holds sign-ins by a hash of the cookie's session id, never the id itself.
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
CREATE TABLE IF NOT EXISTS auth_sessions (
    id_hash    TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);
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
_pool_lock = threading.Lock()
_initialised: set[str] = set()
_pools: dict[str, Any] = {}
# Where the SQLite file lives; STUDY_DB_PATH overrides it (use ':memory:' in tests).
def db_path() -> str:
    return os.getenv(DB_PATH_VAR, "").strip() or DEFAULT_DB_PATH
# Where LangGraph keeps its checkpoints, so a paused quiz survives a restart.
def checkpoint_path() -> str:
    return os.getenv(CHECKPOINT_PATH_VAR, "").strip() or DEFAULT_CHECKPOINT_PATH
# The hosted Postgres connection string, or '' when the app runs on local SQLite.
def database_url() -> str:
    url = os.getenv(DATABASE_URL_VAR, "").strip()
    return url if url.startswith(("postgres://", "postgresql://")) else ""
# True when data lives in hosted Postgres rather than a local file.
def using_postgres() -> bool:
    return bool(database_url())
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
# One shared pool of Postgres connections per purpose, opened on first use.
# A hosted database is a network hop away, so reusing connections matters: opening a fresh TLS
# connection for every query would make each Streamlit rerun noticeably slow. `check` replaces
# connections the server dropped while idle (Neon suspends an idle database after a few minutes).
# Prepared statements are off so a pooled (PgBouncer) connection string works too.
def postgres_pool(purpose: str = "app") -> Any:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    with _pool_lock:
        pool = _pools.get(purpose)
        if pool is None:
            pool = ConnectionPool(
                database_url(),
                min_size=1,
                max_size=max(int(os.getenv(POOL_SIZE_VAR, "") or 5), 1),
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
                check=ConnectionPool.check_connection,
                name=f"study-{purpose}",
                open=True,
            )
            _pools[purpose] = pool
            log_step("DB", f"Opened the Postgres connection pool for {purpose!r}")
        return pool
# The schema in Postgres terms. SQLite's REAL is 8 bytes but Postgres's is only 4, so scores and
# timestamps use DOUBLE PRECISION to keep the same precision.
def _postgres_schema() -> str:
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", SCHEMA)
# Rewrite a sqlite3-style statement for psycopg: '?' placeholders become '%s', and a literal '%'
# has to be doubled once placeholders are in play. No statement here has a '?' inside a string.
def _to_postgres(sql: str) -> str:
    return sql.replace("%", "%%").replace("?", "%s")
# A pooled Postgres connection that behaves like the sqlite3 connection the repositories expect:
# execute/executemany with '?' placeholders, rows readable by column name, `with connection:`
# as one transaction and close() to give it back. psycopg errors are re-raised as their sqlite3
# counterparts, so the existing `except sqlite3.IntegrityError / sqlite3.Error` handling, and
# its friendly messages, applies to both backends unchanged.
class PostgresConnection:
    def __init__(self, pool: Any) -> None:
        self._pool = pool
        self._connection = pool.getconn()
        self._transactions: list[Any] = []
    # Run one statement. Outside a `with` block it commits on its own (autocommit).
    def execute(self, sql: str, parameters: tuple | list = ()) -> Any:
        return self._run(lambda: self._connection.execute(_to_postgres(sql), tuple(parameters)))
    # Run one statement once per parameter set.
    def executemany(self, sql: str, rows: list) -> Any:
        def run() -> Any:
            cursor = self._connection.cursor()
            cursor.executemany(_to_postgres(sql), [tuple(row) for row in rows])
            return cursor
        return self._run(run)
    # Run a script of several statements with no parameters, such as the schema.
    def executescript(self, script: str) -> Any:
        return self._run(lambda: self._connection.execute(script))
    # Translate driver errors into the sqlite3 exceptions the callers already handle.
    @staticmethod
    def _run(action: Any) -> Any:
        import psycopg
        try:
            return action()
        except psycopg.IntegrityError as error:
            raise sqlite3.IntegrityError(str(error)) from error
        except psycopg.Error as error:
            raise sqlite3.Error(str(error)) from error
    # `with connection:` is one transaction: committed on success, rolled back on an error.
    def __enter__(self) -> "PostgresConnection":
        transaction = self._connection.transaction()
        transaction.__enter__()
        self._transactions.append(transaction)
        return self
    def __exit__(self, *exc_info: Any) -> bool:
        return bool(self._transactions.pop().__exit__(*exc_info))
    # Hand the connection back to the pool.
    def close(self) -> None:
        if self._connection is not None:
            self._pool.putconn(self._connection)
            self._connection = None
# Borrow a Postgres connection, creating the schema the first time this process connects.
def _postgres_connection() -> PostgresConnection:
    try:
        connection = PostgresConnection(postgres_pool())
    except Exception:
        log_error("Could not connect to the Postgres database")
        raise DatabaseError("The app could not reach its database. Please check the DATABASE_URL setting.")
    with _init_lock:
        if POSTGRES_TARGET not in _initialised:
            try:
                with connection:
                    connection.executescript(_postgres_schema())
            except sqlite3.Error:
                connection.close()
                log_error("Could not create the Postgres schema")
                raise DatabaseError("The app could not prepare its database. Please try again.")
            _initialised.add(POSTGRES_TARGET)
            log_step("DB", "Postgres database ready")
    return connection
# Column names already present on a table.
def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
# Bring a database created by an older version up to the current schema.
# CREATE TABLE IF NOT EXISTS cannot add columns, so column changes are applied here; the v3/v4
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
    if using_postgres():
        return _postgres_connection()  # type: ignore[return-value]
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
