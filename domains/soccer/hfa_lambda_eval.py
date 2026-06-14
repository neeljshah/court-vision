"""domains.soccer.hfa_lambda_eval — Evaluation harness for HFA lambda correction.

Compares symmetric Poisson baseline vs HFA-corrected model on:
  1X2 macro Brier/logloss/ECE; home & away 1X2 split Brier; per-side goals RMSE.

HONEST: value = calibration from correcting the systematic home-bias in the symmetric
Poisson baseline.  NO edge claimed; gate decides signal merit.

Run: python domains/soccer/hfa_lambda_eval.py  (from repo root with PYTHONPATH=.)
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from domains.soccer.hfa_lambda import walk_forward_hfa
from domains.soccer.ratings import walk_forward_goals
from domains.soccer.scoreline_engine import markets_from_matrix, scoreline_matrix

# ---------------------------------------------------------------------------
# Scoring helpers (stdlib + numpy only; no scipy, no src.*)
# ---------------------------------------------------------------------------


def _brier(probs: List[float], targets: List[float]) -> float:
    if not probs:
        return float("nan")
    return float(np.mean((np.array(probs) - np.array(targets)) ** 2))


def _log_loss(probs: List[float], targets: List[float], eps: float = 1e-12) -> float:
    if not probs:
        return float("nan")
    p = np.clip(np.array(probs), eps, 1.0 - eps)
    t = np.array(targets)
    return float(-np.mean(t * np.log(p) + (1.0 - t) * np.log(1.0 - p)))


def _ece(probs: List[float], targets: List[float], n_bins: int = 10) -> float:
    if not probs:
        return float("nan")
    p, t = np.array(probs), np.array(targets)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece_sum = 0.0
    n = len(p)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (p >= lo) & (p < hi)
        if not mask.any():
            continue
        ece_sum += (mask.sum() / n) * abs(p[mask].mean() - t[mask].mean())
    return float(ece_sum)


def _rmse(pred: List[float], actual: List[float]) -> float:
    if not pred:
        return float("nan")
    return float(np.sqrt(np.mean((np.array(pred) - np.array(actual)) ** 2)))


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "domains" / "soccer" / "matches.parquet"
    if not path.exists():
        raise FileNotFoundError(f"matches.parquet not found at {path}")
    matches_df = pd.read_parquet(path)

    hfa = walk_forward_hfa(matches_df)
    wf_base = walk_forward_goals(matches_df)  # same sorted order as hfa

    actual_fthg = wf_base["fthg"].astype(float).values
    actual_ftag = wf_base["ftag"].astype(float).values
    ftr_col = wf_base["ftr"].values if "ftr" in wf_base.columns else None

    # Accumulators
    base_hp, base_dp, base_ap = [], [], []
    adj_hp, adj_dp, adj_ap = [], [], []
    t_h, t_d, t_a = [], [], []
    b_ph, b_pa, a_ph, a_pa = [], [], [], []
    act_h, act_a = [], []

    for i in range(len(hfa)):
        fg, fa = actual_fthg[i], actual_ftag[i]
        if not (math.isfinite(fg) and math.isfinite(fa)):
            continue
        lhb = float(hfa["lam_home_base"].iloc[i])
        lab = float(hfa["lam_away_base"].iloc[i])
        lha = float(hfa["lam_home_adj"].iloc[i])
        laa = float(hfa["lam_away_adj"].iloc[i])
        try:
            P_b = scoreline_matrix(lhb, lab, rho=0.0)
            P_a = scoreline_matrix(lha, laa, rho=0.0)
        except Exception:
            continue
        mb = markets_from_matrix(P_b)
        ma = markets_from_matrix(P_a)

        ftr = str(ftr_col[i]) if ftr_col is not None else (
            "H" if fg > fa else ("A" if fg < fa else "D")
        )
        t_h.append(1.0 if ftr == "H" else 0.0)
        t_d.append(1.0 if ftr == "D" else 0.0)
        t_a.append(1.0 if ftr == "A" else 0.0)

        base_hp.append(mb["1X2_home"]); base_dp.append(mb["1X2_draw"]); base_ap.append(mb["1X2_away"])
        adj_hp.append(ma["1X2_home"]); adj_dp.append(ma["1X2_draw"]); adj_ap.append(ma["1X2_away"])

        b_ph.append(lhb); b_pa.append(lab)
        a_ph.append(lha); a_pa.append(laa)
        act_h.append(fg); act_a.append(fa)

    n = len(base_hp)
    if n == 0:
        print("No valid rows to evaluate.")
        return

    def macro_brier(hp, dp, ap, th, td, ta):
        return (_brier(hp, th) + _brier(dp, td) + _brier(ap, ta)) / 3.0

    base_macro = macro_brier(base_hp, base_dp, base_ap, t_h, t_d, t_a)
    adj_macro  = macro_brier(adj_hp,  adj_dp,  adj_ap,  t_h, t_d, t_a)

    base_ll = (_log_loss(base_hp, t_h) + _log_loss(base_dp, t_d) + _log_loss(base_ap, t_a)) / 3.0
    adj_ll  = (_log_loss(adj_hp,  t_h) + _log_loss(adj_dp,  t_d) + _log_loss(adj_ap,  t_a)) / 3.0

    base_ece = (_ece(base_hp, t_h) + _ece(base_dp, t_d) + _ece(base_ap, t_a)) / 3.0
    adj_ece  = (_ece(adj_hp,  t_h) + _ece(adj_dp,  t_d) + _ece(adj_ap,  t_a)) / 3.0

    home_mask = [v == 1.0 for v in t_h]
    away_mask = [v == 1.0 for v in t_a]
    n_home, n_away = sum(home_mask), sum(away_mask)
    base_h_split = _brier([p for p, m in zip(base_hp, home_mask) if m], [1.0] * n_home)
    adj_h_split  = _brier([p for p, m in zip(adj_hp,  home_mask) if m], [1.0] * n_home)
    base_a_split = _brier([p for p, m in zip(base_ap, away_mask) if m], [1.0] * n_away)
    adj_a_split  = _brier([p for p, m in zip(adj_ap,  away_mask) if m], [1.0] * n_away)

    h_median = float(np.median(hfa["h"].values[20:]))
    emp_hm = float(np.mean(act_h))
    emp_am = float(np.mean(act_a))
    emp_h = emp_hm / emp_am if emp_am > 0 else float("nan")

    print("=" * 65)
    print("  HFA Lambda Correction -- Soccer Poisson Walk-Forward Eval")
    print("=" * 65)
    print(f"  Matches evaluated  : {n:,}")
    print(f"  Empirical home mean: {emp_hm:.4f}")
    print(f"  Empirical away mean: {emp_am:.4f}")
    print(f"  Empirical h        : {emp_h:.4f}  (h = home_mean / away_mean)")
    print(f"  Typical h (median) : {h_median:.4f}")
    print()
    print("  1X2 macro Brier (lower=better):")
    print(f"    Baseline  : {base_macro:.6f}")
    print(f"    HFA-adj   : {adj_macro:.6f}")
    d = adj_macro - base_macro
    print(f"    Delta     : {d:+.6f}  [{'IMPROVEMENT' if d < 0 else 'DEGRADATION'}]")
    print()
    print("  1X2 macro logloss (lower=better):")
    print(f"    Baseline  : {base_ll:.6f}")
    print(f"    HFA-adj   : {adj_ll:.6f}  (delta {adj_ll - base_ll:+.6f})")
    print()
    print("  1X2 macro ECE (lower=better):")
    print(f"    Baseline  : {base_ece:.6f}")
    print(f"    HFA-adj   : {adj_ece:.6f}  (delta {adj_ece - base_ece:+.6f})")
    print()
    print(f"  1X2 split Brier -- Home wins (n={n_home}):")
    print(f"    Baseline  : {base_h_split:.6f}  |  HFA-adj : {adj_h_split:.6f}"
          f"  (delta {adj_h_split - base_h_split:+.6f})")
    print(f"  1X2 split Brier -- Away wins (n={n_away}):")
    print(f"    Baseline  : {base_a_split:.6f}  |  HFA-adj : {adj_a_split:.6f}"
          f"  (delta {adj_a_split - base_a_split:+.6f})")
    print()
    print("  Goals RMSE (predicted lambda vs actual goals):")
    print(f"    Home baseline : {_rmse(b_ph, act_h):.4f}  |  adj : {_rmse(a_ph, act_h):.4f}"
          f"  (delta {_rmse(a_ph, act_h) - _rmse(b_ph, act_h):+.4f})")
    print(f"    Away baseline : {_rmse(b_pa, act_a):.4f}  |  adj : {_rmse(a_pa, act_a):.4f}"
          f"  (delta {_rmse(a_pa, act_a) - _rmse(b_pa, act_a):+.4f})")
    print()
    print("  HONEST: NO edge claimed; gate decides signal merit.")
    print("=" * 65)

    if d < -0.0001:
        verdict = f"VERDICT: HFA IMPROVES 1X2 macro Brier (delta={d:+.5f}). Calibration gain confirmed."
    elif abs(d) <= 0.0001:
        verdict = f"VERDICT: HFA is NULL on 1X2 macro Brier (|delta|={abs(d):.5f} <= 0.0001)."
    else:
        verdict = f"VERDICT: HFA DEGRADES 1X2 macro Brier (delta={d:+.5f}). Symmetric baseline preferred."
    print()
    print(verdict)


if __name__ == "__main__":
    main()
