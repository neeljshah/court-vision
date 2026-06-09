"""
test_c1_clean_backtest.py
==========================
C1 Clean-Label Re-test: HOT_PTS (INT-5) x HELP_DEFENSE (INT-12) -> OVER PTS

Uses the REBUILT streak_signatures.parquet (Bug 7 + Bug 5 + Bug 29 fixed labels).
Compares against pre-fix baseline: n=52, WR=67.3%, ROI=+1.82 shift, z=2.09.

Also tests C1+C2 meta-signal:
  HOT_PTS x (HELP_DEFENSE OR PERIMETER_DENIAL) -> OVER PTS

Outputs:
  data/intelligence/c1_clean_backtest_results.json
  vault/Intelligence/C1_Clean_Backtest_Result.md

Constraints:
  - NO pre-fix streak_signatures snapshot used anywhere
  - Curry excluded (Bug 29) — verified not in atlas
  - safe_odds() guard applied (from V8 pattern)
  - Bonferroni z_crit = 2.054 (k=5 hypotheses, alpha=0.10)
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

sys.path.insert(0, str(Path(__file__).parent))
from lib_betting_validation import safe_odds  # Bug 10 guard

warnings.filterwarnings("ignore")
np.random.seed(42)

ROOT = Path("C:/Users/neelj/nba-ai-system")
INTEL = ROOT / "data/intelligence"
LINES_DIR = ROOT / "data/external/historical_lines"

BONFERRONI_Z_CRIT = 2.054   # k=5 tests, alpha=0.10 one-sided
PRE_FIX_N   = 52
PRE_FIX_WR  = 0.673
PRE_FIX_MU  = 1.82
PRE_FIX_Z   = 2.09
PRE_FIX_CI  = (0.17, 3.58)
PRE_FIX_P   = 0.018

# Zero-CV exclusion list (Bug 29)
ZERO_CV_PLAYERS = {"stephen curry", "keshad johnson"}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS (identical to V6/V8 pattern)
# ─────────────────────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    return str(s).strip().lower()


# safe_odds imported from lib_betting_validation above
def _safe_odds_extended(v) -> float:
    """Extended range check (kept as reference; safe_odds from lib is canonical)."""
    try:
        f = float(v)
        if np.isnan(f) or f == 0:
            return -110.0
        if -99 < f < 100:          # not a valid American-odds value
            return -110.0
        if f < -300 or f > 500:    # explicitly out-of-range guard
            return -110.0
        return f
    except Exception:
        return -110.0


def roi_per_bet(won: bool, odds: float = -110.0) -> float:
    """Unit-stake P&L at given American odds (1 unit risked)."""
    if odds < 0:
        win_amt = 100.0 / abs(odds)
    else:
        win_amt = odds / 100.0
    return win_amt if won else -1.0


def bootstrap_roi_ci(pnl_series: pd.Series, n_boot: int = 3000, ci: float = 0.95):
    """Bootstrap CI on mean unit ROI * 100 (i.e., ROI%)."""
    if len(pnl_series) < 3:
        return (None, None)
    boots = [pnl_series.sample(frac=1, replace=True).mean() * 100 for _ in range(n_boot)]
    lo = np.percentile(boots, (1 - ci) / 2 * 100)
    hi = np.percentile(boots, (1 + ci) / 2 * 100)
    return (round(float(lo), 2), round(float(hi), 2))


def bootstrap_shift_ci(shift_series: pd.Series, n_boot: int = 3000):
    """Bootstrap 95% CI on mean stat shift (pts above line)."""
    if len(shift_series) < 3:
        return (None, None)
    boots = [shift_series.sample(frac=1, replace=True).mean() for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (round(float(lo), 4), round(float(hi), 4))


def z_roi_gt_zero(pnl_series: pd.Series):
    """One-sample z-test: is mean PnL significantly > 0?"""
    if len(pnl_series) < 5:
        return None, None
    mu = pnl_series.mean()
    se = pnl_series.std(ddof=1) / np.sqrt(len(pnl_series))
    if se == 0:
        return None, None
    z = mu / se
    p = float(1 - scipy_stats.norm.cdf(z))
    return round(float(z), 4), round(float(p), 5)


def z_proportion(wins: int, n: int):
    """One-sided proportion z-test: is WR > 0.5?"""
    if n < 5:
        return None, None
    p_hat = wins / n
    se = np.sqrt(0.5 * 0.5 / n)
    z = (p_hat - 0.5) / se
    p = float(1 - scipy_stats.norm.cdf(z))
    return round(float(z), 4), round(float(p), 5)


def z_shift(shift_series: pd.Series):
    """One-sided z-test: is mean shift > 0?"""
    n = len(shift_series)
    if n < 5:
        return None, None
    mu = shift_series.mean()
    se = shift_series.std(ddof=1) / np.sqrt(n)
    if se == 0:
        return None, None
    z = mu / se
    p = float(1 - scipy_stats.norm.cdf(z))
    return round(float(z), 4), round(float(p), 5)


def aggregate_signal(bets_list: list, name: str) -> dict:
    if not bets_list:
        return {
            "name": name, "n": 0, "win_rate": None, "roi_flat_pct": None,
            "ci_95_roi": [None, None], "z_roi": None, "p_roi": None,
            "z_proportion": None, "p_proportion": None,
            "mean_shift": None, "ci_95_shift": [None, None],
            "z_shift": None, "p_shift": None,
            "verdict": "INSUFFICIENT_SAMPLE",
        }
    df = pd.DataFrame(bets_list)
    n = len(df)
    wins = int(df["won"].sum())
    wr = float(df["won"].mean())
    roi_flat = float(df["pnl"].mean() * 100)
    shift_s = df["shift"]
    mean_shift = float(shift_s.mean())
    ci_roi = bootstrap_roi_ci(df["pnl"]) if n >= 3 else (None, None)
    ci_shift = bootstrap_shift_ci(shift_s) if n >= 3 else (None, None)
    z_r, p_r = z_roi_gt_zero(df["pnl"]) if n >= 5 else (None, None)
    z_p, p_p = z_proportion(wins, n)
    z_s, p_s = z_shift(shift_s)

    if n < 10:
        verdict = "TOO_SMALL"
    elif n < 20:
        verdict = "SMALL_SAMPLE"
    elif ci_roi[0] is not None and ci_roi[0] > 0:
        verdict = "POSITIVE_CI"
    elif roi_flat > 3.0:
        verdict = "POSITIVE_ROI"
    elif roi_flat < -3.0:
        verdict = "NEGATIVE_ROI"
    else:
        verdict = "NOISE"

    return {
        "name": name,
        "n": n,
        "wins": wins,
        "win_rate": round(wr, 4),
        "roi_flat_pct": round(roi_flat, 2),
        "ci_95_roi": list(ci_roi),
        "z_roi": z_r,
        "p_roi": p_r,
        "z_proportion": z_p,
        "p_proportion": p_p,
        "mean_shift": round(mean_shift, 4),
        "ci_95_shift": list(ci_shift),
        "z_shift": z_s,
        "p_shift": p_s,
        "verdict": verdict,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("C1 CLEAN BACKTEST — HOT_PTS x HELP_DEFENSE -> OVER PTS")
print("Using REBUILT streak_signatures (Bug 7 + Bug 5 + Bug 29 fixed)")
print("=" * 70)
print()

print("[1] Loading intelligence sources...")

streak = pd.read_parquet(INTEL / "streak_signatures.parquet")
streak["player_norm"] = streak["player_name"].map(norm)
print(f"  streak_signatures: {len(streak)} rows, {streak['player_norm'].nunique()} players")
print(f"  HOT_PTS count: {(streak['label_pts']=='HOT').sum()}")
print(f"  Label method: post-Bug7 (prior-5-game rolling window)")

# Verify Curry is absent
curry_check = streak[streak["player_norm"].str.contains("curry", na=False)]
if len(curry_check) > 0:
    raise RuntimeError(f"Bug 29 gate failed — Curry is still in atlas: {curry_check['player_name'].tolist()}")
print("  Curry exclusion check: PASSED (Curry not in atlas)")

schemes = pd.read_parquet(INTEL / "defensive_schemes.parquet")
help_def_teams = schemes[schemes["all_tags"].str.contains("HELP DEFENSE", na=False)]["team"].tolist()
perim_denial_teams = schemes[schemes["dominant_tag"].str.contains("PERIMETER DENIAL", na=False)]["team"].tolist()
print(f"  HELP DEFENSE teams: {help_def_teams}")
print(f"  PERIM DENIAL teams: {perim_denial_teams}")

print()
print("[2] Loading sportsbook lines pool...")

line_sources = [
    ROOT / "data/external/historical_lines/extended_oos_canonical.csv",
    ROOT / "data/external/historical_lines/benashkar_2026_canonical.csv",
    ROOT / "data/external/historical_lines/regular_season_2025_26_oddsapi.csv",
    ROOT / "data/external/historical_lines/regular_season_2024_25_oddsapi.csv",
]

line_dfs = []
for p in line_sources:
    if p.exists():
        d = pd.read_csv(p, on_bad_lines="skip")
        d["date"] = pd.to_datetime(d["date"])
        d["player_norm"] = d["player"].map(norm)
        d["stat"] = d["stat"].str.lower().str.strip()
        d["opp"] = d["opp"].str.upper().str.strip()
        line_dfs.append(d)
        print(f"  Loaded {p.name}: {len(d):,} rows")

if not line_dfs:
    raise RuntimeError("No line files found!")

lines_pool = (
    pd.concat(line_dfs, ignore_index=True)
    .drop_duplicates(subset=["player_norm", "date", "stat"])
    .reset_index(drop=True)
)
lines_pool = lines_pool.dropna(subset=["actual_value", "closing_line"])
for _odds_col in ("over_odds", "under_odds"):  # Bug 10 guard
    if _odds_col in lines_pool.columns:
        lines_pool[_odds_col] = lines_pool[_odds_col].apply(safe_odds)
pts_lines = lines_pool[lines_pool["stat"] == "pts"].copy()
print(f"  Total lines pooled: {len(lines_pool):,}")
print(f"  PTS lines: {len(pts_lines):,}")
print(f"  Date range: {pts_lines['date'].min().date()} to {pts_lines['date'].max().date()}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. BUILD PLAYER SETS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[3] Building player sets from CLEAN atlas...")

hot_pts_players = {
    p for p in streak[streak["label_pts"] == "HOT"]["player_norm"].unique()
    if p not in ZERO_CV_PLAYERS
}
print(f"  HOT_PTS players (clean, n={len(hot_pts_players)}): {sorted(hot_pts_players)}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. BUILD BET LOGS
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[4] Building bet logs...")


def build_bets_for_signal(player_set, opp_teams, signal_name):
    """Build per-bet records for a signal."""
    sub = pts_lines[
        pts_lines["player_norm"].isin(player_set) &
        pts_lines["opp"].isin(opp_teams)
    ].copy()
    bets = []
    for _, row in sub.iterrows():
        over_odds = safe_odds(row.get("over_odds", -110))
        line = float(row["closing_line"])
        actual = float(row["actual_value"])
        won = actual > line
        pnl = roi_per_bet(won, over_odds)
        shift = actual - line
        bets.append({
            "player": str(row["player"]),
            "player_norm": str(row["player_norm"]),
            "game_date": str(row["date"])[:10],
            "opp": str(row["opp"]),
            "closing_line": line,
            "actual_value": actual,
            "shift": shift,
            "over_odds": over_odds,
            "won": bool(won),
            "pnl": float(pnl),
            "signal": signal_name,
        })
    return bets


# C1: HOT_PTS x HELP_DEFENSE -> OVER PTS
c1_bets = build_bets_for_signal(hot_pts_players, help_def_teams, "C1_HOT_PTS_x_HELP_DEFENSE")
c1_stats = aggregate_signal(c1_bets, "C1_HOT_PTS_x_HELP_DEFENSE")

# C2 standalone: HOT_PTS x PERIM_DENIAL -> OVER PTS
c2_bets = build_bets_for_signal(hot_pts_players, perim_denial_teams, "C2_HOT_PTS_x_PERIM_DENIAL")
c2_stats = aggregate_signal(c2_bets, "C2_HOT_PTS_x_PERIM_DENIAL")

# C1+C2 meta-signal: HOT_PTS x (HELP_DEF OR PERIM_DENIAL)
c1c2_bets = build_bets_for_signal(
    hot_pts_players,
    list(set(help_def_teams + perim_denial_teams)),
    "C1C2_META_HOT_PTS_x_HELP_OR_PERIM"
)
c1c2_stats = aggregate_signal(c1c2_bets, "C1C2_META_HOT_PTS_x_HELP_OR_PERIM")

print(f"  C1  (HELP_DEF):     n={c1_stats['n']}, WR={c1_stats['win_rate']}, "
      f"ROI={c1_stats['roi_flat_pct']}%, z_shift={c1_stats['z_shift']}, "
      f"mean_shift={c1_stats['mean_shift']}")
print(f"  C2  (PERIM_DENIAL): n={c2_stats['n']}, WR={c2_stats['win_rate']}, "
      f"ROI={c2_stats['roi_flat_pct']}%, z_shift={c2_stats['z_shift']}, "
      f"mean_shift={c2_stats['mean_shift']}")
print(f"  C1+C2 meta:         n={c1c2_stats['n']}, WR={c1c2_stats['win_rate']}, "
      f"ROI={c1c2_stats['roi_flat_pct']}%, z_shift={c1c2_stats['z_shift']}, "
      f"mean_shift={c1c2_stats['mean_shift']}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. BONFERRONI ANALYSIS + VERDICT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[5] Bonferroni analysis and verdicts...")

def bonferroni_distance(z_val, z_crit=BONFERRONI_Z_CRIT):
    if z_val is None:
        return None
    return round(float(z_val - z_crit), 4)


def signal_verdict(stats: dict, signal_label: str) -> str:
    """Map stats to SIGNAL_SURVIVED / SIGNAL_DECAYED / SIGNAL_GONE."""
    n = stats["n"]
    z = stats["z_shift"]
    wr = stats["win_rate"] or 0
    ci_lo = stats["ci_95_shift"][0]

    if n < 10:
        return "SIGNAL_GONE"
    if z is None:
        return "SIGNAL_GONE"
    if z >= BONFERRONI_Z_CRIT and ci_lo is not None and ci_lo > 0:
        return "SIGNAL_SURVIVED"
    if z >= 1.28 and wr >= 0.55:  # one-tail 10%, WR > 55%
        return "SIGNAL_DECAYED"
    if z >= 0.5 and wr >= 0.50:
        return "SIGNAL_DECAYED"
    return "SIGNAL_GONE"


c1_verdict = signal_verdict(c1_stats, "C1")
c2_verdict = signal_verdict(c2_stats, "C2")
c1c2_verdict = signal_verdict(c1c2_stats, "C1+C2 meta")

c1_bonf_dist = bonferroni_distance(c1_stats["z_shift"])
c1c2_bonf_dist = bonferroni_distance(c1c2_stats["z_shift"])

print(f"  C1 verdict:     {c1_verdict}")
print(f"  C2 verdict:     {c2_verdict}")
print(f"  C1+C2 verdict:  {c1c2_verdict}")
print(f"  C1  z vs Bonferroni ({BONFERRONI_Z_CRIT}): {c1_bonf_dist:+.4f}" if c1_bonf_dist is not None else "  C1 z: N/A")
print(f"  C1+C2 z vs Bonferroni ({BONFERRONI_Z_CRIT}): {c1c2_bonf_dist:+.4f}" if c1c2_bonf_dist is not None else "  C1+C2 z: N/A")


# ─────────────────────────────────────────────────────────────────────────────
# 5. PER-BET DETAIL PRINTOUT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[6] Per-bet detail for C1:")
if c1_bets:
    for b in sorted(c1_bets, key=lambda x: x["game_date"]):
        result = "WIN" if b["won"] else "LOSS"
        print(f"  {b['player']:25s} {b['game_date']} vs {b['opp']:3s} "
              f"line={b['closing_line']:.1f} actual={b['actual_value']:.1f} "
              f"shift={b['shift']:+.1f} odds={b['over_odds']:+.0f} [{result}]")
else:
    print("  No bets found.")


# ─────────────────────────────────────────────────────────────────────────────
# 6. SAVE JSON OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[7] Saving results...")

output = {
    "meta": {
        "generated": pd.Timestamp.now().isoformat()[:19],
        "script": "scripts/test_c1_clean_backtest.py",
        "label_method": "Bug-7-fixed rolling prior-5-game window (no same-game leakage)",
        "atlas_version": "post-Bug7-Bug5-Bug29",
        "bonferroni_z_crit": BONFERRONI_Z_CRIT,
        "bonferroni_k": 5,
        "bonferroni_alpha": 0.10,
        "curry_in_atlas": False,
        "zero_cv_exclusions": sorted(ZERO_CV_PLAYERS),
        "safe_odds_guard": "reject < -300 or > +500",
        "help_def_teams": help_def_teams,
        "perim_denial_teams": perim_denial_teams,
        "hot_pts_players_clean": sorted(hot_pts_players),
        "hot_pts_n_clean": len(hot_pts_players),
    },
    "pre_fix_baseline": {
        "n": PRE_FIX_N,
        "win_rate": PRE_FIX_WR,
        "mean_shift": PRE_FIX_MU,
        "z": PRE_FIX_Z,
        "p": PRE_FIX_P,
        "ci_95_shift": list(PRE_FIX_CI),
        "label_method": "same-game z-score (BUG: leakage)",
        "curry_included": True,
    },
    "signals": {
        "c1_hot_pts_x_help_defense": {
            **c1_stats,
            "verdict": c1_verdict,
            "bonferroni_distance": c1_bonf_dist,
            "bets": c1_bets,
        },
        "c2_hot_pts_x_perim_denial": {
            **c2_stats,
            "verdict": c2_verdict,
            "bonferroni_distance": bonferroni_distance(c2_stats["z_shift"]),
            "bets": c2_bets,
        },
        "c1c2_meta_hot_pts_x_help_or_perim": {
            **c1c2_stats,
            "verdict": c1c2_verdict,
            "bonferroni_distance": c1c2_bonf_dist,
            "bets": c1c2_bets,
        },
    },
    "comparison_table": {
        "pre_fix": {
            "n": PRE_FIX_N, "win_rate": PRE_FIX_WR, "mean_shift": PRE_FIX_MU,
            "z": PRE_FIX_Z, "p": PRE_FIX_P, "ci_95_shift": list(PRE_FIX_CI),
        },
        "post_fix_c1": {
            "n": c1_stats["n"], "win_rate": c1_stats["win_rate"],
            "mean_shift": c1_stats["mean_shift"],
            "z": c1_stats["z_shift"], "p": c1_stats["p_shift"],
            "ci_95_shift": c1_stats["ci_95_shift"],
            "roi_flat_pct": c1_stats["roi_flat_pct"],
            "z_roi": c1_stats["z_roi"],
        },
        "post_fix_c1c2_meta": {
            "n": c1c2_stats["n"], "win_rate": c1c2_stats["win_rate"],
            "mean_shift": c1c2_stats["mean_shift"],
            "z": c1c2_stats["z_shift"], "p": c1c2_stats["p_shift"],
            "ci_95_shift": c1c2_stats["ci_95_shift"],
            "roi_flat_pct": c1c2_stats["roi_flat_pct"],
            "z_roi": c1c2_stats["z_roi"],
        },
    },
}

out_json = INTEL / "c1_clean_backtest_results.json"
with open(out_json, "w") as f:
    json.dump(output, f, indent=2, default=str)
print(f"  Saved: {out_json}")


# ─────────────────────────────────────────────────────────────────────────────
# 7. WRITE VAULT MD
# ─────────────────────────────────────────────────────────────────────────────
def fmt_ci(ci):
    if ci[0] is None:
        return "N/A"
    return f"[{ci[0]}, {ci[1]}]"


def fmt_z(z, p):
    if z is None:
        return "N/A"
    return f"{z:.3f} (p={p:.4f})"


def deployment_posture(stats, verdict, bonf_dist):
    """Return deployment recommendation based on signal strength."""
    n = stats["n"]
    z = stats["z_shift"]
    if verdict == "SIGNAL_GONE":
        return "DO NOT DEPLOY — signal gone after leakage removal. Bug 7 was the signal."
    if verdict == "SIGNAL_SURVIVED":
        gap = f"{bonf_dist:+.3f}" if bonf_dist is not None else "N/A"
        return (f"DEPLOY (watch-list) — signal survived clean labels. "
                f"Bonferroni gap: {gap}. Recommend n>=30 before live sizing.")
    if verdict == "SIGNAL_DECAYED":
        if n < 15:
            return (f"MONITOR — signal decayed but residual is directional (z={z:.3f}). "
                    f"n={n} is too small for deployment. Watch as CV coverage grows.")
        return (f"WATCH — signal decayed (z={z:.3f} < Bonferroni {BONFERRONI_Z_CRIT}). "
                f"Directional residual present. Do not deploy until z > {BONFERRONI_Z_CRIT}.")
    return "INCONCLUSIVE"


c1_posture = deployment_posture(c1_stats, c1_verdict, c1_bonf_dist)
c1c2_posture = deployment_posture(c1c2_stats, c1c2_verdict, c1c2_bonf_dist)

# Bug 7 leakage attribution
n_drop = PRE_FIX_N - c1_stats["n"]
pct_drop = 100.0 * n_drop / PRE_FIX_N if PRE_FIX_N > 0 else 0

# Determine if Bug 7 was the ENTIRE signal
if c1_verdict == "SIGNAL_GONE":
    bug7_attribution = (
        f"**Bug 7 leakage was the primary driver of the pre-fix signal.** "
        f"n dropped from {PRE_FIX_N} → {c1_stats['n']} ({pct_drop:.0f}% reduction). "
        f"The remaining {c1_stats['n']} bets show {c1_stats['win_rate']:.1%} WR "
        f"and z={c1_stats.get('z_shift', 'N/A')}. "
        f"There is no meaningful residual above noise."
    )
elif c1_verdict == "SIGNAL_DECAYED":
    bug7_attribution = (
        f"**Bug 7 leakage inflated the pre-fix signal substantially.** "
        f"n dropped from {PRE_FIX_N} → {c1_stats['n']} ({pct_drop:.0f}% reduction). "
        f"A directional residual persists (z={c1_stats.get('z_shift', 'N/A')}) "
        f"but is sub-Bonferroni. Signal was real but overstated by "
        f"{PRE_FIX_Z - (c1_stats.get('z_shift') or 0):.2f}z units."
    )
else:
    bug7_attribution = (
        f"Bug 7 leakage was not the primary driver. "
        f"The signal survives on clean labels with z={c1_stats.get('z_shift', 'N/A')}."
    )


md = f"""---
created: 2026-05-28
type: backtest
signal: C1 HOT_PTS x HELP_DEFENSE -> OVER PTS
atlas: streak_signatures post-Bug7-Bug5-Bug29
script: scripts/test_c1_clean_backtest.py
json: data/intelligence/c1_clean_backtest_results.json
---

