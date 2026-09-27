# Shared fixtures: every test gets its own throwaway SQLite database.
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth.config import OAuthConfig
from db.database import connect, init_db
from db.repository import StudySessionRepository, UserRepository
# Never let a test touch the real database: db.database loads .env, which may hold the production
# DATABASE_URL. Tests use throwaway SQLite files; tests/test_postgres.py opts in explicitly with
# TEST_DATABASE_URL. Set to empty rather than removed, because load_dotenv() never overrides a
# variable that already exists, so a module imported mid-test cannot bring the real one back.
@pytest.fixture(autouse=True)
def _no_production_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
# Point the app at a fresh database file for the duration of one test.
@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "test_study.db"
    monkeypatch.setenv("STUDY_DB_PATH", str(path))
    monkeypatch.setenv("STUDY_CHECKPOINT_PATH", str(tmp_path / "test_checkpoints.db"))
    import db.database as database
    database._initialised.clear()
    yield str(path)
    database._initialised.clear()
# An open connection to the test database, with the schema created.
@pytest.fixture
def connection(db_file):
    connection = connect(db_file)
    init_db(connection)
    yield connection
    connection.close()
@pytest.fixture
def users(connection) -> UserRepository:
    return UserRepository(connection)
@pytest.fixture
def sessions_repo(connection) -> StudySessionRepository:
    return StudySessionRepository(connection)
# OAuth settings that look real enough for the flow, with no network calls behind them.
@pytest.fixture
def oauth_config() -> OAuthConfig:
    return OAuthConfig(
        client_id="test-client-id.apps.googleusercontent.com",
        client_secret="test-client-secret",
        redirect_uri="http://localhost:8501",
        session_ttl_minutes=60,
    )
# Verified Google claims for a fake signed-in account.
@pytest.fixture
def google_claims() -> dict:
    return {
        "iss": "https://accounts.google.com",
        "sub": "112233445566778899000",
        "email": "Ada@Example.com",
        "email_verified": True,
        "name": "Ada Lovelace",
        "picture": "https://example.com/ada.png",
    }
