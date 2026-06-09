"""
effects_opp_defense.py
Measures how opponent defensive quality (season-rolling def_rtg) suppresses
team offensive efficiency (off_rtg and eFG%) on a per-game basis.

Source: data/team_advanced_stats.parquet
  - Each game has 2 rows (one per team)
  - off_rtg = team's offensive rating that game
  - def_rtg = team's defensive rating that game (= opponent's off_rtg)
  - efg_pct = team's eFG% that game

Method:
  1. Self-join on game_id to get "opp" row
  2. Compute opponent's SEASON-TO-DATE def_rtg (rolling mean, excluding current game) as
     the pre-game defense signal -- not the in-game mirror (which is trivially equal)
  3. Bin opponents into strong/mid/weak defense quintiles by season-rolling def_rtg
  4. OLS regression: off_rtg ~ opp_season_def_rtg + season_FE
  5. Report eFG% and ORtg deltas, compute xfg_mult
"""

import pandas as pd
import numpy as np
from scipy import stats

# ── 1. Load & parse ──────────────────────────────────────────────────────────
df = pd.read_parquet("data/team_advanced_stats.parquet")
df["game_date"] = pd.to_datetime(df["game_date"])
df["season"] = df["game_id"].str[3:5].astype(int)

# ── 2. Self-join to get opponent row per game ─────────────────────────────────
left = df[["game_id", "game_date", "season", "team_tricode", "off_rtg", "efg_pct"]].copy()
right = df[["game_id", "team_tricode", "def_rtg", "off_rtg"]].copy()
right = right.rename(columns={
    "team_tricode": "opp_tricode",
    "def_rtg": "opp_game_def_rtg",   # opp's in-game def_rtg (= our off_rtg, just for sanity)
    "off_rtg": "opp_game_off_rtg",
})

merged = left.merge(right, on="game_id")
# Drop self-matches
merged = merged[merged["team_tricode"] != merged["opp_tricode"]].copy()
print(f"Game-team observations (after join): {len(merged):,}")

# ── 3. Compute opponent season-to-date def_rtg (rolling, excl. current game) ──
# For each team-season, compute cumulative mean def_rtg BEFORE each game
df_sorted = df.sort_values(["team_tricode", "season", "game_date"]).copy()
df_sorted["opp_season_def_rtg_cum"] = (
    df_sorted.groupby(["team_tricode", "season"])["def_rtg"]
    .expanding()
    .mean()
    .shift(1)   # exclude current game (pre-game signal)
    .values
)

rolling_def = df_sorted[["game_id", "team_tricode", "opp_season_def_rtg_cum"]].rename(
    columns={"team_tricode": "opp_tricode", "opp_season_def_rtg_cum": "opp_season_def_rtg"}
)

merged = merged.merge(rolling_def, on=["game_id", "opp_tricode"], how="left")
# Drop early-season rows with no rolling history (first game of season for each team)
merged = merged.dropna(subset=["opp_season_def_rtg"])
print(f"After dropping NaN rolling def_rtg: {len(merged):,}")

# Sanity: lower def_rtg = better defense
print(f"\nOpp season def_rtg -- mean: {merged['opp_season_def_rtg'].mean():.2f}, "
      f"std: {merged['opp_season_def_rtg'].std():.2f}, "
      f"min: {merged['opp_season_def_rtg'].min():.2f}, "
      f"max: {merged['opp_season_def_rtg'].max():.2f}")

# ── 4. Quintile bins for strong/mid/weak defense ──────────────────────────────
merged["def_quintile"] = pd.qcut(
    merged["opp_season_def_rtg"], q=5,
    labels=["Q1_elite", "Q2_good", "Q3_avg", "Q4_below", "Q5_poor"]
)

print("\n--- ORtg and eFG% by opponent defense quintile ---")
print("  (Q1_elite = best defense, Q5_poor = worst defense)")
qstats = (
    merged.groupby("def_quintile", observed=True)
    .agg(
        n=("off_rtg", "count"),
        opp_def_rtg_mean=("opp_season_def_rtg", "mean"),
        off_rtg_mean=("off_rtg", "mean"),
        efg_pct_mean=("efg_pct", "mean"),
    )
    .reset_index()
)
print(qstats.to_string(index=False))

