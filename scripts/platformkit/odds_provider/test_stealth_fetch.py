"""Per-file tests for stealth_fetch (NETWORK-FREE -- fake fetcher injected,
scrapling never imported/touched)."""
from __future__ import annotations

import json

import pytest
import urllib.error

from scripts.platformkit.odds_provider.stealth_fetch import (
    StealthUnavailable, stealth_available, stealth_get_json)


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body


def test_stealth_get_json_success_parses_body():
    def fake_fetcher(url, timeout=20.0):
        return _FakeResponse(200, json.dumps({"ok": True, "url": url}))

    result = stealth_get_json("https://example.com/api", fetcher=fake_fetcher)
    assert result == {"ok": True, "url": "https://example.com/api"}


def test_stealth_get_json_success_bytes_body():
    def fake_fetcher(url, timeout=20.0):
        return _FakeResponse(200, json.dumps({"a": 1}).encode("utf-8"))

    result = stealth_get_json("https://example.com/api", fetcher=fake_fetcher)
    assert result == {"a": 1}


def test_stealth_get_json_403_raises_http_error_with_real_code():
    def fake_fetcher(url, timeout=20.0):
        return _FakeResponse(403, "forbidden")

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        stealth_get_json("https://example.com/blocked", fetcher=fake_fetcher)
    assert exc_info.value.code == 403


def test_stealth_get_json_401_raises_http_error_with_real_code():
    def fake_fetcher(url, timeout=20.0):
        return _FakeResponse(401, "unauthorized")

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        stealth_get_json("https://example.com/blocked", fetcher=fake_fetcher)
    assert exc_info.value.code == 401


def test_stealth_get_json_html_body_raises_value_error():
    def fake_fetcher(url, timeout=20.0):
        return _FakeResponse(200, "<html>not json</html>")

    with pytest.raises(ValueError):
        stealth_get_json("https://example.com/wall", fetcher=fake_fetcher)


def test_stealth_available_false_when_import_fails(monkeypatch):
    import scripts.platformkit.odds_provider.stealth_fetch as sf
    monkeypatch.setattr(sf, "_available_cache", None)

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("scrapling"):
            raise ImportError("no scrapling in this test env")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert stealth_available() is False


def test_stealth_get_json_raises_stealth_unavailable_when_no_scrapling(monkeypatch):
    import scripts.platformkit.odds_provider.stealth_fetch as sf
    monkeypatch.setattr(sf, "stealth_available", lambda: False)

    with pytest.raises(StealthUnavailable):
        stealth_get_json("https://example.com/api")
