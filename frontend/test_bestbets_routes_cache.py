"""frontend.test_bestbets_routes_cache -- the per-sport TTL cache on /api/v1/bestbets.

build_edge_view line-shops + decides every market live (~30s for a full slate), so the
route caches the OK envelope for _VIEW_TTL_SEC to keep the UI responsive. These tests pin
that behavior: a live-path hit is served from cache (assembler NOT re-run), a store_dir
caller (tests) always bypasses the cache, and an 'unavailable' result is never cached.
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import frontend.bestbets_routes as br


def _body(resp) -> dict:
    return json.loads(bytes(resp.body))


def _ok_view():
    return {"status": "ok", "generated_at": "2026-06-24T00:00:00+00:00", "games": []}


def setup_function(_func) -> None:
    br._view_cache.clear()


def test_live_path_caches_ok_envelope():
    """Two live calls within the TTL build the edge view ONCE (second is cache-served)."""
    fake = MagicMock(return_value=_ok_view())
    with patch.object(br, "build_edge_view", fake):
        r1 = br.bestbets_for_sport("mlb")
        r2 = br.bestbets_for_sport("mlb")
    assert fake.call_count == 1, "second live call should hit the cache"
    assert _body(r1)["status"] == _body(r2)["status"]


def test_store_dir_caller_bypasses_cache():
    """A caller passing store_dir (tests) always recomputes -- never cached/served."""
    fake = MagicMock(return_value=_ok_view())
    with patch.object(br, "build_edge_view", fake):
        br.bestbets_for_sport("mlb", store_dir="/tmp/x")
        br.bestbets_for_sport("mlb", store_dir="/tmp/x")
    assert fake.call_count == 2
    assert "mlb" not in br._view_cache


def test_unavailable_is_not_cached():
    """An 'unavailable' view is recomputed every call (stale-never-green)."""
    fake = MagicMock(return_value={"status": "unavailable", "reason": "no snapshot"})
    with patch.object(br, "build_edge_view", fake):
        br.bestbets_for_sport("mlb")
        br.bestbets_for_sport("mlb")
    assert fake.call_count == 2
    assert "mlb" not in br._view_cache


def test_stale_cache_serves_immediately_and_refreshes_in_background():
    """Past the TTL the route serves the last-good copy at once AND rebuilds in the
    background (serve-stale-while-revalidate), so a user request never blocks on a slow
    rebuild after the first warm."""
    fake = MagicMock(return_value=_ok_view())
    with patch.object(br, "build_edge_view", fake):
        r1 = br.bestbets_for_sport("mlb")          # cold -> compute #1 + cache
        assert _body(r1)["status"] == "ok"
        # age the cached entry beyond the TTL
        ts, env = br._view_cache["mlb"]
        br._view_cache["mlb"] = (ts - br._VIEW_TTL_SEC - 1.0, env)
        r2 = br.bestbets_for_sport("mlb")          # stale -> serve now + bg refresh #2
        assert _body(r2)["status"] == "ok"         # served immediately (no block)
        # the background refresh runs in a daemon thread -> wait briefly for it
        deadline = time.time() + 3.0
        while fake.call_count < 2 and time.time() < deadline:
            time.sleep(0.02)
    assert fake.call_count == 2, "stale read should trigger exactly one bg rebuild"
