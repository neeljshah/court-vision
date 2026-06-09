"""
effects_three_pt_variance.py

Decomposes game-to-game team scoring variance into:
  - 3P% component (fg3a held fixed at mean, 3P% varies)
  - 3PA component (3P% held fixed at mean, fg3a varies)
  - 2P + FT residual
  - Cross-term

Sources: player gamelogs aggregated to team-game level (2022-25 regular season),
         plus team_game.parquet (2025-26).
"""

import pandas as pd
import numpy as np
import glob
import json
import sys
import os

DATA_ROOT = os.path.join(os.path.dirname(__file__), '..', '..', 'data')

# ── 1. Load player gamelogs → team-game aggregates ──────────────────────────
print("Loading player gamelogs...")
all_records = []
files = sorted(glob.glob(os.path.join(DATA_ROOT, 'nba', 'gamelog_full_*.json')))

for f in files:
    try:
        with open(f) as fh:
            data = json.load(fh)
        if isinstance(data, list):
            all_records.extend(data)
    except Exception:
        pass

print(f"  {len(all_records)} player-game records loaded from {len(files)} files")

df = pd.DataFrame(all_records)

# Extract team abbreviation from matchup string (e.g. "NYK vs. BOS" -> "NYK")
df['team'] = df['matchup'].str.split().str[0]

# Keep only regular season (season_id prefix 2)
df = df[df['season_id'].astype(str).str.startswith('2')].copy()
print(f"  After regular-season filter: {len(df)} rows")

# Numeric cast
for col in ['fg3m', 'fg3a', 'fgm', 'fga', 'ftm', 'fta', 'pts']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.dropna(subset=['fg3m', 'fg3a', 'fgm', 'fga', 'ftm', 'fta', 'pts'])

# Aggregate to team-game
tg = (
    df.groupby(['game_id', 'game_date', 'team'])
    .agg(
        pts=('pts', 'sum'),
        fgm=('fgm', 'sum'),
        fga=('fga', 'sum'),
        fg3m=('fg3m', 'sum'),
        fg3a=('fg3a', 'sum'),
        ftm=('ftm', 'sum'),
        fta=('fta', 'sum'),
    )
    .reset_index()
)

# ── 2. Supplement with team_game.parquet (2025-26) ──────────────────────────
tg25 = pd.read_parquet(os.path.join(DATA_ROOT, 'cache', 'team_system', 'team_game.parquet'))
tg25 = tg25[tg25['kind'] == 'reg'][['gid', 'date', 'team', 'pts', 'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta']].copy()
tg25.columns = ['game_id', 'game_date', 'team', 'pts', 'fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta']

# Combine
tg_all = pd.concat([tg, tg25], ignore_index=True)
tg_all = tg_all.drop_duplicates(subset=['game_id', 'team'])
print(f"  Combined team-game rows: {len(tg_all)}")

# Basic filters: reasonable box score
tg_all = tg_all[
    (tg_all['pts'] > 50) &
    (tg_all['fga'] > 50) &
    (tg_all['fg3a'] >= 10) &
    (tg_all['fg3a'] <= 60)
].copy()
print(f"  After quality filters: {len(tg_all)} team-game rows")

# ── 3. Compute per-game rates ────────────────────────────────────────────────
tg_all['fg3_pct'] = tg_all['fg3m'] / tg_all['fg3a']
tg_all['fg2a'] = tg_all['fga'] - tg_all['fg3a']
tg_all['fg2m'] = tg_all['fgm'] - tg_all['fg3m']
tg_all['fg2_pct'] = tg_all['fg2m'] / tg_all['fg2a'].replace(0, np.nan)

# Pts check: pts ≈ 3*fg3m + 2*fg2m + ftm (minor OT/tech differences ignored)
tg_all['pts_2pt'] = 2 * tg_all['fg2m']
tg_all['pts_3pt'] = 3 * tg_all['fg3m']
tg_all['pts_ft']  = tg_all['ftm']
# Reconstruct to verify alignment
tg_all['pts_check'] = tg_all['pts_2pt'] + tg_all['pts_3pt'] + tg_all['pts_ft']
# Some teams may have free-throw data off; keep rows within 5 pts
tg_all = tg_all[abs(tg_all['pts'] - tg_all['pts_check']) <= 5].copy()
print(f"  After pts reconstruction filter: {len(tg_all)} rows")

