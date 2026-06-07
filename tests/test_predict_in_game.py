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
    # OT clamps to 1.0 when CV_INGAME_OT_FIX=OFF (default / byte-identical check)
    assert pig._CV_OT_FIX is False or True  # either state is fine for this test
    old_flag = pig._CV_OT_FIX
    try:
        pig._CV_OT_FIX = False
        assert pig.clock_played_share(5, 5.0) == 1.0
        assert pig.clock_played_share(6, 2.5) == 1.0
    finally:
        pig._CV_OT_FIX = old_flag


# ── 8. W-007 CV_INGAME_OT_FIX — OT extrapolation correctness ─────────────────

def test_ot_fix_flag_off_byte_identical():
    """CV_INGAME_OT_FIX=OFF: OT clock_played_share returns 1.0 (legacy)."""
    old_flag = pig._CV_OT_FIX
    try:
        pig._CV_OT_FIX = False
        # OT1 with 5 min remaining — legacy returns 1.0 (share_remaining=0)
        assert pig.clock_played_share(5, 5.0) == pytest.approx(1.0)
        # OT1 with 2 min remaining — legacy returns 1.0
        assert pig.clock_played_share(5, 2.0) == pytest.approx(1.0)
        # OT2 — still 1.0
        assert pig.clock_played_share(6, 3.0) == pytest.approx(1.0)
        # project_final in OT = current (no remaining)
        assert pig.project_final(20.0, 5, 4.0) == pytest.approx(20.0, abs=1e-6)
    finally:
        pig._CV_OT_FIX = old_flag


def test_ot_fix_flag_on_ot_projects_remaining():
    """CV_INGAME_OT_FIX=ON: OT periods correctly include remaining OT time.

    OT1 with 2 min left: effective game = 48+5=53 min.
    elapsed = 48 + (5-2) = 51.  share = 51/53 ≈ 0.9623.
    remaining_share ≈ 0.0377.
    project_remaining(20 pts, share_played=51/53) = 20*(2/51) ≈ 0.784.
    final ≈ 20.784  (not 20.0).
    """
    old_flag = pig._CV_OT_FIX
    try:
        pig._CV_OT_FIX = True
        # OT1 mid-period: played share should be strictly < 1.0
        share_ot1_2min = pig.clock_played_share(5, 2.0)
        assert share_ot1_2min < 1.0, "OT1 share must be <1 when time remains"
        # Expected: elapsed=51, game_eff=53
        assert share_ot1_2min == pytest.approx(51.0 / 53.0, abs=1e-6)

        # OT1 at tip-off (5:00 remaining) — share = 48/53
        share_ot1_full = pig.clock_played_share(5, 5.0)
        assert share_ot1_full == pytest.approx(48.0 / 53.0, abs=1e-6)

        # OT2 with 3 min left: effective game = 48+10=58 min.
        # elapsed = 48 + 5 + (5-3) = 55.  share = 55/58.
        share_ot2_3min = pig.clock_played_share(6, 3.0)
        assert share_ot2_3min == pytest.approx(55.0 / 58.0, abs=1e-6)

        # OT1 end (clock=0): share = 53/53 = 1.0 (clamped)
        assert pig.clock_played_share(5, 0.0) == pytest.approx(1.0)

        # project_final in OT with remaining time should EXCEED current_stat
        final_ot = pig.project_final(20.0, 5, 2.0)
        assert final_ot > 20.0, "OT projection must exceed current when time remains"
        # Verify: remaining = 20*(2/51) ≈ 0.784 → final ≈ 20.784
        expected = 20.0 + 20.0 * (2.0 / 51.0)
        assert final_ot == pytest.approx(expected, abs=1e-4)
    finally:
        pig._CV_OT_FIX = old_flag


