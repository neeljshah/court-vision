"""
test_v8_clean_subset.py — V8 UNDER Signal: Clean-Subset Bonferroni Analysis
=============================================================================

MOTIVATION:
  Bug 2 (CV_Pipeline_Bug_Roadmap.md): Certain players have all-zero or near-zero
  CV features in the cv_features EAV table despite having game_id records. Their
  ELEVATOR classification in INT-23 (clutch_rankings.json) is therefore derived
  from incomplete or absent behavioral data.

  The "cv_feature_completeness" for a player = (nonzero feature rows) /
  (total feature rows) in nba_ai.db cv_features table. A player with 0% or near-0%
  completeness has their ELEVATOR tag built on noise.

  This script re-runs the V8 UNDER backtest EXCLUDING any ELEVATOR player whose
  cv_feature_completeness is below a configurable threshold, then checks whether
  the cleaner subset crosses the Bonferroni threshold.

IMPORTANT NOTE ON DIRECTIONALITY:
  Per V9 script rationale: V8 showed S4_ELEVATOR_OVER had ROI=-41.57% and WR=0.31,
  meaning actual < line 69% of the time → the deployed bet is UNDER (not OVER).
  Completeness filtering removes players from the UNDER bet pool.

BONFERRONI CONTEXT:
  5-hypothesis family at alpha=0.10 → per-test alpha=0.02 → z_crit = 2.054 (one-sided).
  Break-even WR at -110 odds = 110/210 = 0.52381.

OUTPUTS:
  data/intelligence/v8_clean_subset_results.json
  vault/Intelligence/V8_Clean_Subset_Analysis.md (written by this script)
"""

import json
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")
np.random.seed(42)

ROOT = Path("C:/Users/neelj/nba-ai-system")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
COMPLETENESS_THRESHOLDS = [0.0, 0.05, 0.10, 0.20]  # configurable filter levels
BONFERRONI_Z_CRIT = 2.054   # 5-hypothesis family, alpha=0.10, one-sided
BREAKEVEN_WR = 110 / 210    # 0.52381 at -110 odds
N_BOOT = 5000

print("=" * 70)
print("V8 UNDER Clean-Subset Analysis — Bug 2 Data-Quality Filter")
print("=" * 70)
print()
print(f"Bonferroni z_crit (5-hyp family, alpha=0.10, one-sided): {BONFERRONI_Z_CRIT}")
print(f"Break-even WR at -110 odds: {BREAKEVEN_WR:.4f} ({BREAKEVEN_WR:.2%})")
print()

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    return str(s).strip().lower()


def safe_odds(v) -> float:
    try:
        f = float(v)
        if np.isnan(f) or f == 0:
            return -110.0
        if -99 < f < 100:
            return -110.0
        return f
    except Exception:
        return -110.0


def roi_per_bet(won: bool, odds: float = -110.0) -> float:
    if odds < 0:
        win_amt = 100.0 / abs(odds)
    else:
        win_amt = odds / 100.0
    return win_amt if won else -1.0


def bootstrap_roi_ci(pnl: pd.Series, n_boot: int = N_BOOT, ci: float = 0.95):
    if len(pnl) < 3:
        return (None, None)
    boots = [pnl.sample(frac=1, replace=True).mean() * 100 for _ in range(n_boot)]
    lo = np.percentile(boots, (1 - ci) / 2 * 100)
    hi = np.percentile(boots, (1 + ci) / 2 * 100)
    return (round(float(lo), 2), round(float(hi), 2))


def z_proportion(n_wins: int, n_total: int, p0: float = BREAKEVEN_WR) -> tuple:
    """One-sided z-test: H0: p <= p0  vs  H1: p > p0"""
    if n_total < 5:
        return None, None
    p_hat = n_wins / n_total
    se = (p0 * (1 - p0) / n_total) ** 0.5
    if se == 0:
        return None, None
    z = (p_hat - p0) / se
    p_val = 1 - scipy_stats.norm.cdf(z)
    return round(float(z), 4), round(float(p_val), 5)


def z_roi(pnl: pd.Series) -> tuple:
    """One-sided z-test: H0: mu_pnl <= 0  vs  H1: mu_pnl > 0"""
    if len(pnl) < 5:
        return None, None
    mu = pnl.mean()
    se = pnl.std(ddof=1) / np.sqrt(len(pnl))
    if se == 0:
        return None, None
    z = mu / se
    p_val = 1 - scipy_stats.norm.cdf(z)
    return round(float(z), 4), round(float(p_val), 5)


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD V8 BET POOL FROM v9_unified_results.json
# ─────────────────────────────────────────────────────────────────────────────
print("[1] Loading V8 UNDER bets from v9_unified_results.json ...")

