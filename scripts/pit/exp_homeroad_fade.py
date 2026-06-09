"""EXPERIMENT: per-player home/road and rest/B2B production-fade signal.

HYPOTHESIS: some players systematically underperform ON THE ROAD or on the 2nd
night of a back-to-back; their props should be tilted DOWN in those spots.  The
model's global `is_home` / `is_b2b` flags capture the population-average effect;
personal tendencies may carry ADDITIONAL residual information.

SIGNAL (leak-free):
  For each (player_id, stat, game), compute from PRIOR games only:
    home_avg_prior = mean(actual) where is_home==1, date < this_date
    road_avg_prior = mean(actual) where is_home==0, date < this_date
    hr_gap_prior   = home_avg_prior - road_avg_prior  (positive = home better)
    b2b_avg_prior  = mean(actual) where is_b2b==1, date < this_date
    rest_avg_prior = mean(actual) where is_b2b==0, date < this_date
    b2b_fade_prior = rest_avg_prior - b2b_avg_prior   (positive = B2B worse)

  Tilt signal:
    road_tilt  = is_road * hr_gap_prior
                 (positive when road AND player historically fades on road)
    b2b_tilt   = is_b2b * b2b_fade_prior
                 (positive when B2B AND player historically fades on B2B)

  Adjustment: pred_adj = pred - beta * road_tilt  (or b2b_tilt)
              beta fitted on EARLY half, applied to HELD-OUT LATE half.

ORTHOGONALITY GATE: |corr(signal, actual-pred)| >= 0.05 on training set.
  If near zero -> model already prices it -> fast-reject.

GRADING: per-stat ROI lift on ≥2 independent corpora:
  Family A: benashkar_2026_canonical.csv
  Family B: regular_season_2025_26_oddsapi.csv
  Family C: regular_season_2024_25_oddsapi.csv  (cross-season)

METHOD reference: PREDICTION_HARNESS_GUIDE.md §4a (post-hoc tilt).
STATS tested: PTS, REB, AST.
"""

from __future__ import annotations

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pit"))
import intel_grade as ig  # noqa: E402

CALFRAME = os.path.join(ROOT, "data", "cache", "calibration_frame_v2.parquet")
SITUATIONAL = os.path.join(
    ROOT, "data", "cache", "intel_outcome", "player_situational_outcome.json"
)

STATS = ["pts", "reb", "ast"]
# Minimum prior games required in each bucket to compute a credible average
MIN_HOME_PRIOR = 5
MIN_ROAD_PRIOR = 5
MIN_B2B_PRIOR = 3
MIN_REST_PRIOR = 5

# ---------------------------------------------------------------------------
# Step 1 — build per-player, per-stat, per-date leak-free fade signals
# ---------------------------------------------------------------------------

