"""tests/test_g4_ingame.py — unit tests for the G4 live in-game driver's pure logic
(the replay-validated foul-out lever, OT-aware clock/elapsed, and live-snapshot -> state parsing).
The sim-dependent end-to-end path is validated manually; these lock the deterministic math."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "team_system"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import g4_ingame as G  # noqa: E402


def test_foulout_mult_no_risk_is_identity():
    assert G.foulout_mult(2, 20, 0.25, 0.75) == 1.0     # pf2: no risk
    assert G.foulout_mult(4, 27, 0.25, 0.75) == 1.0     # pf4 in 27 min: low foul rate, not a real risk
    assert G.foulout_mult(0, 30, 0.25, 0.75) == 1.0     # no fouls


def test_foulout_mult_fires_on_real_risk():
    m = G.foulout_mult(5, 22, 0.25, 0.75)               # pf5 late: real foul-out risk
    assert 0.45 <= m < 1.0
    assert G.foulout_mult(5, 14, 0.25, 0.75) >= 0.45    # never below the 0.45 floor (don't zero a star prematurely)


def test_foulout_mult_fouled_out_is_zero():
    assert G.foulout_mult(6, 30, 0.25, 0.75) == 0.0
    assert G.foulout_mult(7, 30, 0.25, 0.75) == 0.0


def test_foulout_mult_early_game_no_haircut():
    assert G.foulout_mult(2, 2, 0.25, 0.75) == 1.0      # < 3 min played -> too noisy, identity
    assert G.foulout_mult(3, 10, 1.0, 0.0) == 1.0       # frac_el ~ 0 (pre-tip) -> identity


def test_elapsed_min_regulation_and_ot():
    assert abs(G._elapsed_min(1, 12 * 60) - 0.0) < 1e-9     # tip-off
    assert abs(G._elapsed_min(2, 6 * 60) - 18.0) < 1e-9     # mid Q2
    assert abs(G._elapsed_min(4, 0.0) - 48.0) < 1e-9        # end of regulation
    assert abs(G._elapsed_min(5, 5 * 60) - 48.0) < 1e-9     # start of OT1
    assert abs(G._elapsed_min(5, 0.0) - 53.0) < 1e-9        # end of OT1


def test_parse_clock_forms():
    assert G.MI_parse_clock("6:58") == 6 * 60 + 58
    assert G.MI_parse_clock("0:00") == 0.0
    assert G.MI_parse_clock(123.0) == 123.0


def test_parse_clock_iso8601_pt_duration():
    # the raw cdn.nba.com liveData clock format -- must NOT silently return 0.0
    assert abs(G.MI_parse_clock("PT08M10.00S") - 490.0) < 1e-6
    assert abs(G.MI_parse_clock("PT11M00.00S") - 660.0) < 1e-6
    assert abs(G.MI_parse_clock("PT00M04.50S") - 4.5) < 1e-6


def test_parse_state_overtime_is_not_frozen():
    # REGRESSION: OT used to clamp frac_rem to 0 (frozen score, 0/100 WP). It must give real remaining time.
    snap = {"period": 5, "clock": "3:00", "home_score": 118, "away_score": 118,
            "home_team": "NYK", "away_team": "SAS", "players": []}
    st = G.parse_state(snap)
    assert abs(st["elapsed"] - 50.0) < 1e-9          # 48 + (5-3) into OT1
    assert st["frac_rem"] > 0.0                       # NOT frozen
    assert abs(st["frac_rem"] - (3.0 / 48.0)) < 1e-9  # remaining OT clock / 48
    # 2OT also works
    st2 = G.parse_state({**snap, "period": 6, "clock": "2:00"})
    assert st2["frac_rem"] > 0.0


def test_parse_state_shape_and_fractions():
    snap = {
        "period": 3, "clock": "6:00", "home_score": 73, "away_score": 72,
        "home_team": "NYK", "away_team": "SAS", "game_status": "LIVE",
        "players": [
            {"name": "A", "team": "NYK", "pts": 20, "reb": 4, "ast": 1, "fg3m": 2, "stl": 0, "blk": 1, "min": 25.0, "pf": 2},
            {"name": "B", "team": "SAS", "pts": 17, "reb": 5, "ast": 4, "fg3m": 0, "stl": 1, "blk": 2, "min": 24.0, "pf": 5},
        ],
    }
    st = G.parse_state(snap)
    assert st["period"] == 3 and st["home_score"] == 73 and st["away_score"] == 72
    assert abs(st["elapsed"] - 30.0) < 1e-9              # Q3 6:00 -> 30 min elapsed
    assert abs(st["frac_rem"] - 0.375) < 1e-9           # 18/48
    assert abs(st["frac_el"] - 0.625) < 1e-9
    assert st["players"]["B"]["pf"] == 5 and st["players"]["A"]["pts"] == 20
