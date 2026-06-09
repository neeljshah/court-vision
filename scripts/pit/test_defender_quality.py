"""H3: Team defender quality (rolling) as a matchup conditioner.

Hypothesis: a player facing a team whose defenders allow high pts/fg% should
over-perform their model prediction.

Signal source: build_defender_quality.py -> defender_team_quality_asof.parquet
Join key: (player's opp = defending team's def_team_tricode, game_date)

Tests:
  1. Residual correlation: corr(signal, actual - pred) per stat  (in-sample diagnostic)
  2. Held-out correction: fit beta on EARLY half, grade strictly on LATE half  (decisive)
  3. Selection screen: restrict to HIGH-signal bets (soft defense), both halves
  4. Cross-season: fit on full primary, grade on regular_season_2024_25_oddsapi.csv
     (NOTE: no 2024-25 defender_matchups — cross-season signal will be NaN; report honestly)

Primary corpus: extended_oos_canonical.csv (4068 joined bets, benashkar window).

DISCIPLINE:
  - drop |odds|<100 handled by intel_grade
  - coherence guard must pass
  - no in-sample cherry-pick; decisive screen = held-out late-half correction
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUBSTRATE = os.path.join(ROOT, "data", "cache", "pit", "defender_team_quality_asof.parquet")

PRIMARY_CORPUS = "extended_oos_canonical.csv"
CROSS_CORPUS = "regular_season_2024_25_oddsapi.csv"

# Signals to test: (substrate_col, label)
SIGNALS = [
    ("team_def_fg_pct_vs_league",    "def_fg_pct_vs_league"),   # primary perimeter-defense signal
    ("team_def_pts_pm_vs_league",    "def_pts_pm_vs_league"),   # pts-per-minute allowed vs league
    ("team_def_fg3_pct_vs_league",   "def_fg3_pct_vs_league"),  # 3pt defense quality
    ("team_def_switch_rate_vs_league","def_switch_rate_vs_league"),
]

STATS = ["pts", "reb", "ast", "fg3m"]


# ---- substrate loader -------------------------------------------------------

def load_substrate() -> dict:
    """Return a dict keyed (team_tricode, game_date_normalized) -> {col:val}."""
    df = pd.read_parquet(SUBSTRATE)
    df["d"] = pd.to_datetime(df["game_date"]).dt.normalize()
    sig_cols = [c for c in df.columns if c.startswith("team_") and
                ("vs_league" in c or "_asof" in c)] + ["n_games_asof"]
    idx = {}
    for r in df.itertuples(index=False):
        idx[(r.team, r.d)] = {c: getattr(r, c) for c in sig_cols}
    print(f"  substrate: {len(df):,} rows  ({df['team'].nunique()} teams, "
          f"dates {df['game_date'].min()} -> {df['game_date'].max()})")
    return idx


def attach_defender_signal(bets: list, idx: dict) -> list:
    """Join substrate by (opp, gdate) -> bet's opponent is the defending team."""
    matched = 0
    sig_cols = None
    for b in bets:
        key = (b["opp"], b["gdate"])
        m = idx.get(key)
        if m is not None:
            b.update(m)
            matched += 1
            if sig_cols is None:
                sig_cols = list(m.keys())
        else:
            # set NaN so later code can detect missing coverage
            if sig_cols is None:
                # try to find keys from a known good row
                pass  # will be set on first hit
    total = len(bets)
    print(f"  defender-signal matched {matched}/{total} "
          f"({100*matched/max(total,1):.1f}%) "
          f"[only 2025-26 season has coverage]")
    return bets


# ---- residual correlation ---------------------------------------------------

