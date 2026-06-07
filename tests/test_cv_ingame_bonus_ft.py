"""tests/test_cv_ingame_bonus_ft.py — CV_INGAME_BONUS_FT bonus-state FT bump.

Tests:
  1. Byte-identical guarantee: flag OFF produces zero-delta vs baseline.
  2. Flag ON, opp PF < bonus threshold: bump = 0 (marginal_p <= 0).
  3. Flag ON, opp PF >= bonus threshold: bump > 0 for high-FTA player.
  4. Only pts stat is affected (reb/ast/fg3m/stl/blk/tov unchanged).
  5. Bump decreases with fewer remaining periods (endQ3 < endQ2 < endQ1).
  6. Player absent from atlas: bump = 0 (graceful fallback).
  7. End of game (share_remaining = 0): bump = 0.
  8. project_snapshot: pts changes by expected delta for in-bonus case.
"""
from __future__ import annotations

import importlib
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Clear flag before import so module initializes with it OFF.
os.environ.pop("CV_INGAME_BONUS_FT", None)


def _reload_pig(flag_on: bool):
    """Reload predict_in_game with CV_INGAME_BONUS_FT ON/OFF."""
    if flag_on:
        os.environ["CV_INGAME_BONUS_FT"] = "1"
    else:
        os.environ.pop("CV_INGAME_BONUS_FT", None)
    import predict_in_game as pig
    importlib.reload(pig)
    return pig


# High-FTA real player (fta_per_36 ≈ 9.7) who is in the atlas.
_HIGH_FTA_PID = 1628983

# A player that is NOT in the atlas (synthetic id).
_UNKNOWN_PID = 8888888


def _snap(period: int, opp_pf: float, opp_team: str = "ATL") -> dict:
    """Build a minimal snapshot with one BOS player and opp team PF."""
    return {
        "game_id": "0022400001",
        "period": period,
        "clock": "12:00",
        "home_team": "BOS",
        "away_team": opp_team,
        "home_score": 30.0,
        "away_score": 25.0,
        "players": [
            {
                "player_id": _HIGH_FTA_PID,
                "name": "High FTA Star",
                "team": "BOS",
                "min": float(12 * (period - 1)),
                "pts": 8.0,
                "reb": 3.0,
                "ast": 2.0,
                "fg3m": 1.0,
                "stl": 0.0,
                "blk": 0.0,
                "tov": 1.0,
                "pf": 1.0,
                "min_q1": 12.0,
                "min_q2": 12.0 if period > 2 else 0.0,
                "min_q3": 12.0 if period > 3 else 0.0,
                "min_q4": 0.0,
            },
            {
                "player_id": 5555,
                "name": "Opp Player",
                "team": opp_team,
                "min": float(12 * (period - 1)),
                "pts": 6.0,
                "reb": 4.0,
                "ast": 1.0,
                "fg3m": 0.0,
                "stl": 0.0,
                "blk": 0.0,
                "tov": 1.0,
                "pf": opp_pf,
                "min_q1": 12.0,
                "min_q2": 12.0 if period > 2 else 0.0,
                "min_q3": 12.0 if period > 3 else 0.0,
                "min_q4": 0.0,
            },
        ],
    }


# ── 1. Byte-identical guarantee ────────────────────────────────────────────────

class TestByteIdentical:
    def test_flag_off_zero_delta(self):
        """With CV_INGAME_BONUS_FT=0, output is identical to baseline."""
        pig_off = _reload_pig(False)
        snap = _snap(period=2, opp_pf=7.0)
        rows_off = pig_off.project_snapshot(snap)

        pig_on = _reload_pig(True)
        rows_off2 = pig_on.project_snapshot(_snap(period=2, opp_pf=7.0))

        # Reload with flag OFF again and compare
        pig_off2 = _reload_pig(False)
        rows_baseline = pig_off2.project_snapshot(_snap(period=2, opp_pf=7.0))

        vals_off = {(r["player_id"], r["stat"]): r["projected_final"]
                    for r in rows_baseline}
        rows_off_set = {(r["player_id"], r["stat"]): r["projected_final"]
                        for r in rows_off}
        for key, v_baseline in vals_off.items():
            assert abs(rows_off_set[key] - v_baseline) < 1e-9, (
                f"flag OFF produced different output for {key}: "
                f"{rows_off_set[key]} vs {v_baseline}"
            )

    def test_flag_off_bonus_ft_is_false(self):
        pig = _reload_pig(False)
        assert pig._CV_BONUS_FT is False

    def test_flag_on_bonus_ft_is_true(self):
        pig = _reload_pig(True)
        assert pig._CV_BONUS_FT is True


