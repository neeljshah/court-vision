"""Per-file tests for transport (NETWORK-FREE -- plain_get/stealth_get injected,
tmp_path used for every prefs file so the real disk cache is never touched)."""
from __future__ import annotations

import json
import urllib.error

import pytest

from scripts.platformkit.odds_provider.transport import (
    DEFAULT_STEALTH_TTL_SEC, _load_prefs, mark_stealth_first, resilient_get_json)

URL = "https://example.com/api/data"
HOST = "example.com"


def _prefs_path(tmp_path):
    return tmp_path / "transport_prefs.json"


def test_plain_success_never_calls_stealth(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    calls = {"stealth": 0}

    def plain_get(url, timeout=20.0):
        return {"ok": True}

    def stealth_get(url, timeout=20.0):
        calls["stealth"] += 1
        return {"should": "not happen"}

    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=_prefs_path(tmp_path))
    assert result == {"ok": True}
    assert calls["stealth"] == 0


def test_plain_403_falls_back_to_stealth_and_writes_prefs(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 403, "forbidden", None, None)

    def stealth_get(url, timeout=20.0):
        return {"via": "stealth"}

    prefs_path = _prefs_path(tmp_path)
    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=prefs_path, now=lambda: 1000.0)
    assert result == {"via": "stealth"}
    prefs = _load_prefs(prefs_path)
    assert HOST in prefs
    assert prefs[HOST]["since"] == 1000.0


def test_fresh_prefs_try_stealth_first(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    prefs_path = _prefs_path(tmp_path)
    mark_stealth_first(HOST, prefs_path=prefs_path, now=lambda: 1000.0)

    calls = {"plain": 0, "stealth": 0}

    def plain_get(url, timeout=20.0):
        calls["plain"] += 1
        return {"via": "plain"}

    def stealth_get(url, timeout=20.0):
        calls["stealth"] += 1
        return {"via": "stealth"}

    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=prefs_path, now=lambda: 1010.0)
    assert result == {"via": "stealth"}
    assert calls["stealth"] == 1
    assert calls["plain"] == 0


def test_expired_prefs_go_plain_first_again(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    prefs_path = _prefs_path(tmp_path)
    mark_stealth_first(HOST, prefs_path=prefs_path, now=lambda: 1000.0)

    calls = {"plain": 0, "stealth": 0}

    def plain_get(url, timeout=20.0):
        calls["plain"] += 1
        return {"via": "plain"}

    def stealth_get(url, timeout=20.0):
        calls["stealth"] += 1
        return {"via": "stealth"}

    later = 1000.0 + DEFAULT_STEALTH_TTL_SEC + 1.0
    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=prefs_path, now=lambda: later)
    assert result == {"via": "plain"}
    assert calls["plain"] == 1
    assert calls["stealth"] == 0


def test_stealth_failure_reraises_original_plain_error(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 401, "unauthorized", None, None)

    def stealth_get(url, timeout=20.0):
        raise RuntimeError("stealth also broken")

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                           prefs_path=_prefs_path(tmp_path))
    assert exc_info.value.code == 401


def test_hanging_stealth_get_is_bounded_not_wedged(tmp_path, monkeypatch):
    """Root-cause regression test for the m1_paper wedge: a stealth_get that
    never returns (simulates a 3rd-party lib ignoring its own timeout=) must
    NOT block resilient_get_json forever -- the watchdog reraises the
    original plain error within timeout+grace instead."""
    import time as _time

    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 429, "too many requests", None, None)

    def stealth_get(url, timeout=20.0):
        _time.sleep(timeout + 60)  # simulate a lib that ignores timeout=
        return {"should": "never return"}

    started = _time.monotonic()
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        resilient_get_json(URL, timeout=0.2, plain_get=plain_get,
                           stealth_get=stealth_get, prefs_path=_prefs_path(tmp_path))
    elapsed = _time.monotonic() - started
    assert exc_info.value.code == 429
    assert elapsed < 10.0  # bounded by timeout(0.2) + grace(5s), not 60s+


def test_non_blocked_error_reraises_without_stealth(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    calls = {"stealth": 0}

    def plain_get(url, timeout=20.0):
        raise urllib.error.HTTPError(url, 404, "not found", None, None)

    def stealth_get(url, timeout=20.0):
        calls["stealth"] += 1
        return {"should": "not happen"}

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                           prefs_path=_prefs_path(tmp_path))
    assert exc_info.value.code == 404
    assert calls["stealth"] == 0


def test_json_parse_failure_is_blocked_shaped_and_escalates(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)

    def plain_get(url, timeout=20.0):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    def stealth_get(url, timeout=20.0):
        return {"via": "stealth"}

    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=_prefs_path(tmp_path))
    assert result == {"via": "stealth"}


def test_kill_switch_env_skips_stealth_entirely(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_STEALTH_FALLBACK", "0")
    calls = {"plain": 0, "stealth": 0}

    def plain_get(url, timeout=20.0):
        calls["plain"] += 1
        return {"via": "plain"}

    def stealth_get(url, timeout=20.0):
        calls["stealth"] += 1
        return {"via": "stealth"}

    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=_prefs_path(tmp_path))
    assert result == {"via": "plain"}
    assert calls["plain"] == 1
    assert calls["stealth"] == 0


def test_kill_switch_env_false_string_also_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_STEALTH_FALLBACK", "false")

    def plain_get(url, timeout=20.0):
        return {"via": "plain"}

    def stealth_get(url, timeout=20.0):
        raise AssertionError("stealth must not be called")

    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=_prefs_path(tmp_path))
    assert result == {"via": "plain"}


def test_corrupt_prefs_file_tolerated(tmp_path, monkeypatch):
    monkeypatch.delenv("CV_STEALTH_FALLBACK", raising=False)
    prefs_path = _prefs_path(tmp_path)
    prefs_path.write_text("{not valid json", encoding="utf-8")

    def plain_get(url, timeout=20.0):
        return {"via": "plain"}

    def stealth_get(url, timeout=20.0):
        raise AssertionError("should not be reached on a plain success")

    result = resilient_get_json(URL, plain_get=plain_get, stealth_get=stealth_get,
                                prefs_path=prefs_path)
    assert result == {"via": "plain"}


def test_mark_stealth_first_preserves_original_since(tmp_path):
    prefs_path = _prefs_path(tmp_path)
    mark_stealth_first(HOST, prefs_path=prefs_path, now=lambda: 500.0)
    mark_stealth_first(HOST, prefs_path=prefs_path, now=lambda: 600.0)
    prefs = _load_prefs(prefs_path)
    assert prefs[HOST]["since"] == 500.0
    assert prefs[HOST]["last_used"] == 600.0


def test_missing_prefs_file_is_empty(tmp_path):
    prefs = _load_prefs(tmp_path / "does_not_exist.json")
    assert prefs == {}


# Tier 3 (browser) escalation tests live in test_transport_browser_tier.py
# (split out to keep both files under the 300-LOC/file limit).
