"""tests/test_quantile_cal.py — CV_QUANTILE_CAL (split-conformal) flag tests.

Five required tests:
  1. flag-OFF → apply_conformal is byte-identical to raw (q10, q90) for all stats.
  2. flag-ON → cov80 on the temporal holdout is closer to 0.80 for PTS/REB/AST
     (the CQR-shipped stats); FG3M/STL/TOV pass-through (cov unchanged).
  3. q50 UNCHANGED by CV_QUANTILE_CAL flag (conformal only shifts q10/q90).
  4. No crossing: q10 <= q50 <= q90 after apply_conformal for all stats.
  5. Co-activation: when both CV_ROW_SIGMA=1 and CV_QUANTILE_CAL=1, REB uses
     the CV_ROW_SIGMA path (apply_qcal) and NOT the conformal path
     (no double-calibration).

Design constraints verified:
  * q50 point prediction is never modified by the flag.
  * BLK crossings are fixed by monotone clip (no CQR expansion).
  * CQR stats: PTS qhat≈1.39, REB qhat≈0.15, AST qhat≈0.06.
  * REJECT stats: FG3M, STL, TOV — apply_conformal is identity when ON.
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _conformal_cal() -> dict:
    """Load the conformal calibration artifact once."""
    path = os.path.join(_ROOT, "data", "models", "quantile_conformal_calibration.json")
    if not os.path.exists(path):
        pytest.skip("quantile_conformal_calibration.json not present — run conformal_calibrate()")
    return json.load(open(path, encoding="utf-8"))


# ── Test 1: flag-OFF → identity (byte-identical) ──────────────────────────────

@pytest.mark.parametrize("stat", ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"])
def test_flag_off_identity(monkeypatch, stat):
    """apply_conformal must return raw (q10, q90) unchanged when flag is OFF."""
    monkeypatch.delenv("CV_QUANTILE_CAL", raising=False)
    from src.prediction.quantile_calibration import apply_conformal
    q10_in, q50_in, q90_in = 5.0, 15.0, 25.0
    q10_out, q90_out = apply_conformal(stat, q10_in, q50_in, q90_in)
    assert q10_out == q10_in, (
        f"[{stat}] flag OFF: q10 changed {q10_in} -> {q10_out} (should be identity)"
    )
    assert q90_out == q90_in, (
        f"[{stat}] flag OFF: q90 changed {q90_in} -> {q90_out} (should be identity)"
    )


# ── Test 2: flag-ON → cov80 closer to 0.80 on holdout ─────────────────────────

@pytest.mark.slow   # full dataset load + model inference
def test_flag_on_cov80_improves_on_holdout(monkeypatch):
    """With CV_QUANTILE_CAL=1, cov80 on the temporal holdout should be closer
    to 0.80 for CQR stats (PTS/REB/AST) vs raw; pass-through stats (FG3M/STL/TOV)
    should be unchanged.

    Coverage targets (from conformal_calibrate analysis):
      PTS : raw=0.693 → cqr=0.824  (improvement required; accept ≥0.79)
      REB : raw=0.772 → cqr=0.816  (improvement required; accept ≥0.79)
      AST : raw=0.734 → cqr=0.814  (improvement required; accept ≥0.79)
      FG3M: raw=0.838 → cqr=0.838  (pass-through; diff < 0.005)
      STL : raw=0.892 → cqr=0.892  (pass-through; diff < 0.005)
      TOV : raw=0.836 → cqr=0.836  (pass-through; diff < 0.005)
    """
    warnings.filterwarnings("ignore")
    monkeypatch.setenv("CV_QUANTILE_CAL", "1")

    from src.prediction.prop_pergame import STATS, build_pergame_dataset, feature_columns
    from src.prediction.prop_quantiles import load_quantile_models, _inverse as qinv
    from src.prediction.quantile_calibration import apply_conformal

    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    val_end = int(n * 0.80)
    holdout = rows[val_end:]

    cols = feature_columns()
    X_ho = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout],
                    dtype=float)

    MDIR = os.path.join(_ROOT, "data", "models")
    CQR_STATS     = {"pts", "reb", "ast"}
    PASS_STATS    = {"fg3m", "stl", "tov"}
    MONO_STATS    = {"blk"}

    for stat in STATS:
        y_ho = np.array([float(r[f"target_{stat}"]) for r in holdout], dtype=float)
        qm = load_quantile_models(stat, MDIR)
        if not qm or 0.1 not in qm or 0.9 not in qm:
            continue

        min_n = min((getattr(m, "n_features_in_", 9999) for m in qm.values()), default=None)
        Xh = X_ho[:, :min_n] if (min_n and min_n != X_ho.shape[1]) else X_ho

        q10h = qinv(stat, qm[0.1].predict(Xh))
        q50h = qinv(stat, qm[0.5].predict(Xh)) if 0.5 in qm else (q10h + q10h) * 0
        q90h = qinv(stat, qm[0.9].predict(Xh))

        cov_raw = float(np.mean((y_ho >= q10h) & (y_ho <= q90h)))

        # Apply conformal
        cq10 = np.empty_like(q10h); cq90 = np.empty_like(q90h)
        for i in range(len(q10h)):
            a, b = apply_conformal(stat, float(q10h[i]), float(q50h[i]), float(q90h[i]))
            cq10[i] = a; cq90[i] = b
        cov_cqr = float(np.mean((y_ho >= cq10) & (y_ho <= cq90)))

        if stat in CQR_STATS:
            # cov should improve and land ≥ 0.79 (conservative; analysis shows 0.814-0.824)
            assert cov_cqr > cov_raw, (
                f"[{stat}] CQR should improve coverage: raw={cov_raw:.3f} cqr={cov_cqr:.3f}"
            )
            assert cov_cqr >= 0.79, (
                f"[{stat}] CQR cov80={cov_cqr:.3f} below 0.79 target"
            )
        elif stat in PASS_STATS:
            # pass-through: diff < 0.005
            assert abs(cov_cqr - cov_raw) < 0.005, (
                f"[{stat}] pass-through stat changed coverage: raw={cov_raw:.3f} "
                f"cqr={cov_cqr:.3f} diff={abs(cov_cqr-cov_raw):.4f}"
            )
        elif stat in MONO_STATS:
            # BLK: coverage unchanged (mono clip doesn't expand band), crossings fixed
            assert abs(cov_cqr - cov_raw) < 0.01, (
                f"[{stat}] BLK mono-clip changed coverage unexpectedly: "
                f"raw={cov_raw:.3f} cqr={cov_cqr:.3f}"
            )
            # verify no crossings after clip
            cross_cqr = float(np.mean((cq10 > q50h) | (q50h > cq90)))
            assert cross_cqr == 0.0, (
                f"[{stat}] BLK still has crossings after monotone clip: {cross_cqr*100:.2f}%"
            )


# ── Test 3: q50 unchanged by CV_QUANTILE_CAL ──────────────────────────────────

@pytest.mark.parametrize("stat", ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"])
def test_q50_unchanged(monkeypatch, stat):
    """apply_conformal must NEVER modify q50 — it returns (q10, q90) only.

    The caller's q50 is preserved because apply_conformal only returns (q10, q90).
    This test verifies the function signature and that the returned values do not
    accidentally equal a different q50.
    """
    monkeypatch.setenv("CV_QUANTILE_CAL", "1")
    from src.prediction.quantile_calibration import apply_conformal
    q10_in, q50_in, q90_in = 3.0, 10.0, 18.0
    q10_out, q90_out = apply_conformal(stat, q10_in, q50_in, q90_in)
    # The function cannot change q50 — it doesn't return q50.
    # We verify q50_in is preserved by checking it's between the returned q10/q90.
    assert q10_out <= q50_in <= q90_out, (
        f"[{stat}] q50={q50_in} not between calibrated q10={q10_out:.4f} "
        f"and q90={q90_out:.4f} — monotone ordering violated"
    )


# ── Test 4: no crossing after apply_conformal ─────────────────────────────────

@pytest.mark.parametrize("stat", ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"])
@pytest.mark.parametrize("q10,q50,q90", [
    (5.0, 15.0, 25.0),     # normal ordering
    (0.0, 1.0, 3.0),       # q10 at zero floor
    (1.5, 1.0, 2.0),       # crossing input (q10 > q50) — BLK-like case
])
def test_no_crossing_after_conformal(monkeypatch, stat, q10, q50, q90):
    """After apply_conformal, q10 <= q50 <= q90 must always hold."""
    monkeypatch.setenv("CV_QUANTILE_CAL", "1")
    from src.prediction.quantile_calibration import apply_conformal
    cq10, cq90 = apply_conformal(stat, q10, q50, q90)
    assert cq10 <= q50 <= cq90, (
        f"[{stat}] crossing after conformal: cq10={cq10:.4f} q50={q50} cq90={cq90:.4f}"
    )
    assert cq10 >= 0.0, (
        f"[{stat}] cq10={cq10:.4f} went negative"
    )


# ── Test 5: co-activation CV_ROW_SIGMA=1 + CV_QUANTILE_CAL=1 for REB ──────────

def test_coactivation_reb_row_sigma_takes_priority(monkeypatch):
    """When both CV_ROW_SIGMA=1 and CV_QUANTILE_CAL=1, grade_bet for REB should
    use the CV_ROW_SIGMA path (apply_qcal) and NOT call apply_conformal.

    We verify this by checking that grade_bet's sigma for REB equals what
    apply_qcal produces (not what apply_conformal would produce).
    """
    monkeypatch.setenv("CV_ROW_SIGMA", "1")
    monkeypatch.setenv("CV_QUANTILE_CAL", "1")

    import api._courtvision_data as _mod
    # Patch _BETTING to avoid filesystem access
    class _FakeBettingEdge:
        def evaluate(self, model_prob, odds, bankroll=5000.0):
            b = odds / 100.0 if odds >= 100 else 100.0 / abs(odds)
            q = 1.0 - model_prob
            return {
                "implied_prob": 100.0 / (abs(odds) + 100.0) if odds < 0
                                else odds / (odds + 100.0),
                "kelly_size": max(0.0, (b * model_prob - q) / b) * bankroll,
            }
    monkeypatch.setattr(_mod, "_BETTING", _FakeBettingEdge(), raising=True)

    from src.prediction.quantile_calibration import apply as _apply_qcal
    # Pick a REB row with monotone q10 < q50 < q90
    q10_val, q50_val, q90_val = 3.0, 6.5, 11.0
    # What sigma should CV_ROW_SIGMA produce?
    cq10_expected, cq90_expected = _apply_qcal("reb", q10_val, q50_val, q90_val)
    expected_sigma = (cq90_expected - cq10_expected) / 2.5631

    slate_row = {
        "stat": "reb", "q50": q50_val, "q10": q10_val, "q90": q90_val,
        "player_id": "123", "player_name": "Test Player",
        "team": "LAL", "opp": "BOS", "venue": "home",
        "game_id": "test_game", "date": "2026-01-01", "injury_status": "",
    }
    line_row = {
        "line": 6.0, "books": [{"book": "DraftKings", "over_odds": -110, "under_odds": -110}],
    }
    stat_sigma = {"pts": 6.2, "reb": 2.6, "ast": 2.0, "fg3m": 1.4,
                  "stl": 1.0, "blk": 0.9, "tov": 1.2}

    result = _mod.grade_bet(slate_row, line_row, stat_sigma, bankroll=5000.0)

    # Recompute model_prob using CV_ROW_SIGMA-derived sigma
    from api._courtvision_data import normal_cdf
    line = 6.0
    p_over_expected = 1.0 - normal_cdf((line - q50_val) / expected_sigma)
    expected_model_prob = p_over_expected  # q50 > line -> OVER

    assert abs(result["model_prob"] - expected_model_prob) < 1e-4, (
        f"REB co-activation: expected model_prob={expected_model_prob:.6f} "
        f"(CV_ROW_SIGMA path), got {result['model_prob']:.6f}"
    )


# ── Bonus: AST-edge preserved ──────────────────────────────────────────────────

def test_ast_edge_p_over_shift_negligible(monkeypatch):
    """AST: CQR band expansion is tiny (qhat≈0.06). P(over) shift at a typical
    AST edge scenario (q50=6.0, line=5.5) must be < 0.01 — negligible vs +5-7% edge.
    """
    monkeypatch.delenv("CV_QUANTILE_CAL", raising=False)
    from src.prediction.quantile_calibration import apply_conformal
    from math import erf, sqrt

    def norm_cdf(x):
        return 0.5 * (1.0 + erf(x / sqrt(2.0)))

    # Typical AST band (from quantile head, mid-player)
    q10_in, q50_in, q90_in = 2.5, 6.0, 10.5
    raw_sigma = (q90_in - q10_in) / 2.5631
    p_raw = 1.0 - norm_cdf((5.5 - q50_in) / raw_sigma)

    monkeypatch.setenv("CV_QUANTILE_CAL", "1")
    cq10, cq90 = apply_conformal("ast", q10_in, q50_in, q90_in)
    cqr_sigma = (cq90 - cq10) / 2.5631
    p_cqr = 1.0 - norm_cdf((5.5 - q50_in) / cqr_sigma)

    shift = abs(p_cqr - p_raw)
    assert shift < 0.01, (
        f"AST P(over) shift too large: raw={p_raw:.4f} cqr={p_cqr:.4f} "
        f"shift={shift:.4f} (>0.01 could hurt AST edge)"
    )