# ── 2. Bump = 0 when opp PF < bonus threshold ─────────────────────────────────

class TestBumpZeroWhenBelowThreshold:
    def test_low_opp_pf_no_bump(self):
        """Opp with < BONUS_FOULS PF in period: raw_bonus_prob=0 → marginal_p<0 → bump=0."""
        pig = _reload_pig(True)
        pig._load_bft_atlas()
        snap_players = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 1.0},
            {"player_id": 5555, "team": "ATL", "pf": 3.0},  # below 5
        ]
        bump = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_players, period=2, clock_rem=12.0
        )
        assert bump == 0.0, f"Expected 0 for opp 3 PF; got {bump:.4f}"

    def test_exactly_below_threshold(self):
        pig = _reload_pig(True)
        pig._load_bft_atlas()
        snap_players = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 1.0},
            {"player_id": 5555, "team": "ATL", "pf": 4.0},  # just below 5
        ]
        bump = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_players, period=2, clock_rem=12.0
        )
        assert bump == 0.0, f"Expected 0 for opp 4 PF; got {bump:.4f}"


# ── 3. Bump > 0 when opp PF >= bonus threshold ────────────────────────────────

class TestBumpPositiveWhenInBonus:
    def test_opp_at_bonus_threshold_gives_positive_bump(self):
        pig = _reload_pig(True)
        pig._load_bft_atlas()
        snap_players = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 1.0},
            {"player_id": 5555, "team": "ATL", "pf": 5.0},  # exactly at threshold
        ]
        bump = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_players, period=2, clock_rem=12.0
        )
        assert bump > 0.0, f"Expected bump > 0 at threshold; got {bump:.4f}"

    def test_opp_above_bonus_threshold_gives_positive_bump(self):
        pig = _reload_pig(True)
        pig._load_bft_atlas()
        snap_players = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 1.0},
            {"player_id": 5555, "team": "ATL", "pf": 7.0},  # well above
        ]
        bump = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_players, period=2, clock_rem=12.0
        )
        assert bump > 0.0, f"Expected bump > 0 at 7 PF; got {bump:.4f}"
        assert bump < 1.0, f"Bump should be small (< 1 pt); got {bump:.4f}"


# ── 4. Only pts stat affected ──────────────────────────────────────────────────

class TestOnlyPtsAffected:
    def test_non_pts_stats_unchanged(self):
        """reb/ast/fg3m/stl/blk/tov must be byte-identical whether flag ON or OFF."""
        snap = _snap(period=2, opp_pf=7.0)

        pig_off = _reload_pig(False)
        rows_off = pig_off.project_snapshot(snap)

        pig_on = _reload_pig(True)
        rows_on = pig_on.project_snapshot(_snap(period=2, opp_pf=7.0))

        vals_off = {(r["player_id"], r["stat"]): r["projected_final"]
                    for r in rows_off}
        vals_on = {(r["player_id"], r["stat"]): r["projected_final"]
                   for r in rows_on}

        non_pts_stats = ("reb", "ast", "fg3m", "stl", "blk", "tov")
        for stat in non_pts_stats:
            for pid in (_HIGH_FTA_PID, 5555):
                key = (pid, stat)
                v_off = vals_off.get(key)
                v_on = vals_on.get(key)
                if v_off is not None and v_on is not None:
                    assert abs(v_off - v_on) < 1e-9, (
                        f"stat={stat} pid={pid} changed: {v_off} -> {v_on}"
                    )


# ── 5. Bump decreases with fewer remaining periods ─────────────────────────────

class TestBumpDecreasesByPeriod:
    def test_endQ1_larger_than_endQ2_larger_than_endQ3(self):
        """Bump scales with remaining periods; use opp_pf that triggers bonus at each."""
        pig = _reload_pig(True)
        pig._load_bft_atlas()
        # endQ1 (period=2, 1 completed period): opp_pf=7 → 7/1=7 > 5 → in bonus
        snap_q1 = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 1.0},
            {"player_id": 5555, "team": "ATL", "pf": 7.0},
        ]
        # endQ2 (period=3, 2 completed periods): opp_pf=12 → 12/2=6 > 5 → in bonus
        snap_q2 = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 2.0},
            {"player_id": 5555, "team": "ATL", "pf": 12.0},
        ]
        # endQ3 (period=4, 3 completed periods): opp_pf=18 → 18/3=6 > 5 → in bonus
        snap_q3 = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 3.0},
            {"player_id": 5555, "team": "ATL", "pf": 18.0},
        ]
        bump_q1 = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_q1, period=2, clock_rem=12.0
        )
        bump_q2 = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_q2, period=3, clock_rem=12.0
        )
        bump_q3 = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_q3, period=4, clock_rem=12.0
        )
        assert bump_q1 > bump_q2 > bump_q3 > 0.0, (
            f"Bumps must decrease: endQ1={bump_q1:.4f} endQ2={bump_q2:.4f} "
            f"endQ3={bump_q3:.4f}"
        )
        # Exact ratio: endQ1/endQ3 ≈ 3 (3 remaining vs 1 remaining).
        # The marginal_p can differ slightly across periods due to the pf-rate estimate,
        # but since raw_bonus_prob=1.0 for all cases (opp always above threshold),
        # p_bonus and marginal_p are identical, so ratio is exactly 3/1=3.
        assert abs(bump_q1 / bump_q3 - 3.0) < 0.01, (
            f"endQ1/endQ3 ratio should be ~3; got {bump_q1/bump_q3:.3f}"
        )