v9_path = ROOT / "data/intelligence/v9_unified_results.json"
if not v9_path.exists():
    print("ERROR: v9_unified_results.json not found. Run test_unified_deployment_v9.py first.")
    sys.exit(1)

with open(v9_path) as f:
    v9_data = json.load(f)

v8_bets_raw = v9_data.get("v8_bets", [])
if not v8_bets_raw:
    print("ERROR: v8_bets list is empty in v9_unified_results.json")
    sys.exit(1)

print(f"  Loaded {len(v8_bets_raw)} V8 UNDER bets from v9 results")

# Per-player summary from raw bets
bets_df = pd.DataFrame(v8_bets_raw)
bets_df["player_norm"] = bets_df["player_name"].map(norm)

print()
print("  Per-player raw bet summary:")
for pn, grp in bets_df.groupby("player_name"):
    n = len(grp)
    wins = grp["won"].sum()
    roi = grp["pnl"].mean() * 100
    print(f"    {pn}: n={n}, wins={wins}, WR={wins/n:.1%}, ROI={roi:+.1f}%")


# ─────────────────────────────────────────────────────────────────────────────
# 2. COMPUTE CV FEATURE COMPLETENESS PER ELEVATOR PLAYER
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[2] Computing CV feature completeness from nba_ai.db cv_features table ...")

# The cv_features table is EAV: (game_id, player_id, feature_name, feature_value)
# Completeness = nonzero values / total values for that player across ALL their game records.
# This is the same db INT-23 used to derive ELEVATOR classifications.

db_path = ROOT / "data/nba_ai.db"
if not db_path.exists():
    print("ERROR: nba_ai.db not found")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cv_all = pd.read_sql(
    "SELECT player_id, feature_name, feature_value FROM cv_features", conn
)
conn.close()
print(f"  cv_features total rows: {len(cv_all):,}")

# Load INT-23 elevator player IDs
clutch_path = ROOT / "data/intelligence/clutch_rankings.json"
with open(clutch_path) as f:
    clutch_data = json.load(f)

elevator_list = clutch_data.get("elevators", [])
elevator_player_ids = {
    norm(e["player_name"]): int(e["player_id"])
    for e in elevator_list
}
elevator_scores = {
    norm(e["player_name"]): e.get("elevator_score", 0.0)
    for e in elevator_list
}
elevator_n_games = {
    norm(e["player_name"]): e.get("n_games", 0)
    for e in elevator_list
}

print()
print("  Per-elevator CV completeness (nba_ai.db cv_features EAV):")
completeness_by_name: dict[str, float] = {}

for pname_norm, pid in elevator_player_ids.items():
    pdata = cv_all[cv_all["player_id"] == pid]
    n_total = len(pdata)
    n_nonzero = (pdata["feature_value"].fillna(0) != 0).sum() if n_total > 0 else 0
    completeness = n_nonzero / n_total if n_total > 0 else 0.0
    completeness_by_name[pname_norm] = completeness

    unique_feats = pdata["feature_name"].nunique() if n_total > 0 else 0
    all_zero = [f for f, g in pdata.groupby("feature_name")
                if (g["feature_value"].fillna(0) == 0).all()] if n_total > 0 else ["N/A"]
    n_games_cv = elevator_n_games[pname_norm]
    elev_score = elevator_scores[pname_norm]

    print(f"    {pname_norm} (id={pid}):")
    print(f"      elevator_score={elev_score:.3f}, n_games_for_INT23={n_games_cv}")
    print(f"      cv_rows={n_total}, unique_feats={unique_feats}, nonzero={n_nonzero}")
    print(f"      completeness={completeness:.2%}")
    print(f"      all-zero features: {all_zero[:6]}{'...' if len(all_zero) > 6 else ''}")
    print()

# Flag: which players are BELOW each threshold?
print("  Summary completeness table:")
print(f"    {'player':<25} {'completeness':>14} {'n_cv_rows':>10}")
for pname_norm in sorted(completeness_by_name):
    pid = elevator_player_ids[pname_norm]
    n_cv = len(cv_all[cv_all["player_id"] == pid])
    comp = completeness_by_name[pname_norm]
    below_10 = " <<BELOW 10%" if comp < 0.10 else ""
    print(f"    {pname_norm:<25} {comp:>13.2%} {n_cv:>10}{below_10}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. APPLY COMPLETENESS FILTERS AND RECOMPUTE V8 STATS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[3] Applying completeness thresholds and recomputing V8 stats ...")
print(f"  Thresholds tested: {COMPLETENESS_THRESHOLDS}")
print()

threshold_results = []

