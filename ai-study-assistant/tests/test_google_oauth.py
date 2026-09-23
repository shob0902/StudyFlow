# The OAuth flow: PKCE, CSRF state, callback errors and profile extraction. No network calls.
from urllib.parse import parse_qs, urlparse
import pytest
from auth.errors import AccessDeniedError, OAuthCallbackError
from auth.google_oauth import (
    PendingLoginStore,
    build_authorization_url,
    complete_login,
    profile_from_claims,
    raise_for_callback_error,
)
# The consent URL carries the client id, redirect, scopes, a state and an S256 PKCE challenge.
def test_authorization_url_has_state_and_pkce(oauth_config):
    store = PendingLoginStore()
    url = build_authorization_url(oauth_config, store)
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == [oauth_config.client_id]
    assert query["redirect_uri"] == [oauth_config.redirect_uri]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    assert store.pop(query["state"][0]) is not None
# Only the account scopes the app needs are requested.
def test_authorization_url_requests_minimal_scopes(oauth_config):
    url = build_authorization_url(oauth_config, PendingLoginStore())
    scopes = set(parse_qs(urlparse(url).query)["scope"][0].split(" "))
    assert scopes == {
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    }
# The client secret is never put in the URL the browser follows.
def test_authorization_url_never_carries_the_secret(oauth_config):
    url = build_authorization_url(oauth_config, PendingLoginStore())
    assert oauth_config.client_secret not in url
# A state can only be redeemed once, so a replayed callback fails.
def test_state_is_single_use(oauth_config):
    store = PendingLoginStore()
    url = build_authorization_url(oauth_config, store)
    state = parse_qs(urlparse(url).query)["state"][0]
    assert store.pop(state) is not None
    assert store.pop(state) is None
# A callback with an unknown state is rejected before any token exchange.
def test_unknown_state_is_rejected(oauth_config):
    with pytest.raises(OAuthCallbackError):
        complete_login(oauth_config, PendingLoginStore(), code="abc", state="forged-state")
# A callback missing its code or state is rejected.
def test_incomplete_callback_is_rejected(oauth_config):
    store = PendingLoginStore()
    with pytest.raises(OAuthCallbackError):
        complete_login(oauth_config, store, code="", state="")
# A user who clicks Cancel gets a friendly message, not an error page.
def test_user_denied_access():
    with pytest.raises(AccessDeniedError):
        raise_for_callback_error("access_denied")
# Any other Google error is reported without leaking details.
def test_other_oauth_errors_are_generic():
    with pytest.raises(OAuthCallbackError) as error:
        raise_for_callback_error("invalid_request")
    assert "invalid_request" not in str(error.value)
# Verified claims become the small profile the app stores, with the email normalised.
def test_profile_from_claims(google_claims):
    profile = profile_from_claims(google_claims)
    assert profile.google_id == "112233445566778899000"
    assert profile.email == "ada@example.com"
    assert profile.name == "Ada Lovelace"
    assert profile.picture == "https://example.com/ada.png"
    assert profile.email_verified is True
# Claims without a Google subject or email are refused.
def test_profile_requires_sub_and_email():
    with pytest.raises(OAuthCallbackError):
        profile_from_claims({"email": "ada@example.com"})
    with pytest.raises(OAuthCallbackError):
        profile_from_claims({"sub": "google-1"})
# A full callback exchanges the code with the PKCE verifier and verifies the ID token.
def test_complete_login_uses_the_pkce_verifier(oauth_config, google_claims, monkeypatch):
    store = PendingLoginStore()
    url = build_authorization_url(oauth_config, store)
    state = parse_qs(urlparse(url).query)["state"][0]
    seen = {}
    def fake_exchange(config, code, code_verifier):
        seen["code"] = code
        seen["verifier"] = code_verifier
        return {"id_token": "fake.id.token"}
    monkeypatch.setattr("auth.google_oauth.exchange_code", fake_exchange)
    monkeypatch.setattr("auth.google_oauth.verify_id_token", lambda config, token: google_claims)
    profile = complete_login(oauth_config, store, code="auth-code", state=state)
    assert seen["code"] == "auth-code"
    assert len(seen["verifier"]) > 40
    assert profile.email == "ada@example.com"
# A public client (no secret) exchanges the code with PKCE alone.
def test_public_client_exchange_sends_no_secret(oauth_config, google_claims, monkeypatch):
    from dataclasses import replace
    import auth.google_oauth as google_oauth
    public_config = replace(oauth_config, client_secret="")
    store = PendingLoginStore()
    state = parse_qs(urlparse(build_authorization_url(public_config, store)).query)["state"][0]
    sent = {}
    class FakeResponse:
        status_code = 200
        @staticmethod
        def json():
            return {"id_token": "fake.id.token"}
    def fake_post(url, data, timeout):
        sent.update(data)
        return FakeResponse()
    monkeypatch.setattr(google_oauth.requests, "post", fake_post)
    monkeypatch.setattr(google_oauth, "verify_id_token", lambda config, token: google_claims)
    profile = complete_login(public_config, store, code="auth-code", state=state)
    assert "client_secret" not in sent
    assert sent["client_id"] == public_config.client_id
    assert sent["code_verifier"]
    assert profile.email == "ada@example.com"
