"""Per-file test for odds_provider.inplay_espn (offline, canned ESPN payloads).

Proves: fetch_espn_inplay flattens an IN-PROGRESS ESPN event's pickcenter moneyline
into per-side in-play ticks stamped status="in"; a pre/post game contributes NOTHING;
the emitted tick passes the daemon's venue-native liveness gate; tennis is mapped.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_espn.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.odds_provider import inplay_espn
from scripts.platformkit.odds_provider.inplay_feed import default_is_live_native

NOW = datetime(2026, 6, 18, 23, 30, tzinfo=timezone.utc)


def _scoreboard(state):
    """One event in *state* ('in'/'pre'/'post')."""
    return {"events": [{
        "id": "401",
        "competitions": [{
            "status": {"type": {"state": state}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Athletics"}},
                {"homeAway": "away", "team": {"displayName": "Angels"}},
            ],
        }],
    }]}


_SUMMARY = {"pickcenter": [{
    "provider": {"name": "DraftKings"},
    "homeTeamOdds": {"moneyLine": -150},
    "awayTeamOdds": {"moneyLine": +160},
}]}


def _patch(monkeypatch, board, summary, *, source_ts="2026-06-18T23:29:30+00:00"):
    """Route the module's disk_cache_get* to canned scoreboard/summary payloads.

    _ticks_for_event now uses disk_cache_get_meta (LA-P0-a) to carry the body's TRUE
    fetch time as source_ts; the scoreboard read stays body-only (disk_cache_get).
    """
    import scripts.platformkit.odds_provider.http_cache as hc

    def fake_body(url, **kw):
        return summary if "summary" in url else board

    def fake_meta(url, **kw):
        body = summary if "summary" in url else board
        return body, source_ts, True

    monkeypatch.setattr(hc, "disk_cache_get", fake_body)
    monkeypatch.setattr(hc, "disk_cache_get_meta", fake_meta)


def test_live_event_yields_two_sided_moneyline_ticks(monkeypatch):
    _patch(monkeypatch, _scoreboard("in"), _SUMMARY)
    ticks = inplay_espn.fetch_espn_inplay("mlb")
    assert len(ticks) == 2
    sides = {t["side"] for t in ticks}
    assert sides == {"home", "away"}
    for t in ticks:
        assert t["venue"] == "espn:DraftKings"
        assert t["status"] == "in"
        assert t["commence_time"] is None
        assert 0.0 < t["prob"] < 1.0
        # The emitted tick must pass the daemon's native liveness gate.
        assert default_is_live_native(t, NOW) is True


def test_pregame_and_final_yield_nothing(monkeypatch):
    _patch(monkeypatch, _scoreboard("pre"), _SUMMARY)
    assert inplay_espn.fetch_espn_inplay("mlb") == []
    _patch(monkeypatch, _scoreboard("post"), _SUMMARY)
    assert inplay_espn.fetch_espn_inplay("mlb") == []


def test_unsupported_sport_is_empty_not_error(monkeypatch):
    _patch(monkeypatch, _scoreboard("in"), _SUMMARY)
    assert inplay_espn.fetch_espn_inplay("cricket") == []


def test_tennis_is_mapped(monkeypatch):
    # Tennis has two ESPN league paths (atp/wta); a live two-competitor match flows.
    _patch(monkeypatch, _scoreboard("in"), _SUMMARY)
    ticks = inplay_espn.fetch_espn_inplay("tennis")
    # Two paths x two sides = 4 ticks from the same canned live event.
    assert len(ticks) == 4
    assert all(t["status"] == "in" for t in ticks)


def test_fetch_never_raises_on_bad_payload(monkeypatch):
    _patch(monkeypatch, {"events": "garbage"}, None)
    assert inplay_espn.fetch_espn_inplay("mlb") == []


def test_emitted_tick_carries_true_source_ts(monkeypatch):
    # LA-P0-a: the emitted tick must carry the BODY's TRUE fetch time (source_ts),
    # not now() -- so a cached/frozen body cannot re-stamp itself fresh downstream.
    _patch(monkeypatch, _scoreboard("in"), _SUMMARY,
           source_ts="2026-06-18T23:29:30+00:00")
    ticks = inplay_espn.fetch_espn_inplay("mlb")
    assert all(t["source_ts"] == "2026-06-18T23:29:30+00:00" for t in ticks)


# --------------------------------------------------------------------------- #
# 2c: a frozen 'in' body (stale source_ts) is NOT admitted live indefinitely.
# --------------------------------------------------------------------------- #


def test_native_live_in_status_stale_source_ts_excluded():
    # An explicit-live 'in' tick whose source_ts is OLD (feed frozen) must NOT read
    # live forever -- the freshness guard turns it off once the body goes stale.
    stale = {"status": "in", "source_ts": "2026-06-18T23:20:00+00:00"}  # 10m old
    assert default_is_live_native(stale, NOW) is False


def test_native_live_in_status_fresh_source_ts_admitted():
    fresh = {"status": "in", "source_ts": "2026-06-18T23:29:40+00:00"}  # 20s old
    assert default_is_live_native(fresh, NOW) is True


def test_native_live_in_status_no_source_ts_back_compat_admitted():
    # Back-compat: an 'in' tick with no source_ts (legacy native ESPN) still admits.
    assert default_is_live_native({"status": "in"}, NOW) is True