N = len(tg_all)
print(f"\n{'='*60}")
print(f"DATASET: {N} team-game observations (regular season 2022-26)")
print(f"{'='*60}")

# ── 4. Variance decomposition ────────────────────────────────────────────────
# pts = 3*fg3m + 2*fg2m + ftm
#      = 3*(fg3a * fg3_pct) + 2*(fg2a * fg2_pct) + ftm
#
# Decompose Var(pts) into contributions from each component.
# Method: OLS attribution (regress pts components on total pts variance)
# and direct variance partitioning.

# --- 4a. Raw variance of each component ---
var_total = np.var(tg_all['pts'], ddof=1)
var_3pm   = np.var(tg_all['pts_3pt'], ddof=1)
var_2pm   = np.var(tg_all['pts_2pt'], ddof=1)
var_ft    = np.var(tg_all['pts_ft'],  ddof=1)

cov_3_2   = np.cov(tg_all['pts_3pt'], tg_all['pts_2pt'], ddof=1)[0,1]
cov_3_ft  = np.cov(tg_all['pts_3pt'], tg_all['pts_ft'],  ddof=1)[0,1]
cov_2_ft  = np.cov(tg_all['pts_2pt'], tg_all['pts_ft'],  ddof=1)[0,1]

# Var(A+B+C) = Var(A)+Var(B)+Var(C)+2Cov(A,B)+2Cov(A,C)+2Cov(B,C)
var_reconstruct = var_3pm + var_2pm + var_ft + 2*cov_3_2 + 2*cov_3_ft + 2*cov_2_ft
print(f"\n--- Raw variance components ---")
print(f"Var(pts total):         {var_total:.2f}  pts² (SD={np.sqrt(var_total):.2f})")
print(f"Var(pts_3pt):           {var_3pm:.2f}  ({100*var_3pm/var_total:.1f}% of total var)")
print(f"Var(pts_2pt):           {var_2pm:.2f}  ({100*var_2pm/var_total:.1f}% of total var)")
print(f"Var(pts_ft):            {var_ft:.2f}  ({100*var_ft/var_total:.1f}% of total var)")
print(f"Cov terms combined:     {2*(cov_3_2+cov_3_ft+cov_2_ft):.2f}")
print(f"Var reconstructed:      {var_reconstruct:.2f}  (check vs {var_total:.2f})")

# --- 4b. Separate 3P% variance from 3PA variance ---
# pts_3pt = 3 * fg3a * fg3_pct
# Var(X*Y) ≈ E[X]²*Var(Y) + E[Y]²*Var(X) + Var(X)*Var(Y)  [if independent]
# But they're correlated, so use direct decomposition:

mu_fg3a   = tg_all['fg3a'].mean()
mu_fg3pct = tg_all['fg3_pct'].mean()

# Component 1: 3P% variance holding fg3a at mean
# Δpts_3pct = 3 * mu_fg3a * (fg3_pct - mu_fg3pct)
tg_all['delta_3pct'] = 3 * mu_fg3a * (tg_all['fg3_pct'] - mu_fg3pct)

# Component 2: 3PA variance holding fg3_pct at mean
# Δpts_3pa = 3 * mu_fg3pct * (fg3a - mu_fg3a)
tg_all['delta_3pa'] = 3 * mu_fg3pct * (tg_all['fg3a'] - mu_fg3a)

var_3pct_component = np.var(tg_all['delta_3pct'], ddof=1)
var_3pa_component  = np.var(tg_all['delta_3pa'],  ddof=1)