# C1 Clean-Label Backtest Result

> **Re-test of C1 (HOT_PTS × HELP_DEFENSE → OVER PTS) on REBUILT atlas**
> Bug 7 (same-game leakage) + Bug 5 (CV-quality gate) + Bug 29 (zero-CV exclusion) all fixed.
> Pre-fix signal was computed on contaminated labels. This is the honest re-evaluation.

---

## Pre-fix vs Post-fix Comparison

| Metric | Pre-fix (BUG 7 leak) | Post-fix (clean) | Change |
|--------|---------------------|------------------|--------|
| n (player-games) | {PRE_FIX_N} | {c1_stats['n']} | {c1_stats['n'] - PRE_FIX_N:+d} ({pct_drop:.0f}% drop) |
| Win Rate (OVER) | {PRE_FIX_WR:.1%} | {f"{c1_stats['win_rate']:.1%}" if c1_stats['win_rate'] else 'N/A'} | {f"{(c1_stats['win_rate'] or 0) - PRE_FIX_WR:+.1%}" if c1_stats['win_rate'] else 'N/A'} |
| Mean shift (pts vs line) | +{PRE_FIX_MU:.2f} | {f"{c1_stats['mean_shift']:+.2f}" if c1_stats['mean_shift'] else 'N/A'} | {f"{(c1_stats['mean_shift'] or 0) - PRE_FIX_MU:+.2f}" if c1_stats['mean_shift'] else 'N/A'} |
| z-stat (shift) | {PRE_FIX_Z:.3f} | {fmt_z(c1_stats['z_shift'], c1_stats['p_shift'])} | - |
| 95% CI (shift) | {fmt_ci(list(PRE_FIX_CI))} | {fmt_ci(c1_stats['ci_95_shift'])} | - |
| p-value | {PRE_FIX_P:.4f} | {f"{c1_stats['p_shift']:.4f}" if c1_stats['p_shift'] else 'N/A'} | - |
| ROI (flat Kelly @-110) | est. +~9-12% | {f"{c1_stats['roi_flat_pct']:+.2f}%" if c1_stats['roi_flat_pct'] else 'N/A'} | - |
| Curry in sample? | YES | NO (Bug 29) | Excluded |
| Label method | Same-game z (leakage) | Prior-5-game rolling | Fixed |

