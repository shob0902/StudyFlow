# Google OAuth settings read from environment variables (never hard-coded).
import os
from dataclasses import dataclass
from urllib.parse import urlparse
from dotenv import load_dotenv
from auth.errors import AuthConfigError
from utils.helpers import log_step
load_dotenv()
CLIENT_ID_VAR = "GOOGLE_CLIENT_ID"
CLIENT_SECRET_VAR = "GOOGLE_CLIENT_SECRET"
REDIRECT_URI_VAR = "GOOGLE_REDIRECT_URI"
SESSION_TTL_VAR = "AUTH_SESSION_TTL_MINUTES"
DEFAULT_REDIRECT_URI = "http://localhost:8501"
DEFAULT_SESSION_TTL_MINUTES = 720
_PLACEHOLDERS = {"your_google_client_id_here", "your_google_client_secret_here", ""}
# Only what the app needs: the user's Google account identity, nothing else.
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    # Optional: newer Google web clients authenticate with PKCE alone. Only sent when set.
    client_secret: str = ""
    redirect_uri: str = DEFAULT_REDIRECT_URI
    session_ttl_minutes: int = DEFAULT_SESSION_TTL_MINUTES
    # True when this is a public client: PKCE only, no secret configured.
    @property
    def is_public_client(self) -> bool:
        return not self.client_secret
    # Never let the secret reach a log line or the UI.
    def __repr__(self) -> str:
        kind = "public" if self.is_public_client else "confidential"
        return f"OAuthConfig(client_id={self.client_id[:8]}..., {kind}, redirect_uri={self.redirect_uri!r})"
# Read an environment variable, treating blanks and .env.example placeholders as missing.
def _read(name: str) -> str:
    value = os.getenv(name, "").strip()
    return "" if value.lower() in _PLACEHOLDERS else value
# Read the client secret, ignoring the masked value the Google console shows (e.g. "****0Ez").
# A masked string is not a usable secret, and PKCE already secures the exchange without one.
def _read_secret() -> str:
    value = _read(CLIENT_SECRET_VAR)
    if value and "*" in value:
        log_step("AUTH", f"{CLIENT_SECRET_VAR} looks masked; signing in with PKCE only")
        return ""
    return value
# True when GOOGLE_CLIENT_SECRET holds the console's masked display value instead of a real secret.
def has_masked_secret() -> bool:
    value = _read(CLIENT_SECRET_VAR)
    return bool(value) and "*" in value
# List the OAuth variables that still need a real value. Only the client id is required:
# a Google web client that uses PKCE has no secret to configure.
def missing_settings() -> list[str]:
    return [] if _read(CLIENT_ID_VAR) else [CLIENT_ID_VAR]
# True when Google OAuth is fully configured.
def is_configured() -> bool:
    return not missing_settings()
# Read the session lifetime, falling back to the default on a bad value.
def _session_ttl() -> int:
    try:
        minutes = int(os.getenv(SESSION_TTL_VAR, "").strip() or DEFAULT_SESSION_TTL_MINUTES)
    except ValueError:
        return DEFAULT_SESSION_TTL_MINUTES
    return minutes if minutes > 0 else DEFAULT_SESSION_TTL_MINUTES
# Warn when the redirect URI has a sub-path: Streamlit redirects those to the app root and drops
# the ?code=/?state= query string, so the callback would never arrive. Only a custom
# server.baseUrlPath makes a path correct, so this is a warning and not a hard failure.
def _check_redirect_path(redirect_uri: str) -> None:
    path = urlparse(redirect_uri).path.strip("/")
    if path:
        log_step(
            "AUTH",
            f"{REDIRECT_URI_VAR} points at '/{path}'. Streamlit serves the app at '/' and drops the "
            "query string on other paths, so sign-in will not complete unless you run it with "
            "--server.baseUrlPath.",
        )
# Build the OAuth config, or explain exactly which variables are missing.
def load_config() -> OAuthConfig:
    missing = missing_settings()
    if missing:
        raise AuthConfigError(
            f"Google sign-in is not configured: {', '.join(missing)} is missing. "
            "Copy .env.example to .env and add your Google OAuth credentials."
        )
    redirect_uri = _read(REDIRECT_URI_VAR) or DEFAULT_REDIRECT_URI
    _check_redirect_path(redirect_uri)
    return OAuthConfig(
        client_id=_read(CLIENT_ID_VAR),
        client_secret=_read_secret(),
        redirect_uri=redirect_uri,
        session_ttl_minutes=_session_ttl(),
    )
