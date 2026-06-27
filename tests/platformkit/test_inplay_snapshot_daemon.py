"""Per-file test for odds_provider.inplay_snapshot_daemon (offline, fake clock).

Proves: poll_inplay_once writes schema-correct in-play ticks + a freshness sidecar
for LIVE games only; serve_inplay_forever polls fast while live and idles when not;
a per-sport fetch error is isolated (healthy sport's freshness advances, failing
sport's does NOT); writes go through os.replace (atomic), so no partial line.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_snapshot_daemon.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.platformkit.odds_provider import inplay_snapshot_daemon as daemon
from scripts.platformkit.odds_provider import inplay_feed

NOW = datetime(2026, 6, 18, 23, 30, tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ticks(sport="nba", game_id="G1", source_ts=None):
    """Two canned current-market tick-dicts (the shape fetch_fn returns).

    tradeable=True marks them as liquidity-gated in-play prices (the 4b contract:
    only a PROVEN tradeable tick is persisted as an in-play observation). A FRESH
    source_ts is carried because the 2a contract now REQUIRES a tradeable in-play
    tick to expose its TRUE feed time (the frozen-feed guard is unavoidable)."""
    src = source_ts if source_ts is not None else _iso(NOW - timedelta(seconds=10))
    return [
        {"sport": sport, "game_id": game_id, "venue": "kalshi",
         "market_type": "moneyline", "side": "home", "ticker": "KX-1", "prob": 0.62,
         "tradeable": True, "source_ts": src},
        {"sport": sport, "game_id": game_id, "venue": "polymarket",
         "market_type": "moneyline", "side": "away", "ticker": "PM-1", "prob": 0.40,
         "tradeable": True, "source_ts": src},
    ]


def _read_jsonl(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def test_poll_writes_schema_correct_ticks_for_live_game(tmp_path):
    rep = daemon.poll_inplay_once(
        "nba", now=NOW, out_dir=tmp_path,
        fetch_fn=lambda s: _ticks(),
        is_live_fn=lambda gid, **kw: True)

    assert rep["status"] == "ok"
    assert rep["n_ticks"] == 2
    assert rep["n_games_live"] == 1
    rows = _read_jsonl(rep["out_path"])
    assert len(rows) == 2
    for r in rows:
        assert 0.0 <= r["prob"] <= 1.0
        assert r["phase"] == "in_play"
        assert r["ts"] == "2026-06-18T23:30:00Z"
        assert set(r) >= {"sport", "game_id", "venue", "market_type",
                          "side", "ticker", "prob", "ts", "phase"}
    # Freshness sidecar updated with this capture.
    fresh = json.loads((tmp_path / "nba" / "_freshness.json").read_text())
    assert fresh["last_capture_ts"] == "2026-06-18T23:30:00Z"
    assert fresh["last_n_ticks"] == 2


def test_poll_skips_non_live_game_no_ticks(tmp_path):
    rep = daemon.poll_inplay_once(
        "nba", now=NOW, out_dir=tmp_path,
        fetch_fn=lambda s: _ticks(),
        is_live_fn=lambda gid, **kw: False)  # pregame/final -> not in-play
    assert rep["status"] == "ok"
    assert rep["n_ticks"] == 0
    assert rep["out_path"] is None  # nothing written
    assert not (tmp_path / "nba" / "2026-06-18.jsonl").exists()
    # A successful (empty) poll still stamps freshness.
    assert (tmp_path / "nba" / "_freshness.json").exists()


def test_poll_drops_out_of_range_prob(tmp_path):
    bad = [{"sport": "nba", "game_id": "G1", "venue": "kalshi",
            "market_type": "moneyline", "side": "home", "ticker": "X",
            "prob": 1.7, "tradeable": True,
            "source_ts": _iso(NOW - timedelta(seconds=10))}]  # out of [0,1] -> skipped
    rep = daemon.poll_inplay_once(
        "nba", now=NOW, out_dir=tmp_path, fetch_fn=lambda s: bad,
        is_live_fn=lambda gid, **kw: True)
    assert rep["n_ticks"] == 0


def test_serve_fast_while_live_idle_when_not(tmp_path):
    sleeps = []
    it = iter([NOW, NOW + timedelta(seconds=5), NOW + timedelta(seconds=10)])

    live_flag = {"v": True}

    def fetch(_s):
        return _ticks()

    def is_live(gid, **kw):
        return live_flag["v"]

    def record_sleep(s):
        sleeps.append(s)
        # After the first (live) poll, flip to no-live so the next sleep idles.
        live_flag["v"] = False

    daemon.serve_inplay_forever(
        sports=["nba"], clock=lambda: next(it), sleep=record_sleep,
        fetch_fn=fetch, is_live_fn=is_live, out_dir=tmp_path,
        interval=5, idle_interval=120, max_ticks=3)

    # First sleep was after a LIVE poll -> fast (5s); subsequent -> idle (120s).
    assert sleeps[0] == daemon.FAST_INTERVAL_SEC
    assert sleeps[1] == daemon.IDLE_INTERVAL_SEC


def test_per_sport_isolation_freshness(tmp_path):
    def fetch(sport):
        if sport == "mlb":
            raise RuntimeError("feed down")
        return _ticks(sport="nba", game_id="G1")

    reps = daemon.serve_inplay_forever(
        sports=["nba", "mlb"], clock=lambda: NOW, sleep=lambda _s: None,
        fetch_fn=fetch, is_live_fn=lambda gid, **kw: True,
        out_dir=tmp_path, max_ticks=1)

    nba_rep, mlb_rep = reps[0]["sports"]
    assert nba_rep["status"] == "ok" and nba_rep["n_ticks"] == 2
    assert mlb_rep["status"].startswith("error")  # isolated, did not raise
    # Healthy sport's freshness advanced; failing sport's did NOT (no sidecar).
    assert (tmp_path / "nba" / "_freshness.json").exists()
    assert not (tmp_path / "mlb" / "_freshness.json").exists()


def test_failed_poll_does_not_advance_freshness(tmp_path):
    # Seed a good poll, capture its freshness ts.
    daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                            fetch_fn=lambda s: _ticks(),
                            is_live_fn=lambda gid, **kw: True)
    first = json.loads((tmp_path / "nba" / "_freshness.json").read_text())

    # A later poll whose fetch raises must NOT advance the freshness ts.
    def boom(_s):
        raise RuntimeError("boom")

    rep = daemon.poll_inplay_once("nba", now=NOW + timedelta(minutes=5),
                                  out_dir=tmp_path, fetch_fn=boom,
                                  is_live_fn=lambda gid, **kw: True)
    assert rep["status"].startswith("error")
    after = json.loads((tmp_path / "nba" / "_freshness.json").read_text())
    assert after["last_capture_ts"] == first["last_capture_ts"]  # unchanged


def test_atomic_append_no_partial_line(tmp_path):
    # Two successive polls append; the file must contain exactly 4 valid JSON
    # lines (no partial/corrupt tail -- os.replace swaps the whole file).
    for t in (NOW, NOW + timedelta(seconds=5)):
        daemon.poll_inplay_once("nba", now=t, out_dir=tmp_path,
                                fetch_fn=lambda s: _ticks(),
                                is_live_fn=lambda gid, **kw: True)
    path = tmp_path / "nba" / "2026-06-18.jsonl"
    rows = _read_jsonl(path)  # would raise if any line were corrupt
    assert len(rows) == 4
    # No leftover tmp file (the rename consumed it).
    assert not (path.with_suffix(".jsonl.tmp")).exists()


# --------------------------------------------------------------------------- #
# Venue-native default liveness fn (the fix: no ESPN id cross-join).
# --------------------------------------------------------------------------- #


def _tick(**over):
    base = {"sport": "mlb", "game_id": "G1", "venue": "polymarket",
            "prob": 0.55, "status": "open"}
    base.update(over)
    return base


def test_native_live_future_commence_excluded():
    # Pregame: game starts in 2h -> NOT in-play (honesty guard).
    t = _tick(commence_time=_iso(NOW + timedelta(hours=2)))
    assert inplay_feed.default_is_live_native(t, NOW) is False


def test_native_live_started_unsettled_included():
    # Started 30m ago, no settlement bound passed -> in-play.
    t = _tick(commence_time=_iso(NOW - timedelta(minutes=30)))
    assert inplay_feed.default_is_live_native(t, NOW) is True


def test_native_live_far_past_start_is_futures_excluded():
    # A start far in the past with no close (a Polymarket futures contract whose
    # startDate is its CREATION date, not a tip-off) must NOT read as in-play.
    t = _tick(commence_time=_iso(NOW - timedelta(days=300)), close_time=None)
    assert inplay_feed.default_is_live_native(t, NOW) is False


def test_native_live_settled_close_in_past_excluded():
    # Started but its close_time already passed -> settled, NOT in-play.
    t = _tick(commence_time=_iso(NOW - timedelta(hours=4)),
              close_time=_iso(NOW - timedelta(minutes=10)))
    assert inplay_feed.default_is_live_native(t, NOW) is False


def test_native_live_explicit_settled_status_excluded():
    t = _tick(commence_time=_iso(NOW - timedelta(minutes=30)), status="settled")
    assert inplay_feed.default_is_live_native(t, NOW) is False


def test_native_live_missing_commence_close_soon_heuristic_included():
    # Kalshi case: no commence_time, only a close_time within the live window ->
    # documented heuristic treats an open market settling soon as live.
    t = _tick(venue="kalshi", commence_time=None,
              close_time=_iso(NOW + timedelta(hours=2)))
    assert inplay_feed.default_is_live_native(t, NOW) is True


def test_native_live_missing_commence_close_far_future_excluded():
    # No commence_time and close_time is far in the future (a pregame contract) ->
    # outside the live window -> NOT in-play.
    t = _tick(venue="kalshi", commence_time=None,
              close_time=_iso(NOW + timedelta(days=3)))
    assert inplay_feed.default_is_live_native(t, NOW) is False


def test_native_live_no_timestamps_unknown_excluded():
    # No commence and no close -> liveness unknown -> never captured.
    t = _tick(commence_time=None, close_time=None)
    assert inplay_feed.default_is_live_native(t, NOW) is False


def test_poll_default_gate_excludes_pregame_includes_live(tmp_path):
    # End-to-end with the DEFAULT (venue-native) gate -- NO is_live_fn injected.
    # One pregame market (future commence) and one live market (started). Only the
    # live one is captured; the pregame one must NOT leak through.
    src = _iso(NOW - timedelta(seconds=10))
    raw = [
        {"sport": "mlb", "game_id": "PRE", "venue": "polymarket", "side": "home",
         "ticker": "PRE", "prob": 0.50, "status": "open", "tradeable": True,
         "source_ts": src,
         "commence_time": _iso(NOW + timedelta(hours=3)), "close_time": None},
        {"sport": "mlb", "game_id": "LIVE", "venue": "polymarket", "side": "home",
         "ticker": "LIVE", "prob": 0.61, "status": "open", "tradeable": True,
         "source_ts": src,
         "commence_time": _iso(NOW - timedelta(minutes=20)), "close_time": None},
    ]
    rep = daemon.poll_inplay_once("mlb", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: raw)
    assert rep["status"] == "ok"
    assert rep["n_games_live"] == 1
    assert rep["n_ticks"] == 1
    rows = _read_jsonl(rep["out_path"])
    assert [r["game_id"] for r in rows] == ["LIVE"]  # pregame did NOT leak


def test_poll_default_gate_excludes_settled(tmp_path):
    raw = [
        {"sport": "mlb", "game_id": "DONE", "venue": "polymarket", "side": "home",
         "ticker": "DONE", "prob": 0.99, "status": "open", "tradeable": True,
         "source_ts": _iso(NOW - timedelta(seconds=10)),
         "commence_time": _iso(NOW - timedelta(hours=4)),
         "close_time": _iso(NOW - timedelta(minutes=5))},
    ]
    rep = daemon.poll_inplay_once("mlb", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: raw)
    assert rep["status"] == "ok"
    assert rep["n_ticks"] == 0
    assert rep["out_path"] is None


# --------------------------------------------------------------------------- #
# 2a STALE-NEVER-GREEN: a frozen/cached feed body carries an OLD source_ts ->
# its tick is DROPPED (never re-stamped fresh) and the sidecar reads RED.
# --------------------------------------------------------------------------- #


def _frozen_tick(source_ts, **over):
    base = {"sport": "nba", "game_id": "G1", "venue": "kalshi", "side": "home",
            "market_type": "moneyline", "ticker": "KX-1", "prob": 0.5455,
            "status": "in", "tradeable": True, "source_ts": source_ts}
    base.update(over)
    return base


def test_frozen_feed_tick_dropped_and_sidecar_reads_red(tmp_path):
    from scripts.platformkit.odds_provider import freshness
    # A body fetched 10 min ago, re-served on this poll (TTL/cache hit or a dead
    # feed). source_ts is OLD; the poll wall-clock is NOW. The tick must be DROPPED
    # (not re-stamped fresh), nothing persisted, and the sidecar read stale/RED.
    old = _iso(NOW - timedelta(minutes=10))
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [_frozen_tick(old)])
    assert rep["status"] == "ok"
    assert rep["n_ticks"] == 0          # frozen tick dropped, never re-stamped fresh
    assert rep["out_path"] is None
    side = json.loads((tmp_path / "nba" / "_freshness.json").read_text())
    assert side["last_source_ts"] is None       # no fresh source time advanced
    st = freshness.sidecar_status(tmp_path / "nba", now=NOW)
    assert st["ok"] is False and st["status"] == "stale"   # RED, not green


def test_fresh_source_ts_kept_and_carried_and_sidecar_green(tmp_path):
    from scripts.platformkit.odds_provider import freshness
    fresh = _iso(NOW - timedelta(seconds=20))   # within SOURCE_MAX_AGE_SEC
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [_frozen_tick(fresh)])
    assert rep["n_ticks"] == 1
    rows = _read_jsonl(rep["out_path"])
    # The persisted tick carries BOTH the poll ts AND the TRUE source_ts (distinct).
    assert rows[0]["ts"] == _iso(NOW)
    assert rows[0]["source_ts"] == fresh
    side = json.loads((tmp_path / "nba" / "_freshness.json").read_text())
    assert side["last_source_ts"] == fresh
    st = freshness.sidecar_status(tmp_path / "nba", now=NOW)
    assert st["ok"] is True and st["status"] == "fresh"   # GREEN on a live feed


# --------------------------------------------------------------------------- #
# 4b LIQUIDITY-GATE: an ungated/depthless ESPN/PM line (tradeable absent/False)
# is NOT persisted as an in-play price; a liquid (tradeable=True) tick IS.
# --------------------------------------------------------------------------- #


def test_ungated_espn_line_not_graded_as_inplay(tmp_path):
    # The exact audit case: a frozen ESPN:DraftKings 0.5455 on a 7-1 blowout, with
    # NO depth proof -> tradeable False -> NOT persisted as a tradeable in-play price.
    ungated = {"sport": "nba", "game_id": "BLOWOUT", "venue": "espn:DraftKings",
               "market_type": "moneyline", "side": "home", "ticker": "401",
               "prob": 0.5455, "status": "in", "tradeable": False}
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [ungated])
    assert rep["status"] == "ok"
    assert rep["n_ticks"] == 0          # ungated/depthless -> DEGRADED, not in-play
    assert rep["out_path"] is None


def test_missing_tradeable_flag_defaults_degraded(tmp_path):
    # A raw line with NO tradeable field is treated as DEGRADED (not proven liquid).
    raw = {"sport": "nba", "game_id": "G1", "venue": "espn:DraftKings",
           "market_type": "moneyline", "side": "home", "ticker": "401",
           "prob": 0.61, "status": "in"}
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [raw])
    assert rep["n_ticks"] == 0


def test_liquid_tradeable_tick_is_emitted(tmp_path):
    # A liquidity-gated (tradeable=True) live tick IS persisted as an in-play price.
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: _ticks(),
                                  is_live_fn=lambda gid, **kw: True)
    assert rep["n_ticks"] == 2
    rows = _read_jsonl(rep["out_path"])
    assert {r["venue"] for r in rows} == {"kalshi", "polymarket"}


# --------------------------------------------------------------------------- #
# L1 2a: a TRADEABLE in-play tick MUST carry a present source_ts (the frozen-
# feed guard is unavoidable). tradeable + None source_ts -> DROPPED; fresh ->
# kept; stale -> dropped (RED). tradeable=False corroborators are unaffected.
# --------------------------------------------------------------------------- #


def test_tradeable_tick_missing_source_ts_is_dropped(tmp_path):
    # The latent escape hatch: a tradeable in-play tick with NO source_ts could be
    # admitted/persisted/graded WITHOUT any frozen-feed check. It must be DROPPED.
    no_src = {"sport": "nba", "game_id": "G1", "venue": "kalshi",
              "market_type": "moneyline", "side": "home", "ticker": "KX-1",
              "prob": 0.62, "status": "in", "tradeable": True}  # no source_ts
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [no_src],
                                  is_live_fn=lambda gid, **kw: True)
    assert rep["status"] == "ok"
    assert rep["n_ticks"] == 0           # tradeable but unverifiable freshness -> dropped
    assert rep["out_path"] is None


def test_tradeable_tick_fresh_source_ts_is_kept(tmp_path):
    fresh = _iso(NOW - timedelta(seconds=10))
    tick = {"sport": "nba", "game_id": "G1", "venue": "kalshi",
            "market_type": "moneyline", "side": "home", "ticker": "KX-1",
            "prob": 0.62, "status": "in", "tradeable": True, "source_ts": fresh}
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [tick],
                                  is_live_fn=lambda gid, **kw: True)
    assert rep["n_ticks"] == 1
    rows = _read_jsonl(rep["out_path"])
    assert rows[0]["source_ts"] == fresh


def test_tradeable_tick_stale_source_ts_is_dropped(tmp_path):
    from scripts.platformkit.odds_provider import freshness
    stale = _iso(NOW - timedelta(minutes=10))   # beyond SOURCE_MAX_AGE_SEC
    tick = {"sport": "nba", "game_id": "G1", "venue": "kalshi",
            "market_type": "moneyline", "side": "home", "ticker": "KX-1",
            "prob": 0.62, "status": "in", "tradeable": True, "source_ts": stale}
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [tick],
                                  is_live_fn=lambda gid, **kw: True)
    assert rep["n_ticks"] == 0          # frozen-feed re-serve -> dropped, RED
    assert rep["out_path"] is None
    st = freshness.sidecar_status(tmp_path / "nba", now=NOW)
    assert st["ok"] is False


def test_nontradeable_corroborator_unaffected_by_source_ts_rule(tmp_path):
    # A tradeable=False corroborator (never persisted/graded) is dropped by the 4b
    # liquidity gate regardless of source_ts -- the new 2a require-source_ts rule does
    # NOT change its handling (it was never an in-play observation to begin with).
    corr = {"sport": "nba", "game_id": "G1", "venue": "espn:DraftKings",
            "market_type": "moneyline", "side": "home", "ticker": "401",
            "prob": 0.55, "status": "in", "tradeable": False}  # no source_ts, degraded
    rep = daemon.poll_inplay_once("nba", now=NOW, out_dir=tmp_path,
                                  fetch_fn=lambda s: [corr],
                                  is_live_fn=lambda gid, **kw: True)
    assert rep["status"] == "ok"
    assert rep["n_ticks"] == 0           # 4b: degraded corroborator, not in-play
    assert rep["out_path"] is None