---

## Verdict: **{c1_verdict}**

{bug7_attribution}

### Deployment posture
{c1_posture}

### Bonferroni distance
- Required z-crit: {BONFERRONI_Z_CRIT} (k=5, alpha=0.10 one-sided)
- C1 post-fix z: {c1_stats.get('z_shift', 'N/A')}
- Distance from Bonferroni: {f"{c1_bonf_dist:+.4f}" if c1_bonf_dist is not None else 'N/A'}

---

## C1+C2 Meta-Signal: HOT_PTS × (HELP_DEF OR PERIM_DENIAL) → OVER PTS

Pre-fix estimate: n~73, z~2.1-2.3

| Metric | Post-fix result |
|--------|----------------|
| n | {c1c2_stats['n']} |
| Win Rate | {f"{c1c2_stats['win_rate']:.1%}" if c1c2_stats['win_rate'] else 'N/A'} |
| Mean shift | {f"{c1c2_stats['mean_shift']:+.2f}" if c1c2_stats['mean_shift'] else 'N/A'} pts |
| z-stat (shift) | {fmt_z(c1c2_stats['z_shift'], c1c2_stats['p_shift'])} |
| 95% CI (shift) | {fmt_ci(c1c2_stats['ci_95_shift'])} |
| ROI flat | {f"{c1c2_stats['roi_flat_pct']:+.2f}%" if c1c2_stats['roi_flat_pct'] else 'N/A'} |
| Bonferroni distance | {f"{c1c2_bonf_dist:+.4f}" if c1c2_bonf_dist is not None else 'N/A'} |
| **Verdict** | **{c1c2_verdict}** |

