"""
effects_travel_altitude.py
Measure the effect of travel miles and opponent arena altitude on
team offensive rating and pace. Merges rest_travel (team-game level)
with team_advanced_stats (team-game efficiency).

Output: multipliers/deltas suitable for basketball_sim.py
"""
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

DATA = "C:/Users/neelj/nba-ai-system/data"

# ── 1. Load data ──────────────────────────────────────────────────────────────
rt = pd.read_parquet(f"{DATA}/rest_travel.parquet")
adv = pd.read_parquet(f"{DATA}/team_advanced_stats.parquet")

# Normalise keys
rt["game_id"] = rt["game_id"].astype(str).str.strip()
rt["team"] = rt["team_abbreviation"].str.strip()
adv["game_id"] = adv["game_id"].astype(str).str.strip()
adv["team"] = adv["team_tricode"].str.strip()

# ── 2. Merge ──────────────────────────────────────────────────────────────────
df = adv.merge(rt[["game_id", "team", "miles_traveled", "altitude_ft"]],
               on=["game_id", "team"], how="inner")

print(f"Merged rows: {len(df):,}  (adv={len(adv):,}, rt={len(rt):,})")
print(f"miles_traveled non-null: {df['miles_traveled'].notna().sum():,}")
print(f"altitude_ft non-null:    {df['altitude_ft'].notna().sum():,}")

# Drop rows with missing outcome vars or predictors
df = df.dropna(subset=["off_rtg", "pace", "miles_traveled", "altitude_ft"])
print(f"Clean rows for regression: {len(df):,}\n")

# ── 3. Basic stats ────────────────────────────────────────────────────────────
baseline_ortg = df["off_rtg"].mean()
baseline_pace = df["pace"].mean()
print(f"Baseline ORtg (all games): {baseline_ortg:.2f}")
print(f"Baseline pace (all games): {baseline_pace:.2f}\n")

# ── 4. Bucket analysis: travel miles ─────────────────────────────────────────
# 0 = home / no travel; low = short trip; med; high
df["travel_bucket"] = pd.cut(
    df["miles_traveled"],
    bins=[-1, 0, 500, 1200, 5000],
    labels=["home/none", "short(<500)", "med(500-1200)", "long(>1200)"]
)

bucket_stats = df.groupby("travel_bucket", observed=True).agg(
    n=("off_rtg", "count"),
    ortg_mean=("off_rtg", "mean"),
    ortg_se=("off_rtg", lambda x: x.sem()),
    pace_mean=("pace", "mean"),
    pace_se=("pace", lambda x: x.sem()),
).reset_index()

print("=== Travel miles buckets ===")
print(bucket_stats.to_string(index=False))
print()

# Delta vs home/none bucket
home_ortg = bucket_stats.loc[bucket_stats["travel_bucket"] == "home/none", "ortg_mean"].values[0]
home_pace = bucket_stats.loc[bucket_stats["travel_bucket"] == "home/none", "pace_mean"].values[0]
print(f"Delta ORtg (long travel vs home/none): {bucket_stats.loc[bucket_stats['travel_bucket']=='long(>1200)','ortg_mean'].values[0] - home_ortg:+.2f} pts/100")
print(f"Delta pace (long travel vs home/none): {bucket_stats.loc[bucket_stats['travel_bucket']=='long(>1200)','pace_mean'].values[0] - home_pace:+.2f} poss/48")
print()

# ── 5. Bucket analysis: arena altitude ───────────────────────────────────────
# Sea-level <200 ft; low 200-1000; moderate 1000-3000; high = Denver ~5183 ft
df["alt_bucket"] = pd.cut(
    df["altitude_ft"],
    bins=[-1, 200, 1000, 3000, 6000],
    labels=["sea(<200)", "low(200-1000)", "mod(1000-3000)", "high(>3000)"]
)

