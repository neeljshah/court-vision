"""Per-file tests for browser_fetch (NETWORK-FREE -- fake fetcher injected,
scrapling/playwright never imported/touched)."""
from __future__ import annotations

import json

import pytest
import urllib.error

from scripts.platformkit.odds_provider.browser_fetch import (
    BrowserBlockedShape, BrowserUnavailable, _NAV_BLOCKED_MARKER,
    browser_available, browser_get_json)


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body


def test_browser_get_json_success_parses_body():
    def fake_fetcher(url, timeout=30.0):
        return _FakeResponse(200, json.dumps({"ok": True, "url": url}))

    result = browser_get_json("https://example.com/api", fetcher=fake_fetcher)
    assert result == {"ok": True, "url": "https://example.com/api"}


def test_browser_get_json_success_bytes_body():
    def fake_fetcher(url, timeout=30.0):
        return _FakeResponse(200, json.dumps({"a": 1}).encode("utf-8"))

    result = browser_get_json("https://example.com/api", fetcher=fake_fetcher)
    assert result == {"a": 1}


def test_browser_get_json_403_raises_http_error_with_real_code():
    def fake_fetcher(url, timeout=30.0):
        return _FakeResponse(403, "forbidden")

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        browser_get_json("https://example.com/blocked", fetcher=fake_fetcher)
    assert exc_info.value.code == 403


def test_browser_get_json_401_raises_http_error_with_real_code():
    def fake_fetcher(url, timeout=30.0):
        return _FakeResponse(401, "unauthorized")

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        browser_get_json("https://example.com/blocked", fetcher=fake_fetcher)
    assert exc_info.value.code == 401


def test_browser_get_json_html_body_raises_value_error():
    """The 200-trap: a 2xx status but an HTML/challenge body where JSON was
    expected must surface as a JSON parse error, same as the other two tiers."""
    def fake_fetcher(url, timeout=30.0):
        return _FakeResponse(200, "<html>not json</html>")

    with pytest.raises(ValueError):
        browser_get_json("https://example.com/wall", fetcher=fake_fetcher)


def test_browser_get_json_nav_blocked_shape_raises_browser_blocked_shape(monkeypatch):
    """Simulates the real, verified-on-this-box failure mode: DynamicFetcher's
    underlying page.goto raises before a Response object exists for a non-2xx
    status. No `fetcher` injection point exists for this path (it happens
    inside `_real_fetcher`), so we monkeypatch `_real_fetcher` directly and
    force `browser_available` to report True without touching the network."""
    import scripts.platformkit.odds_provider.browser_fetch as mod

    monkeypatch.setattr(mod, "_available_cache", True)

    def fake_real_fetcher(url, *, timeout):
        raise RuntimeError(
            f"Page.goto: net::{_NAV_BLOCKED_MARKER} at {url}")

    monkeypatch.setattr(mod, "_real_fetcher", fake_real_fetcher)

    with pytest.raises(BrowserBlockedShape):
        browser_get_json("https://example.com/wall")


def test_browser_unavailable_raised_when_no_fetcher_and_not_available(monkeypatch):
    import scripts.platformkit.odds_provider.browser_fetch as mod

    monkeypatch.setattr(mod, "_available_cache", False)

    with pytest.raises(BrowserUnavailable):
        browser_get_json("https://example.com/api")


def test_browser_available_result_is_cached(monkeypatch):
    import scripts.platformkit.odds_provider.browser_fetch as mod

    monkeypatch.setattr(mod, "_available_cache", None)
    calls = {"n": 0}

    class _FakeSyncPlaywright:
        def __enter__(self):
            calls["n"] += 1

            class _P:
                class chromium:
                    @staticmethod
                    def launch(headless=True):
                        class _B:
                            def close(self):
                                pass
                        return _B()
            return _P()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright", lambda: _FakeSyncPlaywright())

    first = browser_available()
    second = browser_available()
    assert first == second
    assert calls["n"] == 1  # only launched once -- cached after first check


def test_fetcher_injection_skips_availability_check_entirely(monkeypatch):
    """When a fetcher is injected, browser_available() must never be called --
    tests never need the real package/binary, matching stealth_fetch's contract."""
    import scripts.platformkit.odds_provider.browser_fetch as mod

    def fail_if_called():
        raise AssertionError("browser_available should not be called")

    monkeypatch.setattr(mod, "browser_available", fail_if_called)

    def fake_fetcher(url, timeout=30.0):
        return _FakeResponse(200, json.dumps({"ok": True}))

    result = browser_get_json("https://example.com/api", fetcher=fake_fetcher)
    assert result == {"ok": True}
