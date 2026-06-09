"""
Home-court advantage effect on ORtg, eFG, FT rate, and pace.
Sources:
  - data/team_advanced_stats.parquet: per-game team rows (off_rtg/def_rtg/pace/efg_pct/tov_ratio)
  - data/rest_travel.parquet: game_id + team + miles_traveled (proxy for home=0 miles)
  - data/cache/team_system/team_game.parquet: 2025-26 season with explicit is_home + fta/fga/fgm
Author: effects harness
"""
import pandas as pd
import numpy as np
from scipy import stats
import sys

# ── Load data ──────────────────────────────────────────────────────────────
ta = pd.read_parquet("data/team_advanced_stats.parquet")
rt = pd.read_parquet("data/rest_travel.parquet")
tg = pd.read_parquet("data/cache/team_system/team_game.parquet")

print(f"team_advanced_stats: {ta.shape}, seasons via game_id: {ta['game_id'].str[3:5].unique()}")
print(f"rest_travel: {rt.shape}")
print(f"team_game: {tg.shape}, date range: {tg['date'].min()} to {tg['date'].max()}")

# ── Part A: Use rest_travel to assign is_home for multi-season team_advanced_stats ──
# home = miles_traveled == 0 AND exactly 1 team per game has 0 miles
rt['is_home_cand'] = rt['miles_traveled'] == 0
per_game_zero = rt.groupby('game_id')['is_home_cand'].sum()
clean_gids = per_game_zero[per_game_zero == 1].index
print(f"\nClean games (exactly 1 team at 0 miles): {len(clean_gids)} / {len(per_game_zero)} total games in rest_travel")

rt_clean = rt[rt['game_id'].isin(clean_gids)][['game_id', 'team_abbreviation', 'is_home_cand']].copy()
rt_clean = rt_clean.rename(columns={'team_abbreviation': 'team_tricode', 'is_home_cand': 'is_home'})

# Join team_advanced_stats with home indicator
ta_home = ta.merge(rt_clean, on=['game_id', 'team_tricode'], how='inner')
print(f"team_advanced_stats after home-join: {ta_home.shape}")
print(f"  home rows: {ta_home['is_home'].sum()}, road rows: {(~ta_home['is_home']).sum()}")

# ── Part B: Compute ORtg and eFG splits ──────────────────────────────────
home = ta_home[ta_home['is_home']]
road = ta_home[~ta_home['is_home']]
n_home = len(home)
n_road = len(road)
print(f"\n=== Sample sizes ===")
print(f"  Home: {n_home}, Road: {n_road}")

# ORtg (offensive rating = pts per 100 possessions)
home_ortg = home['off_rtg'].mean()
road_ortg = road['off_rtg'].mean()
delta_ortg = home_ortg - road_ortg

# eFG%
home_efg = home['efg_pct'].mean()
road_efg = road['efg_pct'].mean()
delta_efg = home_efg - road_efg

# Pace (possessions per 48min)
home_pace = home['pace'].mean()
road_pace = road['pace'].mean()
delta_pace = home_pace - road_pace

print(f"\n=== From team_advanced_stats (2022-25) ===")
print(f"ORtg:  home={home_ortg:.2f}, road={road_ortg:.2f}, delta={delta_ortg:+.2f} pts/100")
print(f"eFG%:  home={home_efg:.4f}, road={road_efg:.4f}, delta={delta_efg:+.4f} ({delta_efg*100:+.2f} pp)")
print(f"Pace:  home={home_pace:.2f}, road={road_pace:.2f}, delta={delta_pace:+.2f} poss/48")

# Significance tests (t-test)
t_ortg, p_ortg = stats.ttest_ind(home['off_rtg'].dropna(), road['off_rtg'].dropna())
t_efg, p_efg = stats.ttest_ind(home['efg_pct'].dropna(), road['efg_pct'].dropna())
t_pace, p_pace = stats.ttest_ind(home['pace'].dropna(), road['pace'].dropna())
print(f"\n=== Statistical significance (two-sided t-test) ===")
print(f"ORtg:  t={t_ortg:.2f}, p={p_ortg:.4f}")
print(f"eFG%:  t={t_efg:.2f}, p={p_efg:.4f}")
print(f"Pace:  t={t_pace:.2f}, p={p_pace:.4f}")

# ── Part C: FT rate from team_game (2025-26, has fta/fga directly) ──────
# FT rate = FTA per FGA
tg_reg = tg[tg['kind'] == 'reg'].copy()
tg_reg['ft_rate'] = tg_reg['fta'] / tg_reg['fga']
tg_reg['efg'] = (tg_reg['fgm'] + 0.5 * tg_reg['fg3m']) / tg_reg['fga']
# poss available directly
home_tg = tg_reg[tg_reg['is_home']]
road_tg = tg_reg[~tg_reg['is_home']]

