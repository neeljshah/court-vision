"""
tests/test_blowout_ot_v2.py — Unit tests for BlowoutOTPredictorV2.

Synthetic 100-game dataset — no NBA API calls, no network.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.blowout_ot_v2 import (
    BlowoutOTPredictorV2,
    BLOWOUT_FEATURES,
    OT_FEATURES,
    _calibration_bins,
    _engineer_features,
)


# ── Synthetic dataset ────────────────────────────────────────────────────────────

def _make_synthetic_rows(n: int = 200, seed: int = 42) -> list:
    """Generate synthetic game rows that mimic scored_games_*.json schema."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        net_h = rng.normal(0, 5)
        net_a = rng.normal(0, 5)
        spread = net_h - net_a + rng.normal(0, 8)
        total  = 220 + rng.normal(0, 12)
        season = "2022-23" if i < 80 else ("2023-24" if i < 160 else "2024-25")
        rows.append({
            "game_id":   f"TEST{i:04d}",
            "season":    season,
            "game_date": f"202{'2' if season=='2022-23' else ('3' if season=='2023-24' else '4')}"
                         f"-11-{(i % 28 + 1):02d}",
            "home_team": "LAL",
            "away_team": "BOS",
            "game_total": float(total),
            "spread":     float(spread),
            "first_half_proxy": float(total * 0.47),
            "game_pace":  float(98 + rng.normal(0, 3)),
            # Features
            "home_net_rtg":        float(net_h),
            "away_net_rtg":        float(net_a),
            "home_net_rtg_L10":    float(net_h + rng.normal(0, 1)),
            "away_net_rtg_L10":    float(net_a + rng.normal(0, 1)),
            "home_off_rtg_L10":    float(112 + net_h / 2),
            "away_off_rtg_L10":    float(112 + net_a / 2),
            "home_def_rtg_L10":    float(112 - net_h / 2),
            "away_def_rtg_L10":    float(112 - net_a / 2),
            "home_off_rtg":        float(112 + net_h / 2),
            "away_off_rtg":        float(112 + net_a / 2),
            "home_def_rtg":        float(112 - net_h / 2),
            "away_def_rtg":        float(112 - net_a / 2),
            "srs_home":            float(net_h * 0.8),
            "srs_away":            float(net_a * 0.8),
            "srs_diff":            float((net_h - net_a) * 0.8),
            "home_rest_days":      float(rng.integers(1, 5)),
            "away_rest_days":      float(rng.integers(1, 5)),
            "rest_diff":           0.0,
            "b2b_diff":            0.0,
            "home_form_l5":        float(rng.uniform(0.2, 0.8)),
            "away_form_l5":        float(rng.uniform(0.2, 0.8)),
            "home_season_win_pct": float(rng.uniform(0.3, 0.7)),
            "away_season_win_pct": float(rng.uniform(0.3, 0.7)),
            "home_pace_l10":       float(98 + rng.normal(0, 2)),
            "away_pace_l10":       float(98 + rng.normal(0, 2)),
            "pace_expectation":    float(98.0),
            "net_rtg_diff":        float(net_h - net_a),
            "win_prob_home":       float(0.5 + (net_h - net_a) * 0.02),
            "month_early":         1.0,
            "month_mid":           0.0,
            "month_late":          0.0,
            "ot_game":             int(rng.random() < 0.07),  # ~7% OT rate
        })
    return rows