# ── 6. Absent player → bump = 0 ───────────────────────────────────────────────

class TestAbsentPlayerGraceful:
    def test_unknown_player_zero_bump(self):
        pig = _reload_pig(True)
        pig._load_bft_atlas()
        assert _UNKNOWN_PID not in (pig._FT_FLOOR_ATLAS or {}), (
            f"pid {_UNKNOWN_PID} unexpectedly in atlas"
        )
        snap_players = [
            {"player_id": _UNKNOWN_PID, "team": "BOS", "pf": 1.0},
            {"player_id": 5555, "team": "ATL", "pf": 7.0},
        ]
        bump = pig._bonus_ft_pts_bump(
            _UNKNOWN_PID, "BOS", "ATL", snap_players, period=2, clock_rem=12.0
        )
        assert bump == 0.0, (
            f"Unknown player should get 0 bump; got {bump:.4f}"
        )


# ── 7. End-of-game → bump = 0 ─────────────────────────────────────────────────

class TestEndOfGameZeroBump:
    def test_end_of_game_zero_bump(self):
        pig = _reload_pig(True)
        pig._load_bft_atlas()
        snap_players = [
            {"player_id": _HIGH_FTA_PID, "team": "BOS", "pf": 1.0},
            {"player_id": 5555, "team": "ATL", "pf": 8.0},
        ]
        # period=4, clock=0.0 → share_remaining = 0 → bump = 0
        bump = pig._bonus_ft_pts_bump(
            _HIGH_FTA_PID, "BOS", "ATL", snap_players, period=4, clock_rem=0.0
        )
        assert bump == 0.0, f"End-of-game bump should be 0; got {bump:.4f}"


# ── 8. project_snapshot PTS delta ─────────────────────────────────────────────

class TestProjectSnapshotDelta:
    def test_pts_bumped_for_bonus_case(self):
        """Flag ON with opp in bonus should increase pts projection."""
        snap = _snap(period=2, opp_pf=7.0)

        pig_off = _reload_pig(False)
        rows_off = pig_off.project_snapshot(snap)
        pts_off = {r["player_id"]: r["projected_final"]
                   for r in rows_off if r["stat"] == "pts"}

        pig_on = _reload_pig(True)
        rows_on = pig_on.project_snapshot(_snap(period=2, opp_pf=7.0))
        pts_on = {r["player_id"]: r["projected_final"]
                  for r in rows_on if r["stat"] == "pts"}

        # High-FTA BOS player should get bumped
        assert _HIGH_FTA_PID in pts_off and _HIGH_FTA_PID in pts_on
        delta = pts_on[_HIGH_FTA_PID] - pts_off[_HIGH_FTA_PID]
        assert delta > 0.0, (
            f"PTS for BOS player should increase when ATL in bonus; delta={delta:.4f}"
        )
        assert delta < 1.0, (
            f"PTS delta should be small (< 1 pt); delta={delta:.4f}"
        )

    def test_pts_unchanged_when_opp_below_bonus(self):
        """Flag ON with opp NOT in bonus: pts projection unchanged (bump=0)."""
        snap_low = _snap(period=2, opp_pf=3.0)

        pig_off = _reload_pig(False)
        rows_off = pig_off.project_snapshot(snap_low)

        pig_on = _reload_pig(True)
        rows_on = pig_on.project_snapshot(_snap(period=2, opp_pf=3.0))

        pts_off = {r["player_id"]: r["projected_final"]
                   for r in rows_off if r["stat"] == "pts"}
        pts_on = {r["player_id"]: r["projected_final"]
                  for r in rows_on if r["stat"] == "pts"}

        for pid in pts_off:
            delta = abs(pts_on.get(pid, pts_off[pid]) - pts_off[pid])
            assert delta < 1e-9, (
                f"pts for pid={pid} changed even with opp below bonus: delta={delta:.8f}"
            )
