"""scripts/platformkit/proof_mlb/curve_oos.py — OOS-validate the per-inning run curve.

W160 audit P1. The MLB in-game repricer's empirical per-inning run-share curve
(domains/mlb/repricer.py ``_INNING_SHARES``, W135) was FIT on the full linescore corpus,
and the in-game backtest (scripts/ingame/repricer_calibration.py) evaluated on the SAME
corpus. So the headline "~35% final-total bias-cut vs flat (9-n)/9 scaling" is IN-SAMPLE
at the SHAPE level: not a per-game outcome leak, but the curve has seen the era it is
graded on. This module makes it honest.

THE TEST (leak-free, era-split OOS):
  * TRAIN era  = seasons 2010-2016. Fit the per-inning run-share curve from these
                 linescores ONLY (sum of runs in inning i / total runs, i=1..9).
  * VAL era    = seasons 2017-2021. NEVER touches the fit. For each val game, reconstruct
                 a leak-free mid-game state at innings 3/5/7 (cumulative runs through N from
                 the real per-inning strings; innings > N are never read), then predict the
                 FINAL TOTAL two ways and grade RMSE + signed BIAS (NEVER MAE) vs the
                 realized final:
      (a) TRAIN-FIT CURVE : remaining = (lam_h+lam_a) * curve_remaining_frac(N)
                            curve_remaining_frac(N) = sum(train_shares[N:]) / sum(train_shares)
      (b) FLAT            : remaining = (lam_h+lam_a) * (9 - N)/9
    final_pred = (runs already scored through N) + remaining.

  Reconstruction mirrors repricer_calibration._eval_mlb exactly (cumulative through N is a
  genuine observable; the final is the full sum). The pregame run-rate prior lambda is the
  league constant the repricer uses (4.5/team), held FIXED across both methods so the ONLY
  difference is the inning-share SHAPE — that is what we are OOS-testing.

VERDICT:
  holds_oos      : the train-fit curve's |bias| (and/or RMSE) on the VAL era beats flat by a
                   meaningful margin at the checkpoints, i.e. the shape win generalises.
  in_sample_only : on the held-out era the curve does NOT beat flat (the win was in-sample).

HONEST: calibration/forecaster-quality only; a live book also sees the score, so this is
NOT a market edge and none is claimed. Markets are efficient. DEFAULT-OFF tooling; reads
on-disk data only. INVARIANTS: never edit src/ or kernel/; pure numpy/pandas; <=300 LOC.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_TRAIN_SEASONS = (2010, 2011, 2012, 2013, 2014, 2015, 2016)
_VAL_SEASONS = (2017, 2018, 2019, 2020, 2021)
_CHECKPOINTS = (3, 5, 7)            # innings at which to reconstruct a mid-game state
_LEAGUE_LAMBDA = 4.5               # repricer's pregame run-rate prior, per team (held FIXED)
_FULL_INNINGS = 9


# ---------------------------------------------------------------------------
# Metric helpers (RMSE + signed bias only; MAE deliberately excluded)
# ---------------------------------------------------------------------------

def _rmse_bias(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    err = pred - truth
    return float(np.sqrt(np.mean(err ** 2))), float(np.mean(err))


def _parse_innings(s: Any) -> Optional[List[int]]:
    if not isinstance(s, str):
        return None
    out: List[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok in ("", "x", "X"):
            continue
        try:
            out.append(int(tok))
        except ValueError:
            return None
    return out or None


# ---------------------------------------------------------------------------
# Curve fitting (TRAIN era only) and remaining-fraction helpers
# ---------------------------------------------------------------------------

def fit_inning_shares(df_train: pd.DataFrame) -> Tuple[float, ...]:
    """Per-inning share of a 9-inning game's runs, fit on TRAIN-era linescores ONLY.

    share[i] = (total runs scored in inning i+1, both teams) / (total runs, both teams),
    summed over the first 9 innings of every train game (extra innings ignored so the
    9-slot curve matches the repricer's 9-inning model). Leak-free w.r.t. the val era.
    """
    sums = np.zeros(_FULL_INNINGS, dtype=float)
    for hi, ai in zip(df_train["home_innings"], df_train["away_innings"]):
        for s in (_parse_innings(hi), _parse_innings(ai)):
            if s is None:
                continue
            for i in range(min(len(s), _FULL_INNINGS)):
                sums[i] += s[i]
    tot = sums.sum()
    if tot <= 0:
        return tuple(1.0 / _FULL_INNINGS for _ in range(_FULL_INNINGS))
    return tuple((sums / tot).tolist())


def curve_remaining_frac(shares: Tuple[float, ...], innings_played: int) -> float:
    """Fraction of a game's runs still to come AFTER ``innings_played`` per the curve."""
    n = max(0, min(_FULL_INNINGS, innings_played))
    ssum = sum(shares)
    if ssum <= 0:
        return max(0.0, _FULL_INNINGS - n) / _FULL_INNINGS
    return sum(shares[n:]) / ssum


def flat_remaining_frac(innings_played: int) -> float:
    """Flat baseline: (9 - n)/9."""
    return max(0.0, _FULL_INNINGS - innings_played) / _FULL_INNINGS


# ---------------------------------------------------------------------------
# OOS evaluation
# ---------------------------------------------------------------------------

def _eval(df: pd.DataFrame, shares: Tuple[float, ...],
          limit: Optional[int]) -> Optional[Dict[str, Any]]:
    """Score train-fit-curve vs flat final-total RMSE+bias on the val-era games."""
    curve_pred: List[float] = []
    flat_pred: List[float] = []
    truth: List[float] = []
    # Per-checkpoint accumulators for a checkpoint breakdown.
    per_ck: Dict[int, Dict[str, List[float]]] = {
        ck: {"curve": [], "flat": [], "truth": []} for ck in _CHECKPOINTS
    }
    n_games = 0
    lam_pair = 2.0 * _LEAGUE_LAMBDA  # league total run-rate prior (both teams)
    for hi, ai in zip(df["home_innings"], df["away_innings"]):
        h, a = _parse_innings(hi), _parse_innings(ai)
        if h is None or a is None or len(h) < 1 or len(a) < 1:
            continue
        final_total = float(sum(h) + sum(a))
        used = False
        for ck in _CHECKPOINTS:
            if len(h) < ck or len(a) < ck:
                continue
            scored = float(sum(h[:ck]) + sum(a[:ck]))  # leak-free: only innings <= N read
            cf = curve_remaining_frac(shares, ck)
            ff = flat_remaining_frac(ck)
            cp = scored + lam_pair * cf
            fp = scored + lam_pair * ff
            curve_pred.append(cp)
            flat_pred.append(fp)
            truth.append(final_total)
            per_ck[ck]["curve"].append(cp)
            per_ck[ck]["flat"].append(fp)
            per_ck[ck]["truth"].append(final_total)
            used = True
        if used:
            n_games += 1
            if limit and n_games >= limit:
                break
    if not truth:
        return None

    c_rmse, c_bias = _rmse_bias(np.array(curve_pred), np.array(truth))
    f_rmse, f_bias = _rmse_bias(np.array(flat_pred), np.array(truth))

    ck_break: Dict[int, Dict[str, float]] = {}
    for ck in _CHECKPOINTS:
        if not per_ck[ck]["truth"]:
            continue
        cr, cb = _rmse_bias(np.array(per_ck[ck]["curve"]), np.array(per_ck[ck]["truth"]))
        fr, fb = _rmse_bias(np.array(per_ck[ck]["flat"]), np.array(per_ck[ck]["truth"]))
        ck_break[ck] = {
            "n": len(per_ck[ck]["truth"]),
            "curve_rmse": round(cr, 4), "curve_bias": round(cb, 4),
            "flat_rmse": round(fr, 4), "flat_bias": round(fb, 4),
            "bias_abs_cut": round(abs(fb) - abs(cb), 4),
            "rmse_cut": round(fr - cr, 4),
        }

    # bias-abs cut as a fraction of the flat |bias| — the headline "~35%" comparison.
    bias_abs_cut = abs(f_bias) - abs(c_bias)
    bias_cut_pct = (bias_abs_cut / abs(f_bias)) if abs(f_bias) > 1e-9 else 0.0
    rmse_cut = f_rmse - c_rmse
    # Holds OOS if the curve's |bias| is meaningfully smaller AND RMSE is no worse than flat.
    holds = bool(bias_abs_cut > 0.02 and rmse_cut >= -0.01)
    return {
        "n_games": n_games,
        "n_checkpoints": len(truth),
        "train_seasons": list(_TRAIN_SEASONS),
        "val_seasons": list(_VAL_SEASONS),
        "train_inning_shares": [round(s, 4) for s in shares],
        "curve_final_total_rmse": round(c_rmse, 4),
        "curve_final_total_bias": round(c_bias, 4),
        "flat_final_total_rmse": round(f_rmse, 4),
        "flat_final_total_bias": round(f_bias, 4),
        "bias_abs_cut": round(bias_abs_cut, 4),
        "bias_cut_pct": round(bias_cut_pct, 4),
        "rmse_cut": round(rmse_cut, 4),
        "verdict": "holds_oos" if holds else "in_sample_only",
        "by_checkpoint": ck_break,
    }


def run(limit: Optional[int] = None) -> Dict[str, Any]:
    """OOS-validate the per-inning run curve. Returns the result dict (also the public API)."""
    path = os.path.join(ROOT, "data", "domains", "mlb", "pitchers.parquet")
    if not os.path.exists(path):
        return {"status": "no_data", "note": f"missing {path}"}
    df = pd.read_parquet(path, columns=["season", "home_innings", "away_innings"])
    df_train = df[df["season"].isin(_TRAIN_SEASONS)]
    df_val = df[df["season"].isin(_VAL_SEASONS)]
    if df_train.empty or df_val.empty:
        return {"status": "data_limited",
                "note": f"train n={len(df_train)} val n={len(df_val)}"}
    shares = fit_inning_shares(df_train)
    res = _eval(df_val, shares, limit)
    if res is None:
        return {"status": "data_limited", "note": "no reconstructable val checkpoints"}
    res["status"] = "ok"
    res["n_train_games"] = int(len(df_train))
    res["n_val_games"] = int(len(df_val))
    return res


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="max val games (smoke-test).")
    args = ap.parse_args()
    r = run(args.limit)
    print("=" * 78)
    print("MLB PER-INNING RUN-CURVE — OOS validation (train era 2010-2016 -> val 2017-2021)")
    print("Final-total prediction at innings 3/5/7; GRADED RMSE + signed BIAS, never MAE.")
    print("=" * 78)
    if r.get("status") != "ok":
        print(f"  {r.get('status')}: {r.get('note', '')}")
        return
    print(f"  train games={r['n_train_games']}  val games={r['n_val_games']}  "
          f"val checkpoints={r['n_checkpoints']}")
    print(f"  train-fit inning shares (i=1..9): {r['train_inning_shares']}")
    print("-" * 78)
    print(f"  TRAIN-FIT CURVE  final-total RMSE={r['curve_final_total_rmse']:.4f}  "
          f"bias={r['curve_final_total_bias']:+.4f}")
    print(f"  FLAT (9-n)/9     final-total RMSE={r['flat_final_total_rmse']:.4f}  "
          f"bias={r['flat_final_total_bias']:+.4f}")
    print(f"  |bias| cut curve vs flat = {r['bias_abs_cut']:+.4f} "
          f"({r['bias_cut_pct'] * 100:+.1f}% of flat |bias|);  "
          f"RMSE cut = {r['rmse_cut']:+.4f}")
    print(f"  VERDICT: {r['verdict']}")
    print("-" * 78)
    print("  by checkpoint (inning N):")
    for ck, b in r["by_checkpoint"].items():
        print(f"    N={ck}  n={b['n']:6d}  curve RMSE={b['curve_rmse']:.3f} "
              f"bias={b['curve_bias']:+.3f} | flat RMSE={b['flat_rmse']:.3f} "
              f"bias={b['flat_bias']:+.3f} | |bias| cut={b['bias_abs_cut']:+.3f} "
              f"RMSE cut={b['rmse_cut']:+.3f}")
    print("  HONEST: forecaster quality only (a live book also sees the score) — NO edge.")


if __name__ == "__main__":
    main()