# A confidential client still sends its secret with the exchange.
def test_confidential_client_exchange_sends_the_secret(oauth_config, google_claims, monkeypatch):
    import auth.google_oauth as google_oauth
    store = PendingLoginStore()
    state = parse_qs(urlparse(build_authorization_url(oauth_config, store)).query)["state"][0]
    sent = {}
    class FakeResponse:
        status_code = 200
        @staticmethod
        def json():
            return {"id_token": "fake.id.token"}
    monkeypatch.setattr(
        google_oauth.requests, "post", lambda url, data, timeout: (sent.update(data), FakeResponse())[1]
    )
    monkeypatch.setattr(google_oauth, "verify_id_token", lambda config, token: google_claims)
    complete_login(oauth_config, store, code="auth-code", state=state)
    assert sent["client_secret"] == oauth_config.client_secret
# A public client that Google rejects is told the secret may be needed after all.
def test_public_client_rejection_explains_the_secret(oauth_config, monkeypatch):
    from dataclasses import replace
    import auth.google_oauth as google_oauth
    class FakeResponse:
        status_code = 401
    monkeypatch.setattr(google_oauth.requests, "post", lambda url, data, timeout: FakeResponse())
    with pytest.raises(OAuthCallbackError) as error:
        google_oauth.exchange_code(replace(oauth_config, client_secret=""), "code", "verifier")
    assert "GOOGLE_CLIENT_SECRET" in str(error.value)
# Expired login attempts are dropped from the pending store.
def test_pending_logins_expire(oauth_config):
    store = PendingLoginStore(ttl_seconds=0)
    url = build_authorization_url(oauth_config, store)
    state = parse_qs(urlparse(url).query)["state"][0]
    assert store.pop(state) is None
# A masked secret in .env is named as the cause when Google rejects the exchange.
def test_masked_secret_is_named_when_google_rejects(oauth_config, monkeypatch):
    from dataclasses import replace
    import auth.google_oauth as google_oauth
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "****0EAU")
    class FakeResponse:
        status_code = 401
        @staticmethod
        def json():
            return {"error": "invalid_client", "error_description": "Unauthorized"}
    monkeypatch.setattr(google_oauth.requests, "post", lambda url, data, timeout: FakeResponse())
    with pytest.raises(OAuthCallbackError) as error:
        google_oauth.exchange_code(replace(oauth_config, client_secret=""), "code", "verifier")
    assert "masked" in str(error.value)
    assert "Add secret" in str(error.value)
# Google's error code is logged for the developer but kept out of the user's message.
def test_google_error_is_logged_not_shown(oauth_config, monkeypatch, caplog):
    from dataclasses import replace
    import auth.google_oauth as google_oauth
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    class FakeResponse:
        status_code = 400
        @staticmethod
        def json():
            return {"error": "invalid_grant", "error_description": "Bad Request"}
    monkeypatch.setattr(google_oauth.requests, "post", lambda url, data, timeout: FakeResponse())
    with caplog.at_level("ERROR", logger="study_assistant"):
        with pytest.raises(OAuthCallbackError) as error:
            google_oauth.exchange_code(replace(oauth_config, client_secret=""), "code", "verifier")
    assert "invalid_grant" in caplog.text
    assert "invalid_grant" not in str(error.value)
# The ID token is verified with a clock tolerance, so a one-second skew does not block sign-in.
def test_id_token_verification_allows_clock_skew(oauth_config, google_claims, monkeypatch):
    import google.oauth2.id_token as google_id_token
    from auth.google_oauth import CLOCK_SKEW_SECONDS, verify_id_token
    seen = {}
    def fake_verify(token, request, audience, **kwargs):
        seen.update(kwargs)
        seen["audience"] = audience
        return google_claims
    monkeypatch.setattr(google_id_token, "verify_oauth2_token", fake_verify)
    claims = verify_id_token(oauth_config, "fake.id.token")
    assert claims["sub"] == google_claims["sub"]
    assert seen["audience"] == oauth_config.client_id
    assert seen["clock_skew_in_seconds"] == CLOCK_SKEW_SECONDS
    assert CLOCK_SKEW_SECONDS >= 30
# A token that genuinely fails verification is still rejected.
def test_invalid_id_token_is_still_rejected(oauth_config, monkeypatch):
    import google.oauth2.id_token as google_id_token
    from auth.google_oauth import verify_id_token
    def fake_verify(token, request, audience, **kwargs):
        raise ValueError("Wrong issuer")
    monkeypatch.setattr(google_id_token, "verify_oauth2_token", fake_verify)
    with pytest.raises(OAuthCallbackError):
        verify_id_token(oauth_config, "bad.id.token")