**C1+C2 posture:** {c1c2_posture}

---

## Per-Bet Audit (C1: HOT_PTS x HELP_DEFENSE)

| Player | Date | OPP | Line | Actual | Shift | Odds | Result |
|--------|------|-----|------|--------|-------|------|--------|
"""

for b in sorted(c1_bets, key=lambda x: x["game_date"]):
    result_str = "WIN" if b["won"] else "LOSS"
    md += (f"| {b['player']} | {b['game_date']} | {b['opp']} "
           f"| {b['closing_line']:.1f} | {b['actual_value']:.1f} "
           f"| {b['shift']:+.1f} | {b['over_odds']:+.0f} | **{result_str}** |\n")

if not c1_bets:
    md += "| *(no bets found)* | - | - | - | - | - | - | - |\n"

md += f"""
---

## Root Cause Analysis

### Was Bug 7 the entire signal?
{bug7_attribution}

### n shrinkage breakdown
- Pre-fix HOT_PTS = {PRE_FIX_N} (included same-game z-scored labels + Curry + low-CV games)
- Clean HOT_PTS players in atlas = {len(hot_pts_players)}
- C1 matched bets (HOT players vs HELP DEF teams in lines pool) = {c1_stats['n']}
- Key drop drivers:
  - Bug 7 label shift: 31 pre-fix HOT → 9 still HOT post-shift (from Bug_7_5_29_Fix_Verification.md)
  - Bug 5 CV gate: removed 36% of rows with n_nonzero_cv < 5
  - Bug 29: Curry excluded (was 1 HOT row in pre-fix atlas)
  - Lines pool coverage: HOT players not appearing in same games as HELP DEF opponents