# ── 5. Strong vs Weak comparison (Q1 vs Q5) ──────────────────────────────────
q1 = merged[merged["def_quintile"] == "Q1_elite"]
q5 = merged[merged["def_quintile"] == "Q5_poor"]

# Off_rtg
off_diff = q5["off_rtg"].mean() - q1["off_rtg"].mean()
t_off, p_off = stats.ttest_ind(q5["off_rtg"], q1["off_rtg"])

# eFG%
efg_diff = q5["efg_pct"].mean() - q1["efg_pct"].mean()
t_efg, p_efg = stats.ttest_ind(q5["efg_pct"], q1["efg_pct"])

print(f"\n--- Strong (Q1) vs Weak (Q5) defense comparison ---")
print(f"n Q1={len(q1)}, n Q5={len(q5)}")
print(f"Opp def_rtg Q1={q1['opp_season_def_rtg'].mean():.2f}, Q5={q5['opp_season_def_rtg'].mean():.2f}")
print(f"ORtg:  Q1={q1['off_rtg'].mean():.2f}, Q5={q5['off_rtg'].mean():.2f}  "
      f"diff=+{off_diff:.2f} pts/100  t={t_off:.2f}  p={p_off:.4f}")
print(f"eFG%:  Q1={q1['efg_pct'].mean():.4f}, Q5={q5['efg_pct'].mean():.4f}  "
      f"diff=+{efg_diff:.4f}  t={t_efg:.2f}  p={p_efg:.4f}")

# ── 6. OLS regression: off_rtg ~ opp_season_def_rtg + season dummies ─────────
# Season dummies to remove year-to-year ORtg inflation
season_dummies = pd.get_dummies(merged["season"], prefix="s", drop_first=True)
X = pd.concat([merged[["opp_season_def_rtg"]], season_dummies], axis=1).astype(float)
X = np.column_stack([np.ones(len(X)), X.values])
y = merged["off_rtg"].values

# OLS via numpy
beta, res, rank, sv = np.linalg.lstsq(X, y, rcond=None)
y_hat = X @ beta
resid = y - y_hat
n, k = X.shape
se = np.sqrt(np.sum(resid**2) / (n - k) * np.linalg.inv(X.T @ X).diagonal())
t_stat = beta / se
p_vals = 2 * stats.t.sf(np.abs(t_stat), df=n - k)

feature_names = ["intercept", "opp_season_def_rtg"] + list(pd.get_dummies(merged["season"], prefix="s", drop_first=True).columns)
print("\n--- OLS: off_rtg ~ opp_season_def_rtg + season_FE ---")
for name, b, s, t, p in zip(feature_names, beta, se, t_stat, p_vals):
    print(f"  {name:30s}  coef={b:+.4f}  se={s:.4f}  t={t:+.2f}  p={p:.4f}")

r2 = 1 - np.sum(resid**2) / np.sum((y - y.mean())**2)
print(f"  R^2 = {r2:.4f}")

opp_def_coef = beta[1]  # coefficient on opp_season_def_rtg

# ── 7. eFG% regression ────────────────────────────────────────────────────────
y_efg = merged["efg_pct"].values
beta_efg, _, _, _ = np.linalg.lstsq(X, y_efg, rcond=None)
y_hat_efg = X @ beta_efg
resid_efg = y_efg - y_hat_efg
se_efg = np.sqrt(np.sum(resid_efg**2) / (n - k) * np.linalg.inv(X.T @ X).diagonal())
t_efg_reg = beta_efg / se_efg
p_efg_reg = 2 * stats.t.sf(np.abs(t_efg_reg), df=n - k)
efg_coef = beta_efg[1]

print(f"\n--- OLS: efg_pct ~ opp_season_def_rtg + season_FE ---")
for name, b, s, t, p in zip(feature_names[:2], beta_efg[:2], se_efg[:2], t_efg_reg[:2], p_efg_reg[:2]):
    print(f"  {name:30s}  coef={b:+.6f}  se={s:.6f}  t={t:+.2f}  p={p:.4f}")