for threshold in COMPLETENESS_THRESHOLDS:
    # Players excluded at this threshold
    excluded = {pn for pn, comp in completeness_by_name.items() if comp < threshold}
    included = {pn for pn in completeness_by_name if pn not in excluded}

    # Filter bet pool
    mask_include = ~bets_df["player_norm"].isin(excluded)
    subset = bets_df[mask_include].copy()

    n = len(subset)
    if n == 0:
        result = {
            "threshold": threshold,
            "excluded_players": sorted(excluded),
            "included_players": sorted(included),
            "n": 0,
            "win_rate": None,
            "roi_pct": None,
            "ci_95": [None, None],
            "z_proportion": None,
            "z_roi": None,
            "p_proportion": None,
            "p_roi": None,
            "crosses_bonferroni_proportion": False,
            "crosses_bonferroni_roi": False,
            "verdict": "EMPTY",
        }
        threshold_results.append(result)
        print(f"  threshold={threshold:.0%}: ALL PLAYERS EXCLUDED — no bets")
        continue

    wins = int(subset["won"].sum())
    pnl = subset["pnl"]
    roi_pct = round(float(pnl.mean() * 100), 2)
    wr = round(float(wins / n), 4)
    ci = bootstrap_roi_ci(pnl)
    zp, pp = z_proportion(wins, n)
    zr, pr = z_roi(pnl)

    crosses_bonf_prop = (zp is not None and zp >= BONFERRONI_Z_CRIT)
    crosses_bonf_roi  = (zr is not None and zr >= BONFERRONI_Z_CRIT)
    crosses_either = crosses_bonf_prop or crosses_bonf_roi

    result = {
        "threshold": threshold,
        "excluded_players": sorted(excluded),
        "included_players": sorted(included),
        "n": n,
        "n_wins": wins,
        "win_rate": wr,
        "roi_pct": roi_pct,
        "ci_95": list(ci),
        "z_proportion": zp,
        "p_proportion": pp,
        "z_roi": zr,
        "p_roi": pr,
        "crosses_bonferroni_proportion": crosses_bonf_prop,
        "crosses_bonferroni_roi": crosses_bonf_roi,
        "crosses_bonferroni_either": crosses_either,
        "verdict": "CROSSES BONFERRONI" if crosses_either else (
            "NEAR BONFERRONI" if (zp is not None and zp >= BONFERRONI_Z_CRIT - 0.15)
            else "BELOW BONFERRONI"
        ),
    }
    threshold_results.append(result)

    gap_prop = (zp - BONFERRONI_Z_CRIT) if zp is not None else None
    gap_str = f"gap={gap_prop:+.4f}" if gap_prop is not None else "gap=N/A"
    excl_str = f"excluded={sorted(excluded)}" if excluded else "excluded=NONE"
    print(f"  threshold={threshold:.0%}:  n={n}, WR={wr:.1%}, ROI={roi_pct:+.1f}%,  "
          f"z_prop={zp},  CI={ci}  |  {gap_str}  |  {excl_str}")
    print(f"    z_roi={zr},  "
          f"crosses_bonferroni_proportion={crosses_bonf_prop},  "
          f"crosses_bonferroni_roi={crosses_bonf_roi}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 4. SAVE JSON OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
print("[4] Saving results to data/intelligence/v8_clean_subset_results.json ...")

# Full per-player betting detail for transparency
per_player_detail = {}
for pn in sorted(bets_df["player_name"].unique()):
    grp = bets_df[bets_df["player_name"] == pn]
    pn_norm = norm(pn)
    per_player_detail[pn] = {
        "player_name": pn,
        "player_name_norm": pn_norm,
        "player_id_in_lines": int(grp["player_id"].iloc[0]) if "player_id" in grp.columns else None,
        "cv_player_id": elevator_player_ids.get(pn_norm),
        "cv_completeness": completeness_by_name.get(pn_norm, 0.0),
        "elevator_score": elevator_scores.get(pn_norm),
        "n_bets": len(grp),
        "n_wins": int(grp["won"].sum()),
        "win_rate": round(float(grp["won"].mean()), 4),
        "roi_pct": round(float(grp["pnl"].mean() * 100), 2),
        "bet_dates": sorted(str(d)[:10] for d in grp["game_date"].tolist()),
    }

output = {
    "meta": {
        "generated": pd.Timestamp.now().isoformat()[:19],
        "version": "V8-CleanSubset",
        "bonferroni_z_crit": BONFERRONI_Z_CRIT,
        "bonferroni_family_size": 5,
        "bonferroni_alpha": 0.10,
        "breakeven_wr": BREAKEVEN_WR,
        "total_bets_original": len(bets_df),
        "original_win_rate": round(float(bets_df["won"].mean()), 4),
        "original_roi_pct": round(float(bets_df["pnl"].mean() * 100), 2),
        "motivation": (
            "Bug 2 (CV_Pipeline_Bug_Roadmap.md): Players with cv_feature_completeness < 10% "
            "have their ELEVATOR classification built on absent/corrupted CV data. "
            "This is a DATA QUALITY exclusion, independent of betting performance. "
            "If a player has zero useful CV behavioral data, their INT-23 tag is unreliable."
        ),
        "honest_note": (
            "This analysis was motivated by observing that Stephen Curry has all-zero "
            "cv_features in nba_ai.db (completeness=7.14%). The data-quality filter is "
            "justified independently — we would apply it regardless of Curry's betting record. "
            "However: Curry's ACTUAL betting record is 7/7 WINS (ROI=+85.3%), not 0/7 as "
            "previously reported. The revalidation doc had the direction inverted. "
            "Excluding a 7/7 WINNER on data-quality grounds HURTS V8 performance. "
            "This is the correct and honest outcome of the analysis."
        ),
        "thresholds_tested": COMPLETENESS_THRESHOLDS,
    },
    "per_player_detail": per_player_detail,
    "threshold_results": threshold_results,
}

out_path = ROOT / "data/intelligence/v8_clean_subset_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved: {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. PRINT FINAL HEADLINE TABLE
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 90)
print("V8 UNDER Clean-Subset — Headline Results Table")
print("=" * 90)
print()
print(f"  {'threshold':<12} {'n':>4} {'WR':>8} {'ROI':>8} {'z_proportion':>14} {'z_roi':>8} {'crosses Bonf?':>15}")
print("  " + "-" * 74)
for r in threshold_results:
    if r["n"] == 0:
        print(f"  {r['threshold']:.0%}          {'0':>4}  {'N/A':>7}  {'N/A':>7}  {'N/A':>13}  {'N/A':>7}  {'N/A':<15}")
        continue
    excl_tag = f"  (excl: {', '.join(r['excluded_players'])})" if r["excluded_players"] else "  (all included)"
    zp_str = f"{r['z_proportion']:.4f}" if r["z_proportion"] is not None else "N/A"
    zr_str = f"{r['z_roi']:.4f}" if r["z_roi"] is not None else "N/A"
    bonf_str = "YES ***" if r["crosses_bonferroni_either"] else (
        "NEAR (<0.15)" if r.get("verdict") == "NEAR BONFERRONI" else "NO"
    )
    print(f"  {r['threshold']:.0%}          {r['n']:>4}  {r['win_rate']:>7.1%}  {r['roi_pct']:>+7.1f}%  "
          f"{zp_str:>13}  {zr_str:>7}  {bonf_str:<15}{excl_tag}")