### Leakage mechanism
Same-game z-score (pre-fix): labeled a game HOT if pts were ≥1.5z above **that same game's** contribution
to the rolling mean — a circular definition. Players appeared HOT precisely in their big games,
which by construction would OVER their normal line. Post-fix: HOT means pts ≥1.5z above the
**prior 5 games' mean/std** — a genuine forward-looking signal. The drop from z=2.09 to
z={c1_stats.get('z_shift', 'N/A')} directly measures how much of the pre-fix signal was this artifact.

---

## C2 Standalone (HOT_PTS x PERIM_DENIAL)

| Metric | Result |
|--------|--------|
| n | {c2_stats['n']} |
| Win Rate | {f"{c2_stats['win_rate']:.1%}" if c2_stats['win_rate'] else 'N/A'} |
| Mean shift | {f"{c2_stats['mean_shift']:+.2f}" if c2_stats['mean_shift'] else 'N/A'} pts |
| z-stat | {fmt_z(c2_stats['z_shift'], c2_stats['p_shift'])} |
| Verdict | {c2_verdict} |

---

## Connections
- [[Bug_7_5_29_Fix_Verification]] — describes what changed
- [[Compound_Signal_Candidates]] — original C1 spec and pre-fix numbers
- [[Streak_Atlas]] — rebuilt HOT/COLD labels
- [[Defensive_Schemes_Atlas]] — INT-12 team tags
"""

vault_path = ROOT / "vault/Intelligence/C1_Clean_Backtest_Result.md"
vault_path.parent.mkdir(parents=True, exist_ok=True)
with open(vault_path, "w", encoding="utf-8") as f:
    f.write(md)
print(f"  Vault note saved: {vault_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("C1 CLEAN BACKTEST — FINAL SUMMARY")
print("=" * 70)
print()
print(f"Pre-fix:  n={PRE_FIX_N}, WR={PRE_FIX_WR:.1%}, "
      f"shift={PRE_FIX_MU:+.2f}, z={PRE_FIX_Z:.3f}, "
      f"CI=[{PRE_FIX_CI[0]}, {PRE_FIX_CI[1]}], p={PRE_FIX_P:.4f}")
print(f"Post-fix: n={c1_stats['n']}, WR={c1_stats['win_rate']:.1%} (if n>0 else N/A), "
      f"shift={c1_stats['mean_shift'] or 'N/A'}, "
      f"z={c1_stats['z_shift'] or 'N/A'}, "
      f"CI={c1_stats['ci_95_shift']}, "
      f"p={c1_stats['p_shift'] or 'N/A'}")
print()
print(f"VERDICT (C1):     {c1_verdict}")
print(f"VERDICT (C1+C2):  {c1c2_verdict} (n={c1c2_stats['n']}, z={c1c2_stats['z_shift']})")
print(f"Bonferroni dist:  C1={c1_bonf_dist}, C1+C2={c1c2_bonf_dist}")
print()
print(f"Deployment posture: {c1_posture}")
print()
print(f"JSON:  {out_json}")
print(f"Vault: {vault_path}")
print("=" * 70)