home_ftr = home_tg['ft_rate'].mean()
road_ftr = road_tg['ft_rate'].mean()
delta_ftr = home_ftr - road_ftr

home_efg2 = home_tg['efg'].mean()
road_efg2 = road_tg['efg'].mean()
delta_efg2 = home_efg2 - road_efg2

home_pace2 = home_tg['poss'].mean()
road_pace2 = road_tg['poss'].mean()
delta_pace2 = home_pace2 - road_pace2

# ORtg from team_game: pts / poss * 100
home_ortg2 = (home_tg['pts'] / home_tg['poss'] * 100).mean()
road_ortg2 = (road_tg['pts'] / road_tg['poss'] * 100).mean()
delta_ortg2 = home_ortg2 - road_ortg2

print(f"\n=== From team_game.parquet (2025-26, n_home={len(home_tg)}, n_road={len(road_tg)}) ===")
print(f"ORtg:   home={home_ortg2:.2f}, road={road_ortg2:.2f}, delta={delta_ortg2:+.2f} pts/100")
print(f"eFG%:   home={home_efg2:.4f}, road={road_efg2:.4f}, delta={delta_efg2:+.4f} ({delta_efg2*100:+.2f} pp)")
print(f"FT/FGA: home={home_ftr:.4f}, road={road_ftr:.4f}, delta={delta_ftr:+.4f} ({delta_ftr*100:+.2f} pp)")
print(f"Pace:   home={home_pace2:.2f}, road={road_pace2:.2f}, delta={delta_pace2:+.2f} poss/game")

t_ftr, p_ftr = stats.ttest_ind(home_tg['ft_rate'].dropna(), road_tg['ft_rate'].dropna())
t_efg2, p_efg2 = stats.ttest_ind(home_tg['efg'].dropna(), road_tg['efg'].dropna())
t_pace2, p_pace2 = stats.ttest_ind(home_tg['poss'].dropna(), road_tg['poss'].dropna())
t_ortg2, p_ortg2 = stats.ttest_ind(
    (home_tg['pts'] / home_tg['poss'] * 100).dropna(),
    (road_tg['pts'] / road_tg['poss'] * 100).dropna()
)
print(f"\n=== Significance (team_game) ===")
print(f"ORtg:   t={t_ortg2:.2f}, p={p_ortg2:.4f}")
print(f"eFG%:   t={t_efg2:.2f}, p={p_efg2:.4f}")
print(f"FT/FGA: t={t_ftr:.2f}, p={p_ftr:.4f}")
print(f"Pace:   t={t_pace2:.2f}, p={p_pace2:.4f}")

# ── Part D: Compute multipliers for sim ──────────────────────────────────
# Use multi-season (team_advanced_stats) for ORtg/eFG/pace (larger n)
# Use team_game for FT rate (has fta/fga)
print(f"\n=== HEADLINE EFFECTS FOR SIMULATOR ===")
print(f"Source: team_advanced_stats (n_home={n_home}, n_road={n_road}) for ORtg/eFG/pace")
print(f"Source: team_game 2025-26 (n_home={len(home_tg)}, n_road={len(road_tg)}) for FT rate")
print()

# eFG multiplier: home_efg / road_efg
efg_mult = home_efg / road_efg
print(f"xfg_mult (home eFG / road eFG): {efg_mult:.4f}  [home={home_efg:.4f}, road={road_efg:.4f}]")

# FT rate multiplier: home_ftr / road_ftr
ftr_mult = home_ftr / road_ftr
print(f"ft_rate_mult (home FTA/FGA / road FTA/FGA): {ftr_mult:.4f}  [home={home_ftr:.4f}, road={road_ftr:.4f}]")

# Pace multiplier: home_pace / road_pace
pace_mult = home_pace / road_pace
print(f"pace_mult (home pace / road pace): {pace_mult:.4f}  [home={home_pace:.2f}, road={road_pace:.2f}]")

# ORtg additive delta (per 100 poss) -- more natural as additive for ORtg
print(f"ORtg additive delta: {delta_ortg:+.2f} pts/100 poss  (home minus road)")
print()
print("VERDICT:")
print(f"  eFG lift: +{delta_efg*100:.2f} pp ({efg_mult:.4f}x) -- {'significant' if p_efg < 0.05 else 'NOT significant'}")
print(f"  FT rate:  +{delta_ftr*100:.2f} pp ({ftr_mult:.4f}x) -- {'significant' if p_ftr < 0.05 else 'NOT significant'}")
print(f"  Pace:     {delta_pace:+.2f} poss  ({pace_mult:.4f}x) -- {'significant' if p_pace < 0.05 else 'NOT significant'}")
print(f"  ORtg:     {delta_ortg:+.2f} pts/100 -- {'significant' if p_ortg < 0.05 else 'NOT significant'}")