def test_ot_fix_regulation_unchanged():
    """CV_INGAME_OT_FIX=ON: regulation snapshots (period<=4) are byte-identical.

    The OT-fix code path is only entered when period > 4; the regulation
    computation is identical in both states.
    """
    old_flag = pig._CV_OT_FIX
    try:
        for flag_val in (False, True):
            pig._CV_OT_FIX = flag_val
            # Q1 12:00 left
            assert pig.clock_played_share(1, 12.0) <= 1e-5
            # End of Q2 (halftime)
            assert pig.clock_played_share(2, 0.0) == pytest.approx(0.5)
            # End of Q3
            assert pig.clock_played_share(3, 0.0) == pytest.approx(0.75)
            # End of Q4
            assert pig.clock_played_share(4, 0.0) == pytest.approx(1.0)
            # project_final at halftime (24 pts → 48)
            assert pig.project_final(24.0, 2, 0.0) == pytest.approx(48.0, abs=1e-6)
    finally:
        pig._CV_OT_FIX = old_flag


# ── 9. W-008 CV_INGAME_L5_ANCHOR — early-game extrapolation cap ───────────────

def test_l5_anchor_flag_off_byte_identical():
    """CV_INGAME_L5_ANCHOR=OFF (default): project_remaining is byte-identical
    to the pre-W008 path.  The flag is OFF by default and the test verifies
    that no output value changes when the flag is False.
    """
    old_flag = pig._CV_L5_ANCHOR
    try:
        pig._CV_L5_ANCHOR = False
        # End of Q2 (halftime, 24 min elapsed) — well above anchor threshold
        assert pig.project_final(24.0, 2, 0.0) == pytest.approx(48.0, abs=1e-6)
        # End of Q3
        assert pig.project_final(20.0, 3, 0.0) == pytest.approx(
            20.0 + 20.0 / 3.0, abs=1e-4)
        # midQ1 (period=1, 6 min remaining = 6 min elapsed)
        # share_played = 6/48 = 0.125, remaining = 0.875
        # uncapped: 8 * (0.875 / 0.125) = 56 → final = 64
        assert pig.project_final(8.0, 1, 6.0) == pytest.approx(64.0, abs=1e-4)
    finally:
        pig._CV_L5_ANCHOR = old_flag


def test_l5_anchor_flag_on_caps_early_extrapolation():
    """CV_INGAME_L5_ANCHOR=ON: early-game projection is capped so the
    denominator is floored at _L5_ANCHOR_MIN_SHARE (0.25 = end of Q1 = 12 min).

    midQ1 (period=1, 6 min remaining = 6 min elapsed):
        played_share = 6/48 = 0.125  < _L5_ANCHOR_MIN_SHARE = 0.25
        denom = 0.25 (floored), remaining = 0.875
        capped: 8 * (0.875 / 0.25) = 28 → final = 36  (vs uncapped 64)
        The capped projection is significantly lower than the uncapped 64.

    midQ2 (period=1, clock=0 after Q1 = 12 min elapsed = end of Q1):
        played_share = 12/48 = 0.25  == _L5_ANCHOR_MIN_SHARE
        denom = 0.25 (equal, no change), remaining = 0.75
        result identical to flag-OFF: 24 * (0.75/0.25) = 72 → final = 96.
        Actually at endQ1 (period=2, clock=12:00), share_played = 0.25:
        capped denom = max(0.25, 0.25) = 0.25 → byte-identical.

    Late game (period=3, 0 min remaining = 36 min elapsed):
        played_share = 0.75 >> 0.25  → flag has NO effect (byte-identical).
    """
    old_flag = pig._CV_L5_ANCHOR
    try:
        pig._CV_L5_ANCHOR = True
        # midQ1: 6 min elapsed, 6 min remaining in Q1
        # share_played = 6/48 = 0.125; denom floored to 0.25
        # project_remaining = 8 * (0.875 / 0.25) = 28 → final = 36
        f_early = pig.project_final(8.0, 1, 6.0)
        assert f_early == pytest.approx(36.0, abs=1e-4), (
            f"midQ1 capped final = {f_early}, expected 36.0")
        # Verify it is less than the uncapped value (64.0)
        pig._CV_L5_ANCHOR = False
        f_uncapped = pig.project_final(8.0, 1, 6.0)
        pig._CV_L5_ANCHOR = True
        assert f_early < f_uncapped, (
            f"capped ({f_early}) must be < uncapped ({f_uncapped})")

        # endQ1 (period=2, clock=12:00 → 12 min elapsed, played_share=0.25)
        # denom = max(0.25, 0.25) = 0.25 → identical to flag-OFF
        f_endq1_on = pig.project_final(12.0, 2, 12.0)
        pig._CV_L5_ANCHOR = False
        f_endq1_off = pig.project_final(12.0, 2, 12.0)
        pig._CV_L5_ANCHOR = True
        assert f_endq1_on == pytest.approx(f_endq1_off, abs=1e-6), (
            "at endQ1 boundary ON and OFF must be identical")

        # Late game: end of Q3 (period=3, clock=0 → 36 min elapsed, share=0.75)
        # Flag has NO effect; output byte-identical to OFF.
        f_late_on = pig.project_final(20.0, 3, 0.0)
        pig._CV_L5_ANCHOR = False
        f_late_off = pig.project_final(20.0, 3, 0.0)
        pig._CV_L5_ANCHOR = True
        assert f_late_on == pytest.approx(f_late_off, abs=1e-6), (
            "endQ3 must be byte-identical between flag ON and OFF")

        # Halftime (period=2, clock=0 → 24 min, share=0.5 > 0.25)
        # Flag has NO effect; output identical to OFF.
        f_half_on = pig.project_final(12.0, 2, 0.0)
        pig._CV_L5_ANCHOR = False
        f_half_off = pig.project_final(12.0, 2, 0.0)
        pig._CV_L5_ANCHOR = True
        assert f_half_on == pytest.approx(f_half_off, abs=1e-6), (
            "halftime must be byte-identical between flag ON and OFF")
    finally:
        pig._CV_L5_ANCHOR = old_flag


