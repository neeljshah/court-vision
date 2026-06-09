"""DECISIVE held-out test: does an opp-allowed residual correction beat the raw
model on real lines OUT OF SAMPLE?

pred_corr = pred + beta * signal, where beta is fit STRICTLY on the early half
(beta = cov(signal, actual-pred)/var(signal)), then applied to the held-out late
half and graded vs real lines. Also fit-on-full-primary -> grade cross-season.

This is the legitimate zero-retrain screen (§2 additive-residual-correction path)
that gates whether REB is worth the expensive OOF regeneration (H2).

Reject unless corrected ROI > raw ROI on the held-out late half (mechanism must
generalize forward), with bet-direction changes actually occurring.
"""
from __future__ import annotations

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402


def split_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def fit_beta(bets, stat, key):
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 50:
        return None, 0
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    beta = np.cov(sig, resid)[0, 1] / np.var(sig)
    return beta, len(sub)


def grade_corrected(bets, stat, key, beta, edge_min=0.0):
    """Grade raw vs pred+beta*signal on this stat's bets. Reports direction flips."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        b["_pred_corr"] = b["pred"] + beta * b[key]
        if (b["pred"] > b["line"]) != (b["_pred_corr"] > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred", edge_min=edge_min)
    cor = ig.roi(sub, predictor="_pred_corr", edge_min=edge_min)
    return raw, cor, flips, len(sub)


def run(stat, key_stem):
    key = f"opp_{key_stem}_allowed_vs_league"
    print(f"\n{'='*72}\n {stat.upper()}  signal={key}\n{'='*72}")

    prim = ig.prepare("extended_oos_canonical.csv")
    early, late = split_halves(prim)

    # fit early -> grade late (true held-out)
    beta_e, ne = fit_beta(early, stat, key)
    print(f" fit beta on EARLY (n={ne}): beta={beta_e if beta_e is None else round(beta_e,4)}")
    if beta_e is not None:
        raw, cor, flips, n = grade_corrected(late, stat, key, beta_e)
        print(f"  held-out LATE: raw {raw['roi_pct']:+.2f}% (n{raw['n']}) -> "
              f"corrected {cor['roi_pct']:+.2f}% (n{cor['n']})  [flips={flips}/{n}]  "
              f"delta={cor['roi_pct']-raw['roi_pct']:+.2f}pp")

    # fit late -> grade early (symmetry)
    beta_l, nl = fit_beta(late, stat, key)
    if beta_l is not None:
        raw, cor, flips, n = grade_corrected(early, stat, key, beta_l)
        print(f"  (symmetry) fit LATE beta={round(beta_l,4)} -> held-out EARLY: "
              f"raw {raw['roi_pct']:+.2f}% -> corrected {cor['roi_pct']:+.2f}%  "
              f"delta={cor['roi_pct']-raw['roi_pct']:+.2f}pp [flips={flips}/{n}]")

    # fit full primary -> grade cross-season 2024-25
    beta_f, nf = fit_beta(prim, stat, key)
    cross = ig.prepare("regular_season_2024_25_oddsapi.csv")
    if beta_f is not None:
        raw, cor, flips, n = grade_corrected(cross, stat, key, beta_f)
        print(f"  CROSS-SEASON 2024-25 (fit beta={round(beta_f,4)} on primary): "
              f"raw {raw['roi_pct']:+.2f}% (n{raw['n']}) -> corrected {cor['roi_pct']:+.2f}% "
              f"[flips={flips}/{n}]  delta={cor['roi_pct']-raw['roi_pct']:+.2f}pp")

    # sign check: beta should be positive (soft D => more of the stat)
    if beta_e is not None:
        print(f"  mechanism sign: beta {'POSITIVE (consistent: soft D => over)' if beta_e>0 else 'NEGATIVE (anti-mechanism)'}")


if __name__ == "__main__":
    run("reb", "reb")
    run("pts", "pts")
    run("ast", "ast")