class _MockPredictor(BlowoutOTPredictorV2):
    """Predictor that uses synthetic data instead of the NBA API cache."""

    def __init__(self, model_dir: str):
        super().__init__(model_dir=model_dir)
        self._rows = _make_synthetic_rows(200)

    def train(self, seasons=None):  # type: ignore[override]
        """Override to skip API calls — use synthetic rows directly."""
        import pandas as pd
        from src.prediction.blowout_ot_v2 import (
            _engineer_features, _eval_binary, _feature_importance,
            _calibration_bins, _save_model, BLOWOUT_FEATURES, OT_FEATURES,
        )
        import lightgbm as lgb
        from sklearn.calibration import CalibratedClassifierCV

        df = pd.DataFrame(self._rows)
        df = _engineer_features(df)
        df = df.sort_values("game_date").reset_index(drop=True)

        df_tv = df[df["season"] != "2024-25"].reset_index(drop=True)
        df_ho = df[df["season"] == "2024-25"].reset_index(drop=True)
        tv_cut = int(len(df_tv) * 0.70)
        df_tr  = df_tv.iloc[:tv_cut].reset_index(drop=True)
        df_val = df_tv.iloc[tv_cut:].reset_index(drop=True)

        lgb_params = dict(
            n_estimators=50, learning_rate=0.1, num_leaves=15,
            min_child_samples=5, random_state=42, n_jobs=1, verbose=-1,
        )

        blo_feats = [c for c in BLOWOUT_FEATURES if c in df.columns]
        y_bl_tr  = (df_tr["spread"].abs() > 15).astype(int).values
        y_bl_val = (df_val["spread"].abs() > 15).astype(int).values
        y_bl_ho  = (df_ho["spread"].abs() > 15).astype(int).values

        X_bl_tr  = df_tr[blo_feats].fillna(0).values.astype(float)
        X_bl_val = df_val[blo_feats].fillna(0).values.astype(float)
        X_bl_ho  = df_ho[blo_feats].fillna(0).values.astype(float)

        bl_rate = y_bl_tr.mean()
        clf_bl = lgb.LGBMClassifier(objective="binary",
                                     scale_pos_weight=(1-bl_rate)/max(bl_rate, 1e-6),
                                     **lgb_params)
        clf_bl.fit(X_bl_tr, y_bl_tr)
        cal_bl = CalibratedClassifierCV(clf_bl, method="isotonic", cv="prefit")
        cal_bl.fit(X_bl_val, y_bl_val)
        self._blowout_model = cal_bl

        ot_feats = [c for c in OT_FEATURES if c in df.columns]
        y_ot_tr  = df_tr["ot_game"].fillna(0).astype(int).values
        y_ot_val = df_val["ot_game"].fillna(0).astype(int).values
        y_ot_ho  = df_ho["ot_game"].fillna(0).astype(int).values

        X_ot_tr  = df_tr[ot_feats].fillna(0).values.astype(float)
        X_ot_val = df_val[ot_feats].fillna(0).values.astype(float)
        X_ot_ho  = df_ho[ot_feats].fillna(0).values.astype(float)

        ot_rate = y_ot_tr.mean()
        clf_ot = lgb.LGBMClassifier(objective="binary",
                                     scale_pos_weight=(1-ot_rate)/max(ot_rate, 1e-6),
                                     **lgb_params)
        clf_ot.fit(X_ot_tr, y_ot_tr)
        cal_ot = CalibratedClassifierCV(clf_ot, method="isotonic", cv="prefit")
        cal_ot.fit(X_ot_val, y_ot_val)
        self._ot_model = cal_ot

        bl_probs_val = cal_bl.predict_proba(X_bl_val)[:, 1]
        ot_probs_val = cal_ot.predict_proba(X_ot_val)[:, 1]

        bl_ho_probs = cal_bl.predict_proba(X_bl_ho)[:, 1]
        ot_ho_probs = cal_ot.predict_proba(X_ot_ho)[:, 1]

        _save_model(cal_bl, os.path.join(self.model_dir, "blowout_v2.pkl"))
        _save_model(cal_ot, os.path.join(self.model_dir, "ot_v2.pkl"))

        results = {
            "blowout": {
                **_eval_binary(y_bl_val, bl_probs_val),
                "holdout": _eval_binary(y_bl_ho, bl_ho_probs),
                "blowout_rate": round(float(bl_rate), 4),
                "n": len(df_tr) + len(df_val),
                "features": blo_feats,
                "calibration_bins": _calibration_bins(y_bl_val, bl_probs_val),
            },
            "ot": {
                **_eval_binary(y_ot_val, ot_probs_val),
                "holdout": _eval_binary(y_ot_ho, ot_ho_probs),
                "ot_rate": round(float(ot_rate), 4),
                "n": len(df_tr) + len(df_val),
                "features": ot_feats,
                "calibration_bins": _calibration_bins(y_ot_val, ot_probs_val),
            },
        }
        self._save_metrics(results)
        return results


# ── Tests ────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def trained_predictor(tmp_path_factory):
    model_dir = str(tmp_path_factory.mktemp("models"))
    p = _MockPredictor(model_dir=model_dir)
    p.train()
    return p


def test_blowout_prob_in_range(trained_predictor):
    """predict_blowout() must return a value in [0, 1]."""
    feats = {f: 0.0 for f in BLOWOUT_FEATURES}
    feats["talent_gap_l10"] = 5.0
    feats["home_net_rtg_L10"] = 4.0
    prob = trained_predictor.predict_blowout(feats)
    assert 0.0 <= prob <= 1.0, f"blowout prob out of range: {prob}"


def test_ot_prob_in_range(trained_predictor):
    """predict_ot() must return a value in [0, 1]."""
    feats = {f: 0.0 for f in OT_FEATURES}
    feats["talent_gap_l10"] = 1.0
    feats["is_division_rivalry"] = 1.0
    prob = trained_predictor.predict_ot(feats)
    assert 0.0 <= prob <= 1.0, f"OT prob out of range: {prob}"