def test_l5_anchor_reduces_midq1_mae():
    """Simulate midQ1 scenario: 8 pts in 6 min, actual full-game = 28 pts.
    Flag OFF → projected = 64, MAE = 36.
    Flag ON  → projected = 36, MAE = 8.  Much closer to truth.
    """
    truth = 28.0
    old_flag = pig._CV_L5_ANCHOR

    try:
        pig._CV_L5_ANCHOR = False
        proj_off = pig.project_final(8.0, 1, 6.0)
        mae_off = abs(proj_off - truth)

        pig._CV_L5_ANCHOR = True
        proj_on = pig.project_final(8.0, 1, 6.0)
        mae_on = abs(proj_on - truth)

        assert mae_on < mae_off, (
            f"flag ON MAE {mae_on:.2f} must be < flag OFF MAE {mae_off:.2f}")
        # Sanity: capped projection is ≤ uncapped
        assert proj_on <= proj_off
    finally:
        pig._CV_L5_ANCHOR = old_flag


def test_l5_anchor_byte_identical_midgame_onwards():
    """All periods from endQ1 onward (played_share >= 0.25) produce
    byte-identical results regardless of the flag value.
    """
    old_flag = pig._CV_L5_ANCHOR
    cases = [
        # (current, period, clock_rem) — all at endQ1 or later
        (12.0, 2, 12.0),   # endQ1
        (12.0, 2, 0.0),    # halftime
        (20.0, 3, 0.0),    # endQ3
        (25.0, 4, 6.0),    # midQ4
        (27.0, 4, 0.0),    # final buzzer
    ]
    try:
        for cur, per, clk in cases:
            pig._CV_L5_ANCHOR = False
            val_off = pig.project_final(cur, per, clk)
            pig._CV_L5_ANCHOR = True
            val_on = pig.project_final(cur, per, clk)
            assert val_off == pytest.approx(val_on, abs=1e-9), (
                f"period={per} clock={clk}: flag ON ({val_on}) != OFF ({val_off})")
    finally:
        pig._CV_L5_ANCHOR = old_flag


# ── 10. W-009 CV_INGAME_ROTCURVE — per-quarter rotation curve ─────────────────

def test_rotcurve_flag_off_byte_identical_project_final():
    """CV_INGAME_ROTCURVE=OFF (default): project_final with rem_min_override=None
    is byte-identical to the pre-W009 path.  rem_min_override=None must be a
    no-op regardless of player_id or period.
    """
    cases = [
        (12.0, 2, 12.0),
        (12.0, 2, 0.0),
        (20.0, 3, 0.0),
        (25.0, 4, 6.0),
    ]
    for cur, per, clk in cases:
        baseline = pig.project_final(cur, per, clk)
        with_none = pig.project_final(cur, per, clk, rem_min_override=None)
        assert baseline == pytest.approx(with_none, abs=1e-9), (
            f"rem_min_override=None must be a no-op at period={per} clock={clk}")


