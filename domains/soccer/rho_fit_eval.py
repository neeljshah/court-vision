"""domains.soccer.rho_fit_eval — Evaluation harness for the DC rho fitter.

Imports core fit functions from domains.soccer.rho_fit and runs a walk-forward
calibration evaluation, printing baseline vs fitted metrics.

HONEST: rho redistributes probability mass within the low-score zone (0-0, 0-1, 1-0, 1-1).
Expected win: better 1X2 / draw / correct-score calibration. O/U-2.5 dBrier ≈ 0 (redistribution
is within the under-3 mass, barely shifts the over-2.5 boundary). NO edge claimed.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np

# Core fit functions — imported read-only from rho_fit
from domains.soccer.rho_fit import walk_forward_rho

# Scoreline engine — imported read-only
from domains.soccer.scoreline_engine import scoreline_matrix, markets_from_matrix

# Ratings walk-forward
from domains.soccer.ratings import walk_forward_goals


# ---------------------------------------------------------------------------
# Calibration metric helpers (used only by evaluate — not in test imports)
# ---------------------------------------------------------------------------

def _brier(probs: np.ndarray, actuals: np.ndarray) -> float:
    return float(np.mean((probs - actuals) ** 2))


def _log_loss(probs: np.ndarray, actuals: np.ndarray, eps: float = 1e-7) -> float:
    p = np.clip(probs, eps, 1.0 - eps)
    return float(-np.mean(actuals * np.log(p) + (1 - actuals) * np.log(1 - p)))


def _ece(probs: np.ndarray, actuals: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error (equal-width bins)."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(probs)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        mean_pred = probs[mask].mean()
        mean_act = actuals[mask].mean()
        ece += (mask.sum() / n) * abs(mean_pred - mean_act)
    return float(ece)


# ---------------------------------------------------------------------------
# Main evaluation function
# ---------------------------------------------------------------------------

def evaluate(matches_path: Optional[str] = None) -> None:
    """Run walk-forward rho fit and print baseline vs fitted metrics.

    Metrics reported (all STRICTLY walk-forward, no future data):
      - 1X2 log-loss, Brier, ECE (3-class via macro average)
      - Draw probability Brier and ECE specifically
      - O/U-2.5 dBrier (expected ~0; honest)
      - Typical fitted rho value (median over non-warmup matches)
    """
    import pandas as pd

    root = Path(__file__).resolve().parents[2]
    path = Path(matches_path) if matches_path else root / "data" / "domains" / "soccer" / "matches.parquet"
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)

    matches_df = pd.read_parquet(path)
    wf = walk_forward_goals(matches_df)

    # Filter rows with valid scores
    valid = wf[wf["fthg"].notna() & wf["ftag"].notna()].copy()
    n = len(valid)

    lam_h = valid["lam_home"].values.astype(float)
    lam_a = valid["lam_away"].values.astype(float)
    fthg = valid["fthg"].values.astype(int)
    ftag = valid["ftag"].values.astype(int)
    ftr = valid["ftr"].values  # H/D/A
    target_over25 = valid["target_over25"].values.astype(float)

    print(f"Corpus: {n} matches with valid scores")

    # Walk-forward rho array
    rho_arr = walk_forward_rho(lam_h, lam_a, fthg, ftag, refit_every=300)
    non_warmup = rho_arr[rho_arr != 0.0]
    median_rho = float(np.median(non_warmup)) if len(non_warmup) > 0 else 0.0
    print(f"Typical fitted rho (median, non-warmup): {median_rho:.4f}")

    # Build per-match market predictions for both baseline and fitted
    home_base, draw_base, away_base, ou_base = [], [], [], []
    home_fit, draw_fit, away_fit, ou_fit = [], [], [], []

    for i in range(n):
        lh, la = lam_h[i], lam_a[i]

        P0 = scoreline_matrix(lh, la, rho=0.0)
        m0 = markets_from_matrix(P0)
        home_base.append(m0["1X2_home"])
        draw_base.append(m0["1X2_draw"])
        away_base.append(m0["1X2_away"])
        ou_base.append(m0["over_2.5"])

        Pr = scoreline_matrix(lh, la, rho=rho_arr[i])
        mr = markets_from_matrix(Pr)
        home_fit.append(mr["1X2_home"])
        draw_fit.append(mr["1X2_draw"])
        away_fit.append(mr["1X2_away"])
        ou_fit.append(mr["over_2.5"])

    home_base = np.array(home_base)
    draw_base = np.array(draw_base)
    away_base = np.array(away_base)
    ou_base = np.array(ou_base)
    home_fit = np.array(home_fit)
    draw_fit = np.array(draw_fit)
    away_fit = np.array(away_fit)
    ou_fit = np.array(ou_fit)

    act_home = (ftr == "H").astype(float)
    act_draw = (ftr == "D").astype(float)
    act_away = (ftr == "A").astype(float)

    # 1X2 macro-averaged metrics
    b_logloss = (
        _log_loss(home_base, act_home) + _log_loss(draw_base, act_draw) + _log_loss(away_base, act_away)
    ) / 3
    f_logloss = (
        _log_loss(home_fit, act_home) + _log_loss(draw_fit, act_draw) + _log_loss(away_fit, act_away)
    ) / 3

    b_brier = (
        _brier(home_base, act_home) + _brier(draw_base, act_draw) + _brier(away_base, act_away)
    ) / 3
    f_brier = (
        _brier(home_fit, act_home) + _brier(draw_fit, act_draw) + _brier(away_fit, act_away)
    ) / 3

    b_ece = (
        _ece(home_base, act_home) + _ece(draw_base, act_draw) + _ece(away_base, act_away)
    ) / 3
    f_ece = (
        _ece(home_fit, act_home) + _ece(draw_fit, act_draw) + _ece(away_fit, act_away)
    ) / 3

    b_draw_brier = _brier(draw_base, act_draw)
    f_draw_brier = _brier(draw_fit, act_draw)
    b_draw_ece = _ece(draw_base, act_draw)
    f_draw_ece = _ece(draw_fit, act_draw)

    b_ou_brier = _brier(ou_base, target_over25)
    f_ou_brier = _brier(ou_fit, target_over25)

    print(f"\n{'Metric':<28} {'Baseline (rho=0)':>18} {'Fitted rho':>18} {'Delta':>10}")
    print("-" * 76)
    print(f"{'1X2 macro log-loss':<28} {b_logloss:>18.5f} {f_logloss:>18.5f} {f_logloss - b_logloss:>+10.5f}")
    print(f"{'1X2 macro Brier':<28} {b_brier:>18.5f} {f_brier:>18.5f} {f_brier - b_brier:>+10.5f}")
    print(f"{'1X2 macro ECE':<28} {b_ece:>18.5f} {f_ece:>18.5f} {f_ece - b_ece:>+10.5f}")
    print(f"{'Draw Brier':<28} {b_draw_brier:>18.5f} {f_draw_brier:>18.5f} {f_draw_brier - b_draw_brier:>+10.5f}")
    print(f"{'Draw ECE':<28} {b_draw_ece:>18.5f} {f_draw_ece:>18.5f} {f_draw_ece - b_draw_ece:>+10.5f}")
    print(f"{'O/U-2.5 Brier':<28} {b_ou_brier:>18.5f} {f_ou_brier:>18.5f} {f_ou_brier - b_ou_brier:>+10.5f}")
    print()
    print("HONEST: O/U-2.5 dBrier expected ~0 (rho redistributes within low totals).")
    print("Expected win from rho: 1X2 / draw / correct-score calibration (negative delta = improvement).")
    print("NO edge claimed — accuracy/calibration only.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Walk-forward Dixon-Coles rho calibration for soccer.")
    parser.add_argument("--matches", default=None, help="Path to matches.parquet (optional)")
    args = parser.parse_args()
    evaluate(matches_path=args.matches)


if __name__ == "__main__":
    main()
