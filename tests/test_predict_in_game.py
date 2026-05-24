"""tests/test_predict_in_game.py — cycle 88b (loop 5).

Pure-function tests for the in-game projector. All tests are offline (no
nba_api, no model load, no disk I/O beyond the snapshot-parsing test which
writes to tmp_path).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import predict_in_game as pig   # noqa: E402


# ── 1. pace-based projector arithmetic ────────────────────────────────────────

def test_halftime_projection_doubles_current():
    """A player with 12 PTS at halftime (Q2 ended, clock=0) projects to 24 final.

    Halftime = 24 game-min elapsed of 48 → played_share = 0.5,
    remaining_share = 0.5. project_remaining = 12 * (0.5/0.5) = 12 → final=24.
    """
    # End of Q2: period=2 reporting the period that JUST ended with clock 0
    # is equivalent to start of Q3 (period=3, clock=12:00).
    final = pig.project_final(
        current_stat=12.0, period=2, clock_remaining_min=0.0,
    )
    assert final == pytest.approx(24.0, abs=1e-6)
    # Equivalent halftime representation (start of Q3):
    final_alt = pig.project_final(
        current_stat=12.0, period=3, clock_remaining_min=12.0,
    )
    assert final_alt == pytest.approx(24.0, abs=1e-6)


def test_quarter_remaining_scales_proportionally():
    """A player with 20 PTS at end-of-Q3 (3/4 played) projects to 20 + 20/3."""
    final = pig.project_final(
        current_stat=20.0, period=3, clock_remaining_min=0.0,
    )
    # share_played = 36/48 = 0.75; remaining = 0.25; rem = 20 * (0.25/0.75) = 6.667
    assert final == pytest.approx(20.0 + 20.0 / 3.0, abs=1e-4)


# ── 2. foul-trouble penalty fires correctly ──────────────────────────────────

def test_foul_trouble_penalty_q3_4fouls():
    """4 PF in Q3 -> 0.55 multiplier on remaining projection.

    Cycle 89b (loop 5): canonical table unified into ``src.prediction.live_factors``;
    the old 0.70 value (one of three disagreeing copies) is gone. We now use the
    most conservative table — Q3 pf=4 -> 0.55 — and pf=5 anywhere -> 0.40.
    """
    base = pig.project_final(
        current_stat=20.0, period=3, clock_remaining_min=6.0,
    )
    penalized = pig.project_final(
        current_stat=20.0, period=3, clock_remaining_min=6.0,
        foul_factor=pig.foul_trouble_factor(4, 3, 6.0),
    )
    assert pig.foul_trouble_factor(4, 3, 6.0) == pytest.approx(0.55)
    # base = 20 + 20 * (((48-30)/48) / (30/48)) = 20 + 20 * (18/30) = 32
    # penalized remaining = 12 * 0.55 = 6.6 -> final = 26.6
    assert base == pytest.approx(32.0, abs=1e-4)
    assert penalized == pytest.approx(26.6, abs=1e-4)
    # Q4 5+ fouls is the strictest band (foul-out risk): 0.40 under unified table.
    assert pig.foul_trouble_factor(5, 4, 2.0) == pytest.approx(0.40)
    # Q1 with 0-2 fouls: no penalty
    assert pig.foul_trouble_factor(2, 1, 10.0) == 1.0


# ── 3. blowout penalty applies to stars in Q4 ────────────────────────────────

def test_blowout_penalty_q4_star():
    """Margin > 20 in Q4 reduces star projection; non-star unaffected."""
    # Star: applied
    f_star = pig.blowout_factor(score_margin=25, period=4, is_star=True)
    assert f_star < 1.0
    assert f_star == pytest.approx(0.45)
    # Non-star: not applied
    f_role = pig.blowout_factor(score_margin=25, period=4, is_star=False)
    assert f_role == 1.0
    # Q3 even huge margin: not applied (game not decided yet for projection)
    f_q3 = pig.blowout_factor(score_margin=30, period=3, is_star=True)
    assert f_q3 == 1.0
    # Margin <= 20: no penalty even in Q4
    f_close = pig.blowout_factor(score_margin=18, period=4, is_star=True)
    assert f_close == 1.0


# ── 4. bench player projects from prior-quarter rate, not game clock ─────────

def test_bench_player_projects_from_player_clock():
    """Player who played 16 min in Q1+Q2, sat all Q3, projects from rate.

    cur_min=16, current_stat=10 PTS at end of Q3 → bench in Q3 (min_q3=0).
    With player_clock_played_min basis: share_played = 16/48 = 1/3,
    remaining = 2/3, rem = 10 * (2/3 / 1/3) = 20 → final = 30.

    Compare to game-clock basis at end of Q3 (3/4 played):
    rem = 10 * (0.25/0.75) = 3.33 → final = 13.33 (much smaller).

    Player-clock basis must produce the LARGER projection — bench player
    accumulated stats faster per minute than the game-clock heuristic.
    """
    final_player_basis = pig.project_final(
        current_stat=10.0, period=3, clock_remaining_min=0.0,
        player_clock_played_min=16.0,
    )
    final_game_basis = pig.project_final(
        current_stat=10.0, period=3, clock_remaining_min=0.0,
    )
    assert final_player_basis == pytest.approx(30.0, abs=1e-4)
    assert final_game_basis == pytest.approx(13.333, abs=1e-3)
    assert final_player_basis > final_game_basis

    # is_bench_in_current_period helper:
    p_bench = {"min": 16.0, "min_q1": 8.0, "min_q2": 8.0, "min_q3": 0.0}
    p_active = {"min": 24.0, "min_q1": 8.0, "min_q2": 8.0, "min_q3": 8.0}
    # default period_elapsed_min=12.0 (full quarter passed): bench=True
    assert pig.is_bench_in_current_period(p_bench, 3) is True
    assert pig.is_bench_in_current_period(p_active, 3) is False
    # Missing per-quarter fields → assume on-floor (returns False)
    assert pig.is_bench_in_current_period({"min": 20.0}, 3) is False
    # START-of-period guard: at the literal start of Q3 (no elapsed time)
    # every player has min_q3=0 — must NOT be flagged as bench. This was
    # the cycle-88b first-pass bug (Jokic at halftime projecting to 41 PTS).
    assert pig.is_bench_in_current_period(
        p_bench, 3, period_elapsed_min=0.0) is False
    assert pig.is_bench_in_current_period(
        p_bench, 3, period_elapsed_min=1.0) is False
    assert pig.is_bench_in_current_period(
        p_bench, 3, period_elapsed_min=3.0) is True


# ── 5. end-of-game projection equals current (no remaining time) ─────────────

def test_end_of_game_projection_equals_current():
    """At final buzzer (period=4, clock=0) projected_final == current_stat.

    No multiplier (foul/blow/pace) can manufacture stats out of zero
    remaining time — the floor is current_stat.
    """
    final = pig.project_final(
        current_stat=27.0, period=4, clock_remaining_min=0.0,
    )
    assert final == pytest.approx(27.0, abs=1e-6)
    # Even with hostile factors: zero remaining * anything = 0
    final2 = pig.project_final(
        current_stat=27.0, period=4, clock_remaining_min=0.0,
        pace_factor=2.0, foul_factor=0.5, blow_factor=0.5,
    )
    assert final2 == pytest.approx(27.0, abs=1e-6)
    # OT clamps share to 1.0
    final_ot = pig.project_final(
        current_stat=30.0, period=5, clock_remaining_min=5.0,
    )
    assert final_ot == pytest.approx(30.0, abs=1e-6)


# ── 6. snapshot file parsing handles missing fields gracefully ───────────────

def test_snapshot_parsing_missing_fields(tmp_path):
    """Load snapshot with only player_id+min+pts; projector survives without
    home/away/clock/period or foul fields. clock_remaining defaults to 0
    (end-of-period treatment) — projector returns sensible numbers."""
    snap = {
        "game_id": "0022400999",
        # NO period, NO clock, NO home, NO away — defaults from load_snapshot
        "players": [
            {"player_id": 111, "name": "Test Player", "team": "TST",
             "min": 24.0, "pts": 18},
            # Truly minimal — no name, no team. Should still project.
            {"player_id": 222, "min": 0, "pts": 0},
        ],
    }
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(snap), encoding="utf-8")
    loaded = pig.load_snapshot(str(path))
    assert loaded["period"] == 1  # default
    assert loaded["clock"] == "12:00"  # default

    rows = pig.project_snapshot(loaded)
    assert len(rows) == 2 * len(pig.STATS)  # 2 players × 7 stats
    # All numeric, none None / nan
    for r in rows:
        assert r["current"] is not None
        assert r["projected_final"] is not None
        assert r["projected_final"] >= r["current"] - 1e-6
        assert r["foul_factor"] == 1.0  # missing pf → 1.0
        assert r["blow_factor"] == 1.0  # missing margin → 1.0

    # parse_clock survives garbage
    assert pig.parse_clock(None) == 0.0
    assert pig.parse_clock("") == 0.0
    assert pig.parse_clock("not a clock") == 0.0
    assert pig.parse_clock("07:24") == pytest.approx(7 + 24 / 60.0)
    assert pig.parse_clock("PT07M24.00S") == pytest.approx(7 + 24 / 60.0)


# ── 7. (bonus) clock_played_share monotonic and bounded ──────────────────────

def test_clock_played_share_bounds():
    # Start of game (Q1, 12:00 left) — almost 0 played
    s_start = pig.clock_played_share(1, 12.0)
    assert s_start <= 1e-5
    assert s_start > 0
    # End of game (Q4, 0:00 left) — 1.0
    assert pig.clock_played_share(4, 0.0) == pytest.approx(1.0)
    # Halftime (Q3 starting, 12:00 left in Q3) — 0.5
    assert pig.clock_played_share(3, 12.0) == pytest.approx(0.5)
    # OT clamps to 1.0
    assert pig.clock_played_share(5, 5.0) == 1.0