print(f"\n--- 3P decomposition (fg3a vs fg3_pct contributions) ---")
print(f"mu_fg3a = {mu_fg3a:.1f} attempts/game")
print(f"mu_fg3pct = {mu_fg3pct:.3f}")
print(f"SD(fg3_pct) = {tg_all['fg3_pct'].std():.4f}")
print(f"SD(fg3a)    = {tg_all['fg3a'].std():.2f} attempts")
print(f"")
print(f"Var from 3P% swings:    {var_3pct_component:.2f}  ({100*var_3pct_component/var_total:.1f}% of total pts var)")
print(f"Var from 3PA swings:    {var_3pa_component:.2f}  ({100*var_3pa_component/var_total:.1f}% of total pts var)")

# --- 4c. OLS: regress pts on pts_3pt, pts_2pt, pts_ft (should be identity) ---
# More useful: regress pts on delta_3pct, delta_3pa, pts_2pt, pts_ft
from numpy.linalg import lstsq

X = np.column_stack([
    tg_all['delta_3pct'],
    tg_all['delta_3pa'],
    tg_all['pts_2pt'],
    tg_all['pts_ft'],
    np.ones(N)
])
y = tg_all['pts'].values
beta, _, _, _ = lstsq(X, y, rcond=None)
y_hat = X @ beta
ss_res = np.sum((y - y_hat)**2)
ss_tot = np.sum((y - y.mean())**2)
r2 = 1 - ss_res/ss_tot
print(f"\n--- OLS decomp R² check ---")
print(f"R²(pts ~ delta_3pct + delta_3pa + pts_2pt + pts_ft): {r2:.4f}")

# --- 4d. Variance-fraction approach using actual pts_3pt ---
# More rigorous: what fraction of Var(pts) is attributable to 3P%?
# Use partial variance (regress out other components)

# Partial out: pts ~ pts_2pt + pts_ft
Xbase = np.column_stack([tg_all['pts_2pt'], tg_all['pts_ft'], np.ones(N)])
beta_base, _, _, _ = lstsq(Xbase, y, rcond=None)
resid_base = y - Xbase @ beta_base

# Var(resid) = variance in pts not explained by 2pt + ft
# Then regress resid on delta_3pct
r_3pct = np.corrcoef(resid_base, tg_all['delta_3pct'])[0,1]
r_3pa  = np.corrcoef(resid_base, tg_all['delta_3pa'])[0,1]

print(f"\n--- Partial correlations with pts residual (after removing 2pt+ft) ---")
print(f"corr(pts_resid, delta_3pct) = {r_3pct:.4f}")
print(f"corr(pts_resid, delta_3pa)  = {r_3pa:.4f}")

# ── 5. Primary result: fraction of total pts variance from 3P% ───────────────
# Direct: Cov(pts, delta_3pct) / Var(pts) — the "explained share" via projection
# This is the most honest single-number metric

cov_pts_3pct = np.cov(tg_all['pts'].values, tg_all['delta_3pct'].values, ddof=1)[0,1]
cov_pts_3pa  = np.cov(tg_all['pts'].values, tg_all['delta_3pa'].values,  ddof=1)[0,1]

frac_3pct = var_3pct_component / var_total
frac_3pa  = var_3pa_component  / var_total
frac_2pt  = var_2pm / var_total
frac_ft   = var_ft  / var_total

print(f"\n{'='*60}")
print(f"PRIMARY RESULT — fraction of total pts variance:")
print(f"{'='*60}")
print(f"3P% swings (fg3a fixed):  {100*frac_3pct:.1f}%   (SD contribution ~= {np.sqrt(var_3pct_component):.2f} pts)")
print(f"3PA swings (fg3_pct fixed): {100*frac_3pa:.1f}%  (SD contribution ~= {np.sqrt(var_3pa_component):.2f} pts)")
print(f"2P scoring:               {100*frac_2pt:.1f}%   (SD contribution ~= {np.sqrt(var_2pm):.2f} pts)")
print(f"Free throws:              {100*frac_ft:.1f}%   (SD contribution ~= {np.sqrt(var_ft):.2f} pts)")
print(f"(Sum >100% because components are correlated)")
print(f"")
print(f"SD of game pts:           {np.sqrt(var_total):.2f} pts")
print(f"SD attributable to 3P%:   {np.sqrt(var_3pct_component):.2f} pts  ({100*frac_3pct:.1f}% of variance)")
print(f"Baseline 3P%: {mu_fg3pct:.3f}, SD 3P%: {tg_all['fg3_pct'].std():.4f}")