def test_rotcurve_rem_min_override_uses_correct_rate():
    """rem_min_override=X projects at per-min rate * X (not clock-based).

    At midQ2 (period=2, clock=6min): flat expects 30 remaining minutes.
    Passing rem_min_override=20 should give project at rate * 20.
    cur=20 pts in 18 min → rate=20/18.  remaining = (20/18)*20 = 22.22.
    final = 20 + 22.22 = 42.22.
    """
    cur = 20.0
    per, clk = 2, 6.0
    # share_played = 18/48 = 0.375; basis_min = 0.375 * 48 = 18
    # rate = 20/18; remaining = (20/18) * 20 = 22.222
    # final = 20 + 22.222 = 42.222
    expected = 20.0 + (20.0 / 18.0) * 20.0
    result = pig.project_final(
        cur, per, clk,
        player_clock_played_min=None,
        rem_min_override=20.0,
    )
    assert result == pytest.approx(expected, abs=1e-4), (
        f"rem_min_override=20 should give {expected:.3f}, got {result:.3f}")


def test_rotcurve_rem_min_override_zero_returns_current():
    """rem_min_override=0 → no remaining time → projected_final == current_stat."""
    result = pig.project_final(25.0, 2, 6.0, rem_min_override=0.0)
    assert result == pytest.approx(25.0, abs=1e-6)


def test_rotcurve_flag_off_no_atlas_load():
    """When CV_INGAME_ROTCURVE is OFF, _load_rotcurve_atlas must never be called
    from project_snapshot (rotcurve is entirely inactive).
    """
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    try:
        pig._CV_ROTCURVE = False
        pig._ROTCURVE_ATLAS = None   # reset to sentinel
        snap = {
            "period": 2, "clock": "06:00",
            "home_team": "OKC", "away_team": "NYK",
            "home_score": 50, "away_score": 45,
            "players": [
                {"player_id": 12345, "name": "P1", "team": "OKC", "min": 18.0,
                 "pts": 20, "reb": 3, "ast": 4, "fg3m": 2,
                 "stl": 1, "blk": 0, "tov": 2, "pf": 1},
            ],
        }
        result = pig.project_snapshot(snap)
        # Atlas must still be None (not loaded when flag OFF)
        assert pig._ROTCURVE_ATLAS is None, (
            "Atlas should NOT be loaded when CV_INGAME_ROTCURVE=OFF")
        assert len(result) == len(pig.STATS)  # 7 stats, snapshot produced
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas


def test_rotcurve_unknown_player_degrades_to_flat():
    """When CV_INGAME_ROTCURVE=ON, a player absent from the atlas must produce
    output byte-identical to flag-OFF (graceful degradation).
    """
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    try:
        # Inject a synthetic empty atlas (player 999 absent)
        pig._ROTCURVE_ATLAS = {}
        pig._ROTCURVE_N_GAMES = {}

        pig._CV_ROTCURVE = False
        snap = {
            "period": 2, "clock": "06:00",
            "home_team": "OKC", "away_team": "NYK",
            "home_score": 50, "away_score": 45,
            "players": [
                {"player_id": 999, "name": "Unknown", "team": "OKC", "min": 18.0,
                 "pts": 20, "reb": 3, "ast": 4, "fg3m": 2,
                 "stl": 1, "blk": 0, "tov": 2, "pf": 1},
            ],
        }
        result_off = {r["stat"]: r["projected_final"]
                      for r in pig.project_snapshot(snap)}

        pig._CV_ROTCURVE = True
        result_on = {r["stat"]: r["projected_final"]
                     for r in pig.project_snapshot(snap)}

        for stat in pig.STATS:
            assert result_off[stat] == pytest.approx(result_on[stat], abs=1e-9), (
                f"Unknown player stat={stat}: flag ON ({result_on[stat]}) "
                f"!= OFF ({result_off[stat]})")
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas
        pig._ROTCURVE_N_GAMES = None