alt_stats = df.groupby("alt_bucket", observed=True).agg(
    n=("off_rtg", "count"),
    ortg_mean=("off_rtg", "mean"),
    ortg_se=("off_rtg", lambda x: x.sem()),
    pace_mean=("pace", "mean"),
    pace_se=("pace", lambda x: x.sem()),
).reset_index()

print("=== Altitude buckets ===")
print(alt_stats.to_string(index=False))
print()

sea_ortg = alt_stats.loc[alt_stats["alt_bucket"] == "sea(<200)", "ortg_mean"].values[0]
sea_pace = alt_stats.loc[alt_stats["alt_bucket"] == "sea(<200)", "pace_mean"].values[0]
high_ortg = alt_stats.loc[alt_stats["alt_bucket"] == "high(>3000)", "ortg_mean"].values[0]
high_pace = alt_stats.loc[alt_stats["alt_bucket"] == "high(>3000)", "pace_mean"].values[0]
print(f"Delta ORtg (high altitude vs sea-level): {high_ortg - sea_ortg:+.2f} pts/100")
print(f"Delta pace (high altitude vs sea-level): {high_pace - sea_pace:+.2f} poss/48")
print()

# ── 6. OLS regression: controlling for home/away + b2b ───────────────────────
# Merge is_b2b from rest_travel, use it as control
df_reg = df.copy()

# Standardise predictors for interpretable betas
df_reg["miles_z"] = (df_reg["miles_traveled"] - df_reg["miles_traveled"].mean()) / df_reg["miles_traveled"].std()
df_reg["alt_z"]   = (df_reg["altitude_ft"]   - df_reg["altitude_ft"].mean())   / df_reg["altitude_ft"].std()

# Simple OLS via numpy (no scipy needed)
def ols_beta(y, X_df):
    """Return (beta, se, t) for each predictor in X_df (no intercept guard)."""
    X = np.column_stack([np.ones(len(y))] + [X_df[c].values for c in X_df.columns])
    y = np.array(y)
    beta, res, _, _ = np.linalg.lstsq(X, y, rcond=None)
    n, p = X.shape
    if n > p:
        sigma2 = np.sum((y - X @ beta)**2) / (n - p)
        cov = sigma2 * np.linalg.inv(X.T @ X)
        se = np.sqrt(np.diag(cov))
    else:
        se = np.full(len(beta), np.nan)
    t = beta / se
    return dict(zip(["intercept"] + list(X_df.columns), zip(beta, se, t)))

predictors = pd.DataFrame({"miles_z": df_reg["miles_z"], "alt_z": df_reg["alt_z"]})

print("=== OLS: ORtg ~ miles_z + alt_z ===")
ortg_res = ols_beta(df_reg["off_rtg"], predictors)
for k, (b, se, t) in ortg_res.items():
    print(f"  {k:12s}: beta={b:+.3f}  se={se:.3f}  t={t:+.2f}")

print()
print("=== OLS: pace ~ miles_z + alt_z ===")
pace_res = ols_beta(df_reg["pace"], predictors)
for k, (b, se, t) in pace_res.items():
    print(f"  {k:12s}: beta={b:+.3f}  se={se:.3f}  t={t:+.2f}")
print()

# ── 7. Denver (high altitude) isolation ─────────────────────────────────────
# Denver arena ~5183 ft; isolate visiting team games there
den_visiting = df[(df["altitude_ft"] > 5000) & (df["miles_traveled"] > 0)]
sea_home     = df[(df["altitude_ft"] < 100)]  # mostly sea-level arenas home games

print(f"=== Denver-altitude visiting games (alt>5000, traveled>0) n={len(den_visiting)} ===")
print(f"  Visitor ORtg:  {den_visiting['off_rtg'].mean():.2f}  (vs baseline {baseline_ortg:.2f}  delta {den_visiting['off_rtg'].mean()-baseline_ortg:+.2f})")
print(f"  Visitor pace:  {den_visiting['pace'].mean():.2f}  (vs baseline {baseline_pace:.2f}  delta {den_visiting['pace'].mean()-baseline_pace:+.2f})")
print()

