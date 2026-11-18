"""Browser OAuth 2.1 (PKCE) login for `databar login`.

Opens the existing Databar consent screen, catches the authorization code on a
local loopback redirect, exchanges it for a short-lived bearer token, then
fetches the workspace API key and writes it to ~/.databar/config.

The consent screen keeps its own tab ("Databar CLI has been Authorized!") and
opens the loopback redirect in a second tab. That second tab is only plumbing:
it is answered once the login has really finished, and on success it closes
itself so the person lands back on the consent screen's tab.
"""

from __future__ import annotations

import base64
import hashlib
import html
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

# Must match oauth.0002_seed_cli_oauth_application / settings.DATABAR_CLI_*.
# The registered redirect is http://127.0.0.1:53682/callback; the server accepts
# any port on a loopback IP redirect (RFC 8252 §7.3), so the CLI listens on a
# free port the OS picks instead of a fixed one another program may hold.
OAUTH_CLIENT_ID = "databar-cli"
OAUTH_CALLBACK_HOST = "127.0.0.1"
OAUTH_CALLBACK_PATH = "/callback"
OAUTH_SCOPE = "cli:access"
DEFAULT_OAUTH_ISSUER = "https://databar.ai"
_LOGIN_TIMEOUT_S = 300
# How long the browser tab waits for the token exchange before it is answered anyway.
_FINISH_TIMEOUT_S = 60

_ERROR_MESSAGES = {
    "access_denied": "You denied access on the Databar consent screen.",
    "plan_not_eligible": "Your plan doesn’t include API and CLI access. Upgrade, then sign in again.",
    "invalid_state": "The sign-in link didn’t match this login attempt.",
}


def _oauth_issuer() -> str:
    return (os.environ.get("DATABAR_OAUTH_ISSUER") or DEFAULT_OAUTH_ISSUER).rstrip("/")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


class LoginError(RuntimeError):
    """A login failure; ``code`` picks the wording on the browser page."""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


