"""Per-file tests for transport's Tier-3 (browser) escalation (NETWORK-FREE --
plain_get/stealth_get/browser_get injected, tmp_path used for every prefs file
so the real disk cache is never touched). Split out of test_transport.py to
keep both files under the 300-LOC/file limit."""
from __future__ import annotations

import urllib.error

import pytest

from scripts.platformkit.odds_provider.transport import (
    _load_prefs, mark_stealth_first, resilient_get_json)

URL = "https://example.com/api/data"
HOST = "example.com"


def _prefs_path(tmp_path):
    return tmp_path / "transport_prefs.json"


def test_browser_tier_default_off_never_called_even_when_stealth_blocked(tmp_path, monkeypatch):
    """CV_BROWSER_FALLBACK unset -> tier 3 must be fully inert: if stealth also
    fails blocked-shaped, the ORIGINAL plain error surfaces, same as pre-tier-3."""
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    monkeypatch.delenv("CV_BROWSER_FALLBACK", raising=False)
    calls = {"browser": 0}

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 403, "forbidden", None, None)

    def stealth_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 403, "forbidden", None, None)

    def browser_get(url, timeout=20.0):
        calls["browser"] += 1
        return {"via": "browser"}

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                           browser_get=browser_get, prefs_path=_prefs_path(tmp_path))
    assert exc_info.value.code == 403
    assert calls["browser"] == 0


def test_browser_tier_fires_when_env_on_and_stealth_also_blocked(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    monkeypatch.setenv("CV_BROWSER_FALLBACK", "1")

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 403, "forbidden", None, None)

    def stealth_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 403, "forbidden", None, None)

    def browser_get(url, timeout=20.0):
        return {"via": "browser"}

    prefs_path = _prefs_path(tmp_path)
    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                browser_get=browser_get, prefs_path=prefs_path,
                                now=lambda: 1000.0)
    assert result == {"via": "browser"}
    prefs = _load_prefs(prefs_path)
    assert prefs[HOST]["tier"] == "browser"


def test_browser_tier_not_tried_when_stealth_fails_non_blocked_shaped(tmp_path, monkeypatch):
    """Tier 3 only fires when stealth's OWN failure is blocked-shaped -- an
    unrelated stealth bug (e.g. StealthUnavailable) must not escalate further."""
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    monkeypatch.setenv("CV_BROWSER_FALLBACK", "1")
    calls = {"browser": 0}

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 403, "forbidden", None, None)

    def stealth_get(url, timeout=20.0):
        raise RuntimeError("stealth package not importable")

    def browser_get(url, timeout=20.0):
        calls["browser"] += 1
        return {"via": "browser"}

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                           browser_get=browser_get, prefs_path=_prefs_path(tmp_path))
    assert exc_info.value.code == 403
    assert calls["browser"] == 0


def test_browser_tier_all_three_fail_reraises_original_plain_error(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    monkeypatch.setenv("CV_BROWSER_FALLBACK", "1")

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 401, "unauthorized", None, None)

    def stealth_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 401, "unauthorized", None, None)

    def browser_get(url, timeout=20.0):
        raise RuntimeError("browser also blocked")

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                           browser_get=browser_get, prefs_path=_prefs_path(tmp_path))
    assert exc_info.value.code == 401


def test_fresh_browser_first_mark_tries_browser_before_plain(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    monkeypatch.setenv("CV_BROWSER_FALLBACK", "1")
    prefs_path = _prefs_path(tmp_path)
    mark_stealth_first(HOST, tier="browser", prefs_path=prefs_path, now=lambda: 1000.0)

    calls = {"plain": 0, "stealth": 0, "browser": 0}

    def plain_get(url, timeout=20.0):
        calls["plain"] += 1
        return {"via": "plain"}

    def stealth_get(url, timeout=20.0):
        calls["stealth"] += 1
        return {"via": "stealth"}

    def browser_get(url, timeout=20.0):
        calls["browser"] += 1
        return {"via": "browser"}

    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                browser_get=browser_get, prefs_path=prefs_path,
                                now=lambda: 1010.0)
    assert result == {"via": "browser"}
    assert calls == {"plain": 0, "stealth": 0, "browser": 1}


def test_browser_first_mark_ignored_when_env_off_falls_through_to_plain(tmp_path, monkeypatch):
    """A stale 'browser' preference must not be honored once the opt-in env is
    off again -- tier 3 stays fully inert by default, never a surprise fetch."""
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    monkeypatch.delenv("CV_BROWSER_FALLBACK", raising=False)
    prefs_path = _prefs_path(tmp_path)
    mark_stealth_first(HOST, tier="browser", prefs_path=prefs_path, now=lambda: 1000.0)

    calls = {"plain": 0, "browser": 0}

    def plain_get(url, timeout=20.0):
        calls["plain"] += 1
        return {"via": "plain"}

    def browser_get(url, timeout=20.0):
        calls["browser"] += 1
        return {"via": "browser"}

    result = resilient_get_json(URL, plain_get=plain_get, browser_get=browser_get,
                                prefs_path=prefs_path, now=lambda: 1010.0)
    assert result == {"via": "plain"}
    assert calls == {"plain": 1, "browser": 0}
