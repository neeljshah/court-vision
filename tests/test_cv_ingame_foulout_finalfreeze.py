"""tests/test_cv_ingame_foulout_finalfreeze.py

Tests for the two deterministic end-state guards on the SERVED in-game path
(src/prediction/live_engine.project_from_snapshot):

  * BUG-1 CV_INGAME_FOULOUT_CAP — a player with pf >= 6 (fouled OUT, ejected)
    must have every counting-stat projected_final clamped to their current box
    value (no further accumulation).
  * BUG-5 CV_INGAME_FINAL_FREEZE — a FINAL / clock-0:00 game must project every
    row at current (game over, no extrapolation).

Both gated default-OFF. Coverage:
  1. OFF byte-identical: both flags unset -> identical to baseline.
  2. FOULOUT cap freezes a pf>=6 player's projection to current.
  3. FOULOUT leaves a normal (pf<6) mid-game player UNCHANGED vs flag OFF.
  4. FINAL freeze clamps every row to current on a FINAL snapshot.
  5. FINAL freeze leaves a live (non-final) snapshot UNCHANGED vs flag OFF.
  6. A tie at 0:00 in Q4 is NOT frozen (game goes to OT).
  7. pf=5 (not fouled out) is NOT capped; pf=6 IS.
  8. Missing pf on a player -> that player is left unchanged (no fabrication).

The guards act on whatever projected_final the upstream heads produce, so the
tests run WITHOUT CV_INGAME_SBS (base cycle-88 path) — that is sufficient to
prove the guard fires on the served projected_final; under SBS the same guard
runs on the routed value because it is applied last.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Ensure both flags are OFF before importing the engine.
os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
os.environ.pop("CV_INGAME_SBS", None)


# Flags whose leaked state from a SIBLING test file could perturb this file's
# OFF baseline (the agent's "large combined run" failure = a cross-file env leak).
_ISOLATED_INGAME_FLAGS = (
    "CV_INGAME_FOULOUT_CAP", "CV_INGAME_FINAL_FREEZE", "CV_INGAME_SBS",
    "CV_SHRINK_CALIBRATED", "CV_INGAME_ROTMINUTES", "CV_INGAME_MARGIN_HAIRCUT",
    "CV_INGAME_LATEQ4_V2", "CV_INGAME_OT_FIX", "CV_INGAME_SIGMA",
)


@pytest.fixture(autouse=True)
def _isolate_ingame_flags():
    """Snapshot + clear the in-game flags before each test, restore after.

    Makes this file hermetic: a sibling test that leaks e.g. CV_INGAME_SBS=1 can
    no longer perturb the OFF baseline these guards compare against. Each test
    starts from a known-clean flag state and the prior process env is restored.
    """
    saved = {k: os.environ.get(k) for k in _ISOLATED_INGAME_FLAGS}
    for k in _ISOLATED_INGAME_FLAGS:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _engine():
    """Import (fresh) the live engine. The guards read os.environ per-call, so a
    reload is not strictly required, but we import lazily so flag state set in a
    test is honoured."""
    import src.prediction.live_engine as le
    importlib.reload(le)
    return le


def _player(pid, team, *, pts, reb, ast, fg3m, stl, blk, tov, pf, mins):
    return {
        "player_id": pid,
        "name": f"P{pid}",
        "team": team,
        "min": float(mins),
        "pts": float(pts), "reb": float(reb), "ast": float(ast),
        "fg3m": float(fg3m), "stl": float(stl), "blk": float(blk),
        "tov": float(tov), "pf": pf,
    }


def _snap(period="3", clock="6:00", game_status="LIVE",
          home_score=60.0, away_score=55.0, players=None):
    return {
        "game_id": "0042500401",
        "game_status": game_status,
        "period": int(period),
        "clock": clock,
        "home_team": "BOS",
        "away_team": "NYK",
        "home_score": home_score,
        "away_score": away_score,
        "players": players or [],
    }


def _midgame_players():
    # Star with 24 played min / 18 pts, mid-Q3, room to score more.
    star = _player(1001, "BOS", pts=18, reb=6, ast=4, fg3m=2, stl=1, blk=0,
                   tov=2, pf=2.0, mins=24.0)
    other = _player(1002, "NYK", pts=12, reb=4, ast=2, fg3m=1, stl=0, blk=1,
                    tov=1, pf=1.0, mins=22.0)
    return [star, other]


def _vals(rows):
    return {(r["player_id"], r["stat"]): r["projected_final"] for r in rows}


# ── 1. OFF byte-identical ─────────────────────────────────────────────────────

class TestOffByteIdentical:
    def test_both_flags_off_identical_to_baseline_foulout_player(self):
        """A pf>=6 player: flags OFF must be byte-identical to no-guard baseline."""
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        le = _engine()
        players = _midgame_players()
        players[0]["pf"] = 6.0  # fouled out — but flags are OFF
        base = _vals(le.project_from_snapshot(_snap(players=players)))

        # Toggle flags ON then back OFF; OFF result must equal the first OFF run.
        os.environ["CV_INGAME_FOULOUT_CAP"] = "1"
        os.environ["CV_INGAME_FINAL_FREEZE"] = "1"
        _ = le.project_from_snapshot(_snap(players=_midgame_players()))
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        players2 = _midgame_players()
        players2[0]["pf"] = 6.0
        again = _vals(le.project_from_snapshot(_snap(players=players2)))

        assert set(base) == set(again)
        for k in base:
            assert abs(base[k] - again[k]) < 1e-9, f"OFF not byte-identical at {k}"

    def test_both_flags_off_identical_on_final_snapshot(self):
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        le = _engine()
        snap = _snap(period="4", clock="0:00", game_status="FINAL",
                     players=_midgame_players())
        a = _vals(le.project_from_snapshot(snap))
        b = _vals(le.project_from_snapshot(_snap(
            period="4", clock="0:00", game_status="FINAL",
            players=_midgame_players())))
        for k in a:
            assert abs(a[k] - b[k]) < 1e-9


# ── 2/3/7/8. FOUL-OUT cap ─────────────────────────────────────────────────────

class TestFoulOutCap:
    def test_foulout_player_frozen_to_current(self):
        """pf>=6: every counting stat projected_final == current box value."""
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        os.environ["CV_INGAME_FOULOUT_CAP"] = "1"
        le = _engine()
        players = _midgame_players()
        players[0]["pf"] = 6.0
        rows = le.project_from_snapshot(_snap(players=players))
        for r in rows:
            if r["player_id"] == 1001:
                assert abs(r["projected_final"] - r["current"]) < 1e-9, (
                    f"foulout {r['stat']} not capped: "
                    f"{r['projected_final']} vs cur {r['current']}"
                )
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)

    def test_normal_player_unchanged_when_cap_on(self):
        """A non-fouled-out player (pf<6) must be unchanged vs flag OFF."""
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        le = _engine()
        off = _vals(le.project_from_snapshot(_snap(players=_midgame_players())))

        os.environ["CV_INGAME_FOULOUT_CAP"] = "1"
        on = _vals(le.project_from_snapshot(_snap(players=_midgame_players())))
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)

        # Neither player has pf>=6 -> on must equal off everywhere.
        for k in off:
            assert abs(off[k] - on[k]) < 1e-9, f"normal player changed at {k}"

    def test_pf5_not_capped_pf6_capped(self):
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        os.environ["CV_INGAME_FOULOUT_CAP"] = "1"
        le = _engine()
        # pf=5 -> NOT fouled out (projection may exceed current).
        p5 = _midgame_players()
        p5[0]["pf"] = 5.0
        rows5 = le.project_from_snapshot(_snap(players=p5))
        pts5 = next(r for r in rows5 if r["player_id"] == 1001 and r["stat"] == "pts")
        assert pts5["projected_final"] >= pts5["current"] - 1e-9
        # the star has room — projection should exceed current at pf=5
        assert pts5["projected_final"] > pts5["current"] + 1e-6

        # pf=6 -> capped to current.
        p6 = _midgame_players()
        p6[0]["pf"] = 6.0
        rows6 = le.project_from_snapshot(_snap(players=p6))
        pts6 = next(r for r in rows6 if r["player_id"] == 1001 and r["stat"] == "pts")
        assert abs(pts6["projected_final"] - pts6["current"]) < 1e-9
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)

    def test_missing_pf_left_unchanged(self):
        """A player with no pf field is not fabricated as fouled out."""
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        le = _engine()
        players = _midgame_players()
        del players[0]["pf"]  # no pf for the star
        off = _vals(le.project_from_snapshot(_snap(players=players)))

        os.environ["CV_INGAME_FOULOUT_CAP"] = "1"
        players2 = _midgame_players()
        del players2[0]["pf"]
        on = _vals(le.project_from_snapshot(_snap(players=players2)))
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        for k in off:
            assert abs(off[k] - on[k]) < 1e-9, f"missing-pf player changed at {k}"


# ── 4/5/6. FINAL freeze ───────────────────────────────────────────────────────

class TestFinalFreeze:
    def test_final_snapshot_freezes_every_row(self):
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        os.environ["CV_INGAME_FINAL_FREEZE"] = "1"
        le = _engine()
        snap = _snap(period="4", clock="0:00", game_status="FINAL",
                     players=_midgame_players())
        rows = le.project_from_snapshot(snap)
        for r in rows:
            assert abs(r["projected_final"] - r["current"]) < 1e-9, (
                f"FINAL row {r['player_id']}/{r['stat']} not frozen: "
                f"{r['projected_final']} vs cur {r['current']}"
            )
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)

    def test_live_snapshot_unchanged_when_freeze_on(self):
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        le = _engine()
        off = _vals(le.project_from_snapshot(_snap(players=_midgame_players())))

        os.environ["CV_INGAME_FINAL_FREEZE"] = "1"
        on = _vals(le.project_from_snapshot(_snap(players=_midgame_players())))
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        for k in off:
            assert abs(off[k] - on[k]) < 1e-9, f"live snapshot changed at {k}"

    def test_clock_zero_final_via_clock_not_status(self):
        """clock 0:00 in Q4, not tied, game_status still LIVE -> still frozen."""
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        os.environ["CV_INGAME_FINAL_FREEZE"] = "1"
        le = _engine()
        snap = _snap(period="4", clock="0:00", game_status="LIVE",
                     home_score=110.0, away_score=104.0,
                     players=_midgame_players())
        rows = le.project_from_snapshot(snap)
        for r in rows:
            assert abs(r["projected_final"] - r["current"]) < 1e-9
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)

    def test_tie_at_zero_q4_not_frozen(self):
        """A tie at 0:00 Q4 -> OT possible -> NOT final -> not frozen."""
        os.environ.pop("CV_INGAME_FOULOUT_CAP", None)
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        le = _engine()
        tied = dict(home_score=100.0, away_score=100.0)
        off = _vals(le.project_from_snapshot(_snap(
            period="4", clock="0:00", game_status="LIVE",
            players=_midgame_players(), **tied)))

        os.environ["CV_INGAME_FINAL_FREEZE"] = "1"
        on = _vals(le.project_from_snapshot(_snap(
            period="4", clock="0:00", game_status="LIVE",
            players=_midgame_players(), **tied)))
        os.environ.pop("CV_INGAME_FINAL_FREEZE", None)
        # Tie -> not frozen -> identical to OFF (no freeze applied).
        for k in off:
            assert abs(off[k] - on[k]) < 1e-9, f"tie-game wrongly frozen at {k}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