# ── 8. Headline multipliers ───────────────────────────────────────────────────
# Travel: use regression beta for miles_z -> convert to per-1000-miles
miles_std = df_reg["miles_traveled"].std()
beta_miles_ortg = ortg_res["miles_z"][0]
per_1000mi_ortg = beta_miles_ortg * (1000 / miles_std)

beta_miles_pace = pace_res["miles_z"][0]
per_1000mi_pace = beta_miles_pace * (1000 / miles_std)

# Altitude: beta for alt_z -> per-1000-ft
alt_std = df_reg["altitude_ft"].std()
beta_alt_ortg = ortg_res["alt_z"][0]
per_1000ft_ortg = beta_alt_ortg * (1000 / alt_std)

beta_alt_pace = pace_res["alt_z"][0]
per_1000ft_pace = beta_alt_pace * (1000 / alt_std)

print("=== Headline effect estimates ===")
print(f"Travel ORtg:   {per_1000mi_ortg:+.3f} pts/100 per 1000 miles traveled")
print(f"Travel pace:   {per_1000mi_pace:+.3f} poss/48 per 1000 miles traveled")
print(f"Altitude ORtg: {per_1000ft_ortg:+.3f} pts/100 per 1000 ft altitude")
print(f"Altitude pace: {per_1000ft_pace:+.3f} poss/48 per 1000 ft altitude")
print()

# Practical multiplier for Denver (5183 ft) visiting team
denver_alt_ortg_delta = per_1000ft_ortg * (5183 / 1000)
denver_alt_pace_delta = per_1000ft_pace * (5183 / 1000)
long_travel_ortg_delta = per_1000mi_ortg * 2.0  # typical 2000 mile cross-country trip
long_travel_pace_delta = per_1000mi_pace * 2.0

print(f"Denver altitude visiting team ORtg delta: {denver_alt_ortg_delta:+.2f} pts/100")
print(f"Denver altitude visiting team pace delta: {denver_alt_pace_delta:+.2f} poss/48")
print(f"Long travel (2000mi) ORtg delta:          {long_travel_ortg_delta:+.2f} pts/100")
print(f"Long travel (2000mi) pace delta:          {long_travel_pace_delta:+.2f} poss/48")
print()

# xFG multiplier: ORtg ≈ eFG-driven; approximate eFG mult via eFG regression too
df_eff = df.dropna(subset=["efg_pct"])
if len(df_eff) > 100:
    pred2 = pd.DataFrame({"miles_z": df_reg.loc[df_eff.index, "miles_z"],
                          "alt_z":   df_reg.loc[df_eff.index, "alt_z"]})
    efg_res = ols_beta(df_eff["efg_pct"], pred2)
    beta_alt_efg = efg_res["alt_z"][0]
    per_1000ft_efg = beta_alt_efg * (1000 / alt_std)
    denver_efg_delta = per_1000ft_efg * (5183 / 1000)
    baseline_efg = df_eff["efg_pct"].mean()
    denver_efg_mult = 1 + (denver_efg_delta / baseline_efg)
    print(f"Baseline eFG: {baseline_efg:.4f}")
    print(f"Altitude eFG per 1000ft: {per_1000ft_efg:+.4f}")
    print(f"Denver visiting eFG delta: {denver_efg_delta:+.4f} => xfg_mult = {denver_efg_mult:.4f}")
    print()

    beta_miles_efg = efg_res["miles_z"][0]
    per_1000mi_efg = beta_miles_efg * (1000 / miles_std)
    long_efg_delta = per_1000mi_efg * 2.0
    long_efg_mult = 1 + (long_efg_delta / baseline_efg)
    print(f"Long travel (2000mi) eFG delta: {long_efg_delta:+.4f} => xfg_mult = {long_efg_mult:.4f}")
    print()

print("=== SUMMARY ===")
print("If effect is < 0.002 in eFG or < 0.3 pts/100 ORtg, treat as ~0 (noise floor).")