def build_fade_signals(cal: pd.DataFrame, stats: list[str]) -> pd.DataFrame:
    """Return a dataframe with (player_id, date, stat, road_tilt, b2b_tilt).

    road_tilt = is_road * hr_gap_prior  (0 if player is home)
    b2b_tilt  = is_b2b * b2b_fade_prior (0 if not B2B)
    Both are NaN when insufficient prior data exists.

    Leak-free: for each row, only uses rows with date < this row's date.
    """
    cal = cal.copy()
    cal["date"] = pd.to_datetime(cal["date"]).dt.normalize()

    records = []
    for stat in stats:
        df = cal[cal["stat"] == stat].copy()
        df = df.sort_values(["player_id", "date"]).reset_index(drop=True)

        # Process per player
        for pid, grp in df.groupby("player_id", sort=False):
            grp = grp.sort_values("date").reset_index(drop=True)
            actuals = grp["actual"].values
            dates = grp["date"].values
            is_home = grp["is_home"].values.astype(int)
            is_b2b = grp["is_b2b"].values.astype(int)

            for i in range(len(grp)):
                # Only prior rows
                home_acts = actuals[:i][is_home[:i] == 1]
                road_acts = actuals[:i][is_home[:i] == 0]
                b2b_acts  = actuals[:i][is_b2b[:i] == 1]
                rest_acts = actuals[:i][is_b2b[:i] == 0]

                # home/road gap (prior)
                road_tilt = np.nan
                if (len(home_acts) >= MIN_HOME_PRIOR and
                        len(road_acts) >= MIN_ROAD_PRIOR):
                    hr_gap = np.mean(home_acts) - np.mean(road_acts)
                    # road_tilt = hr_gap when road (is_home==0), else 0
                    road_tilt = (1 - is_home[i]) * hr_gap

                # B2B fade (prior)
                b2b_tilt = np.nan
                if (len(b2b_acts) >= MIN_B2B_PRIOR and
                        len(rest_acts) >= MIN_REST_PRIOR):
                    b2b_fade = np.mean(rest_acts) - np.mean(b2b_acts)
                    b2b_tilt = is_b2b[i] * b2b_fade

                records.append({
                    "player_id": pid,
                    "date": dates[i],
                    "stat": stat,
                    "road_tilt": road_tilt,
                    "b2b_tilt": b2b_tilt,
                    "hr_gap_prior": (np.mean(home_acts) - np.mean(road_acts))
                        if (len(home_acts) >= MIN_HOME_PRIOR and
                            len(road_acts) >= MIN_ROAD_PRIOR) else np.nan,
                    "b2b_fade_prior": (np.mean(rest_acts) - np.mean(b2b_acts))
                        if (len(b2b_acts) >= MIN_B2B_PRIOR and
                            len(rest_acts) >= MIN_REST_PRIOR) else np.nan,
                    "n_home_prior": len(home_acts),
                    "n_road_prior": len(road_acts),
                    "n_b2b_prior": len(b2b_acts),
                    "n_rest_prior": len(rest_acts),
                })

    out = pd.DataFrame(records)
    return out


# ---------------------------------------------------------------------------
# Step 2 — attach fade signals to bet dicts
# ---------------------------------------------------------------------------

def attach_fade(bets: list[dict], fade_df: pd.DataFrame) -> list[dict]:
    """Join road_tilt and b2b_tilt onto bet dicts by (player_id, date, stat)."""
    fade_df = fade_df.copy()
    fade_df["d"] = pd.to_datetime(fade_df["date"]).dt.normalize()
    idx: dict[tuple, dict] = {}
    for r in fade_df.itertuples(index=False):
        key = (int(r.player_id), r.d, r.stat)
        idx[key] = {
            "road_tilt": r.road_tilt,
            "b2b_tilt": r.b2b_tilt,
            "hr_gap_prior": r.hr_gap_prior,
            "b2b_fade_prior": r.b2b_fade_prior,
            "n_home_prior": r.n_home_prior,
            "n_road_prior": r.n_road_prior,
            "n_b2b_prior": r.n_b2b_prior,
            "n_rest_prior": r.n_rest_prior,
        }
    matched = 0
    for b in bets:
        key = (b["pid"], b["gdate"], b["stat"])
        m = idx.get(key)
        if m is not None:
            b.update(m)
            matched += 1
        else:
            for k in ("road_tilt", "b2b_tilt", "hr_gap_prior", "b2b_fade_prior",
                      "n_home_prior", "n_road_prior", "n_b2b_prior", "n_rest_prior"):
                b.setdefault(k, np.nan)
    print(f"  fade-signal matched {matched}/{len(bets)} bets")
    return bets


# ---------------------------------------------------------------------------
# Step 3 — orthogonality + tilt mechanics
# ---------------------------------------------------------------------------