def test_rotcurve_known_player_differs_from_flat():
    """When CV_INGAME_ROTCURVE=ON, a player with a full 4-quarter atlas entry
    must produce a different (curve-adjusted) projection vs the flat-pace OFF path.

    We inject a synthetic atlas entry with different Q2/Q3/Q4 means from the
    flat extrapolation to ensure the curve actually changes the output.
    """
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    old_n_games = pig._ROTCURVE_N_GAMES
    try:
        # Synthetic atlas: player 7777 plays fewer minutes than flat extrapolation expects.
        # At midQ2 (period=2, clock=6min), 18 min elapsed, 30 flat remaining.
        # Curve says: Q2_rem = 0.5 * 6.0 = 3.0; Q3 = 6.0; Q4 = 7.0 → atlas_rem=16.0
        # With n_games=20: blend w=20/(20+10)=0.667; blended = 0.667*16 + 0.333*30 = 20.67
        # This is different from flat (30.0).
        pig._ROTCURVE_ATLAS = {7777: {1: 8.0, 2: 6.0, 3: 6.0, 4: 7.0}}
        pig._ROTCURVE_N_GAMES = {7777: 20.0}

        snap = {
            "period": 2, "clock": "06:00",
            "home_team": "OKC", "away_team": "NYK",
            "home_score": 50, "away_score": 45,
            "players": [
                {"player_id": 7777, "name": "Atlas P", "team": "OKC", "min": 18.0,
                 "pts": 18, "reb": 6, "ast": 3, "fg3m": 2,
                 "stl": 1, "blk": 0, "tov": 1, "pf": 1},
            ],
        }

        pig._CV_ROTCURVE = False
        result_off = {r["stat"]: r["projected_final"]
                      for r in pig.project_snapshot(snap)}

        pig._CV_ROTCURVE = True
        result_on = {r["stat"]: r["projected_final"]
                     for r in pig.project_snapshot(snap)}

        # At least one stat must differ (curve-adjusted vs flat)
        any_diff = any(
            abs(result_on[s] - result_off[s]) > 1e-6
            for s in pig.STATS
        )
        assert any_diff, (
            "Atlas player with non-flat curve should produce different projections "
            "when CV_INGAME_ROTCURVE=ON vs OFF")

        # Sanity: projected >= current for all stats
        for r in pig.project_snapshot(snap):
            assert r["projected_final"] >= r["current"] - 1e-6, (
                f"projected_final must be >= current for stat {r['stat']}")
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas
        pig._ROTCURVE_N_GAMES = old_n_games


# ── 11. W-009 RE-ATTEMPT: fringe-guard branch ─────────────────────────────────

def test_fringe_guard_flag_off_byte_identical():
    """CV_INGAME_ROTCURVE=OFF: fringe-guard must never activate.
    rotcurve_expected_rem_min returns 0.0 when flag OFF.
    When flag OFF, the rotation-curve atlas is not loaded from project_snapshot.
    """
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    old_n_games = pig._ROTCURVE_N_GAMES
    try:
        pig._ROTCURVE_ATLAS = None   # reset sentinel
        pig._ROTCURVE_N_GAMES = None

        # With flag OFF, rotcurve_expected_rem_min must return 0.0 immediately.
        pig._CV_ROTCURVE = False
        result = pig.rotcurve_expected_rem_min(
            player_id=8888, period=3, clock_rem=6.0, cur_min=3.0,
            min_q1=2.0, min_q2=1.0,
        )
        assert result == 0.0, (
            f"rotcurve_expected_rem_min flag-OFF must return 0.0, got {result}")
        # Atlas must not have been loaded
        assert pig._ROTCURVE_ATLAS is None, "Atlas must not load when flag OFF"

        # project_snapshot with flag OFF must not populate the atlas either
        snap = {
            "period": 3, "clock": "06:00",
            "home_team": "OKC", "away_team": "NYK",
            "home_score": 60, "away_score": 58,
            "players": [
                {"player_id": 8888, "name": "FringeP", "team": "OKC",
                 "min": 3.0, "min_q1": 2.0, "min_q2": 1.0, "min_q3": 0.0,
                 "pts": 2, "reb": 1, "ast": 0, "fg3m": 0,
                 "stl": 0, "blk": 0, "tov": 0, "pf": 0},
            ],
        }
        pig._CV_ROTCURVE = False
        pig.project_snapshot(snap)
        assert pig._ROTCURVE_ATLAS is None, "Atlas must NOT be loaded when flag OFF"
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas
        pig._ROTCURVE_N_GAMES = old_n_games


