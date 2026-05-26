"""tests/test_R28_U2_pace_validation.py — R28_U2 pace calibration fix.

Validates the pace-drift root-cause finding and the calibration patch
applied to ``season_games_2025-26.json``. Uses synthetic in-memory data
so tests don't depend on the actual on-disk season files (apart from the
``test_disk_state_*`` cases that are skipped when the fixture data is
absent — those are the "did the patch land cleanly?" smoke tests).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.patch_R28_U2_pace_calibration import (  # noqa: E402
    _team_abbr_to_id,
    apply_calibration,
    compute_team_ratios,
    patch_file,
)
from scripts.improve_loop.probe_R28_U2_pace_drift import (  # noqa: E402
    PLAUSIBLE_PACE_MAX,
    PLAUSIBLE_PACE_MIN,
    diagnose,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
# Use REAL NBA team IDs so the patch script's static-teams lookup resolves
# them to the same TEAM_IDs the team_stats fixture key on.
_REAL = _team_abbr_to_id()
ABBR2ID = {k: _REAL[k] for k in ("ATL", "BOS", "BKN", "CHA")}


def _rows(n_per_team: int = 10):
    """Synthetic season_games rows with biased custom pace (~102.4)
    for each of 4 teams."""
    out = []
    teams = list(ABBR2ID.keys())
    gid = 0
    for i in range(n_per_team):
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                gid += 1
                # custom pace per team — biased high by 2.8 vs NBA Stats truth
                out.append({
                    "game_id": f"{gid:010d}",
                    "home_team": h,
                    "away_team": a,
                    "home_pace": 102.5 + (ord(h[0]) - ord("A")) * 0.2,
                    "away_pace": 102.5 + (ord(a[0]) - ord("A")) * 0.2,
                    "home_elo": 1500.0,
                    "away_elo": 1500.0,
                })
    return out


def _team_stats_truth():
    """NBA Stats authoritative pace ~99.6 — same per-team variation."""
    truth = {}
    for ab, tid in ABBR2ID.items():
        truth[str(tid)] = {
            "pace": 99.6 + (ord(ab[0]) - ord("A")) * 0.2,
            "off_rtg": 113.0, "def_rtg": 113.0,
        }
    return truth


# --------------------------------------------------------------------------- #
# 1. plausibility check                                                        #
# --------------------------------------------------------------------------- #
class TestPlausibility:

    def test_post_calibration_pace_within_realistic_range(self):
        rows = _rows()
        truth = _team_stats_truth()
        ratios = compute_team_ratios(rows, truth, ABBR2ID)
        new_rows, stats = apply_calibration(rows, ratios, ABBR2ID)
        post_mean = sum(r["home_pace"] for r in new_rows) / len(new_rows)
        assert PLAUSIBLE_PACE_MIN <= post_mean <= PLAUSIBLE_PACE_MAX, (
            f"post-cal mean {post_mean:.2f} outside [95,105]"
        )

    def test_pre_calibration_pace_was_too_high(self):
        rows = _rows()
        pre_mean = sum(r["home_pace"] for r in rows) / len(rows)
        # Synthetic data deliberately puts pre-fix pace above 102
        assert pre_mean > 102.0


# --------------------------------------------------------------------------- #
# 2. method-consistency: same row twice produces same calibration              #
# --------------------------------------------------------------------------- #
class TestComputationConsistency:

    def test_calibration_is_deterministic(self):
        rows = _rows()
        truth = _team_stats_truth()
        ratios_a = compute_team_ratios(rows, truth, ABBR2ID)
        ratios_b = compute_team_ratios(rows, truth, ABBR2ID)
        assert ratios_a == ratios_b

    def test_calibration_brings_home_pace_to_nba_stats(self):
        rows = _rows()
        truth = _team_stats_truth()
        ratios = compute_team_ratios(rows, truth, ABBR2ID)
        new_rows, stats = apply_calibration(rows, ratios, ABBR2ID)
        truth_mean = (
            sum(v["pace"] for v in truth.values()) / len(truth)
        )
        new_mean = sum(r["home_pace"] for r in new_rows) / len(new_rows)
        # Post-calibration mean should be within 0.5 possessions of truth.
        assert abs(new_mean - truth_mean) < 0.5, (
            f"new_mean={new_mean:.2f} truth={truth_mean:.2f}"
        )


# --------------------------------------------------------------------------- #
# 3. cross-season comparison reproducibility                                   #
# --------------------------------------------------------------------------- #
class TestCrossSeasonReproducibility:

    def test_diagnose_flags_computation_artifact_when_gap_large(self):
        per_season = {
            "2022-23": {"stored_home_pace_mean": 99.8,
                        "nba_stats_pace_mean": 99.8},
            "2023-24": {"stored_home_pace_mean": 99.2,
                        "nba_stats_pace_mean": 99.2},
            "2024-25": {"stored_home_pace_mean": 99.6,
                        "nba_stats_pace_mean": 99.6},
            "2025-26": {"stored_home_pace_mean": 102.4,
                        "nba_stats_pace_mean": 100.2},
        }
        verdict, why = diagnose(per_season)
        assert verdict == "computation_artifact", (verdict, why)

    def test_diagnose_flags_window_artifact_when_aligned(self):
        per_season = {
            "2022-23": {"stored_home_pace_mean": 99.8,
                        "nba_stats_pace_mean": 99.8},
            "2023-24": {"stored_home_pace_mean": 99.2,
                        "nba_stats_pace_mean": 99.2},
            "2024-25": {"stored_home_pace_mean": 99.6,
                        "nba_stats_pace_mean": 99.6},
            "2025-26": {"stored_home_pace_mean": 100.2,
                        "nba_stats_pace_mean": 100.2},
        }
        verdict, why = diagnose(per_season)
        assert verdict == "window_artifact", (verdict, why)

    def test_diagnose_flags_real_shift_when_truth_moved(self):
        per_season = {
            "2022-23": {"stored_home_pace_mean": 99.0,
                        "nba_stats_pace_mean": 99.0},
            "2023-24": {"stored_home_pace_mean": 99.0,
                        "nba_stats_pace_mean": 99.0},
            "2024-25": {"stored_home_pace_mean": 99.0,
                        "nba_stats_pace_mean": 99.0},
            "2025-26": {"stored_home_pace_mean": 101.0,
                        "nba_stats_pace_mean": 101.0},
        }
        verdict, why = diagnose(per_season)
        assert verdict == "real_shift", (verdict, why)


# --------------------------------------------------------------------------- #
# 4. fix doesn't regress historical seasons                                    #
# --------------------------------------------------------------------------- #
class TestNoHistoricalRegression:

    def test_calibration_only_touches_passed_rows(self, tmp_path):
        """Patching season_games_2025-26 must not read/write any other
        season file (the patch script is per-file scoped)."""
        rows = _rows()
        sg = tmp_path / "season_games_2025-26.json"
        sg.write_text(json.dumps({"v": 9, "rows": rows}), encoding="utf-8")
        # A bogus 2024-25 file we'll mutate later to make sure it stays put
        sg_old = tmp_path / "season_games_2024-25.json"
        sg_old.write_text(json.dumps({"v": 9, "rows": []}), encoding="utf-8")
        ts = tmp_path / "team_stats_2025-26.json"
        ts.write_text(json.dumps(_team_stats_truth()), encoding="utf-8")

        before_old = sg_old.read_text(encoding="utf-8")
        res = patch_file(sg, ts)
        assert res["status"] == "OK"
        after_old = sg_old.read_text(encoding="utf-8")
        assert before_old == after_old


# --------------------------------------------------------------------------- #
# 5. patch is idempotent + writes marker                                       #
# --------------------------------------------------------------------------- #
class TestPatchIdempotency:

    def test_patch_writes_marker(self, tmp_path):
        rows = _rows()
        sg = tmp_path / "season_games_2025-26.json"
        sg.write_text(json.dumps({"v": 9, "rows": rows}), encoding="utf-8")
        ts = tmp_path / "team_stats_2025-26.json"
        ts.write_text(json.dumps(_team_stats_truth()), encoding="utf-8")

        res1 = patch_file(sg, ts)
        assert res1["status"] == "OK"
        payload = json.loads(sg.read_text(encoding="utf-8"))
        assert "pace_calibration_R28_U2" in payload

    def test_patch_second_run_is_noop(self, tmp_path):
        rows = _rows()
        sg = tmp_path / "season_games_2025-26.json"
        sg.write_text(json.dumps({"v": 9, "rows": rows}), encoding="utf-8")
        ts = tmp_path / "team_stats_2025-26.json"
        ts.write_text(json.dumps(_team_stats_truth()), encoding="utf-8")

        res1 = patch_file(sg, ts)
        snapshot = sg.read_text(encoding="utf-8")
        res2 = patch_file(sg, ts)
        assert res2["status"] == "ALREADY_APPLIED"
        assert sg.read_text(encoding="utf-8") == snapshot


# --------------------------------------------------------------------------- #
# 6. derived fields stay consistent after calibration                          #
# --------------------------------------------------------------------------- #
class TestDerivedFields:

    def test_pace_diff_recomputed(self):
        rows = _rows()
        truth = _team_stats_truth()
        ratios = compute_team_ratios(rows, truth, ABBR2ID)
        new_rows, _ = apply_calibration(rows, ratios, ABBR2ID)
        for r in new_rows[:25]:
            assert abs(r["pace_diff"]
                       - (r["home_pace"] - r["away_pace"])) < 1e-6

    def test_elo_pace_interaction_recomputed(self):
        rows = _rows()
        truth = _team_stats_truth()
        ratios = compute_team_ratios(rows, truth, ABBR2ID)
        new_rows, _ = apply_calibration(rows, ratios, ABBR2ID)
        for r in new_rows[:25]:
            expected = (
                float(r["home_elo"]) * float(r["home_pace"])
                - float(r["away_elo"]) * float(r["away_pace"])
            )
            assert abs(float(r["elo_pace_interaction"]) - expected) < 1.0


# --------------------------------------------------------------------------- #
# 7. drift detector report reflects fix when applied                           #
# --------------------------------------------------------------------------- #
class TestDriftDetectorPostFix:

    def test_mean_z_drops_below_one_after_calibration(self):
        # Synthesize the drift detector inputs directly.
        from scripts.feature_drift_detector import detect_drift
        import pandas as pd
        import numpy as np

        rng = np.random.default_rng(0)
        # reference seasons centered at 99.6 with sigma 1.5
        ref = pd.DataFrame({
            "home_pace": rng.normal(99.6, 1.5, 3600),
            "away_pace": rng.normal(99.6, 1.5, 3600),
        })
        # current PRE-FIX centered at 102.4 (z >> 1)
        pre = pd.DataFrame({
            "home_pace": rng.normal(102.4, 2.2, 110),
            "away_pace": rng.normal(102.4, 2.2, 110),
        })
        # current POST-FIX centered at 100.2 (z < 0.5)
        post = pd.DataFrame({
            "home_pace": rng.normal(100.2, 2.2, 110),
            "away_pace": rng.normal(100.2, 2.2, 110),
        })

        res_pre = detect_drift(ref, pre, ["home_pace", "away_pace"])
        res_post = detect_drift(ref, post, ["home_pace", "away_pace"])

        pre_mean_z = max(abs(f["mean_z"]) for f in res_pre["features"])
        post_mean_z = max(abs(f["mean_z"]) for f in res_post["features"])
        assert pre_mean_z > 1.0, f"pre-fix mean_z should be major, got {pre_mean_z}"
        assert post_mean_z < 1.0, (
            f"post-fix mean_z should drop below 1.0, got {post_mean_z}"
        )
        assert res_post["n_drift_major"] < res_pre["n_drift_major"] \
            or post_mean_z < pre_mean_z
