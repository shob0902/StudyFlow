# Google OAuth 2.0 authorization-code flow with PKCE and CSRF state, plus ID token verification.
import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
import requests
from auth.config import (
    AUTH_ENDPOINT,
    SCOPES,
    TOKEN_ENDPOINT,
    USERINFO_ENDPOINT,
    OAuthConfig,
    has_masked_secret,
)
from auth.errors import AccessDeniedError, OAuthCallbackError
from utils.helpers import log_error, log_step
HTTP_TIMEOUT = 15
PENDING_TTL_SECONDS = 600
# Tolerance for the ID token's iat/exp. google-auth defaults to 0, so a machine clock a second
# behind Google's rejects a perfectly good token ("Token used too early").
CLOCK_SKEW_SECONDS = 60
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
# The Google account fields the app stores. Nothing else is kept.
@dataclass(frozen=True)
class GoogleProfile:
    google_id: str
    email: str
    name: str
    picture: str = ""
    email_verified: bool = False
# One login attempt waiting for Google to call back.
@dataclass(frozen=True)
class PendingLogin:
    state: str
    code_verifier: str
    created_at: float
# Server-side store of in-flight logins, keyed by the CSRF state. The browser only ever sees the state.
class PendingLoginStore:
    def __init__(self, ttl_seconds: int = PENDING_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._pending: dict[str, PendingLogin] = {}
    # Remember a login attempt so the callback can find its PKCE verifier.
    def add(self, pending: PendingLogin) -> None:
        with self._lock:
            self._prune()
            self._pending[pending.state] = pending
    # Take a login attempt out of the store; a state can only be used once.
    def pop(self, state: str) -> PendingLogin | None:
        with self._lock:
            self._prune()
            return self._pending.pop(state, None)
    # Drop attempts that were never completed.
    def _prune(self) -> None:
        cutoff = time.time() - self._ttl
        for state in [s for s, pending in self._pending.items() if pending.created_at <= cutoff]:
            del self._pending[state]
    def __len__(self) -> int:
        with self._lock:
            return len(self._pending)
# Create the PKCE code_verifier / code_challenge pair (S256).
def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge
# Start a login: return the Google consent URL and register the pending attempt.
def build_authorization_url(config: OAuthConfig, store: PendingLoginStore) -> str:
    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()
    store.add(PendingLogin(state=state, code_verifier=verifier, created_at=time.time()))
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    log_step("AUTH", "Built Google authorization URL")
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"
# Swap the one-time code for tokens, server to server. Tokens never reach the browser.
# The PKCE verifier proves this is the client that started the login; a client secret is
# added only when the Google client is a confidential one that has one.
def exchange_code(config: OAuthConfig, code: str, code_verifier: str) -> dict[str, Any]:
    payload = {
        "code": code,
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if config.client_secret:
        payload["client_secret"] = config.client_secret
    try:
        response = requests.post(TOKEN_ENDPOINT, data=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException:
        log_error("Token exchange request to Google failed")
        raise OAuthCallbackError("Could not reach Google to finish signing you in. Please try again.")
    if response.status_code != 200:
        log_error(
            f"Token exchange rejected by Google (HTTP {response.status_code}) {_error_details(response)}"
        )
        if response.status_code in {400, 401} and config.is_public_client:
            if has_masked_secret():
                raise OAuthCallbackError(
                    "Google needs this app's client secret, and GOOGLE_CLIENT_SECRET in .env holds the "
                    "masked value the console shows (****...), not a real secret. In the Google Cloud "
                    "Console open this OAuth client, click 'Add secret', copy the full GOCSPX-... value "
                    "into .env, then restart the app."
                )
            raise OAuthCallbackError(
                "Google rejected the sign-in. This OAuth client needs a client secret: copy it from "
                "the Google Cloud Console into GOOGLE_CLIENT_SECRET in .env and restart the app."
            )
        raise OAuthCallbackError("Google rejected the sign-in attempt. Please try again.")
    return response.json()
# Google's own error code and description, for the terminal log. Never contains a secret.
def _error_details(response: Any) -> str:
    try:
        body = response.json()
    except Exception:
        return ""
    if not isinstance(body, dict):
        return ""
    return f"{body.get('error', '')} {body.get('error_description', '')}".strip()
# Verify the ID token's signature, issuer, audience and expiry against Google's public keys.
def verify_id_token(config: OAuthConfig, raw_id_token: str) -> dict[str, Any]:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            config.client_id,
            clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
        )
    except ValueError:
        log_error("Google ID token failed verification")
        raise OAuthCallbackError("Your Google sign-in could not be verified. Please try again.")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        log_error("Google ID token had an unexpected issuer")
        raise OAuthCallbackError("Your Google sign-in could not be verified. Please try again.")
    return claims
# Fall back to the userinfo endpoint when Google returns no ID token.
def fetch_userinfo(access_token: str) -> dict[str, Any]:
    try:
        response = requests.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException:
        log_error("Userinfo request to Google failed")
        raise OAuthCallbackError("Could not read your Google profile. Please try again.")
    if response.status_code != 200:
        log_error(f"Userinfo request rejected by Google (HTTP {response.status_code})")
        raise OAuthCallbackError("Could not read your Google profile. Please try again.")
    return response.json()
# Turn verified Google claims into the small profile the app stores.
def profile_from_claims(claims: dict[str, Any]) -> GoogleProfile:
    google_id = str(claims.get("sub", "")).strip()
    email = str(claims.get("email", "")).strip().lower()
    if not google_id or not email:
        raise OAuthCallbackError("Google did not return a usable account. Please try again.")
    return GoogleProfile(
        google_id=google_id,
        email=email,
        name=str(claims.get("name") or email.split("@")[0]).strip(),
        picture=str(claims.get("picture") or "").strip(),
        email_verified=bool(claims.get("email_verified", False)),
    )
# Turn the ?error= value Google puts on the redirect into a friendly error.
def raise_for_callback_error(error_code: str) -> None:
    if error_code in {"access_denied", "consent_required"}:
        raise AccessDeniedError("You cancelled the Google sign-in. Use Continue with Google to try again.")
    log_error(f"Google returned OAuth error {error_code!r}")
    raise OAuthCallbackError("Google could not complete the sign-in. Please try again.")
# Finish a callback: check the CSRF state, exchange the code and return the verified profile.
def complete_login(config: OAuthConfig, store: PendingLoginStore, code: str, state: str) -> GoogleProfile:
    if not code or not state:
        raise OAuthCallbackError("That sign-in link was incomplete. Please start again.")
    pending = store.pop(state)
    if pending is None:
        log_error("OAuth callback carried an unknown or expired state")
        raise OAuthCallbackError("That sign-in request expired or was already used. Please start again.")
    tokens = exchange_code(config, code, pending.code_verifier)
    raw_id_token = tokens.get("id_token")
    if raw_id_token:
        claims = verify_id_token(config, raw_id_token)
    else:
        access_token = tokens.get("access_token", "")
        if not access_token:
            raise OAuthCallbackError("Google did not return a usable sign-in. Please try again.")
        claims = fetch_userinfo(access_token)
    profile = profile_from_claims(claims)
    log_step("AUTH", f"Verified Google account for {profile.email}")
    return profile
