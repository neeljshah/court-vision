"""tests/test_streak_features.py -- R10_M16 hot-hand / streak feature coverage.

Three required tests:
  (a) streak features compute correctly for a known 5-game hot streak.
  (b) gating is correct: PTS/REB/AST get NO streak inputs in production.
  (c) regression check that the trained BLK endQ3 head's MAE on a held-out
      fold drops by >= 10% vs the zero-residual baseline. Skipped when the
      head artifact is absent (CI without trained artifacts).
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction import streak_features as sf
from src.prediction import residual_heads as rh


# ─────────────────────────────────────────────────────────────────────────────
# (a) Compute correctness — 5-game hot streak with closed-form expectations.
# ─────────────────────────────────────────────────────────────────────────────

def _build_history(values_by_stat: Dict[str, List[float]], stat_under_test: str = "blk",
                   start_year: int = 2025) -> List[Tuple[datetime, Dict[str, float]]]:
    """Build a list of (date, stat-row) tuples. Each value gets a distinct day."""
    n = len(values_by_stat[stat_under_test])
    rows = []
    for i in range(n):
        d = datetime(start_year, 1, i + 1)
        row = {
            "pts":  values_by_stat.get("pts",  [0.0] * n)[i],
            "reb":  values_by_stat.get("reb",  [0.0] * n)[i],
            "ast":  values_by_stat.get("ast",  [0.0] * n)[i],
            "fg3m": values_by_stat.get("fg3m", [0.0] * n)[i],
            "stl":  values_by_stat.get("stl",  [0.0] * n)[i],
            "blk":  values_by_stat.get("blk",  [0.0] * n)[i],
            "tov":  values_by_stat.get("tov",  [0.0] * n)[i],
            "min":  30.0,
        }
        rows.append((d, row))
    return rows


def test_compute_hot_streak_known_sequence():
    """5-game hot streak followed by 15 cool games -> known closed-form values."""
    # 20 priors: first 15 BLK=0.0, last 5 BLK=3.0 (the "hot" streak).
    blk_vals = [0.0] * 15 + [3.0] * 5
    history = _build_history({"blk": blk_vals}, stat_under_test="blk")
    target = datetime(2026, 1, 1)

    feats = sf.compute_streak_features_for_stat(history, target, "blk")

    # All 20 priors visible -> L3 mean = 3.0 (last 3 are 3.0).
    # L20 mean = (0*15 + 3*5)/20 = 15/20 = 0.75.
    # L20 std (population) = sqrt(sum((v - 0.75)^2)/20)
    #   = sqrt((15 * 0.75^2 + 5 * 2.25^2) / 20)
    #   = sqrt((8.4375 + 25.3125)/20) = sqrt(1.6875) = 1.29903810567...
    # z = (3.0 - 0.75)/(1.29903810567 + 1e-6) = 1.73205...
    expected_mean_l3 = 3.0
    expected_mean_l20 = 0.75
    expected_std_l20 = math.sqrt(1.6875)
    expected_z = (expected_mean_l3 - expected_mean_l20) / (expected_std_l20 + 1e-6)

    assert feats["hot_streak_blk"] == pytest.approx(expected_z, rel=1e-5)
    assert feats["cold_streak_blk"] == pytest.approx(-expected_z, rel=1e-5)
    # consec_above: walks backward from latest; latest 5 BLK=3 > mean_l20 (0.75).
    # The 6th-from-last is BLK=0 (< 0.75) -> streak breaks. So consec == 5.
    assert feats["consec_above_blk"] == 5.0
    assert feats["n_prior_blk"] == 20.0


def test_compute_streak_strict_shift1_excludes_target_date():
    """Games dated on or after target_date must NOT contribute to features."""
    # 5 priors then a hot blowout on target_date itself; that final game must
    # be invisible to the feature computation.
    history = _build_history(
        {"blk": [0.0, 0.0, 0.0, 0.0, 0.0, 99.0]},
        stat_under_test="blk",
    )
    # Target is on the 6th history date — should exclude that row.
    target = history[-1][0]

    feats = sf.compute_streak_features_for_stat(history, target, "blk")
    # Only 5 zero-priors visible -> mean_l3 = mean_l20 = 0, z = 0/eps -> 0.
    assert feats["hot_streak_blk"] == pytest.approx(0.0, abs=1e-6)
    assert feats["consec_above_blk"] == 0.0
    assert feats["n_prior_blk"] == 5.0


def test_compute_returns_empty_for_non_ship_stat():
    """compute_streak_features_for_stat returns {} for pts/reb/ast."""
    history = _build_history({"pts": [10.0] * 5}, stat_under_test="pts")
    target = datetime(2026, 1, 1)
    for non_ship in ("pts", "reb", "ast"):
        assert sf.compute_streak_features_for_stat(history, target, non_ship) == {}


# ─────────────────────────────────────────────────────────────────────────────
# (b) Production gating — PTS/REB/AST must receive NO streak inputs.
# ─────────────────────────────────────────────────────────────────────────────

def test_ship_streak_stats_includes_only_4_winners():
    """SHIP_STREAK_STATS is exactly {fg3m, stl, blk, tov}."""
    assert sf.SHIP_STREAK_STATS == frozenset({"fg3m", "stl", "blk", "tov"})


def test_streak_feature_names_only_for_ship_stats():
    """STREAK_FEATURE_NAMES_PER_STAT has entries only for the 4 winners."""
    keys = set(sf.STREAK_FEATURE_NAMES_PER_STAT.keys())
    assert keys == {"fg3m", "stl", "blk", "tov"}
    for stat, names in sf.STREAK_FEATURE_NAMES_PER_STAT.items():
        assert len(names) == 4
        assert names == [
            f"hot_streak_{stat}",
            f"cold_streak_{stat}",
            f"consec_above_{stat}",
            f"n_prior_{stat}",
        ]


def test_residual_heads_legacy_schema_for_non_ship_stats():
    """For pts/reb/ast: legacy 14-feature schema, no streak names present.

    Meta JSON is allowed to exist for these stats (set by the new trainer)
    but must contain ONLY the legacy 14 features. The live loader's
    `_feature_names_for_stat` is the gate consumers query.
    """
    rh.reset_head_caches()
    feats_pts = rh._feature_names_for_stat("pts")
    feats_reb = rh._feature_names_for_stat("reb")
    feats_ast = rh._feature_names_for_stat("ast")
    for feats in (feats_pts, feats_reb, feats_ast):
        for name in feats:
            assert not name.startswith("hot_streak_"), (
                f"non-ship stat must not have streak inputs: {name}"
            )
            assert not name.startswith("cold_streak_"), (
                f"non-ship stat must not have streak inputs: {name}"
            )
            assert not name.startswith("consec_above_"), (
                f"non-ship stat must not have streak inputs: {name}"
            )
            assert not name.startswith("n_prior_"), (
                f"non-ship stat must not have streak inputs: {name}"
            )


def test_apply_residual_correction_safe_when_streak_stats_absent(monkeypatch):
    """When fg3m/stl/blk/tov heads are absent, pts/reb/ast still get corrected.

    Force a head set that contains ONLY pts to prove streak machinery is
    inert for non-shipping stats.
    """
    rh.reset_head_caches()

    class _ZeroHead:
        def predict(self, x):
            # Predict +1 residual so a change is visible.
            return [1.0]

    monkeypatch.setattr(rh, "_HEAD_CACHE", {"pts": _ZeroHead()}, raising=False)
    monkeypatch.setattr(rh, "_HEAD_META_CACHE", {}, raising=False)
    monkeypatch.setattr(rh, "_POSITIONS_CACHE", {}, raising=False)

    snap = {
        "home_team": "LAL", "away_team": "BOS",
        "home_score": 60.0, "away_score": 55.0,
        "game_date": "2025-12-15",
        "players": [
            {"player_id": 1, "team": "LAL", "pts": 20, "reb": 5, "ast": 3,
             "fg3m": 2, "stl": 1, "blk": 1, "tov": 2, "pf": 2, "min": 36},
        ],
    }
    projs = {(1, "pts"): 25.0, (1, "reb"): 7.0, (1, "fg3m"): 3.0, (1, "blk"): 2.0}

    out = rh.apply_residual_correction(snap, projs)
    # PTS got +1 residual -> 26.0; REB has no head -> unchanged.
    assert out[(1, "pts")] == pytest.approx(26.0, rel=1e-5)
    assert out[(1, "reb")] == 7.0
    assert out[(1, "fg3m")] == 3.0  # no head -> unchanged
    assert out[(1, "blk")] == 2.0   # no head -> unchanged


# ─────────────────────────────────────────────────────────────────────────────
# (c) Regression test: trained BLK endQ3 head must beat zero-residual MAE by
#     >= 10% on a held-out fold. Skipped when the head artifact is absent.
# ─────────────────────────────────────────────────────────────────────────────

def _head_artifact_path(stat: str) -> str:
    return os.path.join(PROJECT_DIR, "data", "models", "residual_heads", f"{stat}.lgb")


def _meta_artifact_path(stat: str) -> str:
    return os.path.join(PROJECT_DIR, "data", "models", "residual_heads", f"{stat}_meta.json")


@pytest.mark.skipif(
    not os.path.exists(_head_artifact_path("blk")),
    reason="BLK endQ3 head artifact not built; run scripts/train_residual_heads_endq3_streak.py",
)
def test_blk_endq3_head_beats_baseline_by_10pct():
    """The trained BLK head must reduce MAE by >= 10% on a held-out fold.

    Reuses the training meta JSON's fold breakdown -- the trainer records
    mae_model + mae_zero per fold. We pick the fold where mae_zero is
    largest (last chronological fold, the most realistic OOF block) and
    assert mae_model / mae_zero <= 0.90.
    """
    meta_path = _meta_artifact_path("blk")
    assert os.path.exists(meta_path), (
        "blk_meta.json missing; rerun the trainer to produce it alongside the .lgb"
    )
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)

    # Verify the schema includes streak features (no silent regression to
    # the legacy 14-feature schema).
    assert "features" in meta
    assert any(name.startswith("hot_streak_blk") for name in meta["features"]), (
        f"BLK head trained without streak features. features={meta['features']}"
    )

    # Inspect training report for per-fold MAEs -- the trainer writes
    # both training_report_R10_M16.json and the per-stat meta. We use the
    # per-stat meta's fold breakdown ('folds' key).
    folds = meta.get("folds") or []
    if not folds:
        # Older meta may not contain folds -- fall back to the consolidated
        # training report.
        report_path = os.path.join(
            PROJECT_DIR, "data", "models", "residual_heads",
            "training_report_R10_M16.json",
        )
        assert os.path.exists(report_path), (
            "no fold breakdown available; trainer didn't write a report"
        )
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
        for entry in report.get("trained_stats", []):
            if entry.get("stat") == "blk":
                folds = entry.get("folds") or []
                break

    # Pick the last fold with a real mae_zero/mae_model pair.
    eligible = [d for d in folds if "mae_model" in d and "mae_zero" in d]
    assert eligible, "no eligible BLK folds with MAE numbers"
    last_fold = eligible[-1]
    mae_model = float(last_fold["mae_model"])
    mae_zero = float(last_fold["mae_zero"])
    assert mae_zero > 0, "degenerate fold; zero-residual MAE is 0"
    ratio = mae_model / mae_zero
    assert ratio <= 0.90, (
        f"BLK head MAE reduction <10%: mae_model={mae_model:.5f} "
        f"mae_zero={mae_zero:.5f} ratio={ratio:.4f} (need <= 0.90)"
    )