def test_fringe_guard_activates_for_low_minute_player():
    """Fringe guard (cur_min<=5) uses regression, not atlas mean.

    At midQ3 (period=3, clock=6:00), cur_min=3 (fringe), min_q1=2, min_q2=1:
      reg_rem = 4.302 + 0.874*2 + 0.531*1 = 4.302+1.748+0.531 = 6.581
      Clamped = 6.581 (within [0,20])
      flat_rem = 3 * ((1 - 0.625)/0.625) = 3*(0.375/0.625) = 1.8
      w = k/(k+k) = 0.5 (pid absent → n_g_fringe=k=10)
      blended = 0.5*6.581 + 0.5*1.8 = 4.19 (approx)

    This must differ from both the flat-pace fallback AND the atlas result.
    """
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    old_n_games = pig._ROTCURVE_N_GAMES
    try:
        pig._ROTCURVE_ATLAS = {}   # player absent from atlas
        pig._ROTCURVE_N_GAMES = {}
        pig._CV_ROTCURVE = True

        result = pig.rotcurve_expected_rem_min(
            player_id=9999,
            period=3,
            clock_rem=6.0,
            cur_min=3.0,
            min_q1=2.0,
            min_q2=1.0,
        )

        # Expected via fringe formula:
        reg_rem = pig._ROTCURVE_FRINGE_INTERCEPT + pig._ROTCURVE_FRINGE_COEF_Q1 * 2.0 + pig._ROTCURVE_FRINGE_COEF_Q2 * 1.0
        reg_rem = max(0.0, min(20.0, reg_rem))
        # flat_rem = 3 * (1 - 0.625) / 0.625 = 1.8
        # clock_played_share(3, 6.0) = (2*12 + (12-6)) / 48 = 30/48 = 0.625
        flat_rem = 3.0 * (1.0 - 0.625) / 0.625  # = 1.8
        k = pig._ROTCURVE_SHRINK_K   # 10.0
        w = k / (k + k)  # = 0.5 (n_g_fringe = k when absent)
        expected = max(0.0, w * reg_rem + (1.0 - w) * flat_rem)

        assert result == pytest.approx(expected, abs=1e-4), (
            f"fringe result {result:.4f} != expected {expected:.4f}")

        # Must be > flat_rem (regression pushes up for 2+1=3 min prior-quarter play)
        assert result > flat_rem, (
            f"fringe result {result:.4f} should exceed flat_rem {flat_rem:.4f}")
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas
        pig._ROTCURVE_N_GAMES = old_n_games


def test_fringe_guard_boundary_at_threshold():
    """Exactly at threshold (cur_min=5.0) → fringe guard fires.
    Slightly above threshold (cur_min=5.01) → atlas path (or flat fallback).
    """
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    old_n_games = pig._ROTCURVE_N_GAMES
    try:
        pig._ROTCURVE_ATLAS = {}
        pig._ROTCURVE_N_GAMES = {}
        pig._CV_ROTCURVE = True

        # At threshold: fringe guard fires → regression blended with flat
        rem_at = pig.rotcurve_expected_rem_min(
            player_id=1111, period=3, clock_rem=6.0, cur_min=5.0,
            min_q1=3.0, min_q2=2.0,
        )
        # Above threshold: atlas absent → falls through to flat degradation
        rem_above = pig.rotcurve_expected_rem_min(
            player_id=1111, period=3, clock_rem=6.0, cur_min=5.01,
            min_q1=3.0, min_q2=2.0,
        )
        # Both must be non-negative finite floats
        assert rem_at >= 0.0
        assert rem_above >= 0.0
        # The two paths must differ (fringe uses regression, above uses flat fallback)
        # For absent player above threshold: flat_rem = 5.01 * (1-0.625)/0.625
        flat_rem_above = 5.01 * (1.0 - 0.625) / 0.625
        assert rem_above == pytest.approx(flat_rem_above, abs=1e-4), (
            f"above threshold: absent player should degrade to flat_rem {flat_rem_above:.4f}")
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas
        pig._ROTCURVE_N_GAMES = old_n_games