class _CallbackResult:
    def __init__(self) -> None:
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self.error_description: Optional[str] = None
        # Set by the handler once the browser delivered the redirect.
        self.received = threading.Event()
        # Set by the login flow once it knows how the login ended.
        self.finished = threading.Event()
        self.failure: Optional[LoginError] = None


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Databar CLI</title>
<style>
  :root {{ --bg: #fafafa; --card: #fff; --text: #1a1a1a; --muted: #555; --border: #e6e6e6; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #141414; --card: #1e1e1e; --text: #f2f2f2; --muted: #b0b0b0; --border: #333; }}
  }}
  body {{ margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
         background: var(--bg); color: var(--text);
         font: 16px/1.6 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  main {{ max-width: 440px; margin: 16px; padding: 36px 40px; background: var(--card);
         border: 1px solid var(--border); border-radius: 12px; }}
  h1 {{ margin: 0 0 12px; font-size: 20px; font-weight: 600; }}
  p {{ margin: 8px 0 0; color: var(--muted); }}
  code {{ font-family: ui-monospace, Menlo, monospace; font-size: 14px; }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
{body}
</main>
{script}
</body>
</html>
"""


def _page(title: str, body: str, *, close: bool) -> bytes:
    # The consent screen opened this tab with window.open, so the browser lets it
    # close itself; if it doesn't, the text is still the right thing to show.
    script = "<script>window.close()</script>" if close else ""
    return _PAGE.format(title=html.escape(title), body=body, script=script).encode()


def _success_page() -> bytes:
    return _page(
        "You’re signed in to Databar CLI",
        "<p>You can close this tab and return to your terminal.</p>",
        close=True,
    )


def _failure_page(failure: LoginError) -> bytes:
    reason = _ERROR_MESSAGES.get(failure.code or "") or str(failure)
    return _page(
        "Sign-in didn’t finish",
        f"<p>{html.escape(reason)}</p>"
        "<p>Run <code>databar login</code> in your terminal to try again.</p>",
        close=False,
    )


def _make_handler(result: _CallbackResult, expected_state: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") != OAUTH_CALLBACK_PATH or result.received.is_set():
                self.send_response(404)
                self.end_headers()
                return

            qs = parse_qs(parsed.query)
            error = (qs.get("error") or [None])[0]
            state = (qs.get("state") or [None])[0]
            if error:
                result.error = error
                result.error_description = (qs.get("error_description") or [None])[0]
            elif state != expected_state:
                result.error = "invalid_state"
                result.error_description = "OAuth state mismatch"
            else:
                result.code = (qs.get("code") or [None])[0]
            result.received.set()

            # Answer the tab only once the login is over, so it never says
            # "signed in" for a code the server then refused.
            finished = result.finished.wait(timeout=_FINISH_TIMEOUT_S)
            if finished and result.failure is None:
                status, body = 200, _success_page()
            else:
                failure = result.failure or LoginError("The terminal didn’t finish the login in time.")
                status, body = 400, _failure_page(failure)

            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _exchange_code(issuer: str, code: str, verifier: str, redirect_uri: str) -> str:
    response = httpx.post(
        f"{issuer}/oauth/token/",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": OAUTH_CLIENT_ID,
            "code_verifier": verifier,
        },
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    if response.status_code != 200:
        detail = response.text[:200]
        raise LoginError(f"Token exchange failed ({response.status_code}): {detail}")
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise LoginError("Token exchange response missing access_token")
    return access_token


def _fetch_api_key(issuer: str, access_token: str) -> dict:
    response = httpx.get(
        f"{issuer}/oauth/api/cli-credentials/",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=30.0,
    )
    if response.status_code != 200:
        code = None
        try:
            code = response.json().get("error")
        except ValueError:
            pass
        if code in _ERROR_MESSAGES:
            raise LoginError(_ERROR_MESSAGES[code], code)
        detail = response.text[:200]
        raise LoginError(f"Could not fetch API key ({response.status_code}): {detail}", code)
    payload = response.json()
    if not payload.get("api_key"):
        raise LoginError("Credentials response missing api_key")
    return payload


def _finish(result: _CallbackResult, issuer: str, verifier: str, redirect_uri: str) -> dict:
    if result.error:
        code = result.error
        message = _ERROR_MESSAGES.get(code) or result.error_description or code
        raise LoginError(f"Login was denied or failed: {message}", code)
    if not result.code:
        raise LoginError("No authorization code received from the browser callback.")
    access_token = _exchange_code(issuer, result.code, verifier, redirect_uri)
    return _fetch_api_key(issuer, access_token)


def run_browser_login(*, print_url=None) -> dict:
    """Run the full browser OAuth flow.

    Returns credentials dict with ``api_key`` and ``email``.
    ``print_url`` is called with the authorize URL (so the CLI can show it if
    the browser fails to open).
    """
    issuer = _oauth_issuer()
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    result = _CallbackResult()

    # Port 0: the OS hands out a free port, so nothing else listening can take the code.
    server = HTTPServer((OAUTH_CALLBACK_HOST, 0), _make_handler(result, state))
    port = server.server_address[1]
    redirect_uri = f"http://{OAUTH_CALLBACK_HOST}:{port}{OAUTH_CALLBACK_PATH}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        params = {
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        authorize_url = f"{issuer}/oauth/authorize/?{urlencode(params)}"

        opened = webbrowser.open(authorize_url)
        if print_url is not None:
            print_url(authorize_url, opened=opened)

        if not result.received.wait(timeout=_LOGIN_TIMEOUT_S):
            raise LoginError("Timed out waiting for browser login. Run `databar login` again.")

        try:
            return _finish(result, issuer, verifier, redirect_uri)
        except LoginError as exc:
            result.failure = exc
            raise
        except Exception as exc:  # network errors etc. — the tab still gets an answer
            result.failure = LoginError(str(exc))
            raise
    finally:
        # Release the waiting browser tab, then stop the server once it has answered.
        result.finished.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
