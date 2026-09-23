# Fetches the Google profile picture server-side and inlines it as a data URI.
# The browser never requests it from Google, which refuses hotlinks once the HTML sanitizer
# drops the referrer policy, and the picture also survives an offline or blocked-tracker browser.
import base64
from urllib.parse import urlparse
import requests
from utils.helpers import log_step
HTTP_TIMEOUT = 10
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_HOST_SUFFIXES = (".googleusercontent.com", ".google.com")
ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
# Only fetch https URLs on Google's own image hosts: the URL comes from a verified ID token,
# and this keeps a surprising claim from turning into a request to anywhere else.
def is_allowed(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in ALLOWED_HOST_SUFFIXES)
# Download the picture and return it as a data URI, or "" when it cannot be used.
def fetch_avatar(url: str) -> str:
    if not is_allowed(url):
        return ""
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT)
    except requests.RequestException:
        log_step("AUTH", "Could not download the profile picture; using initials instead")
        return ""
    if response.status_code != 200:
        log_step("AUTH", f"Profile picture returned HTTP {response.status_code}; using initials instead")
        return ""
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_TYPES:
        log_step("AUTH", f"Profile picture had an unexpected type {content_type!r}; using initials instead")
        return ""
    content = response.content
    if not content or len(content) > MAX_BYTES:
        log_step("AUTH", "Profile picture was empty or too large; using initials instead")
        return ""
    encoded = base64.b64encode(content).decode("ascii")
    log_step("AUTH", f"Inlined the profile picture ({len(content)} bytes)")
    return f"data:{content_type};base64,{encoded}"
