"""H2 test: does opp-stat-allowed BY POSITION beat the team-level reject?

For each bet, we look up the positional as-of signal:
  opp_<stat>_allowed_to_<player_pos>_vs_league  (from opp_pos_allowed_asof_<tag>.parquet)

Then:
  1. Residual correlation: corr(signal, actual - pred)  [n]
  2. Held-out correction (fit beta EARLY half -> grade LATE half)
  3. Cross-season: fit beta on full primary -> grade 2024-25 corpus

Verdict rule: PROMISING only if corrected LATE ROI > raw LATE ROI in the
tradeable direction AND cross-season holds sign.  Most hypotheses SHOULD REJECT.
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # read-only

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIT = os.path.join(ROOT, "data", "cache", "pit")
POS_FILE = os.path.join(ROOT, "data", "player_positions.parquet")

FOCUS_STATS = ["reb", "pts"]


# ---------------------------------------------------------------- position map

def load_pos_map():
    df = pd.read_parquet(POS_FILE)
    _map = {"guard": "G", "forward": "F", "center": "C"}
    out = {}
    for r in df.itertuples(index=False):
        raw = (r.position or "").strip()
        if not raw:
            continue
        first = raw.split("-")[0].strip().lower()
        pos = _map.get(first)
        if pos is None:
            continue
        out[int(r.player_id)] = pos
    return out


# ---------------------------------------------------------------- attach positional signal

def attach_pos_signal(bets, pos_map, tag):
    """Attach per-bet: player position, then the positional as-of signal."""
    path = os.path.join(PIT, f"opp_pos_allowed_asof_{tag}.parquet")
    asof = pd.read_parquet(path)
    asof["d"] = pd.to_datetime(asof["game_date"]).dt.normalize()

    # index: (def_team, date, position) -> {signal cols}
    sig_cols = [c for c in asof.columns if "_vs_league" in c or "_asof" in c or "n_games_asof" in c]
    idx = {}
    for r in asof.itertuples(index=False):
        key = (r.team, r.d, r.position)
        idx[key] = {c: getattr(r, c) for c in sig_cols}

    matched = no_pos = no_sig = 0
    for b in bets:
        pos = pos_map.get(b["pid"])
        if pos is None:
            b["_player_pos"] = None
            b["_pos_sig_reb"] = np.nan
            b["_pos_sig_pts"] = np.nan
            no_pos += 1
            continue
        b["_player_pos"] = pos
        m = idx.get((b["opp"], b["gdate"], pos))
        if m is not None:
            for s in FOCUS_STATS:
                b[f"_pos_sig_{s}"] = m.get(f"opp_{s}_allowed_to_{pos}_vs_league", np.nan)
            matched += 1
        else:
            for s in FOCUS_STATS:
                b[f"_pos_sig_{s}"] = np.nan
            no_sig += 1
    print(f"    positional signal: matched={matched} no_pos={no_pos} no_sig={no_sig} total={len(bets)}")
    return bets


# ---------------------------------------------------------------- held-out helpers (mirror exp_resid_correction)

def split_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def fit_beta(bets, stat, key):
    sub = [b for b in bets
           if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 50:
        return None, len(sub)
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    beta = np.cov(sig, resid)[0, 1] / np.var(sig)
    return beta, len(sub)


def grade_corrected(bets, stat, key, beta):
    sub = [b for b in bets
           if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        b["_pred_corr_pos"] = b["pred"] + beta * b[key]
        if (b["pred"] > b["line"]) != (b["_pred_corr_pos"] > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred")
    cor = ig.roi(sub, predictor="_pred_corr_pos")
    return raw, cor, flips, len(sub)


def resid_corr(bets, stat, key):
    sub = [b for b in bets
           if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 10:
        return np.nan, len(sub)
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    c = np.corrcoef(sig, resid)[0, 1]
    return c, len(sub)


# ---------------------------------------------------------------- per-position breakdown

def per_position_corr(bets, stat, key):
    """Residual correlation by player position (G/F/C)."""
    for pos in ["G", "F", "C"]:
        sub = [b for b in bets
               if b["stat"] == stat
               and b.get("_player_pos") == pos
               and np.isfinite(b.get(key, np.nan))
               and np.isfinite(b.get("pred", np.nan))]
        if len(sub) < 10:
            print(f"      {pos}: n={len(sub)} (too few)")
            continue
        sig = np.array([b[key] for b in sub], float)
        resid = np.array([b["actual"] - b["pred"] for b in sub], float)
        c = np.corrcoef(sig, resid)[0, 1]
        print(f"      {pos}: corr={c:+.4f}  n={len(sub)}")


# ---------------------------------------------------------------- main test

def run_stat(stat, prim, early, late, cross, pos_map):
    key = f"_pos_sig_{stat}"
    print(f"\n{'='*72}")
    print(f" {stat.upper()}  signal=opp_{stat}_allowed_to_<player_pos>_vs_league")
    print(f"{'='*72}")

    # 1. Residual correlation on primary corpus (informational; NOT acceptance criterion)
    c_all, n_all = resid_corr(prim, stat, key)
    print(f" residual corr (primary, all positions): {c_all:+.4f}  n={n_all}")
    print(f"  by position:")
    per_position_corr(prim, stat, key)

    # 2. Held-out correction: fit on EARLY, grade LATE
    beta_e, ne = fit_beta(early, stat, key)
    print(f"\n fit beta on EARLY (n={ne}): beta={None if beta_e is None else round(beta_e, 4)}")
    if beta_e is not None:
        raw, cor, flips, n = grade_corrected(late, stat, key, beta_e)
        delta = cor["roi_pct"] - raw["roi_pct"]
        print(f"  held-out LATE: raw {raw['roi_pct']:+.2f}% (n={raw['n']}) -> "
              f"corrected {cor['roi_pct']:+.2f}% (n={cor['n']})  "
              f"[flips={flips}/{n}]  delta={delta:+.2f}pp")
        if delta > 0:
            print(f"  ** IMPROVEMENT on late half: +{delta:.2f}pp **")
        else:
            print(f"  -- NO improvement on late half ({delta:.2f}pp) -> leans REJECT")

    # 3. Symmetry: fit on LATE, grade EARLY
    beta_l, nl = fit_beta(late, stat, key)
    if beta_l is not None:
        raw2, cor2, flips2, n2 = grade_corrected(early, stat, key, beta_l)
        delta2 = cor2["roi_pct"] - raw2["roi_pct"]
        print(f"  (symmetry) fit LATE beta={round(beta_l,4)} -> EARLY: "
              f"raw {raw2['roi_pct']:+.2f}% -> corrected {cor2['roi_pct']:+.2f}%  "
              f"delta={delta2:+.2f}pp [flips={flips2}/{n2}]")

    # 4. Cross-season: fit on full primary, grade 2024-25
    beta_f, nf = fit_beta(prim, stat, key)
    if beta_f is not None and len(cross) > 0:
        raw_x, cor_x, flips_x, n_x = grade_corrected(cross, stat, key, beta_f)
        delta_x = cor_x["roi_pct"] - raw_x["roi_pct"]
        print(f"  CROSS-SEASON 2024-25 (beta={round(beta_f,4)} fit on primary): "
              f"raw {raw_x['roi_pct']:+.2f}% (n={raw_x['n']}) -> "
              f"corrected {cor_x['roi_pct']:+.2f}%  [flips={flips_x}/{n_x}]  "
              f"delta={delta_x:+.2f}pp")

    # 5. Mechanism sign
    if beta_e is not None:
        sign_lbl = "POSITIVE (soft D for that position => more of the stat)" if beta_e > 0 else "NEGATIVE (anti-mechanism)"
        print(f"  mechanism sign: beta {sign_lbl}")

    # Return summary dict for structured verdict
    return {
        "stat": stat,
        "resid_corr": c_all,
        "n_corr": n_all,
        "beta_early": beta_e,
        "n_early": ne,
        "late_raw_roi": raw["roi_pct"] if beta_e is not None else np.nan,
        "late_corr_roi": cor["roi_pct"] if beta_e is not None else np.nan,
        "late_delta": cor["roi_pct"] - raw["roi_pct"] if beta_e is not None else np.nan,
        "late_flips": flips if beta_e is not None else 0,
        "cross_raw_roi": raw_x["roi_pct"] if beta_f is not None and len(cross) > 0 else np.nan,
        "cross_corr_roi": cor_x["roi_pct"] if beta_f is not None and len(cross) > 0 else np.nan,
        "cross_delta": delta_x if beta_f is not None and len(cross) > 0 else np.nan,
    }


def main():
    pos_map = load_pos_map()

    # ----- primary corpus: extended_oos_canonical.csv (benashkar window)
    print("\n[PRIMARY] loading extended_oos_canonical.csv ...")
    prim = ig.prepare("extended_oos_canonical.csv")
    prim = attach_pos_signal(prim, pos_map, "2025_26_reg")

    # coherence guard
    coh = ig.coherence(prim)
    print(f" COHERENCE: blind-over {coh['over']['roi_pct']:+.2f}% + blind-under "
          f"{coh['under']['roi_pct']:+.2f}% = {coh['sum']:+.2f}%  "
          f"({'OK' if coh['coherent'] else 'CORRUPT'})")
    if not coh["coherent"]:
        print("  ABORT: corpus is not coherent (positive sum)")
        sys.exit(1)

    early, late = split_halves(prim)
    print(f" split: early n={len(early)}, late n={len(late)}")

    # ----- cross-season corpus
    print("\n[CROSS-SEASON] loading regular_season_2024_25_oddsapi.csv ...")
    cross = ig.prepare("regular_season_2024_25_oddsapi.csv")
    cross = attach_pos_signal(cross, pos_map, "2024_25")

    # coverage stats
    for stat in FOCUS_STATS:
        key = f"_pos_sig_{stat}"
        n_valid = sum(1 for b in prim if b["stat"] == stat and np.isfinite(b.get(key, np.nan)))
        n_total = sum(1 for b in prim if b["stat"] == stat)
        print(f" PRIMARY coverage {stat}: {n_valid}/{n_total} ({100*n_valid/max(n_total,1):.0f}%) with positional signal")

    # ---------------------------------------------------------------- run per stat
    results = []
    for stat in FOCUS_STATS:
        r = run_stat(stat, prim, early, late, cross, pos_map)
        results.append(r)

    # ---------------------------------------------------------------- verdict
    print(f"\n{'='*72}")
    print(" SUMMARY")
    print(f"{'='*72}")
    promising_stats = []
    for r in results:
        verdict = "REJECT"
        if r["late_delta"] > 0 and r["cross_delta"] > 0:
            verdict = "PROMISING"
        elif r["late_delta"] > 0 or r["cross_delta"] > 0:
            verdict = "INCONCLUSIVE"
        print(f" {r['stat'].upper():4s}: resid_corr={r['resid_corr']:+.4f} n={r['n_corr']} | "
              f"late delta={r['late_delta']:+.2f}pp | cross delta={r['cross_delta']:+.2f}pp | "
              f"=> {verdict}")
        if verdict == "PROMISING":
            promising_stats.append(r["stat"])

    if promising_stats:
        print(f"\n OVERALL: PROMISING on {promising_stats}")
    else:
        print("\n OVERALL: REJECT (no stat improved on BOTH held-out late + cross-season)")

    return results


if __name__ == "__main__":
    main()