def resid_corr(bets: list, sig_key: str, stat: str) -> dict:
    """corr(signal, actual-pred) with n, for bets where signal is finite."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(sig_key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 10:
        return {"n": len(sub), "corr": np.nan}
    sig = np.array([b[sig_key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    corr = np.corrcoef(sig, resid)[0, 1]
    return {"n": len(sub), "corr": corr}


# ---- held-out correction (fit early -> grade late) -------------------------

def split_halves(bets: list):
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def fit_beta(bets: list, stat: str, key: str):
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    beta = np.cov(sig, resid)[0, 1] / np.var(sig)
    return beta, len(sub)


def grade_corrected(bets: list, stat: str, key: str, beta: float):
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        b["_pred_corr_dq"] = b["pred"] + beta * b[key]
        if (b["pred"] > b["line"]) != (b["_pred_corr_dq"] > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred")
    cor = ig.roi(sub, predictor="_pred_corr_dq")
    return raw, cor, flips, len(sub)


# ---- selection screen: high-signal (soft-defense) bets only ----------------

def selection_screen(bets: list, sig_key: str, stat: str, top_pct: float = 0.33) -> dict:
    """Restrict to bets where sig_key > top-pct threshold (softest defenses).
    Returns ROI for: ALL, HIGH-signal early half, HIGH-signal late half.
    """
    stat_bets = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(sig_key, np.nan))]
    if len(stat_bets) < 20:
        return {}
    vals = np.array([b[sig_key] for b in stat_bets], float)
    thresh = np.nanpercentile(vals, 100 * (1 - top_pct))
    high = [b for b in stat_bets if b[sig_key] >= thresh]
    low  = [b for b in stat_bets if b[sig_key] < thresh]

    early_high = [b for b in high if b in split_halves(bets)[0]]
    late_high  = [b for b in high if b in split_halves(bets)[1]]

    return {
        "all_n": len(stat_bets),
        "high_n": len(high),
        "low_n": len(low),
        "high_roi": ig.roi(high)["roi_pct"],
        "low_roi": ig.roi(low)["roi_pct"],
        "high_early_roi": ig.roi(early_high)["roi_pct"],
        "high_late_roi": ig.roi(late_high)["roi_pct"],
        "high_early_n": len(early_high),
        "high_late_n": len(late_high),
        "thresh": thresh,
    }


# ---- main test run ----------------------------------------------------------

def main():
    print("=" * 72)
    print("H3: Team Defender Quality — as-of matchup conditioner")
    print("=" * 72)

    # Load substrate
    idx = load_substrate()

    # Prepare primary corpus + attach predictions + attach defender signal
    print(f"\n--- Primary corpus: {PRIMARY_CORPUS} ---")
    bets_prim = ig.prepare(PRIMARY_CORPUS)
    bets_prim = attach_defender_signal(bets_prim, idx)
    print(f"  total joined bets (with pred): {len(bets_prim)}")

    # Coherence check
    coh = ig.coherence(bets_prim)
    coh_ok = coh["coherent"]
    print(f"  COHERENCE: blind-over {coh['over']['roi_pct']:+.2f}% + "
          f"blind-under {coh['under']['roi_pct']:+.2f}% = {coh['sum']:+.2f}% "
          f"({'OK' if coh_ok else 'CORRUPT!'})")
    if not coh_ok:
        print("  ABORT: corpus coherence failed — corrupt odds detected")
        return

    # Coverage breakdown: how many have signal attached
    for sig_col, sig_label in SIGNALS:
        n_with_sig = sum(1 for b in bets_prim if np.isfinite(b.get(sig_col, np.nan)))
        print(f"  coverage {sig_label}: {n_with_sig}/{len(bets_prim)} "
              f"({100*n_with_sig/max(len(bets_prim),1):.1f}%) bets with finite signal")

    # === SECTION 1: Residual correlations ===
    print("\n--- Section 1: Residual Correlations (diagnostic, in-sample) ---")
    print(f"  corr(signal, actual-pred) per stat  [n = bets with finite signal]")
    primary_sig = "team_def_fg_pct_vs_league"  # main signal for correction tests
    for stat in STATS:
        rc = resid_corr(bets_prim, primary_sig, stat)
        flag = ""
        if rc["n"] > 20:
            if abs(rc["corr"]) > 0.05:
                flag = " <-- notable"
        print(f"  {stat:5s}  n={rc['n']:4d}  corr(def_fg_pct_vs_league, resid)={rc['corr']:+.4f}{flag}")

    # Also check pts_pm signal for pts
    print()
    for stat in ["pts", "fg3m"]:
        rc = resid_corr(bets_prim, "team_def_pts_pm_vs_league", stat)
        print(f"  {stat:5s}  n={rc['n']:4d}  corr(def_pts_pm_vs_league, resid)={rc['corr']:+.4f}")

    # === SECTION 2: Held-out correction per stat ===
    print("\n--- Section 2: Held-Out Residual Correction (DECISIVE) ---")
    print("  fit beta on EARLY half (strictly before median date) -> grade LATE half")

    early, late = split_halves(bets_prim)
    print(f"  early n={len(early)}, late n={len(late)}")

    results = {}
    for stat in STATS:
        key = "team_def_fg_pct_vs_league"  # primary signal
        beta_e, ne = fit_beta(early, stat, key)
        print(f"\n  {stat.upper()}  key={key}")
        print(f"    fit beta on EARLY (n_fit={ne}): beta={round(beta_e,4) if beta_e is not None else 'None (insufficient data)'}")
        if beta_e is not None:
            raw_l, cor_l, flips_l, nl = grade_corrected(late, stat, key, beta_e)
            delta = cor_l["roi_pct"] - raw_l["roi_pct"]
            print(f"    HELD-OUT LATE:  raw {raw_l['roi_pct']:+.2f}% (n={raw_l['n']}) "
                  f"-> corrected {cor_l['roi_pct']:+.2f}% (n={cor_l['n']})  "
                  f"delta={delta:+.2f}pp  [flips={flips_l}/{nl}]")
            # Symmetry: fit late -> grade early
            beta_l, nl2 = fit_beta(late, stat, key)
            if beta_l is not None:
                raw_e2, cor_e2, flips_e2, ne2 = grade_corrected(early, stat, key, beta_l)
                delta_e = cor_e2["roi_pct"] - raw_e2["roi_pct"]
                print(f"    (symmetry)     raw {raw_e2['roi_pct']:+.2f}% -> "
                      f"corrected {cor_e2['roi_pct']:+.2f}%  delta={delta_e:+.2f}pp  "
                      f"[beta_late={round(beta_l,4)}, flips={flips_e2}/{ne2}]")
            results[stat] = {
                "beta": beta_e, "n_fit": ne,
                "late_raw": raw_l["roi_pct"], "late_cor": cor_l["roi_pct"],
                "late_n": raw_l["n"], "delta": delta, "flips": flips_l,
            }
        else:
            results[stat] = {"beta": None, "n_fit": ne, "late_raw": None, "late_cor": None,
                             "late_n": 0, "delta": None, "flips": 0}

    # === SECTION 3: Selection screen (soft-defense bets) ===
    print("\n--- Section 3: Selection Screen — HIGH signal (soft defense, top 33%) ---")
    print("  Does restricting to bets vs soft-defense teams improve ROI?")
    print("  (both halves shown; must be consistent to avoid overfitting)")

    for stat in STATS:
        ss = selection_screen(bets_prim, "team_def_fg_pct_vs_league", stat, top_pct=0.33)
        if not ss:
            print(f"  {stat.upper()}: insufficient data")
            continue
        print(f"  {stat.upper()}  thresh={ss['thresh']:+.4f}  "
              f"all n={ss['all_n']}  high n={ss['high_n']}  low n={ss['low_n']}")
        print(f"    high-ROI={ss['high_roi']:+.2f}%  low-ROI={ss['low_roi']:+.2f}%")
        print(f"    early-high ROI={ss['high_early_roi']:+.2f}% (n={ss['high_early_n']})  "
              f"late-high ROI={ss['high_late_roi']:+.2f}% (n={ss['high_late_n']})")

    # === SECTION 4: Cross-season ===
    print(f"\n--- Section 4: Cross-Season ({CROSS_CORPUS}) ---")
    print("  NOTE: defender_matchups only covers 2025-26. Cross-season bets (2024-25)")
    print("  will have NO signal coverage -> correction is a no-op for those bets.")
    print("  This section reports signal coverage + raw beta-from-primary outcome.")

    bets_cross = ig.prepare(CROSS_CORPUS)
    bets_cross = attach_defender_signal(bets_cross, idx)
    n_with_sig_cross = sum(1 for b in bets_cross
                           if np.isfinite(b.get("team_def_fg_pct_vs_league", np.nan)))
    print(f"  cross-season bets with defender signal: {n_with_sig_cross}/{len(bets_cross)}")

    coh_cross = ig.coherence(bets_cross)
    print(f"  cross-season COHERENCE: sum={coh_cross['sum']:+.2f}% "
          f"({'OK' if coh_cross['coherent'] else 'CORRUPT!'})")

    for stat in STATS:
        key = "team_def_fg_pct_vs_league"
        beta_full, nf = fit_beta(bets_prim, stat, key)
        if beta_full is not None:
            raw_c, cor_c, flips_c, nc = grade_corrected(bets_cross, stat, key, beta_full)
            delta_c = cor_c["roi_pct"] - raw_c["roi_pct"]
            print(f"  {stat.upper()}  beta_full={round(beta_full,4)}  "
                  f"cross-raw {raw_c['roi_pct']:+.2f}% -> corrected {cor_c['roi_pct']:+.2f}%  "
                  f"delta={delta_c:+.2f}pp  [flips={flips_c}/{nc}]  (coverage={n_with_sig_cross})")
        else:
            print(f"  {stat.upper()} beta_full=None (n_fit={nf})")

    # === Summary ===
    print("\n" + "=" * 72)
    print("VERDICT SUMMARY")
    print("=" * 72)
    for stat in STATS:
        r = results.get(stat, {})
        if r.get("delta") is None:
            print(f"  {stat.upper():5s}: INSUFFICIENT DATA (n_fit={r.get('n_fit',0)})")
        else:
            verdict = "PROMISING" if r["delta"] > 0.5 and r["flips"] > 2 else "REJECT"
            print(f"  {stat.upper():5s}: raw={r['late_raw']:+.2f}% -> corr={r['late_cor']:+.2f}%  "
                  f"delta={r['delta']:+.2f}pp  flips={r['flips']}  beta={round(r['beta'],4)}  "
                  f"-> {verdict}")

    print()
    print("NOTE: defender_matchups has NO off_player_id -> assignment unknowable.")
    print("      Aggregate team-level signal may be too noisy vs per-player matchup signal.")
    print("      Cross-season verdict limited to 2025-26 only.")


if __name__ == "__main__":
    main()