print()
print(f"  Bonferroni threshold: z >= {BONFERRONI_Z_CRIT}")
print()

# Key conclusion
print("=" * 90)
print("KEY FINDINGS")
print("=" * 90)
print()

# Show what happens at 10% threshold specifically
t10 = next((r for r in threshold_results if r["threshold"] == 0.10), None)
if t10:
    if t10["n"] > 0:
        cross = "CROSSES" if t10["crosses_bonferroni_either"] else "DOES NOT CROSS"
        print(f"  At 10% completeness threshold (Bug 2 natural cutoff):")
        print(f"    Players excluded: {t10['excluded_players']}")
        print(f"    n={t10['n']}, WR={t10['win_rate']:.1%}, ROI={t10['roi_pct']:+.1f}%")
        print(f"    z_proportion={t10['z_proportion']}, z_roi={t10['z_roi']}")
        print(f"    Result: {cross} Bonferroni (z_crit={BONFERRONI_Z_CRIT})")
    print()

# Curry note
curry_comp = completeness_by_name.get("stephen curry", 0.0)
print(f"  CRITICAL FINDING — Curry's actual record in V8 UNDER is 7/7 WINS (ROI=+85.3%).")
print(f"  His cv_feature_completeness = {curry_comp:.2%} (below 10% threshold).")
print(f"  Excluding him on Bug 2 grounds REMOVES 7 winning bets from the pool.")
print(f"  This DEGRADES V8 performance at threshold >= 10%, not improves it.")
print(f"  The revalidation doc's 'Curry 0/7 UNDER' description was an error in direction.")
print()

# Keshad Johnson note
kj_comp = completeness_by_name.get("keshad johnson", 0.0)
print(f"  Keshad Johnson completeness = {kj_comp:.2%}. Zero PTS lines in pool anyway — no bets.")
print()

# Multiple-testing note
print("  MULTIPLE TESTING CAUTION:")
print(f"  Testing 4 completeness thresholds expands the family by 4. If any threshold")
print(f"  shows z >= {BONFERRONI_Z_CRIT} that result should be treated with extra skepticism")
print(f"  unless it is robust across multiple thresholds. Within-threshold Bonferroni")
print(f"  was designed for 5 original hypotheses; threshold-sweep adds 3 more comparisons.")
print()

print("=" * 90)
print(f"JSON output: {out_path}")
print("=" * 90)
