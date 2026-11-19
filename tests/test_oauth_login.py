"""Unit tests for CLI OAuth helpers (token exchange + credentials fetch)."""

from __future__ import annotations

import httpx
import pytest
import respx

import threading
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlparse

from databar.cli._oauth import (
    OAUTH_CLIENT_ID,
    LoginError,
    _exchange_code,
    _fetch_api_key,
    _pkce_pair,
    run_browser_login,
)

REDIRECT = "http://127.0.0.1:61234/callback"


def test_pkce_pair_s256_shape():
    verifier, challenge = _pkce_pair()
    assert len(verifier) > 40
    assert len(challenge) >= 43
    assert "=" not in challenge


@respx.mock
def test_exchange_code_posts_pkce_fields():
    route = respx.post("https://databar.ai/oauth/token/").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "token_type": "Bearer"})
    )
    token = _exchange_code("https://databar.ai", "auth-code", "verifier", REDIRECT)
    assert token == "tok"
    assert route.called
    request = route.calls.last.request
    body = request.content.decode()
    assert "grant_type=authorization_code" in body
    assert "code=auth-code" in body
    assert f"client_id={OAUTH_CLIENT_ID}" in body
    assert "code_verifier=verifier" in body
    assert "redirect_uri=" + REDIRECT.replace(":", "%3A").replace("/", "%2F") in body


@respx.mock
def test_fetch_api_key_sends_bearer():
    respx.get("https://databar.ai/oauth/api/cli-credentials/").mock(
        return_value=httpx.Response(
            200,
            json={"api_key": "k", "email": "a@b.com", "workspace_identifier": "w", "workspace_name": "W"},
        )
    )
    payload = _fetch_api_key("https://databar.ai", "tok")
    assert payload["api_key"] == "k"
    assert payload["email"] == "a@b.com"


@respx.mock
def test_exchange_code_raises_on_error():
    respx.post("https://databar.ai/oauth/token/").mock(
        return_value=httpx.Response(400, text="bad")
    )
    with pytest.raises(RuntimeError, match="Token exchange failed"):
        _exchange_code("https://databar.ai", "bad", "v", REDIRECT)


class _Browser:
    """Stands in for the person's browser: follows the consent screen's redirect."""

    def __init__(self, monkeypatch, query=None):
        self.query = query  # callable(state) -> dict of callback params
        self.page_status = None
        self.page = None
        self.redirect_uri = None
        self._thread = None
        monkeypatch.setattr("databar.cli._oauth.webbrowser.open", self.open)

    def open(self, url):
        params = parse_qs(urlparse(url).query)
        self.redirect_uri = params["redirect_uri"][0]
        state = params["state"][0]
        query = self.query(state) if self.query else {"code": "auth-code", "state": state}
        target = f"{self.redirect_uri}?{urlencode(query)}"
        self._thread = threading.Thread(target=self._visit, args=(target,), daemon=True)
        self._thread.start()
        return True

    def _visit(self, target):
        try:
            with urllib.request.urlopen(target, timeout=10) as response:
                self.page_status, self.page = response.status, response.read().decode()
        except urllib.error.HTTPError as exc:
            self.page_status, self.page = exc.code, exc.read().decode()

    def wait(self):
        self._thread.join(timeout=10)


def _mock_server(token_status=200, credentials=None):
    token = respx.post("https://databar.ai/oauth/token/").mock(
        return_value=httpx.Response(token_status, json={"access_token": "tok"} if token_status == 200 else None, text=None if token_status == 200 else "invalid_grant")
    )
    respx.get("https://databar.ai/oauth/api/cli-credentials/").mock(
        return_value=credentials or httpx.Response(200, json={"api_key": "k", "email": "a@b.com"})
    )
    return token


@respx.mock
def test_login_listens_on_a_free_port_and_closes_the_tab(monkeypatch):
    token = _mock_server()
    browser = _Browser(monkeypatch)

    creds = run_browser_login()
    browser.wait()

    assert creds["api_key"] == "k"
    port = urlparse(browser.redirect_uri).port
    assert browser.redirect_uri == f"http://127.0.0.1:{port}/callback"
    # The code is redeemed for the port it was actually sent to.
    assert f"127.0.0.1%3A{port}%2Fcallback" in token.calls.last.request.content.decode()
    assert browser.page_status == 200
    assert "You’re signed in to Databar CLI" in browser.page
    assert "window.close()" in browser.page


@respx.mock
def test_a_refused_code_is_not_shown_as_signed_in(monkeypatch):
    _mock_server(token_status=400)
    browser = _Browser(monkeypatch)

    with pytest.raises(LoginError, match="Token exchange failed"):
        run_browser_login()
    browser.wait()

    assert browser.page_status == 400
    assert "Sign-in didn’t finish" in browser.page
    assert "window.close()" not in browser.page


@respx.mock
def test_a_plan_without_cli_access_says_so_in_the_tab(monkeypatch):
    _mock_server(credentials=httpx.Response(403, json={"error": "plan_not_eligible"}))
    browser = _Browser(monkeypatch)

    with pytest.raises(LoginError, match="plan doesn’t include"):
        run_browser_login()
    browser.wait()

    assert browser.page_status == 400
    assert "plan doesn’t include API and CLI access" in browser.page


@respx.mock
def test_deny_and_a_foreign_state_never_reach_the_token_endpoint(monkeypatch):
    token = _mock_server()

    browser = _Browser(monkeypatch, query=lambda state: {"error": "access_denied", "state": state})
    with pytest.raises(LoginError, match="denied access"):
        run_browser_login()
    browser.wait()
    assert browser.page_status == 400
    assert "You denied access" in browser.page

    browser = _Browser(monkeypatch, query=lambda state: {"code": "stolen", "state": "someone-else"})
    with pytest.raises(LoginError, match="didn’t match"):
        run_browser_login()
    browser.wait()
    assert browser.page_status == 400

    assert not token.called


@respx.mock
@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [(200, {"revoked": True}, True), (200, {"revoked": False}, False), (401, {"detail": "x"}, None)],
)
def test_revoke_sign_in(status_code, body, expected):
    from databar.cli._oauth import revoke_sign_in

    route = respx.post("https://databar.ai/oauth/api/cli-logout/").mock(
        return_value=httpx.Response(status_code, json=body)
    )
    assert revoke_sign_in("k") is expected
    assert route.calls.last.request.headers["x-apikey"] == "k"


@respx.mock
def test_revoke_sign_in_offline():
    from databar.cli._oauth import revoke_sign_in

    respx.post("https://databar.ai/oauth/api/cli-logout/").mock(side_effect=httpx.ConnectError("down"))
    assert revoke_sign_in("k") is None