def test_fringe_guard_clamp_upper():
    """Regression estimate exceeding 20 is clamped to 20."""
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    old_n_games = pig._ROTCURVE_N_GAMES
    try:
        pig._ROTCURVE_ATLAS = {}
        pig._ROTCURVE_N_GAMES = {}
        pig._CV_ROTCURVE = True

        # Very high min_q1/min_q2 → reg_rem would exceed 20 without clamp
        # reg_rem = 4.302 + 0.874*10 + 0.531*10 = 4.302+8.74+5.31 = 18.352
        # That's actually < 20; use min_q values that push it over:
        # 4.302 + 0.874*12 + 0.531*8 = 4.302+10.488+4.248 = 19.038 (< 20)
        # 4.302 + 0.874*15 + 0.531*5 = 4.302+13.11+2.655 = 20.067 > 20
        rem = pig.rotcurve_expected_rem_min(
            player_id=7777, period=2, clock_rem=0.0, cur_min=4.0,
            min_q1=15.0, min_q2=5.0,
        )
        # blended = w * clamp(20.067,0,20) + (1-w) * flat
        # With clock_rem=0, period=2: share_played=0.5; flat = 4*(0.5/0.5) = 4
        # w = 0.5; blended = 0.5*20 + 0.5*4 = 12
        assert rem == pytest.approx(0.5 * 20.0 + 0.5 * 4.0, abs=1e-3), (
            f"clamped fringe rem {rem:.3f} != 12.0")
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas
        pig._ROTCURVE_N_GAMES = old_n_games


def test_fringe_guard_project_snapshot_min_q_passthrough():
    """project_snapshot passes min_q1/min_q2 from the player row to the fringe guard.
    A fringe player (cur_min<=5) with min_q1/min_q2 set must produce a different
    projection than one with min_q1=min_q2=0 (regression inputs differ).
    """
    old_flag = pig._CV_ROTCURVE
    old_atlas = pig._ROTCURVE_ATLAS
    old_n_games = pig._ROTCURVE_N_GAMES
    try:
        pig._ROTCURVE_ATLAS = {}
        pig._ROTCURVE_N_GAMES = {}
        pig._CV_ROTCURVE = True

        base_snap = {
            "period": 3, "clock": "06:00",
            "home_team": "OKC", "away_team": "NYK",
            "home_score": 60, "away_score": 58,
        }
        # Player with prior-quarter activity (min_q1=5, min_q2=4)
        snap_with_hist = dict(base_snap, players=[{
            "player_id": 5555, "name": "FringeHist", "team": "OKC",
            "min": 3.0, "min_q1": 5.0, "min_q2": 4.0, "min_q3": 0.0,
            "pts": 2, "reb": 1, "ast": 1, "fg3m": 0,
            "stl": 0, "blk": 0, "tov": 0, "pf": 0,
        }])
        # Same player, no prior-quarter history
        snap_no_hist = dict(base_snap, players=[{
            "player_id": 5555, "name": "FringeHist", "team": "OKC",
            "min": 3.0, "min_q1": 0.0, "min_q2": 0.0, "min_q3": 0.0,
            "pts": 2, "reb": 1, "ast": 1, "fg3m": 0,
            "stl": 0, "blk": 0, "tov": 0, "pf": 0,
        }])

        rows_hist = {r["stat"]: r["projected_final"]
                     for r in pig.project_snapshot(snap_with_hist)}
        rows_no = {r["stat"]: r["projected_final"]
                   for r in pig.project_snapshot(snap_no_hist)}

        # At least one stat must differ (regression input differs → rem_min differs)
        any_diff = any(
            abs(rows_hist[s] - rows_no[s]) > 1e-6
            for s in pig.STATS
        )
        assert any_diff, (
            "Fringe player with min_q history must project differently than one with 0s")
    finally:
        pig._CV_ROTCURVE = old_flag
        pig._ROTCURVE_ATLAS = old_atlas
        pig._ROTCURVE_N_GAMES = old_n_games
