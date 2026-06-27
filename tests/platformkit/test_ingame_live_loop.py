"""Per-file tests for the in-game LIVE LOOP (Milestone-6 spine).

Covers, with a FAKE clock + canned ESPN payload + a stubbed store prior (NO
network, NO corpus, NO real sleep):
  * N ticks produce live snapshots on disk for a game that HAS a pregame prior;
  * a live game with NO prior is SKIPPED cleanly (no snapshot, no fabricated
    number) while a sibling game with a prior is still written;
  * the written snapshot's win-prob VARIANCE SHRINKS as the fake clock advances
    the game (Q1 wide -> Q4 tight) -- the validated freshness invariant;
  * serve_forever uses the INJECTED clock and never calls real time.sleep.

Run (per-file ONLY -- a full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest tests/platformkit/test_ingame_live_loop.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from predict_service import store as ps_store
from predict_service.contracts import (
    PredictionRecord,
    SnapshotEnvelope,
)
from scripts.platformkit.ingame import live_loop
from scripts.platformkit.ingame import snapshot as igsnap
from scripts.platformkit.ingame.state_bus import StateBus


# ---- canned ESPN payload builders -------------------------------------------

def _competitor(home_away: str, abbr: str, score: int) -> Dict[str, Any]:
    return {"homeAway": home_away,
            "team": {"abbreviation": abbr, "displayName": abbr},
            "score": str(score)}


def _event(game_id: str, period: int, clock: str,
           home_score: int, away_score: int, state: str = "in") -> Dict[str, Any]:
    return {
        "id": game_id,
        "status": {"displayClock": clock, "period": period,
                   "type": {"state": state, "shortDetail": "Q%d %s" % (period, clock)}},
        "competitions": [{"competitors": [
            _competitor("home", "BOS", home_score),
            _competitor("away", "LAL", away_score),
        ]}],
    }


def _payload(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"events": events}


def _seed_prior(store_dir, game_id: str, p_home: float) -> None:
    """Write a pregame prior for *game_id* into a temp predict_service store."""
    env = SnapshotEnvelope(
        sport="nba", generated_at="2026-06-18T00:00:00+00:00", status="ok",
        predictions=[PredictionRecord(
            sport="nba", game_id=game_id, home="BOS", away="LAL",
            pregame_probs={"home_ml": p_home, "away_ml": 1.0 - p_home})],
    )
    ps_store.save(env, out_dir=store_dir, append=False)


# ---- tests ------------------------------------------------------------------

def test_n_ticks_write_live_snapshots(tmp_path):
    """A game with a prior -> a live snapshot on disk after a tick (fake fetch)."""
    snap_dir = tmp_path / "snap"
    store_dir = tmp_path / "store"
    _seed_prior(store_dir, "401", p_home=0.55)

    def fetch(_sport: str) -> Dict[str, Any]:
        return _payload([_event("401", period=2, clock="6:00",
                                home_score=40, away_score=36)])

    bus = StateBus()
    hb = live_loop.poll_once(fetch=fetch, sports=["nba"], bus=bus,
                             out_dir=snap_dir, store_out_dir=store_dir)
    assert hb["n_live"] == 1
    assert hb["n_written"] == 1 and hb["n_skipped"] == 0

    snap = igsnap.read_live("401", sport="nba", out_dir=snap_dir)
    assert snap is not None
    market = snap["market_set"]
    assert market["status"] == "live"
    assert market["available"] is True
    assert market["edge_claimed"] is False
    assert market["variance"] is not None

    # Heartbeat written too.
    assert (snap_dir / "_heartbeat.json").exists()


def test_game_with_no_prior_is_skipped_cleanly(tmp_path):
    """One game has a prior (written), a sibling has none (skipped, no snapshot)."""
    snap_dir = tmp_path / "snap"
    store_dir = tmp_path / "store"
    _seed_prior(store_dir, "401", p_home=0.55)  # only 401 has a prior

    def fetch(_sport: str) -> Dict[str, Any]:
        return _payload([
            _event("401", period=2, clock="6:00", home_score=40, away_score=36),
            _event("402", period=1, clock="8:00", home_score=12, away_score=10),
        ])

    bus = StateBus()
    hb = live_loop.poll_once(fetch=fetch, sports=["nba"], bus=bus,
                             out_dir=snap_dir, store_out_dir=store_dir)
    assert hb["n_live"] == 2
    assert hb["n_written"] == 1 and hb["n_skipped"] == 1

    assert igsnap.read_live("401", sport="nba", out_dir=snap_dir) is not None
    assert igsnap.read_live("402", sport="nba", out_dir=snap_dir) is None

    reasons = {g["game_id"]: g.get("reason") for g in hb["games"] if not g["written"]}
    assert reasons.get("402") == "no_prior"


def test_variance_shrinks_as_clock_advances(tmp_path):
    """FRESHNESS: same lead, later game-state -> smaller written variance."""
    snap_dir = tmp_path / "snap"
    store_dir = tmp_path / "store"
    _seed_prior(store_dir, "401", p_home=0.50)

    # Q1 (lots of time) then Q4 (little time) at the SAME 8-point home lead.
    states = [
        _payload([_event("401", period=1, clock="6:00", home_score=28, away_score=20)]),
        _payload([_event("401", period=4, clock="1:00", home_score=98, away_score=90)]),
    ]
    sleeps: List[float] = []

    def fake_clock(sec: float) -> None:
        sleeps.append(sec)

    idx = {"i": 0}

    def fetch(_sport: str) -> Dict[str, Any]:
        p = states[min(idx["i"], len(states) - 1)]
        idx["i"] += 1
        return p

    bus = StateBus()
    live_loop.serve_forever(clock=fake_clock, max_ticks=2, fetch=fetch,
                            sports=["nba"], bus=bus, out_dir=snap_dir,
                            store_out_dir=store_dir)

    # Re-run each state once to capture the per-state variance written.
    bus2 = StateBus()
    hb_q1 = live_loop.poll_once(fetch=lambda _s: states[0], sports=["nba"], bus=bus2,
                                out_dir=snap_dir, store_out_dir=store_dir)
    var_q1 = igsnap.read_live("401", "nba", out_dir=snap_dir)["market_set"]["variance"]

    hb_q4 = live_loop.poll_once(fetch=lambda _s: states[1], sports=["nba"], bus=bus2,
                                out_dir=snap_dir, store_out_dir=store_dir)
    var_q4 = igsnap.read_live("401", "nba", out_dir=snap_dir)["market_set"]["variance"]

    assert hb_q1["n_written"] == 1 and hb_q4["n_written"] == 1
    assert var_q1 is not None and var_q4 is not None
    assert var_q1 > var_q4, (var_q1, var_q4)

    # serve_forever drove the FAKE clock, never real time.sleep.
    assert len(sleeps) >= 1


def test_feed_down_yields_clean_heartbeat(tmp_path):
    """A down feed -> zero live games, a clean heartbeat, never raises."""
    snap_dir = tmp_path / "snap"
    store_dir = tmp_path / "store"

    def fetch(_sport: str) -> Dict[str, Any]:
        return {}  # feed down

    hb = live_loop.poll_once(fetch=fetch, sports=["nba"], bus=StateBus(),
                             out_dir=snap_dir, store_out_dir=store_dir)
    assert hb["n_live"] == 0 and hb["n_written"] == 0
    assert hb["edge_claimed"] is False


# ---- FIX 2: pregame_carry is unmistakably marked ----------------------------

def test_pregame_carry_helper_marks_reprice_false():
    """_pregame_carry emits reprice=False/is_carry=True so a consumer reading ONLY
    the top-level flags (not _honest_note) knows it is the UNCHANGED pregame prior,
    not a fresh in-game reprice. The honest note is still carried."""
    carry = live_loop._pregame_carry("mlb", {"p0": 0.58}, reason="no clock")
    assert carry["available"] is True            # still a live, written game
    assert carry["reprice"] is False             # UNMISTAKABLE: not a reprice
    assert carry["is_carry"] is True             # UNMISTAKABLE: a carried prior
    assert carry["basis"] == "pregame_carry"
    assert carry["edge_claimed"] is False
    assert carry["variance"] is None             # no in-game conditioning claimed
    assert "pregame prior" in carry["_honest_note"].lower()  # note preserved
    # The carried win-prob is the UNCHANGED prior (p0), not a re-derived number.
    assert carry["probs"]["p_home"] == pytest.approx(0.58)


def test_pregame_carry_through_market_set_is_marked_and_still_live():
    """End-to-end: a carry reprice -> market_set carries the markers AND keeps
    status='live' so the webapp /live classifier (status=='live' -> LIVE) is not
    broken; the carry is distinguishable purely by reprice/is_carry."""
    from scripts.platformkit.ingame import market_set as ms

    carry = live_loop._pregame_carry("mlb", {"p0": 0.6}, reason="no clock")
    market = ms.build("G_MLB", "mlb", carry, as_of="2026-06-20T00:00:00+00:00")
    assert market["status"] == "live"            # consumers filtering on status are safe
    assert market["reprice"] is False            # but unmistakably a carry
    assert market["is_carry"] is True
    assert market["basis"] == "pregame_carry"
    assert market["edge_claimed"] is False
