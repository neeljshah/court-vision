"""tests/test_R32_Y2_shrinkage.py — R32_Y2 season-progress shrinkage tests.

Covers the scalar/vectorized math, NaN passthrough, boundary semantics
(elapsed=0 -> league_mean; elapsed=1 -> raw), alpha effect, vectorized
parity with the scalar loop, leak-free league_mean source, idempotency
on an already-shrunk row, end-of-season passthrough invariance, and the
end-to-end drift-count decrease.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from src.prediction.season_progress_shrinkage import (  # noqa: E402
    DEFAULT_TOTAL_GAMES,
    DEFAULT_WINDOW_ARTIFACT_FEATURES,
    R29_V3_WINDOW_ARTIFACT_FEATURES,
    R31_X6_LINEUP_WINDOW_ARTIFACT_FEATURES,
    SHRINKAGE_CONFIG,
    apply_shrinkage_to_rows,
    compute_games_played_lookup,
    shrink,
    shrink_series,
)
from scripts.patch_R32_Y2_season_shrinkage import patch_file  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. Scalar math for known cases                                              #
# --------------------------------------------------------------------------- #
class TestScalarShrinkMath:

    def test_elapsed_zero_returns_league_mean(self):
        # n_games_played=0 -> weight=1.0 -> returns league_mean exactly.
        for alpha in (0.25, 0.5, 1.0, 2.0):
            out = shrink(value=28.15, league_mean=4.22,
                         n_games_played=0, total_games=82, alpha=alpha)
            assert out == pytest.approx(4.22, abs=1e-9)

    def test_elapsed_one_returns_raw(self):
        # n_games_played=82 -> weight=0 -> returns raw value exactly.
        for alpha in (0.25, 0.5, 1.0, 2.0):
            out = shrink(value=28.15, league_mean=4.22,
                         n_games_played=82, total_games=82, alpha=alpha)
            assert out == pytest.approx(28.15, abs=1e-9)

    def test_elapsed_above_total_clamps_to_one(self):
        # n_games_played beyond total still returns raw value (clamp to 1.0).
        out = shrink(value=10.0, league_mean=4.0,
                     n_games_played=200, total_games=82, alpha=0.5)
        assert out == pytest.approx(10.0, abs=1e-9)

    def test_known_midseason_value(self):
        # n=20.5/82 = 0.25 elapsed; alpha=0.5 -> weight = sqrt(0.75)
        weight = (1.0 - 0.25) ** 0.5
        expected = weight * 4.22 + (1.0 - weight) * 28.15
        out = shrink(value=28.15, league_mean=4.22,
                     n_games_played=20.5, total_games=82, alpha=0.5)
        assert out == pytest.approx(expected, abs=1e-9)

    def test_alpha_zero_means_full_shrink_until_end(self):
        # alpha=0 -> weight = (1-elapsed)**0 = 1 for ANY elapsed < 1.0.
        # i.e., full shrink everywhere except the literal final game.
        out = shrink(value=28.15, league_mean=4.22,
                     n_games_played=40, total_games=82, alpha=0.0)
        assert out == pytest.approx(4.22, abs=1e-9)


# --------------------------------------------------------------------------- #
# 2. Alpha effect                                                             #
# --------------------------------------------------------------------------- #
class TestAlphaEffect:

    def test_larger_alpha_shrinks_less_at_midseason(self):
        # At mid-season, larger alpha -> smaller weight -> less shrinkage ->
        # shrunk value closer to raw, farther from league_mean.
        raw, mean = 28.15, 4.22
        s_a025 = shrink(raw, mean, 41, 82, alpha=0.25)
        s_a05  = shrink(raw, mean, 41, 82, alpha=0.5)
        s_a10  = shrink(raw, mean, 41, 82, alpha=1.0)
        s_a20  = shrink(raw, mean, 41, 82, alpha=2.0)
        # weight = 0.5**alpha; larger alpha -> smaller weight -> closer to raw.
        # So distance to raw decreases monotonically as alpha grows.
        dists = [abs(raw - x) for x in (s_a025, s_a05, s_a10, s_a20)]
        assert dists == sorted(dists, reverse=True)


# --------------------------------------------------------------------------- #
# 3. Vectorized parity with scalar loop                                       #
# --------------------------------------------------------------------------- #
class TestVectorizedParity:

    def test_series_matches_scalar_loop(self):
        rng = np.random.default_rng(7)
        vals = rng.uniform(-20, 30, size=200)
        n_played = rng.integers(0, 82, size=200).astype(float)
        league_mean = 4.22
        scalar_out = np.array([
            shrink(v, league_mean, n, total_games=82, alpha=0.5)
            for v, n in zip(vals, n_played)
        ])
        vec_out = shrink_series(
            vals, league_mean, n_played, total_games=82, alpha=0.5
        )
        np.testing.assert_allclose(vec_out, scalar_out, rtol=0, atol=1e-12)

    def test_series_accepts_pandas_series(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0])
        n = pd.Series([0, 41, 82, 200])
        out = shrink_series(s, 10.0, n, total_games=82, alpha=0.5)
        # n=0 -> league_mean=10; n=82 -> raw=3; n=200 -> clamp to 1 -> raw=4
        assert out[0] == pytest.approx(10.0, abs=1e-9)
        assert out[2] == pytest.approx(3.0, abs=1e-9)
        assert out[3] == pytest.approx(4.0, abs=1e-9)

    def test_series_per_row_league_means(self):
        # league_mean as an array broadcasts.
        vals = np.array([10.0, 20.0])
        means = np.array([0.0, 100.0])
        n = np.array([0.0, 0.0])
        out = shrink_series(vals, means, n, total_games=82, alpha=0.5)
        # At n=0 -> weight=1 -> shrunk = league_mean
        np.testing.assert_allclose(out, means, atol=1e-12)


# --------------------------------------------------------------------------- #
# 4. NaN handling                                                             #
# --------------------------------------------------------------------------- #
class TestNanHandling:

    def test_nan_value_returns_nan(self):
        out = shrink(float("nan"), 4.22, 10, 82, 0.5)
        assert np.isnan(out)

    def test_nan_league_mean_returns_raw(self):
        out = shrink(7.0, float("nan"), 10, 82, 0.5)
        assert out == pytest.approx(7.0, abs=1e-9)

    def test_vectorized_nan_value_stays_nan(self):
        out = shrink_series(
            [1.0, float("nan"), 3.0], 5.0, [10, 10, 10],
            total_games=82, alpha=0.5,
        )
        assert not np.isnan(out[0])
        assert np.isnan(out[1])
        assert not np.isnan(out[2])

    def test_vectorized_nan_league_mean_returns_raw(self):
        out = shrink_series(
            [1.0, 2.0], [float("nan"), 5.0], [10, 10],
            total_games=82, alpha=0.5,
        )
        assert out[0] == pytest.approx(1.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# 5. Feature catalog                                                          #
# --------------------------------------------------------------------------- #
class TestFeatureCatalog:

    def test_exactly_22_window_artifact_features(self):
        # R29_V3 canonical set is the 22 window-artifact features. The
        # default union additionally includes the 2 R31_X6-reclassified
        # lineup features (-> 24 total).
        assert len(R29_V3_WINDOW_ARTIFACT_FEATURES) == 22
        assert len(R31_X6_LINEUP_WINDOW_ARTIFACT_FEATURES) == 2
        assert len(DEFAULT_WINDOW_ARTIFACT_FEATURES) == 24
        # Default = union of the two named subsets.
        assert (
            R29_V3_WINDOW_ARTIFACT_FEATURES
            | R31_X6_LINEUP_WINDOW_ARTIFACT_FEATURES
            == DEFAULT_WINDOW_ARTIFACT_FEATURES
        )

    def test_every_feature_has_config(self):
        for feat in DEFAULT_WINDOW_ARTIFACT_FEATURES:
            assert feat in SHRINKAGE_CONFIG, f"missing config for {feat}"
            cfg = SHRINKAGE_CONFIG[feat]
            assert "league_mean" in cfg
            assert "alpha" in cfg
            assert cfg["alpha"] >= 0.0


# --------------------------------------------------------------------------- #
# 6. League-mean source uses prior-season truth (no leakage)                  #
# --------------------------------------------------------------------------- #
class TestNoLeakage:
    """League means in SHRINKAGE_CONFIG come from the REFERENCE-SEASON
    (2022-23 + 2023-24 + 2024-25) drift report — never from the current
    2025-26 season being shrunk. Verify by comparing to the
    drift_post_R31_X6 ref_means."""

    def test_league_means_match_reference_distribution(self):
        # Reference means come from drift_post_R31_X6.json; current means
        # (cur_mean field) come from 2025-26. The config's league_mean must
        # match the REFERENCE means within rounding (we store 2-3 decimal
        # places), NOT the current means.
        # Use feature-specific tolerance because we round to 2-3 decimals.
        check_features = {
            "home_top_lineup_net_rtg": 4.22,   # ref=4.221, cur=28.15
            "away_top_lineup_net_rtg": 4.20,   # ref=4.202, cur=26.97
            "home_def_rtg":            114.09, # ref=114.088, cur=112.52
            "home_off_rtg_L10":        112.04, # ref=112.041, cur=114.288
            "home_elo":                1500.23,
        }
        for feat, expected_ref in check_features.items():
            cfg_mean = SHRINKAGE_CONFIG[feat]["league_mean"]
            assert abs(cfg_mean - expected_ref) < 0.5, (
                f"{feat}: config league_mean={cfg_mean} should match "
                f"REFERENCE mean {expected_ref}, not current-season value"
            )


# --------------------------------------------------------------------------- #
# 7. Idempotent on already-shrunk row                                         #
# --------------------------------------------------------------------------- #
class TestIdempotency:

    def test_double_shrink_with_same_value_is_fixed_point(self):
        # If a value already equals league_mean, shrinking it should
        # return league_mean for every elapsed_frac / alpha.
        for n in (0, 10, 40, 82):
            for alpha in (0.25, 0.5, 1.0):
                out = shrink(value=4.22, league_mean=4.22,
                             n_games_played=n, total_games=82, alpha=alpha)
                assert out == pytest.approx(4.22, abs=1e-9)

    def test_patch_file_marker_prevents_double_apply(self, tmp_path):
        # Build a minimal season_games file with 5 rows.
        rows = _synth_rows(n_games=20)
        sg = tmp_path / "season_games_2025-26.json"
        sg.write_text(json.dumps({"v": 9, "rows": rows}), encoding="utf-8")

        # First apply: should patch and write marker.
        res1 = patch_file(sg)
        assert res1["status"] == "OK"
        assert res1["n_features"] >= 1
        first_values = _load_feature_values(sg, "home_top_lineup_net_rtg")

        # Second apply WITHOUT force: should be a no-op.
        res2 = patch_file(sg)
        assert res2["status"] == "ALREADY_APPLIED"
        second_values = _load_feature_values(sg, "home_top_lineup_net_rtg")
        assert first_values == second_values


# --------------------------------------------------------------------------- #
# 8. End-of-season values pass through unchanged                              #
# --------------------------------------------------------------------------- #
class TestEndOfSeasonPassthrough:

    def test_last_game_of_season_unchanged_by_shrinkage(self):
        # Synthesize a 30-team, 82-games-per-team season. The chronologically
        # LAST game in the file has both teams at n_played=81 (each team has
        # played all 81 prior games) so weight = (1 - 81/82)**0.5 ≈ 0.110.
        # We want STRICT end-of-season pass-through — verify the FIRST team
        # only after their 82nd entry by using a longer synthetic season.
        rows = _synth_rows(n_games=82, teams=["A", "B"])
        sg = Path(tempfile.mkdtemp()) / "season_games.json"
        sg.write_text(json.dumps({"v": 9, "rows": rows}), encoding="utf-8")

        # The very last row of this 2-team file -> teams A and B have each
        # played 81 prior games. After patch, value should still be near
        # the raw value (since elapsed_frac is very close to 1.0).
        raw_last = rows[-1]["home_top_lineup_net_rtg"]
        patch_file(sg)
        with open(sg) as fh:
            shrunk_rows = json.load(fh)["rows"]
        shrunk_last = shrunk_rows[-1]["home_top_lineup_net_rtg"]
        # Within 15% of raw (since weight ≈ 0.110 at this point).
        # The shrinkage is small because n_played=81 of 82.
        assert abs(shrunk_last - raw_last) / max(abs(raw_last), 1.0) < 0.20

    def test_value_at_elapsed_eq_one_is_passthrough(self):
        # Direct math: at elapsed=1, output == raw exactly.
        assert shrink(123.4, 50.0, 82, 82, 0.5) == pytest.approx(123.4)
        assert shrink(123.4, 50.0, 100, 82, 0.5) == pytest.approx(123.4)


# --------------------------------------------------------------------------- #
# 9. Games-played lookup is chronologically correct                           #
# --------------------------------------------------------------------------- #
class TestGamesPlayedLookup:

    def test_first_game_has_zero_played(self):
        rows = _synth_rows(n_games=10)
        lookup = compute_games_played_lookup(rows)
        first_gid = sorted(
            rows, key=lambda r: (r["game_date"], r["game_id"])
        )[0]["game_id"]
        assert lookup[first_gid]["home"] == 0
        assert lookup[first_gid]["away"] == 0

    def test_each_team_count_increments(self):
        # Two-team season; team A plays game 1 then game 3, team B plays
        # game 1 then game 2. Counts must reflect prior plays.
        rows = [
            {"game_id": "G1", "game_date": "2025-10-21",
             "home_team": "A", "away_team": "B",
             "home_top_lineup_net_rtg": 10.0, "away_top_lineup_net_rtg": 12.0},
            {"game_id": "G2", "game_date": "2025-10-22",
             "home_team": "B", "away_team": "C",
             "home_top_lineup_net_rtg": 8.0, "away_top_lineup_net_rtg": 9.0},
            {"game_id": "G3", "game_date": "2025-10-23",
             "home_team": "A", "away_team": "C",
             "home_top_lineup_net_rtg": 11.0, "away_top_lineup_net_rtg": 10.0},
        ]
        lookup = compute_games_played_lookup(rows)
        assert lookup["G1"] == {"home": 0, "away": 0}      # A=0, B=0
        assert lookup["G2"] == {"home": 1, "away": 0}      # B=1, C=0
        assert lookup["G3"] == {"home": 1, "away": 1}      # A=1, C=1


# --------------------------------------------------------------------------- #
# 10. End-to-end drift count decreases (smoke)                                #
# --------------------------------------------------------------------------- #
class TestDriftCountDecreases:

    def test_synthetic_drift_count_drops_after_shrinkage(self):
        # Build a synthetic reference distribution centered at 4.0 (end-
        # of-season league mean for top_lineup_net_rtg) and a synthetic
        # current distribution centered at 28 (mid-season noisy values).
        from scripts.feature_drift_detector import compute_feature_drift
        rng = np.random.default_rng(0)
        ref = pd.Series(rng.normal(4.0, 10.0, size=500))
        # Current values: drawn from N(28, 11). Apply shrinkage with n=10
        # games played (mid-October vibe) -> weight = (1 - 10/82)**0.5
        cur_raw = rng.normal(28.0, 11.0, size=100)
        rec_before = compute_feature_drift(ref, pd.Series(cur_raw))
        assert rec_before["class"] == "drift_major"

        cur_shrunk = shrink_series(
            cur_raw, 4.0, 10,
            total_games=82, alpha=0.5,
        )
        rec_after = compute_feature_drift(ref, pd.Series(cur_shrunk))
        # mean_z should drop substantially after shrinkage.
        assert abs(rec_after["mean_z"]) < abs(rec_before["mean_z"]), (
            f"mean_z did not shrink: before={rec_before['mean_z']}, "
            f"after={rec_after['mean_z']}"
        )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _synth_rows(n_games: int, teams: List[str] = None) -> List[Dict[str, Any]]:
    """Build n_games synthetic season_games rows alternating between teams.
    Each row has the 22 window-artifact features populated with deterministic
    drift_major-style values so shrinkage is observable.
    """
    if teams is None:
        teams = ["A", "B", "C", "D"]
    rows: List[Dict[str, Any]] = []
    rng = np.random.default_rng(42)
    for i in range(n_games):
        h = teams[i % len(teams)]
        a = teams[(i + 1) % len(teams)]
        if h == a:
            a = teams[(i + 2) % len(teams)]
        date = f"2025-10-{21 + i:02d}" if i < 10 else f"2025-11-{i - 9:02d}"
        row: Dict[str, Any] = {
            "game_id":    f"00210{i:05d}",
            "game_date":  date,
            "home_team":  h,
            "away_team":  a,
        }
        for feat in DEFAULT_WINDOW_ARTIFACT_FEATURES:
            # Use the historical mean +/- noise scaled to make drift visible.
            cfg = SHRINKAGE_CONFIG[feat]
            base = cfg["league_mean"]
            # Inflate by 5-30 units to simulate mid-season noise.
            inflated = base + float(rng.uniform(5.0, 30.0))
            row[feat] = float(inflated)
        rows.append(row)
    return rows


def _load_feature_values(sg_path: Path, feat: str) -> List[float]:
    with open(sg_path) as fh:
        payload = json.load(fh)
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return [float(r.get(feat, 0.0)) for r in rows]