# ── 6. Per-game 3P% fluctuation → scoring impact ─────────────────────────────
sd_3pct = tg_all['fg3_pct'].std()
sd_pts_from_3pct = 3 * mu_fg3a * sd_3pct
print(f"\nWith {mu_fg3a:.1f} avg 3PA: a 1-SD swing in 3P% ({sd_3pct:.4f}) = {sd_pts_from_3pct:.2f} pts")
print(f"2-SD swing: {2*sd_pts_from_3pct:.2f} pts (hot/cold shooting game)")

# ── 7. Simulator calibration recommendation ──────────────────────────────────
# In a possession sim, each 3PA results in make/miss with prob fg3_pct.
# Empirical SD of 3P% across games = realized_sd.
# Binomial prediction: SD_binom = sqrt(p(1-p)/n) ≈ sqrt(0.36*0.64/37) ≈ 0.079
p = mu_fg3pct
n_attempts = mu_fg3a
sd_binomial = np.sqrt(p * (1-p) / n_attempts)
sd_empirical = sd_3pct

inflation_factor = sd_empirical / sd_binomial

print(f"\n{'='*60}")
print(f"SIM CALIBRATION")
print(f"{'='*60}")
print(f"Binomial-expected SD(3P%) for {n_attempts:.1f} attempts: {sd_binomial:.4f}")
print(f"Empirical SD(3P%) per game:                          {sd_empirical:.4f}")
print(f"Variance inflation factor:                            {inflation_factor:.3f}")
print(f"  → shooting_variance multiplier = {inflation_factor:.3f}")
print(f"  → (empirical variance is {inflation_factor**2:.2f}x pure binomial)")
print(f"")
print(f"Interpretation:")
print(f"  A naive sim draws each shot iid → under-dispersed.")
print(f"  Scale shooting variance by {inflation_factor:.3f}x (or sigma by {inflation_factor:.3f}x)")
print(f"  to match realized game-to-game 3P% spread.")
print(f"  This accounts for team-level hot/cold streaks within a game.")

# ── 8. Sensitivity check: high-3PA vs low-3PA games ─────────────────────────
med_3pa = tg_all['fg3a'].median()
lo = tg_all[tg_all['fg3a'] <= med_3pa]
hi = tg_all[tg_all['fg3a'] > med_3pa]
print(f"\n--- Sensitivity: pts variance by 3PA tier ---")
print(f"Low 3PA (≤{med_3pa:.0f}): SD(pts) = {lo['pts'].std():.2f}  n={len(lo)}")
print(f"High 3PA (>{med_3pa:.0f}): SD(pts) = {hi['pts'].std():.2f}  n={len(hi)}")
print(f"→ High-3PA teams have {'more' if hi['pts'].std()>lo['pts'].std() else 'less'} pts variance")

# ── 9. Summary table ─────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"SUMMARY FOR SIMULATOR PARAMETER")
print(f"{'='*60}")
print(f"Dataset: N={N} team-game rows, regular season 2022-26")
print(f"Baseline 3P%: {mu_fg3pct:.3f} ± {sd_empirical:.4f} (1 SD)")
print(f"3P% drives {100*frac_3pct:.1f}% of total game pts variance")
print(f"  (SD from 3P% alone: {sd_pts_from_3pct:.2f} of {np.sqrt(var_total):.2f} total pts SD)")
print(f"Variance inflation vs pure binomial: {inflation_factor:.3f}x")
print(f"")
print(f"Recommended sim param:")
print(f"  shooting_variance_multiplier = {inflation_factor:.3f}")
print(f"  Apply to fg3_pct draw: sigma_3pct = sqrt(p*(1-p)/n) * {inflation_factor:.3f}")
print(f"  (or use Beta(alpha,beta) where Var(Beta)={sd_empirical**2:.6f})")
