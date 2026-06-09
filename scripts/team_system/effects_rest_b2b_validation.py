"""
effects_rest_b2b_validation.py
Validation: control for opponent rest + player-level eFG cross-check
"""
import pandas as pd
import numpy as np
from scipy import stats

rt  = pd.read_parquet("C:/Users/neelj/nba-ai-system/data/rest_travel.parquet")
tas = pd.read_parquet("C:/Users/neelj/nba-ai-system/data/team_advanced_stats.parquet")

rt = rt.rename(columns={"team_abbreviation": "team_tricode"})
merged = tas.merge(
    rt[["game_id", "team_tricode", "is_b2b", "is_b3b"]],
    on=["game_id", "team_tricode"],
    how="inner",
)

# Self-join to get opponent B2B flag
opp = merged[["game_id", "team_tricode", "is_b2b"]].rename(
    columns={"team_tricode": "opp_tricode", "is_b2b": "opp_is_b2b"}
)
merged2 = merged.merge(opp, on="game_id", how="left")
merged2 = merged2[merged2["team_tricode"] != merged2["opp_tricode"]]

both_rested = merged2[(merged2["is_b2b"] == 0) & (merged2["opp_is_b2b"] == 0) & (merged2["is_b3b"] == 0)]
only_b2b    = merged2[(merged2["is_b2b"] == 1) & (merged2["opp_is_b2b"] == 0)]
both_b2b    = merged2[(merged2["is_b2b"] == 1) & (merged2["opp_is_b2b"] == 1)]

print("=== CONTROLLING FOR OPPONENT REST ===")
for label, sub in [("Both rested", both_rested), ("Focal B2B, Opp rested", only_b2b), ("Both B2B", both_b2b)]:
    vals = sub["off_rtg"].dropna()
    efg  = sub["efg_pct"].dropna()
    pace = sub["pace"].dropna()
    print(f"{label} (n={len(vals)}): ORtg={vals.mean():.2f}  eFG={efg.mean():.4f}  Pace={pace.mean():.2f}")

t, p = stats.ttest_ind(only_b2b["off_rtg"].dropna(), both_rested["off_rtg"].dropna(), equal_var=False)
delta = only_b2b["off_rtg"].mean() - both_rested["off_rtg"].mean()
print(f"\nFocal-B2B vs Both-Rested: delta ORtg = {delta:+.2f}  p={p:.4f}")

t2, p2 = stats.ttest_ind(only_b2b["efg_pct"].dropna(), both_rested["efg_pct"].dropna(), equal_var=False)
delta2 = only_b2b["efg_pct"].mean() - both_rested["efg_pct"].mean()
print(f"Focal-B2B vs Both-Rested: delta eFG  = {delta2:+.4f}  p={p2:.4f}")
print(f"eFG multiplier (B2B/rested): {only_b2b['efg_pct'].mean() / both_rested['efg_pct'].mean():.4f}")

t3, p3 = stats.ttest_ind(only_b2b["pace"].dropna(), both_rested["pace"].dropna(), equal_var=False)
delta3 = only_b2b["pace"].mean() - both_rested["pace"].mean()
print(f"Focal-B2B vs Both-Rested: delta Pace = {delta3:+.2f}  p={p3:.4f}")
print(f"Pace multiplier (B2B/rested): {only_b2b['pace'].mean() / both_rested['pace'].mean():.4f}")

print()
print("=== PLAYER-LEVEL eFG CROSS-CHECK (situational_splits) ===")
ss = pd.read_parquet("C:/Users/neelj/nba-ai-system/data/cache/signals/situational_splits.parquet")
valid = ss.dropna(subset=["b2b_efg", "two_plus_efg", "b2b_n_games_rest"])
valid = valid[valid["b2b_n_games_rest"] >= 5]
delta_efg = valid["b2b_efg"] - valid["two_plus_efg"]
print(f"Players with >=5 B2B games: n={len(valid)}")
print(f"Mean b2b_efg:      {valid['b2b_efg'].mean():.4f}")
print(f"Mean two_plus_efg: {valid['two_plus_efg'].mean():.4f}")
print(f"Mean B2B eFG delta: {delta_efg.mean():+.4f}  (median: {delta_efg.median():+.4f})")
t_pl, p_pl = stats.ttest_1samp(delta_efg.dropna(), 0)
print(f"t={t_pl:.3f}  p={p_pl:.4f}")

# Cross-check with b2b_pts_delta
pts_delta = valid["b2b_pts_delta"].dropna()
print(f"\nMean b2b_pts_delta: {pts_delta.mean():+.3f} pts/game")
t_pts, p_pts = stats.ttest_1samp(pts_delta, 0)
print(f"t={t_pts:.3f}  p={p_pts:.4f}")
