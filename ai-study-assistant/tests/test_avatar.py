# The profile picture is fetched server-side, inlined, and falls back to initials when it cannot be.
import base64
import pytest
from auth.avatar import MAX_BYTES, fetch_avatar, is_allowed
from auth.user_context import UserContext
from ui.auth_ui import user_badge
GOOGLE_URL = "https://lh3.googleusercontent.com/a/ACg8ocK...=s96-c"
# A fake requests.get returning one canned response.
def _fake_get(monkeypatch, status=200, content=b"\xff\xd8\xff-jpeg-bytes", content_type="image/jpeg"):
    import auth.avatar as avatar
    class FakeResponse:
        status_code = status
        headers = {"Content-Type": content_type}
    FakeResponse.content = content
    monkeypatch.setattr(avatar.requests, "get", lambda url, timeout: FakeResponse())
# Google's own image hosts over https are fetched.
def test_google_hosts_are_allowed():
    assert is_allowed(GOOGLE_URL) is True
    assert is_allowed("https://lh3.google.com/photo.jpg") is True
# Anything else is not, so a surprising claim cannot make the server call an arbitrary address.
def test_other_hosts_are_refused():
    assert is_allowed("https://evil.example.com/pic.jpg") is False
    assert is_allowed("http://lh3.googleusercontent.com/a/x") is False
    assert is_allowed("https://notgoogleusercontent.com/x") is False
    assert is_allowed("file:///etc/passwd") is False
    assert is_allowed("") is False
# A URL that is not allowed is never fetched at all.
def test_disallowed_url_is_not_fetched(monkeypatch):
    import auth.avatar as avatar
    def explode(*args, **kwargs):
        raise AssertionError("should not reach the network")
    monkeypatch.setattr(avatar.requests, "get", explode)
    assert fetch_avatar("https://evil.example.com/pic.jpg") == ""
# A good picture comes back as a data URI the page can render without calling Google.
def test_picture_is_inlined(monkeypatch):
    _fake_get(monkeypatch)
    result = fetch_avatar(GOOGLE_URL)
    assert result.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(result.split(",", 1)[1]) == b"\xff\xd8\xff-jpeg-bytes"
# Failures degrade quietly to no picture rather than breaking the sidebar.
def test_failures_return_empty(monkeypatch):
    _fake_get(monkeypatch, status=403)
    assert fetch_avatar(GOOGLE_URL) == ""
    _fake_get(monkeypatch, content_type="text/html")
    assert fetch_avatar(GOOGLE_URL) == ""
    _fake_get(monkeypatch, content=b"")
    assert fetch_avatar(GOOGLE_URL) == ""
    _fake_get(monkeypatch, content=b"x" * (MAX_BYTES + 1))
    assert fetch_avatar(GOOGLE_URL) == ""
# A network error is caught, not raised into the page.
def test_network_error_returns_empty(monkeypatch):
    import auth.avatar as avatar
    import requests
    def boom(url, timeout):
        raise requests.ConnectionError("no network")
    monkeypatch.setattr(avatar.requests, "get", boom)
    assert fetch_avatar(GOOGLE_URL) == ""
# The badge renders the inlined picture, and never a URL the browser would have to fetch.
def test_badge_uses_the_inlined_picture():
    user = UserContext(
        user_id="u1", google_id="g1", email="ada@example.com", name="Ada Lovelace",
        profile_picture=GOOGLE_URL,
    )
    html = user_badge(user, "data:image/jpeg;base64,AAAA")
    assert "src='data:image/jpeg;base64,AAAA'" in html
    assert "googleusercontent.com" not in html
    assert "Welcome, Ada" in html
# With no usable picture the badge shows the user's initial instead of a broken image.
def test_badge_falls_back_to_initials():
    user = UserContext(
        user_id="u1", google_id="g1", email="ada@example.com", name="Ada Lovelace",
        profile_picture=GOOGLE_URL,
    )
    html = user_badge(user, "")
    assert "<img" not in html
    assert "<div class='avatar'>A</div>" in html
