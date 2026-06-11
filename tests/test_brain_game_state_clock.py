"""P3.1 — GameState.from_snapshot real clock parsing (fills the placeholder clock TODO).

Proves: (1) MM:SS / ISO-8601 / numeric / bare-string clocks all parse; (2) elapsed/remaining/frac are
computed with the SAME reg-720s / OT-300s arithmetic as game_state_events._elapsed; (3) a clock-less
snapshot falls back to tip-off defaults EXACTLY (the regression guard that keeps the 176 existing tests
+ the leak gate byte-identical); (4) explicit game_elapsed_sec/game_remaining_sec round-trip.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ingame.game_state import (  # noqa: E402
    GameState, _parse_clock_remaining_sec, _clock_fields, REG_GAME_LEN_SEC,
)


# --------------------------------------------------------------------------- parse

def test_parse_mmss():
    assert _parse_clock_remaining_sec("12:00") == 720.0
    assert _parse_clock_remaining_sec("06:00") == 360.0
    assert _parse_clock_remaining_sec("0:24") == 24.0
    assert abs(_parse_clock_remaining_sec("07:24") - 444.0) < 1e-9


def test_parse_iso8601():
    assert abs(_parse_clock_remaining_sec("PT07M24.00S") - 444.0) < 1e-9
    assert _parse_clock_remaining_sec("PT12M00.00S") == 720.0
    assert abs(_parse_clock_remaining_sec("PT00M30.0S") - 30.0) < 1e-9


def test_parse_numeric_and_bad():
    assert _parse_clock_remaining_sec(360) == 360.0
    assert _parse_clock_remaining_sec(360.5) == 360.5
    assert _parse_clock_remaining_sec("360") == 360.0
    assert _parse_clock_remaining_sec(None) is None
    assert _parse_clock_remaining_sec("") is None
    assert _parse_clock_remaining_sec("garbage") is None


# --------------------------------------------------------------------------- fields

def test_clock_fields_regulation():
    # Q4, 6:00 left -> 36 min elapsed +6 of Q4 = 42 min elapsed -> 6 min remaining -> frac 0.125
    cs, el, rem, frac = _clock_fields({"clock": "06:00"}, period=4)
    assert cs == 360
    assert el == (3 * 720.0 + (720.0 - 360.0))      # 2520
    assert rem == REG_GAME_LEN_SEC - 2520           # 360
    assert abs(frac - (360.0 / 2880.0)) < 1e-9


def test_clock_fields_tipoff():
    cs, el, rem, frac = _clock_fields({"clock": "12:00"}, period=1)
    assert (cs, el, rem, frac) == (720, 0.0, float(REG_GAME_LEN_SEC), 1.0)


def test_clock_fields_overtime_clamps_remaining_to_zero():
    # OT (period 5): regulation is over -> game_remaining_sec floors at 0
    cs, el, rem, frac = _clock_fields({"clock": "02:30"}, period=5)
    assert el == 2880.0 + (300.0 - 150.0)           # 3030
    assert rem == 0.0 and frac == 0.0


def test_clock_fields_missing_is_tipoff_default():
    # NO clock field -> EXACT pre-P3.1 defaults (the regression guard).
    assert _clock_fields({}, period=1) == (0, 0.0, float(REG_GAME_LEN_SEC), 1.0)
    assert _clock_fields({"period": 3}, period=3) == (0, 0.0, float(REG_GAME_LEN_SEC), 1.0)


def test_clock_fields_explicit_elapsed_roundtrip():
    cs, el, rem, frac = _clock_fields({"game_elapsed_sec": 600.0, "game_remaining_sec": 2280.0}, period=2)
    assert el == 600.0 and rem == 2280.0
    assert abs(frac - (2280.0 / 2880.0)) < 1e-9


# --------------------------------------------------------------------------- from_snapshot

def _snap(period, clock=None):
    s = {"game_id": "0022500001", "home_team": "NYK", "away_team": "SAS",
         "period": period, "home_score": 50, "away_score": 48,
         "players": [{"player_id": 1, "team": "home", "on_court": True, "min_so_far": 30.0, "pf": 2,
                      "pts": 12.0, "reb": 4.0, "ast": 3.0, "fg3m": 1.0, "stl": 1.0, "blk": 0.0, "tov": 1.0}]}
    if clock is not None:
        s["clock"] = clock
    return s


def test_from_snapshot_uses_real_clock():
    gs = GameState.from_snapshot(_snap(4, "06:00"))
    assert gs.period == 4
    assert gs.game_elapsed_sec == 2520.0
    assert gs.game_remaining_sec == 360.0
    assert abs(gs.remaining_frac - 0.125) < 1e-9
    assert gs.clock_s == 360


def test_from_snapshot_no_clock_preserves_tipoff_default():
    # The exact pre-P3.1 behaviour for a clock-less snapshot (keeps existing tests byte-identical).
    gs = GameState.from_snapshot(_snap(1, clock=None))
    assert gs.game_elapsed_sec == 0.0
    assert gs.game_remaining_sec == float(REG_GAME_LEN_SEC)
    assert gs.remaining_frac == 1.0