def test_metrics_file_produced(trained_predictor):
    """Training must produce blowout_ot_v2_metrics.json."""
    metrics_path = os.path.join(trained_predictor.model_dir, "blowout_ot_v2_metrics.json")
    assert os.path.exists(metrics_path), "metrics file not found"
    with open(metrics_path) as f:
        m = json.load(f)
    assert "blowout" in m
    assert "ot" in m
    assert "acc" in m["blowout"]
    assert "brier" in m["blowout"]
    assert "auc" in m["blowout"]


def test_model_files_produced(trained_predictor):
    """Both pkl files must exist after training."""
    assert os.path.exists(os.path.join(trained_predictor.model_dir, "blowout_v2.pkl"))
    assert os.path.exists(os.path.join(trained_predictor.model_dir, "ot_v2.pkl"))


def test_blowout_monotone_direction(trained_predictor):
    """Higher talent_gap should give higher blowout probability."""
    base = {f: 0.0 for f in BLOWOUT_FEATURES}
    low_gap  = {**base, "talent_gap_l10": 1.0, "srs_diff": 1.0}
    high_gap = {**base, "talent_gap_l10": 12.0, "srs_diff": 10.0}
    p_low  = trained_predictor.predict_blowout(low_gap)
    p_high = trained_predictor.predict_blowout(high_gap)
    assert p_high >= p_low - 0.05, (
        f"Higher talent_gap should yield higher blowout prob: "
        f"low={p_low:.4f} high={p_high:.4f}"
    )


def test_ot_monotone_direction(trained_predictor):
    """Close rivalry game should yield higher OT prob than lopsided game."""
    base = {f: 0.0 for f in OT_FEATURES}
    lopsided = {**base, "talent_gap_l10": 15.0, "is_division_rivalry": 0.0}
    close    = {**base, "talent_gap_l10": 0.5,  "is_division_rivalry": 1.0,
                "close_game_freq_home": 0.9, "close_game_freq_away": 0.9}
    p_lop   = trained_predictor.predict_ot(lopsided)
    p_close = trained_predictor.predict_ot(close)
    assert p_close >= p_lop - 0.05, (
        f"Close game should yield higher OT prob: lopsided={p_lop:.4f} close={p_close:.4f}"
    )


def test_calibration_bins_non_decreasing(trained_predictor):
    """Calibration bins: predicted_mid should be monotone (loosely — ±0.05 tolerance)."""
    metrics_path = os.path.join(trained_predictor.model_dir, "blowout_ot_v2_metrics.json")
    with open(metrics_path) as f:
        m = json.load(f)

    for model_key in ("blowout", "ot"):
        bins = m.get(model_key, {}).get("calibration_bins", [])
        if len(bins) < 3:
            continue  # not enough bins to test (sparse OT data)
        for i in range(len(bins) - 1):
            lo_predicted = bins[i]["predicted_mid"]
            hi_predicted = bins[i + 1]["predicted_mid"]
            lo_actual    = bins[i]["actual_rate"]
            hi_actual    = bins[i + 1]["actual_rate"]
            # Adjacent bins with higher predicted prob should have higher actual rate
            # Allow ±0.05 tolerance for noise
            if hi_predicted > lo_predicted + 0.05:
                assert hi_actual >= lo_actual - 0.05, (
                    f"[{model_key}] Calibration not monotone at bins {i}/{i+1}: "
                    f"predicted {lo_predicted:.2f}→{hi_predicted:.2f} "
                    f"but actual {lo_actual:.3f}→{hi_actual:.3f}"
                )


def test_reload_from_disk(trained_predictor):
    """Model should be loadable from disk and produce valid probabilities."""
    fresh = BlowoutOTPredictorV2(model_dir=trained_predictor.model_dir)
    feats = {f: 0.0 for f in BLOWOUT_FEATURES}
    prob = fresh.predict_blowout(feats)
    assert 0.0 <= prob <= 1.0

    feats_ot = {f: 0.0 for f in OT_FEATURES}
    prob_ot = fresh.predict_ot(feats_ot)
    assert 0.0 <= prob_ot <= 1.0


def test_calibration_bins_utility():
    """Unit test for _calibration_bins helper."""
    rng = np.random.default_rng(0)
    y_true = rng.integers(0, 2, 100)
    y_prob = rng.uniform(0, 1, 100)
    bins = _calibration_bins(y_true, y_prob, n_bins=5)
    assert len(bins) >= 1
    for b in bins:
        assert 0 <= b["actual_rate"] <= 1
        assert b["count"] > 0
        assert 0 <= b["predicted_mid"] <= 1
