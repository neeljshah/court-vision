"""
Phase 1 miner: player_tendencies.parquet
Builds a per-player, leak-flagged tendencies artifact for the NYK vs SAS G4 sim.

LEAK FLAGS applied per PHASE 0 guidance:
- leak_free: calendar/physical facts (height, age, weight, draft), or
             expanding-window per-game raw observation aggregates (season aggregates
             from player_rates which are derived from league_team_game raw observations
             across ALL prior games -- these are season-long but NOT game-specific splits)
- in_season: any same-season opponent-specific, vs-scheme, defender-rel-to-self,
             b2b, matchup_sensitivity, clutch, or situational splits
- scouting_only: percentile vaults (attribute_vault), pbp-derived shot-type
                 frequencies (pbp_attributes) -- these use same-season PBP pooled
                 across all opponent types, so can't be confirmed walk-forward

Each field gets a _lf (leak_flag) column in the output.
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

ROOT = "C:/Users/neelj/nba-ai-system"

# ── Load source tables ────────────────────────────────────────────────────────

pr = pd.read_parquet(f"{ROOT}/data/cache/team_system/player_rates.parquet")
pa = pd.read_parquet(f"{ROOT}/data/cache/team_system/player_attributes.parquet")
roles = pd.read_parquet(f"{ROOT}/data/cache/team_system/player_roles.parquet")
ratings = pd.read_parquet(f"{ROOT}/data/cache/team_system/player_ratings.parquet")
pbp_attr = pd.read_parquet(f"{ROOT}/data/cache/team_system/pbp_attributes.parquet")
pbp_know = pd.read_parquet(f"{ROOT}/data/cache/team_system/pbp_player_knowledge.parquet")
eff_full = pd.read_parquet(f"{ROOT}/data/cache/team_system/player_effects_full.parquet")
eff = pd.read_parquet(f"{ROOT}/data/cache/team_system/player_effects.parquet")
recency = pd.read_parquet(f"{ROOT}/data/cache/team_system/recency_rates.parquet")

print(f"player_rates: {pr.shape}")
print(f"player_attributes: {pa.shape}")
print(f"player_roles: {roles.shape}")
print(f"player_ratings: {ratings.shape}")
print(f"pbp_attributes: {pbp_attr.shape}")
print(f"pbp_player_knowledge: {pbp_know.shape}")
print(f"player_effects_full: {eff_full.shape}")
print(f"player_effects: {eff.shape}")

# ── Start with player_rates as the spine (507 players, has NYK+SAS) ───────────
base = pr[['pid','player','team','g','min','mpg']].copy()

# ── SECTION 1: Zone mix (z_) and FG% by zone (fg_)  → sim z, fg/xfg knobs ───
# Source: player_rates — season aggregates from raw box observations
# LEAK FLAG: leak_free (season-level aggregate of raw observations, not split by opponent)
zone_cols = ['z_rim','z_paint','z_mid','z_3','fg_rim','fg_paint','fg_mid']
for col in zone_cols:
    base[col] = pr[col]
    base[f"{col}_lf"] = "leak_free"

# ── SECTION 2: Usage / rate metrics  → sim use, tov_share, ft_share, oreb ────
# Source: player_rates — season aggregates
# LEAK FLAG: leak_free
rate_cols = {
    'use_per_min': 'use_per_min',      # maps to use (usage share)
    'shot_share': 'shot_share',         # fraction of team shots
    'tov_share': 'tov_share',           # maps to tov_share
    'ft_share': 'ft_share',             # maps to ft_share
    'ft_pts_share': 'ft_pts_share',     # maps to ft_pts_share
    'oreb_per_min': 'oreb_per_min',     # maps to oreb
    'fg3_rate': 'fg3_rate',             # fraction of shots that are 3s
    'fg3_pct': 'fg3_pct',               # 3pt FG%
    'ft_pct': 'ft_pct',                 # FT%
    'ast_per_min': 'ast_per_min',       # playmaking rate
    'pts_pg': 'pts_pg',                 # scoring volume
}
for src_col, dst_col in rate_cols.items():
    base[dst_col] = pr[src_col]
    base[f"{dst_col}_lf"] = "leak_free"

# ── SECTION 3: Self-creation and playmaking  → sim self_create, ast_rate ─────
# Source: pbp_player_knowledge — season aggregate PBP observations (NYK/SAS-heavy, 30 players)
# LEAK FLAG: in_season (PBP pooled across full season, not walk-forward isolated)
pkn = pbp_know[['pid','self_create_rate','assisted_rate','fastbreak_pts_pg',
                 'second_chance_pts_pg','clutch_fg_pct','clutch_fga',
                 'dunk_sh','layup_sh','jumper_sh','steals_pg','blocks_pg']].copy()
pkn = pkn.rename(columns={
    'self_create_rate': 'self_create',
    'assisted_rate': 'assisted_rate',
    'fastbreak_pts_pg': 'fastbreak_pts_pg',
    'second_chance_pts_pg': 'second_chance_pts_pg',
    'clutch_fg_pct': 'clutch_fg_pct',
    'clutch_fga': 'clutch_fga',
    'dunk_sh': 'dunk_sh',
    'layup_sh': 'layup_sh',
    'jumper_sh': 'jumper_sh',
    'steals_pg': 'steals_pg_pbp',
    'blocks_pg': 'blocks_pg_pbp',
})
base = base.merge(pkn, on='pid', how='left')

pkn_cols = ['self_create','assisted_rate','fastbreak_pts_pg','second_chance_pts_pg',
            'clutch_fg_pct','clutch_fga','dunk_sh','layup_sh','jumper_sh',
            'steals_pg_pbp','blocks_pg_pbp']
for col in pkn_cols:
    base[f"{col}_lf"] = "in_season"
# clutch is explicitly scouting_only per PHASE 0 guidance
base['clutch_fg_pct_lf'] = "scouting_only"
base['clutch_cfa_lf'] = "scouting_only"

# ── SECTION 4: Shot-type profile from pbp_attributes  → sim z, fg knobs ──────
# Source: pbp_attributes — PBP per-game aggregated over full season (NYK/SAS+others)
# LEAK FLAG: in_season (same-season pooled PBP; shot-type pcts flagged scouting_only per PHASE 0)
pba_cols_wanted = [
    'rim_finish_att', 'rim_finish_pct', 'rim_finish_freq', 'rim_finish_asst_share',
    'floater_att', 'floater_pct', 'floater_freq', 'floater_asst_share',
    'putback_att', 'putback_pct', 'putback_freq', 'putback_asst_share',
    'post_att', 'post_pct', 'post_freq', 'post_asst_share',
    'midrange_att', 'midrange_pct', 'midrange_freq', 'midrange_asst_share',
    'corner_3_att', 'corner_3_pct', 'corner_3_freq', 'corner_3_asst_share',
    'catch_shoot_3_att', 'catch_shoot_3_pct', 'catch_shoot_3_freq', 'catch_shoot_3_asst_share',
    'pullup_3_att', 'pullup_3_pct', 'pullup_3_freq', 'pullup_3_asst_share',
    'ast_pg', 'and1_pg', 'fastbreak_fgm_pg', 'stl_pg', 'blk_pg',
]
pba_keep = pbp_attr[['pid'] + pba_cols_wanted].copy()
# The _sh columns contain arrays — drop them (not usable without dereferencing)
# Also filter out list-valued columns
base = base.merge(pba_keep, on='pid', how='left')

for col in pba_cols_wanted:
    # per PHASE 0: shot-type pcts from pbp_attributes are scouting_only
    if '_pct' in col or '_freq' in col or '_asst_share' in col:
        base[f"{col}_lf"] = "scouting_only"
    else:
        base[f"{col}_lf"] = "in_season"

# ── SECTION 5: Role/archetype  → sim routing (which knobs dominate) ──────────
# Source: player_roles — derived from season aggregates
# LEAK FLAG: in_season (percentile-normalized within season)
role_cols = ['posgroup','archetype','creation','playmaking','spacing',
             'rim_pressure','rebounding','rim_protect','perimeter_d',
             'self_create_role','usage_pct','scorer_pct']
roles2 = roles[['pid'] + [c for c in role_cols if c in roles.columns]].copy()
# Rename self_create to avoid collision with pbp_know self_create
if 'self_create' in roles2.columns:
    roles2 = roles2.rename(columns={'self_create': 'self_create_role'})
roles2 = roles2.rename(columns={c: f"role_{c}" if c not in ['pid','posgroup','archetype'] else c
                                  for c in roles2.columns if c != 'pid'})
base = base.merge(roles2, on='pid', how='left')

for col in [c for c in roles2.columns if c != 'pid']:
    base[f"{col}_lf"] = "in_season"

# ── SECTION 6: Ratings  → provides int_d / perim_d / blk knobs ───────────────
# Source: player_ratings — role-aware 13-cat ratings
# LEAK FLAG: in_season (computed within season using season aggregates)
rat_cols = ['SCORING','SHOOTING','PLAYMAKING','CREATION','FINISHING',
            'REBOUNDING','INTERIOR_D','PERIMETER_D','CLUTCH','IQ',
            'SIZE','ATHLETICISM','DURABILITY','OVERALL']
rat2 = ratings[['pid'] + [c for c in rat_cols if c in ratings.columns]].copy()
rat2 = rat2.rename(columns={c: f"rat_{c}" for c in rat_cols if c in rat2.columns})
base = base.merge(rat2, on='pid', how='left')

for col in [c for c in rat2.columns if c != 'pid']:
    base[f"{col}_lf"] = "in_season"
# CLUTCH is scouting_only per PHASE 0
base['rat_CLUTCH_lf'] = "scouting_only"

# ── SECTION 7: Physical attributes  → sim height, size knobs ─────────────────
# Source: player_attributes — calendar/physical facts
# LEAK FLAG: leak_free (age, height, weight, draft are physical/calendar facts)
pha_cols = ['height_in','weight_lb','age','exp','draft_number','undrafted_flag',
            'size_z','is_rim_protector','is_small','prime','age_fatigue_w']
pha2 = pa[['pid'] + [c for c in pha_cols if c in pa.columns]].copy()
base = base.merge(pha2, on='pid', how='left')

for col in pha_cols:
    if col in ['height_in','weight_lb','age','exp','draft_number','undrafted_flag']:
        base[f"{col}_lf"] = "leak_free"
    else:
        # derived size_z, is_rim_protector, etc. are in-season percentile flags
        base[f"{col}_lf"] = "in_season"

# ── SECTION 8: Recency rates  → freshness signal ──────────────────────────────
# Source: recency_rates — last N games window ending before G4
# These are aggregated over recent games — expanding-style prior to G4 tip-off
# For G4 (2026-06-10), these would have been computed from prior games
# LEAK FLAG: leak_free IF as_of < tip-off; since we cannot verify the exact window
#   end date, flag conservatively as in_season
rec_cols = ['pts_pg_rec','reb_pg_rec','ast_pg_rec','mpg_rec']
rec2 = recency[['pid'] + rec_cols].copy()
base = base.merge(rec2, on='pid', how='left')
for col in rec_cols:
    base[f"{col}_lf"] = "in_season"  # conservative — window end date unverifiable

# ── SECTION 9: vs_strongD / b2b splits  → in_season / scouting_only ──────────
# Source: player_effects_full — explicitly flagged as scouting_only per PHASE 0
eff_cols = ['overall_efg','overall_ppm','b2b_xfg','b2b_raw','b2b_use',
            'vs_strongD_xfg','vs_strongD_raw','vs_weakD_xfg','vs_weakD_raw',
            'vs_strongD_use','fast_xfg','slow_xfg','fast_use','matchup_sensitivity']
eff2 = eff_full[['pid'] + [c for c in eff_cols if c in eff_full.columns]].copy()
base = base.merge(eff2, on='pid', how='left')

for col in eff_cols:
    if col in ['overall_efg','overall_ppm']:
        base[f"{col}_lf"] = "in_season"
    else:
        # b2b, vs_strongD, matchup_sensitivity are explicitly scouting_only per PHASE 0
        base[f"{col}_lf"] = "scouting_only"

# ── SECTION 10: Home/road effects  → in_season ───────────────────────────────
# Source: player_effects — home/road xfg splits
eff_home_cols = ['home_xfg','road_xfg','plays_better_away']
eff_h2 = eff[['pid'] + [c for c in eff_home_cols if c in eff.columns]].copy()
base = base.merge(eff_h2, on='pid', how='left')
for col in eff_home_cols:
    base[f"{col}_lf"] = "in_season"

# ── Compute composite sim-ready fields ───────────────────────────────────────

# xfg: weighted zone-blend FG% (approximate expected FG rate)
# xfg ~ z_rim*fg_rim + z_paint*fg_paint + z_mid*fg_mid + z_3*fg3_pct*1.5/2
# Standardized to 2pt-equivalent eFG%
base['xfg_blend'] = (
    base['z_rim'].fillna(0) * base['fg_rim'].fillna(0.55) +
    base['z_paint'].fillna(0) * base['fg_paint'].fillna(0.45) +
    base['z_mid'].fillna(0) * base['fg_mid'].fillna(0.43) +
    base['z_3'].fillna(0) * base['fg3_pct'].fillna(0.35) * 1.5
)
base['xfg_blend_lf'] = "leak_free"  # derived from leak_free zone+fg fields

# P&R proxy: combination of floater_freq + pullup_3_freq + playmaking
# (floaters and pullup 3s are the primary PNR handler outputs)
# available only for PBP-covered players
base['pnr_handler_proxy'] = (
    base['floater_freq'].fillna(0) * 0.5 +
    base['pullup_3_freq'].fillna(0) * 0.4 +
    base['ast_per_min'].fillna(0) * 2.0
).clip(0, 1)
base['pnr_handler_proxy_lf'] = "scouting_only"  # floater/pullup freq is scouting_only

# Catch-shoot vs pull-up split ratio (for z_3 zone FG calibration)
# catch_shoot_3_freq / (catch_shoot_3_freq + pullup_3_freq)
cs_total = base['catch_shoot_3_freq'].fillna(0) + base['pullup_3_freq'].fillna(0)
base['catch_shoot_ratio'] = np.where(cs_total > 0,
    base['catch_shoot_3_freq'].fillna(0) / cs_total, np.nan)
base['catch_shoot_ratio_lf'] = "scouting_only"

# Transition rate proxy: fastbreak_fgm_pg / pts_pg
base['transition_rate'] = np.where(
    base['pts_pg'] > 0,
    (base['fastbreak_pts_pg'].fillna(0) * 1.2) / base['pts_pg'].clip(lower=0.1),
    np.nan)
base['transition_rate_lf'] = "in_season"

# Foul-drawing index: ft_share normalized vs usage
base['foul_draw_index'] = np.where(
    base['use_per_min'] > 0,
    base['ft_share'] / base['use_per_min'].clip(lower=0.01),
    np.nan)
base['foul_draw_index_lf'] = "leak_free"

print(f"\nFinal base shape before dedup: {base.shape}")
print(f"Columns: {len(base.columns)}")

# ── Deduplicate: keep highest-mpg row per player ──────────────────────────────
base = base.sort_values('mpg', ascending=False)
base = base.drop_duplicates(subset='pid', keep='first')
base = base.reset_index(drop=True)

print(f"After dedup: {base.shape}")
print(f"Teams represented: {sorted(base['team'].dropna().unique().tolist())[:10]}...")
nyk_sas_count = base[base['team'].isin(['NYK','SAS'])].shape[0]
print(f"NYK/SAS rows: {nyk_sas_count}")

# ── Write output ──────────────────────────────────────────────────────────────
out_path = f"{ROOT}/data/cache/team_system/player_tendencies.parquet"
base.to_parquet(out_path, index=False)
print(f"\nWrote: {out_path}")

# ── Verification ──────────────────────────────────────────────────────────────
verify = pd.read_parquet(out_path)
print(f"Verified shape: {verify.shape}")

# Print NYK/SAS key players
key_players = verify[verify['team'].isin(['NYK','SAS'])][
    ['pid','player','team','mpg','archetype','self_create','xfg_blend',
     'z_rim','z_3','ft_share','tov_share','rat_INTERIOR_D','rat_PERIMETER_D','rat_OVERALL']
].sort_values('mpg', ascending=False)
print("\nKey NYK/SAS players (top by mpg):")
print(key_players.head(20).to_string())

# Print leak flag summary
lf_cols = [c for c in verify.columns if c.endswith('_lf')]
from collections import Counter
all_flags = []
for col in lf_cols:
    all_flags.extend(verify[col].dropna().tolist())
print("\nLeak flag distribution across all field instances:")
print(Counter(all_flags))