r2_efg = 1 - np.sum(resid_efg**2) / np.sum((y_efg - y_efg.mean())**2)
print(f"  R^2 = {r2_efg:.4f}")

# ── 8. Compute xfg_mult for sim ───────────────────────────────────────────────
# Scenario: facing elite D (Q1 mean def_rtg ~108) vs poor D (Q5 mean ~121)
# Typical spread = ~13 def_rtg units
baseline_def_rtg = merged["opp_season_def_rtg"].mean()  # league mean
elite_def_rtg = q1["opp_season_def_rtg"].mean()
weak_def_rtg = q5["opp_season_def_rtg"].mean()

baseline_efg = merged["efg_pct"].mean()
efg_at_elite = baseline_efg + efg_coef * (elite_def_rtg - baseline_def_rtg)
efg_at_weak  = baseline_efg + efg_coef * (weak_def_rtg  - baseline_def_rtg)

xfg_mult_elite = efg_at_elite / baseline_efg
xfg_mult_weak  = efg_at_weak  / baseline_efg

print(f"\n--- xfg_mult derivation ---")
print(f"Baseline eFG% (league mean vs mean D): {baseline_efg:.4f}")
print(f"eFG% vs elite D (def_rtg={elite_def_rtg:.1f}): {efg_at_elite:.4f}  =>  xfg_mult={xfg_mult_elite:.4f}")
print(f"eFG% vs weak D  (def_rtg={weak_def_rtg:.1f}): {efg_at_weak:.4f}  =>  xfg_mult={xfg_mult_weak:.4f}")

# Per-unit slope (per 1 def_rtg point, how much does eFG% shift?)
opp_std = merged['opp_season_def_rtg'].std()
print(f"\neFG% slope: {efg_coef:+.5f} per 1 def_rtg unit")
efg_1sd_change = efg_coef * (-opp_std)
efg_1sd_mult = (baseline_efg + efg_1sd_change) / baseline_efg
print(f"  -> 1 SD better defense (~{opp_std:.1f} def_rtg units lower): "
      f"eFG% change = {efg_1sd_change:+.4f}  "
      f"mult = {efg_1sd_mult:.4f}")

# ── 9. Summary ────────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("SUMMARY -- Opponent Defense -> Offensive Efficiency")
print("="*65)
print(f"N game-team observations: {len(merged):,}")
print(f"Seasons: 2022-23 through 2024-25 (3 seasons)")
print(f"\nQ1 (elite D) off_rtg = {q1['off_rtg'].mean():.2f}  eFG% = {q1['efg_pct'].mean():.4f}")
print(f"Q5 (weak D)  off_rtg = {q5['off_rtg'].mean():.2f}  eFG% = {q5['efg_pct'].mean():.4f}")
print(f"Q1->Q5 delta ORtg: +{off_diff:.2f} pts/100  (p={p_off:.4f})")
print(f"Q1->Q5 delta eFG%: +{efg_diff:.4f}  (p={p_efg:.4f})")
print(f"\nOLS coef (opp_season_def_rtg -> eFG%): {efg_coef:+.5f} per def_rtg unit")
print(f"  (better defense = lower def_rtg = lower eFG% allowed)")
print(f"\nxfg_mult range (elite D to weak D):")
print(f"  vs elite D (def_rtg={elite_def_rtg:.1f}): {xfg_mult_elite:.4f}")
print(f"  vs league mean (def_rtg={baseline_def_rtg:.1f}): 1.0000  (baseline)")
print(f"  vs weak D  (def_rtg={weak_def_rtg:.1f}): {xfg_mult_weak:.4f}")
print(f"\nRecommended sim param:")
print(f"  xfg_mult = 1.0 + {efg_coef:.5f} * (opp_season_def_rtg - {baseline_def_rtg:.2f}) / {baseline_efg:.4f}")
print(f"  Clamp to [{xfg_mult_elite:.3f}, {xfg_mult_weak:.3f}]")
print("="*65)
