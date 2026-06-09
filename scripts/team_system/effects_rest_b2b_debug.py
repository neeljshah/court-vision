"""
effects_rest_b2b_debug.py
Investigate why player situational_splits b2b_efg > two_plus_efg
(apparent contradiction with team-level result)
"""
import pandas as pd
import numpy as np

ss = pd.read_parquet("C:/Users/neelj/nba-ai-system/data/cache/signals/situational_splits.parquet")

# Check the column definitions more carefully
print("Columns with b2b:")
for c in ss.columns:
    if "b2b" in c.lower() or "rest" in c.lower() or "two_plus" in c.lower() or "one_day" in c.lower():
        print(f"  {c}")

# Check what 'b2b_efg' vs 'two_plus_efg' actually means
# Could be 'b2b_efg' = eFG when the PLAYER is on B2B? Or when they play AT HOME on B2B?
# The column b2b_n_games_rest seems important
print()
print("Sample values for rest-related eFG columns:")
print(ss[["b2b_efg","one_day_efg","two_plus_efg","b2b_n_games_rest","b2b_min_pg","one_day_min_pg","two_plus_min_pg"]].describe())

# KEY: check if b2b means something different — b2b_efg might be eFG of the player's OPPONENT's B2B team
# Or it might be that b2b_n_games_rest counts RESTED games while b2b has fewer games

# Check minimum game thresholds effect
valid = ss.dropna(subset=["b2b_efg","two_plus_efg","b2b_n_games_rest"])
print(f"\nAll players with non-null values: n={len(valid)}")
print(f"b2b_n_games_rest distribution:")
print(valid["b2b_n_games_rest"].describe())

# What is the "one_day" bucket? 1 day rest = not B2B but not truly rested
# B2B = 0 days rest, one_day = 1 day, two_plus = 2+ days
print("\nComparison b2b=0d, one_day=1d, two_plus=2+d:")
valid5 = valid[valid["b2b_n_games_rest"] >= 5]
print(f"b2b_efg mean:      {valid5['b2b_efg'].mean():.4f} (n={len(valid5)})")
print(f"one_day_efg mean:  {valid5['one_day_efg'].dropna().mean():.4f}")
print(f"two_plus_efg mean: {valid5['two_plus_efg'].mean():.4f}")

# Could also be that b2b_efg is a player's eFG against B2B OPPONENTS
# Check b2b_pts_delta sign - it should be negative if B2B hurts performance
print()
print("b2b_pts_delta (should be negative if B2B hurts):")
print(valid5["b2b_pts_delta"].describe())
print(f"Positive (b2b helps): {(valid5['b2b_pts_delta'] > 0).mean():.2%}")
print(f"Negative (b2b hurts): {(valid5['b2b_pts_delta'] < 0).mean():.2%}")

# The b2b_pts_delta in situational_splits — compare with b2b_pts_pg_2ndleg
print()
print("b2b_pts_pg_2ndleg vs b2b_pts_delta_vs_rested:")
print(valid5[["b2b_pts_pg_2ndleg","b2b_pts_delta_vs_rested","b2b_reb_delta_vs_rested","b2b_ast_delta_vs_rested","b2b_min_delta_vs_rested"]].describe())

# These "vs_rested" columns are the cleaner signal
delta_pts = valid5["b2b_pts_delta_vs_rested"].dropna()
delta_reb = valid5["b2b_reb_delta_vs_rested"].dropna()
delta_min = valid5["b2b_min_delta_vs_rested"].dropna()
print(f"\nb2b_pts_delta_vs_rested: mean={delta_pts.mean():+.3f}  median={delta_pts.median():+.3f}")
print(f"b2b_reb_delta_vs_rested: mean={delta_reb.mean():+.3f}")
print(f"b2b_min_delta_vs_rested: mean={delta_min.mean():+.3f}  (minutes reduction)")