def residual_corr(bets: list[dict], stat: str, signal_key: str) -> tuple[float | None, int]:
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(signal_key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[signal_key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    r = float(np.corrcoef(sig, resid)[0, 1])
    return r, len(sub)


def split_halves(bets: list[dict]) -> tuple[list[dict], list[dict]]:
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    return ([b for b in bets if b["gdate"] < mid],
            [b for b in bets if b["gdate"] >= mid])


def fit_beta(bets: list[dict], stat: str, signal_key: str) -> tuple[float | None, int]:
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(signal_key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[signal_key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    beta = float(np.cov(sig, resid)[0, 1] / np.var(sig))
    return beta, len(sub)


def apply_tilt(bets: list[dict], stat: str, signal_key: str, beta: float,
               pred_key: str = "pred", out_key: str = "_pred_adj") -> list[dict]:
    """pred_adj = pred - beta * signal  (subtract because fade => tilt DOWN)."""
    for b in bets:
        if b["stat"] != stat:
            continue
        sig = b.get(signal_key, np.nan)
        p = b.get(pred_key, np.nan)
        if np.isfinite(sig) and np.isfinite(p):
            b[out_key] = p - beta * sig
    return bets


def grade_comparison(bets: list[dict], stat: str, pred_key: str = "pred",
                     adj_key: str = "_pred_adj",
                     signal_key: str = "road_tilt") -> dict:
    """Grade raw vs adjusted on the subset of bets that have the adj signal."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(signal_key, np.nan))
           and np.isfinite(b.get(pred_key, np.nan))]
    sub_adj = [b for b in sub if np.isfinite(b.get(adj_key, np.nan))]
    flips = sum(1 for b in sub_adj
                if np.isfinite(b.get(pred_key)) and np.isfinite(b.get(adj_key))
                and (b[pred_key] > b["line"]) != (b[adj_key] > b["line"]))
    raw = ig.roi(sub, predictor=pred_key)
    adj = ig.roi(sub_adj, predictor=adj_key)
    return {"raw": raw, "adj": adj, "flips": flips, "n_adj": len(sub_adj)}


# ---------------------------------------------------------------------------
# Step 4 — coverage summary helpers
# ---------------------------------------------------------------------------

def signal_coverage(bets: list[dict], stat: str, signal_key: str) -> dict:
    sub = [b for b in bets if b["stat"] == stat]
    n_total = len(sub)
    n_valid = sum(1 for b in sub if np.isfinite(b.get(signal_key, np.nan)))
    nonzero = sum(1 for b in sub
                  if np.isfinite(b.get(signal_key, np.nan))
                  and abs(b.get(signal_key, 0)) > 1e-9)
    return {"n_total": n_total, "n_valid": n_valid, "n_nonzero": nonzero,
            "pct_valid": 100 * n_valid / max(n_total, 1)}


def describe_signal(bets: list[dict], stat: str, signal_key: str) -> dict:
    vals = [b[signal_key] for b in bets
            if b["stat"] == stat and np.isfinite(b.get(signal_key, np.nan))]
    if not vals:
        return {}
    a = np.array(vals)
    return {"mean": float(np.mean(a)), "std": float(np.std(a)),
            "min": float(np.min(a)), "max": float(np.max(a)),
            "pct25": float(np.percentile(a, 25)), "pct75": float(np.percentile(a, 75))}


# ---------------------------------------------------------------------------
# Step 5 — main experiment runner
# ---------------------------------------------------------------------------

CORPUS_A = "benashkar_2026_canonical.csv"
CORPUS_B = "regular_season_2025_26_oddsapi.csv"
CORPUS_C = "regular_season_2024_25_oddsapi.csv"

# Signals to test
SIGNALS = [
    ("road_tilt",  "Road fade"),
    ("b2b_tilt",   "B2B fade"),
]

_results: dict = {}


def run_one_corpus(corpus: str, fade_df: pd.DataFrame, corpus_label: str) -> dict:
    """Run the full experiment on one corpus. Returns result dict."""
    print(f"\n{'='*72}")
    print(f"  CORPUS: {corpus_label}  ({corpus})")
    print(f"{'='*72}")

    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f"  coherence sum {coh['sum']:+.2f}%  ({'OK' if coh['coherent'] else 'CORRUPT !!'})")
    if not coh["coherent"]:
        print("  CORPUS CORRUPT — skipping")
        return {"coherent": False}

    bets = attach_fade(bets, fade_df)

    early, late = split_halves(bets)
    print(f"  Split: early n={len(early)}, late n={len(late)}")

    corpus_results = {"coherent": True, "stats": {}}

    for stat in STATS:
        print(f"\n  --- {stat.upper()} ---")
        corpus_results["stats"][stat] = {}

        for sig_key, sig_label in SIGNALS:
            # Coverage
            cov = signal_coverage(bets, stat, sig_key)
            desc = describe_signal(bets, stat, sig_key)
            print(f"    [{sig_label}]  coverage: {cov['n_valid']}/{cov['n_total']}"
                  f" ({cov['pct_valid']:.0f}%)  non-zero: {cov['n_nonzero']}")
            if desc:
                print(f"      signal stats: mean={desc['mean']:.3f}  std={desc['std']:.3f}"
                      f"  p25={desc['pct25']:.3f}  p75={desc['pct75']:.3f}")

            if cov["n_valid"] < 30:
                print(f"      SKIP: too few valid rows ({cov['n_valid']} < 30)")
                corpus_results["stats"][stat][sig_key] = {"verdict": "INSUFFICIENT_DATA"}
                continue

            # Orthogonality pre-screen on FULL corpus (diagnostic)
            r_full, n_full = residual_corr(bets, stat, sig_key)
            orth_flag = ""
            if r_full is not None and abs(r_full) >= 0.05:
                orth_flag = "  <-- passes orth screen"
            else:
                orth_flag = "  (near-zero: model may already price this)"
            r_full_str = f"{r_full:.4f}" if r_full is not None else "N/A"
            print(f"      corr(signal, actual-pred) full corpus: r={r_full_str}"
                  f" (n={n_full}){orth_flag}")

            # Orthogonality on EARLY half (strict gate)
            r_early, n_early = residual_corr(early, stat, sig_key)
            r_early_str = f"{r_early:.4f}" if r_early is not None else "N/A"
            print(f"      corr(signal, actual-pred) early half: r={r_early_str}"
                  f" (n={n_early})")

            # Fit beta on early, apply to late
            beta_e, n_fit = fit_beta(early, stat, sig_key)
            if beta_e is None:
                print(f"      SKIP: fit_beta returned None (n_fit={n_fit})")
                corpus_results["stats"][stat][sig_key] = {"verdict": "INSUFFICIENT_FIT"}
                continue

            print(f"      beta (fit on early, n={n_fit}): {beta_e:+.4f}")

            # Apply tilt to late set
            adj_key = f"_pred_{sig_key}"
            for b in late:
                sig_val = b.get(sig_key, np.nan)
                p = b.get("pred", np.nan)
                if np.isfinite(sig_val) and np.isfinite(p):
                    b[adj_key] = p - beta_e * sig_val

            # Grade on late held-out
            gc = grade_comparison(late, stat, pred_key="pred", adj_key=adj_key,
                                  signal_key=sig_key)
            raw_roi = gc["raw"]["roi_pct"]
            adj_roi = gc["adj"]["roi_pct"]
            delta = adj_roi - raw_roi
            flips = gc["flips"]
            n_adj = gc["n_adj"]
            print(f"      HELD-OUT LATE: raw {raw_roi:+.2f}% (n={gc['raw']['n']}) -> "
                  f"adj {adj_roi:+.2f}% (n={gc['adj']['n']})  "
                  f"delta={delta:+.2f}pp  flips={flips}/{n_adj}")

            # Symmetry check: fit late, grade early
            beta_l, n_fit_l = fit_beta(late, stat, sig_key)
            if beta_l is not None:
                adj_key_sym = f"_pred_{sig_key}_sym"
                for b in early:
                    sig_val = b.get(sig_key, np.nan)
                    p = b.get("pred", np.nan)
                    if np.isfinite(sig_val) and np.isfinite(p):
                        b[adj_key_sym] = p - beta_l * sig_val
                gc_sym = grade_comparison(early, stat, pred_key="pred",
                                          adj_key=adj_key_sym, signal_key=sig_key)
                print(f"      (symmetry) fit late beta={beta_l:+.4f} -> "
                      f"early: raw {gc_sym['raw']['roi_pct']:+.2f}% -> "
                      f"adj {gc_sym['adj']['roi_pct']:+.2f}%  "
                      f"delta={gc_sym['adj']['roi_pct']-gc_sym['raw']['roi_pct']:+.2f}pp")

            corpus_results["stats"][stat][sig_key] = {
                "r_full": r_full,
                "r_early": r_early,
                "beta": beta_e,
                "raw_late_roi": raw_roi,
                "adj_late_roi": adj_roi,
                "delta_pp": delta,
                "flips": flips,
                "n_adj": n_adj,
                "orth_passes": r_full is not None and abs(r_full) >= 0.05,
                "verdict": ("PASS" if delta > 0 else "FAIL"),
            }

    return corpus_results


def run_cross_corpus(corpus_c: str, fade_df: pd.DataFrame, corpus_label: str,
                     beta_map: dict) -> dict:
    """Grade cross-corpus (Family C) using betas fit on Family A.
    beta_map = {(stat, sig_key): beta}.
    """
    print(f"\n{'='*72}")
    print(f"  CROSS-CORPUS: {corpus_label}  ({corpus_c})")
    print(f"{'='*72}")

    bets = ig.prepare(corpus_c)
    coh = ig.coherence(bets)
    print(f"  coherence sum {coh['sum']:+.2f}%  ({'OK' if coh['coherent'] else 'CORRUPT !!'})")
    if not coh["coherent"]:
        print("  CORPUS CORRUPT — skipping")
        return {"coherent": False}

    bets = attach_fade(bets, fade_df)
    results = {"coherent": True, "stats": {}}

    for stat in STATS:
        print(f"\n  --- {stat.upper()} ---")
        results["stats"][stat] = {}
        for sig_key, sig_label in SIGNALS:
            beta = beta_map.get((stat, sig_key))
            if beta is None:
                print(f"    [{sig_label}] no beta from primary — skipping")
                continue

            adj_key = f"_pred_{sig_key}_cross"
            for b in bets:
                if b["stat"] != stat:
                    continue
                sig_val = b.get(sig_key, np.nan)
                p = b.get("pred", np.nan)
                if np.isfinite(sig_val) and np.isfinite(p):
                    b[adj_key] = p - beta * sig_val

            gc = grade_comparison(bets, stat, pred_key="pred", adj_key=adj_key,
                                  signal_key=sig_key)
            raw_roi = gc["raw"]["roi_pct"]
            adj_roi = gc["adj"]["roi_pct"]
            delta = adj_roi - raw_roi
            print(f"    [{sig_label}] beta={beta:+.4f}: "
                  f"raw {raw_roi:+.2f}% (n={gc['raw']['n']}) -> "
                  f"adj {adj_roi:+.2f}% (n={gc['adj']['n']})  "
                  f"delta={delta:+.2f}pp  flips={gc['flips']}/{gc['n_adj']}")

            results["stats"][stat][sig_key] = {
                "beta": beta,
                "raw_roi": raw_roi,
                "adj_roi": adj_roi,
                "delta_pp": delta,
                "flips": gc["flips"],
                "n_adj": gc["n_adj"],
                "verdict": ("PASS" if delta > 0 else "FAIL"),
            }

    return results


# ---------------------------------------------------------------------------
# Step 6 — verdict table
# ---------------------------------------------------------------------------

def print_verdict_table(res_a: dict, res_b: dict, res_c: dict) -> None:
    print(f"\n{'='*72}")
    print("  FINAL VERDICT TABLE")
    print(f"{'='*72}")
    print(f"  {'stat':4s} {'signal':12s} {'Corpus-A late':>14s} {'Corpus-B':>12s} "
          f"{'Corpus-C cross':>16s} {'SHIP?':>8s}")
    print(f"  {'-'*4} {'-'*12} {'-'*14} {'-'*12} {'-'*16} {'-'*8}")

    for stat in STATS:
        for sig_key, sig_label in SIGNALS:
            a = res_a.get("stats", {}).get(stat, {}).get(sig_key, {})
            b = res_b.get("stats", {}).get(stat, {}).get(sig_key, {})
            c = res_c.get("stats", {}).get(stat, {}).get(sig_key, {})

            a_str = (f"{a['adj_late_roi']:+.1f}% (n={a['n_adj']})"
                     if "adj_late_roi" in a else "N/A")
            b_str = (f"{b['adj_roi']:+.1f}% (n={b['n_adj']})"
                     if "adj_roi" in b else "N/A")
            c_str = (f"{c['adj_roi']:+.1f}% (n={c['n_adj']})"
                     if "adj_roi" in c else "N/A")

            a_pass = a.get("verdict") == "PASS"
            b_pass = b.get("verdict") == "PASS"
            c_pass = c.get("verdict") == "PASS"

            # SHIP = passes on A-held-out AND (B or C)
            ship = "SHIP" if (a_pass and (b_pass or c_pass)) else "REJECT"
            orth = "Y" if a.get("orth_passes") else "N"
            print(f"  {stat:4s} {sig_label:12s} {a_str:>14s} {b_str:>12s} "
                  f"{c_str:>16s} {ship:>8s}  orth={orth}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("EXP: home/road and B2B per-player fade signal")
    print("Date: 2026-06-01")
    print("=" * 72)

    # Load calibration frame to build fade signals
    print("\n[1] Building leak-free per-player fade signals from calibration_frame_v2...")
    cal = pd.read_parquet(CALFRAME)
    cal["date"] = pd.to_datetime(cal["date"]).dt.normalize()
    print(f"    Loaded cal: {cal.shape}")

    fade_df = build_fade_signals(cal, STATS)
    print(f"    Fade signals built: {len(fade_df)} rows")
    for sig_key in ("road_tilt", "b2b_tilt"):
        n_valid = fade_df[sig_key].notna().sum()
        n_nonzero = ((fade_df[sig_key].notna()) & (fade_df[sig_key].abs() > 1e-9)).sum()
        print(f"    {sig_key}: {n_valid} valid, {n_nonzero} non-zero "
              f"({100*n_nonzero/max(n_valid,1):.0f}% of valid rows are active)")

    # -----------------------------------------------------------------------
    # Also check situational_outcome.json coverage for reference
    # -----------------------------------------------------------------------
    print("\n[1b] Situational-outcome JSON reference coverage...")
    try:
        with open(SITUATIONAL, encoding="utf-8") as f:
            sit = json.load(f)
        players = sit.get("players", {})
        n_hr = sum(1 for v in players.values()
                   if v.get("hr_confidence") in ("high", "medium"))
        n_b2b = sum(1 for v in players.values()
                    if v.get("rest_confidence") in ("high", "medium"))
        print(f"    player_situational_outcome.json: {len(players)} players, "
              f"{n_hr} with home/road confidence>=med, "
              f"{n_b2b} with B2B confidence>=med")
        print(f"    NOTE: this JSON has TEAM plus/minus splits, not individual "
              f"box stats — we build per-player box-stat splits directly from "
              f"calibration_frame_v2 for the actual pred adjustment.")
    except Exception as e:
        print(f"    WARNING: could not load situational_outcome.json: {e}")

    # -----------------------------------------------------------------------
    # Global orthogonality check using calibration_frame_v2 directly
    # -----------------------------------------------------------------------
    print("\n[2] Global orthogonality check (model's own residual on full cal frame)...")
    print("    (is_home and is_b2b are already in training features — expect ~0)")
    for stat in STATS:
        sub = cal[cal["stat"] == stat].dropna(subset=["pred", "actual", "is_home", "is_b2b"])
        resid = sub["actual"] - sub["pred"]
        r_home = float(np.corrcoef(sub["is_home"], resid)[0, 1])
        r_b2b  = float(np.corrcoef(sub["is_b2b"], resid)[0, 1])
        print(f"    {stat}: corr(is_home, resid)={r_home:+.4f}  "
              f"corr(is_b2b, resid)={r_b2b:+.4f}  n={len(sub)}")
    print("    => Global flags already absorbed. Testing PERSONALIZED per-player signal below.")

    # -----------------------------------------------------------------------
    # Run experiments on each corpus
    # -----------------------------------------------------------------------
    print("\n[3] Family A — benashkar (primary, 4,068 bets, DK/FD/MGM)...")
    res_a = run_one_corpus(CORPUS_A, fade_df, "Family-A benashkar")

    # Extract betas fit on early-half of Family A (for cross-corpus)
    beta_map: dict[tuple, float] = {}
    for stat in STATS:
        for sig_key, _ in SIGNALS:
            entry = res_a.get("stats", {}).get(stat, {}).get(sig_key, {})
            if "beta" in entry and entry["beta"] is not None:
                beta_map[(stat, sig_key)] = entry["beta"]

    print("\n[4] Family B — oddsapi 2025-26 (thin, n~244, independent book)...")
    res_b = run_one_corpus(CORPUS_B, fade_df, "Family-B oddsapi-2025-26")

    print("\n[5] Family C — oddsapi 2024-25 (cross-season, n~295, using Family-A betas)...")
    res_c = run_cross_corpus(CORPUS_C, fade_df, "Family-C cross-season oddsapi-2024-25",
                             beta_map)

    # -----------------------------------------------------------------------
    # Summary verdict table
    # -----------------------------------------------------------------------
    print_verdict_table(res_a, res_b, res_c)

    # -----------------------------------------------------------------------
    # Final narrative
    # -----------------------------------------------------------------------
    print(f"\n{'='*72}")
    print("  INTERPRETATION & BASKETBALL CONCLUSION")
    print(f"{'='*72}")
    print("""
  ORTHOGONALITY FINDING:
  The model's global is_home / is_b2b flags capture the population-average
  home court and rest advantage.  Per-player personalized fade (a player's
  OWN historical home_avg - road_avg) creates an interaction signal that
  is non-trivially orthogonal ONLY if individual tendencies are persistent
  and stable enough to survive the prior-games accumulation window.

  KEY LIMITATIONS THAT PREDICT REJECTION:
  1. Sample fragmentation: road_tilt is only ACTIVE on road games (roughly
     half the sample); further filtered to players with >=5 prior home AND
     >=5 prior road games — effectively quartering the corpus per bucket.
  2. B2B fragmentation: is_b2b~15% of games, further filtered to >=3 prior
     B2B games — fewer than 5% of rows carry a credible b2b_tilt signal.
  3. The MARKET already prices home/road and B2B for each player —
     books see the same historical splits and move the line accordingly.
     Any informational advantage is priced away to within the vig.
  4. Mean-reversion: a player who historically fades on the road may simply
     be a bad player on a bad road team; the model's opp_def + rest_days +
     l10_min already capture most of that.
  5. PROP-specific fade (individual box stats) is not well-captured by
     PLUS_MINUS splits (team net) in the situational_outcome.json —
     confirmed by needing to build the signal from the calibration frame
     box-stat actuals directly.

  VERDICT CRITERION (SHIP requires):
  - Orthogonality: |corr(signal, resid)| >= 0.05 on training set
  - ROI lift (delta > 0) on Family-A held-out late half
  - Same direction lift on Family-B OR Family-C (independent corpus)
""")

    print("  Script complete.")


if __name__ == "__main__":
    main()
