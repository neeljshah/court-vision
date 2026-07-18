"""Per-file test: line-acquisition robustness in http_cache (LA-P0-a / LA-P0-c).

Proves the stale-never-green rail at the cache layer:
  * a body served from the TTL cache reports its ORIGINAL fetched-at time, NOT
    now() -- so a cached/dead feed cannot re-stamp itself fresh within the TTL;
  * an EXPIRED cache entry triggers a live re-fetch (fetched_at = now);
  * the retry wrapper recovers from an injected TRANSIENT error then succeeds;
  * a non-transient (4xx) error is NOT retried -- it surfaces at once.

Offline: no network, injected fetcher + injected clock; time.sleep is no-op'd so
the backoff never actually sleeps.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_http_cache_robustness.py -q
"""
from __future__ import annotations

import os
import urllib.error

import pytest

from scripts.platformkit.odds_provider import http_cache as hc


URL = "https://example.test/markets"


def test_cached_body_reports_original_fetched_at_not_now(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_PROVIDER_CACHE_DIR", str(tmp_path))
    # Re-point the module cache dir (set at import time) at the tmp dir.
    monkeypatch.setattr(hc, "_CACHE_DIR", tmp_path)

    clock = {"t": 1000.0}

    def fake_get(_url):
        return {"markets": [1, 2, 3]}

    # First call: live fetch, stamps fetched_at at t=1000, cache_hit=False.
    body1, fetched1, hit1 = hc.disk_cache_get_meta(
        URL, http_get=fake_get, ttl=60.0, now=lambda: clock["t"])
    assert hit1 is False
    assert body1 == {"markets": [1, 2, 3]}

    # 30s later (< ttl): served from cache. fetched_at must be the ORIGINAL t=1000
    # time, NOT the new now (t=1030) -- a cached body cannot read fresh-as-now.
    clock["t"] = 1030.0

    def boom(_url):  # the network must NOT be touched on a cache hit
        raise AssertionError("network hit on a fresh cache entry")

    body2, fetched2, hit2 = hc.disk_cache_get_meta(
        URL, http_get=boom, ttl=60.0, now=lambda: clock["t"])
    assert hit2 is True
    assert body2 == body1
    assert fetched2 == fetched1  # ORIGINAL fetch time, never re-stamped to now()


def test_cache_write_is_atomic_tmp_replace_no_tmp_left(tmp_path, monkeypatch):
    """The cache-file write on a miss must go tmp + os.replace (like
    transport._save_prefs) so a reader never sees a half-written meta file, and
    the sibling .tmp must be gone afterward."""
    monkeypatch.setattr(hc, "_CACHE_DIR", tmp_path)

    def fake_get(_url):
        return {"markets": ["a", "b"]}

    body, _fetched, hit = hc.disk_cache_get_meta(
        URL, http_get=fake_get, ttl=60.0, now=lambda: 5000.0)
    assert hit is False
    assert body == {"markets": ["a", "b"]}
    cache_path = hc._cache_path(URL)
    assert cache_path.exists()
    assert not cache_path.with_suffix(cache_path.suffix + ".tmp").exists()
    # A second call within the TTL reads the same body back from disk (proves
    # the written file is a complete, loadable JSON document, not a torn write).
    body2, _f2, hit2 = hc.disk_cache_get_meta(
        URL, http_get=lambda _u: (_ for _ in ()).throw(AssertionError("no network")),
        ttl=60.0, now=lambda: 5010.0)
    assert hit2 is True
    assert body2 == body


def test_tmp_write_path_is_unique_per_writer_same_url(tmp_path, monkeypatch):
    """Two concurrent writers for the SAME url must never alias one tmp inode
    (the confirmed bug: path.with_suffix('.tmp') was one shared name per URL --
    a torn/aliased write was possible under concurrent same-URL writes)."""
    monkeypatch.setattr(hc, "_CACHE_DIR", tmp_path)
    path = hc._cache_path(URL)
    fd1, tmp1 = hc._tmp_write_path(path)
    fd2, tmp2 = hc._tmp_write_path(path)
    try:
        assert tmp1 != tmp2  # distinct tmp names for the same target path
        assert os.path.exists(tmp1) and os.path.exists(tmp2)
    finally:
        os.close(fd1)
        os.close(fd2)
        os.remove(tmp1)
        os.remove(tmp2)


def test_disk_cache_write_leaves_no_tmp_litter(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "_CACHE_DIR", tmp_path)

    def fake_get(_url):
        return {"markets": ["x"]}

    body, _fetched, hit = hc.disk_cache_get_meta(
        URL, http_get=fake_get, ttl=60.0, now=lambda: 5000.0)
    assert hit is False
    assert body == {"markets": ["x"]}
    assert list(tmp_path.glob("*.tmp")) == []  # no leftover tmp file after a clean write


def test_expired_entry_refetches_live(tmp_path, monkeypatch):
    monkeypatch.setattr(hc, "_CACHE_DIR", tmp_path)
    clock = {"t": 2000.0}
    calls = {"n": 0}

    def fake_get(_url):
        calls["n"] += 1
        return {"v": calls["n"]}

    hc.disk_cache_get_meta(URL, http_get=fake_get, ttl=60.0, now=lambda: clock["t"])
    # Advance PAST the ttl -> a live re-fetch with a NEW fetched_at.
    clock["t"] = 2000.0 + 120.0
    body, fetched, hit = hc.disk_cache_get_meta(
        URL, http_get=fake_get, ttl=60.0, now=lambda: clock["t"])
    assert hit is False
    assert calls["n"] == 2  # the expired entry forced a second fetch
    assert body == {"v": 2}


def test_retry_recovers_from_transient_then_succeeds(monkeypatch):
    # No real sleep during backoff.
    monkeypatch.setattr(hc.time, "sleep", lambda _s: None)
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise urllib.error.URLError("temporary failure in name resolution")
        return {"ok": True}

    wrapped = hc._retrying(flaky)
    assert wrapped() == {"ok": True}
    assert state["n"] == 3  # failed twice (transient), recovered on the 3rd try


def test_retry_does_not_retry_client_4xx(monkeypatch):
    monkeypatch.setattr(hc.time, "sleep", lambda _s: None)
    state = {"n": 0}

    def forbidden():
        state["n"] += 1
        raise urllib.error.HTTPError(URL, 404, "Not Found", hdrs=None, fp=None)

    wrapped = hc._retrying(forbidden)
    with pytest.raises(urllib.error.HTTPError):
        wrapped()
    assert state["n"] == 1  # a 4xx is NOT retried (it will not self-heal)


def test_retry_gives_up_after_attempts_on_persistent_transient(monkeypatch):
    monkeypatch.setattr(hc.time, "sleep", lambda _s: None)
    state = {"n": 0}

    def always_503():
        state["n"] += 1
        raise urllib.error.HTTPError(URL, 503, "Service Unavailable",
                                     hdrs=None, fp=None)

    wrapped = hc._retrying(always_503)
    with pytest.raises(urllib.error.HTTPError):
        wrapped()
    assert state["n"] == hc.RETRY_ATTEMPTS  # tried, then degraded (never stale-green)
