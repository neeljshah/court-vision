"""Per-file test for domains.basketball_nba.cdn_probe.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_cdn_probe.py -q
"""
from __future__ import annotations

import urllib.error

from domains.basketball_nba.cdn_probe import (
    PROBE_GAME_IDS,
    probe_endpoint,
    run_probe,
)


def _always_blocked(url: str):
    """Simulates the real observed behavior: HTTPError 403 at every tier."""
    raise urllib.error.HTTPError(url, 403, "Access Denied", None, None)


def _always_ok(url: str):
    return {"game": {"gameId": "0022500001"}}


def test_probe_endpoint_blocked_both_tiers():
    r = probe_endpoint("https://cdn.nba.com/x.json",
                        plain_get=_always_blocked, stealth_get=_always_blocked)
    assert r["plain_ok"] is False
    assert r["stealth_ok"] is False
    assert r["reachable"] is False


def test_probe_endpoint_reachable_via_stealth_only():
    r = probe_endpoint("https://cdn.nba.com/x.json",
                        plain_get=_always_blocked, stealth_get=_always_ok)
    assert r["plain_ok"] is False
    assert r["stealth_ok"] is True
    assert r["reachable"] is True


def test_probe_endpoint_reachable_via_plain():
    r = probe_endpoint("https://cdn.nba.com/x.json",
                        plain_get=_always_ok, stealth_get=_always_ok)
    assert r["reachable"] is True


def test_probe_endpoint_non_dict_payload_is_not_reachable():
    """A getter that returns a non-JSON-object payload (e.g. an HTML page that
    happened to parse as a JSON string/list) must NOT count as reachable."""
    def _weird(url: str):
        return "<HTML>Access Denied</HTML>"

    r = probe_endpoint("https://cdn.nba.com/x.json", plain_get=_weird, stealth_get=_weird)
    assert r["reachable"] is False


def test_probe_endpoint_getter_raising_generic_exception_is_handled():
    def _boom(url: str):
        raise ValueError("boom")

    r = probe_endpoint("https://cdn.nba.com/x.json", plain_get=_boom, stealth_get=_boom)
    assert r["reachable"] is False


def test_run_probe_verdict_blocked_when_all_endpoints_blocked():
    summary = run_probe(plain_get=_always_blocked, stealth_get=_always_blocked)
    assert summary["verdict"] == "BLOCKED"
    assert summary["n_reachable"] == 0
    # schedule + scoreboard + len(gids) box + len(gids) pbp
    expected_n = 2 + 2 * len(PROBE_GAME_IDS)
    assert summary["n_endpoints_probed"] == expected_n
    assert len(summary["results"]) == expected_n


def test_run_probe_verdict_reachable_when_any_endpoint_ok():
    summary = run_probe(plain_get=_always_blocked, stealth_get=_always_ok)
    assert summary["verdict"] == "REACHABLE"
    assert summary["n_reachable"] == summary["n_endpoints_probed"]


def test_run_probe_custom_game_ids_shrinks_url_set():
    summary = run_probe(plain_get=_always_blocked, stealth_get=_always_blocked,
                         game_ids=["0022500001"])
    assert summary["n_endpoints_probed"] == 4  # schedule + scoreboard + 1 box + 1 pbp


def test_run_probe_never_raises_on_getter_that_always_throws():
    def _throws(url: str):
        raise RuntimeError("network is down")

    summary = run_probe(plain_get=_throws, stealth_get=_throws)
    assert summary["verdict"] == "BLOCKED"
