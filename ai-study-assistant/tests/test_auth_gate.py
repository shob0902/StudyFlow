# Configuration errors and the state-clearing that protects one user from seeing another's session.
import ast
from pathlib import Path
import pytest
from auth.config import is_configured, load_config, missing_settings
from auth.errors import AuthConfigError
APP_FILE = Path(__file__).resolve().parents[1] / "app.py"
# Real credentials in the environment make the app configured.
@pytest.fixture
def configured_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "super-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
# A missing client id is reported by name instead of crashing the app.
def test_missing_configuration_is_named(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    assert missing_settings() == ["GOOGLE_CLIENT_ID"]
    assert is_configured() is False
    with pytest.raises(AuthConfigError) as error:
        load_config()
    assert "GOOGLE_CLIENT_ID" in str(error.value)
# A Google web client that uses PKCE has no secret, so the client id alone is enough.
def test_client_id_alone_is_enough(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert missing_settings() == []
    assert is_configured() is True
    config = load_config()
    assert config.client_secret == ""
    assert config.is_public_client is True
# The masked secret the Google console displays is ignored rather than sent to Google.
def test_masked_secret_is_ignored(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "****0Ez")
    config = load_config()
    assert config.client_secret == ""
    assert config.is_public_client is True
# A secret is still honoured when the OAuth client was issued one.
def test_secret_is_used_when_present(monkeypatch, configured_env):
    config = load_config()
    assert config.client_secret == "super-secret"
    assert config.is_public_client is False
# The placeholders in .env.example do not count as configuration.
def test_placeholders_count_as_missing(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "your_google_client_id_here")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "your_google_client_secret_here")
    assert is_configured() is False
# With credentials set, the config loads and falls back to the default redirect URI.
def test_configuration_loads(monkeypatch, configured_env):
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
    config = load_config()
    assert config.client_id == "abc.apps.googleusercontent.com"
    assert config.redirect_uri == "http://localhost:8501"
    assert config.session_ttl_minutes > 0
# The client secret never appears in a printed or logged config.
def test_config_repr_hides_the_secret(configured_env):
    assert "super-secret" not in repr(load_config())
# A nonsense session lifetime falls back to the default instead of breaking login.
def test_bad_session_ttl_falls_back(monkeypatch, configured_env):
    monkeypatch.setenv("AUTH_SESSION_TTL_MINUTES", "not-a-number")
    assert load_config().session_ttl_minutes == 720
    monkeypatch.setenv("AUTH_SESSION_TTL_MINUTES", "-5")
    assert load_config().session_ttl_minutes == 720
# Logging out must clear every study key the app keeps, so nothing leaks into the next login.
def test_logout_clears_every_app_session_key():
    from auth.streamlit_auth import USER_SCOPED_KEYS
    tree = ast.parse(APP_FILE.read_text(encoding="utf-8"))
    defaults = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "init_session_state"
    )
    keys = {
        element.value
        for node in ast.walk(defaults)
        if isinstance(node, ast.Dict)
        for element in node.keys
        if isinstance(element, ast.Constant)
    }
    assert keys, "init_session_state should declare the app's session keys"
    assert keys <= set(USER_SCOPED_KEYS)
# Clearing the session drops the session id, the user and their study state.
def test_clear_session_state_removes_user_data(monkeypatch):
    import auth.streamlit_auth as streamlit_auth
    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {
                "auth_session_id": "abc",
                "user_context": object(),
                "thread_id": "user-1::123",
                "study_state": {"topic": "Recursion"},
                "keep_me": 1,
            }
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_auth, "st", fake)
    streamlit_auth._clear_session_state()
    assert fake.session_state == {"keep_me": 1}
# The gate exposes exactly one way in and one way out.
def test_gate_exports():
    import auth.streamlit_auth as streamlit_auth
    assert callable(streamlit_auth.require_login)
    assert callable(streamlit_auth.sign_out)
    assert callable(streamlit_auth.current_user)
# A redirect URI on the app root is used as given.
def test_root_redirect_uri_is_kept(monkeypatch, configured_env):
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
    assert load_config().redirect_uri == "http://localhost:8501"
# A sub-path redirect URI still loads, but the terminal explains why sign-in will not complete.
def test_subpath_redirect_uri_is_flagged(monkeypatch, configured_env, caplog):
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8501/oauth2callback")
    with caplog.at_level("INFO", logger="study_assistant"):
        config = load_config()
    assert config.redirect_uri == "http://localhost:8501/oauth2callback"
    assert "oauth2callback" in caplog.text
    assert "drops the query string" in caplog.text
