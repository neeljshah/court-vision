"""
effects_rest_b2b.py
Measures how B2B rest affects team ORtg, eFG, and pace vs rested (2+ days rest) games.
Sources: data/rest_travel.parquet + data/team_advanced_stats.parquet
Author: subagent, 2026-06-06
"""
import pandas as pd
import numpy as np
from scipy import stats

# ── Load data ────────────────────────────────────────────────────────────────
rt  = pd.read_parquet("C:/Users/neelj/nba-ai-system/data/rest_travel.parquet")
tas = pd.read_parquet("C:/Users/neelj/nba-ai-system/data/team_advanced_stats.parquet")

# ── Join on game_id + team ───────────────────────────────────────────────────
# rest_travel uses team_abbreviation; team_advanced_stats uses team_tricode
# Both are 3-letter codes — check they're compatible
rt = rt.rename(columns={"team_abbreviation": "team_tricode"})

merged = tas.merge(
    rt[["game_id", "team_tricode", "is_b2b", "is_b3b"]],
    on=["game_id", "team_tricode"],
    how="inner",
)

print(f"Merged rows: {len(merged)}")
print(f"B2B rows (is_b2b==1): {(merged['is_b2b']==1).sum()}")
print(f"Rested rows (is_b2b==0, is_b3b==0): {((merged['is_b2b']==0) & (merged['is_b3b']==0)).sum()}")

# ── Filter: B2B vs truly rested (2+ days = neither B2B nor B3B) ─────────────
b2b    = merged[merged["is_b2b"] == 1].copy()
rested = merged[(merged["is_b2b"] == 0) & (merged["is_b3b"] == 0)].copy()

print(f"\n=== SAMPLE COUNTS ===")
print(f"B2B games:    n={len(b2b)}")
print(f"Rested games: n={len(rested)}")

# ── Key metrics: off_rtg, efg_pct, pace ─────────────────────────────────────
metrics = ["off_rtg", "efg_pct", "pace"]

print(f"\n=== B2B vs RESTED — TEAM-GAME LEVEL ===")
results = {}
for m in metrics:
    b2b_vals    = b2b[m].dropna()
    rested_vals = rested[m].dropna()

    b2b_mean    = b2b_vals.mean()
    rested_mean = rested_vals.mean()
    delta       = b2b_mean - rested_mean

    # Welch t-test
    t_stat, p_val = stats.ttest_ind(b2b_vals, rested_vals, equal_var=False)

    results[m] = {
        "rested_mean": rested_mean,
        "b2b_mean":    b2b_mean,
        "delta":       delta,
        "pct_change":  delta / rested_mean * 100,
        "t":           t_stat,
        "p":           p_val,
        "n_b2b":       len(b2b_vals),
        "n_rested":    len(rested_vals),
    }

    sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else ("*" if p_val < 0.05 else "ns"))
    print(f"\n{m}:")
    print(f"  Rested mean : {rested_mean:.3f}  (n={len(rested_vals)})")
    print(f"  B2B mean    : {b2b_mean:.3f}  (n={len(b2b_vals)})")
    print(f"  Delta       : {delta:+.3f}  ({delta/rested_mean*100:+.2f}%)")
    print(f"  t={t_stat:.3f}  p={p_val:.4f}  {sig}")

# ── Multiplier derivation ────────────────────────────────────────────────────
print("\n=== MULTIPLIERS FOR SIM ===")
for m in metrics:
    r = results[m]
    mult = r["b2b_mean"] / r["rested_mean"]
    print(f"  {m}: B2B multiplier = {mult:.4f}  (delta={r['delta']:+.3f})")

# ── Sanity: season breakdown ─────────────────────────────────────────────────
print("\n=== SEASON BREAKDOWN (off_rtg) ===")
merged["season"] = merged["game_date"].str[:4].astype(int)
for season in sorted(merged["season"].unique()):
    sub = merged[merged["season"] == season]
    b2b_s    = sub[sub["is_b2b"] == 1]["off_rtg"].dropna()
    rest_s   = sub[(sub["is_b2b"] == 0) & (sub["is_b3b"] == 0)]["off_rtg"].dropna()
    if len(b2b_s) > 10 and len(rest_s) > 10:
        delta = b2b_s.mean() - rest_s.mean()
        print(f"  {season}: rested={rest_s.mean():.2f} b2b={b2b_s.mean():.2f}  delta={delta:+.2f}  (n_b2b={len(b2b_s)})")

# ── Pace: pts/100 interpretation ─────────────────────────────────────────────
print("\n=== HEADLINE SUMMARY ===")
off_r = results["off_rtg"]
efg_r = results["efg_pct"]
pac_r = results["pace"]

print(f"  ORtg B2B delta  : {off_r['delta']:+.2f} pts/100  (rested={off_r['rested_mean']:.1f})")
print(f"  eFG  B2B delta  : {efg_r['delta']:+.4f}  ({efg_r['pct_change']:+.2f}%)  mult={results['efg_pct']['b2b_mean']/results['efg_pct']['rested_mean']:.4f}")
print(f"  Pace B2B delta  : {pac_r['delta']:+.2f} poss/48  (rested={pac_r['rested_mean']:.1f})")
print(f"  Pace mult       : {results['pace']['b2b_mean']/results['pace']['rested_mean']:.4f}")
print(f"  eFG mult        : {results['efg_pct']['b2b_mean']/results['efg_pct']['rested_mean']:.4f}")
