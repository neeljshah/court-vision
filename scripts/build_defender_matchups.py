"""
Build defender_matchups.parquet
Phase 1 miner: Defender Matchups
Writes to data/cache/team_system/defender_matchups.parquet
All leak flags documented per-field.
"""
import pandas as pd
import numpy as np
import os

ROOT = r'C:\Users\neelj\nba-ai-system'

# Load sources
pr = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/player_ratings.parquet'))
pa = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/player_attributes.parquet'))
dm = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/defender_matchup.parquet'))
ds = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/defender_suppression.parquet'))
pba = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/pbp_attributes.parquet'))
poss = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/pbp_possessions.parquet'))
ltg = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/league_team_game.parquet'))
td = pd.read_parquet(os.path.join(ROOT, 'data/cache/team_system/team_defense.parquet'))

nyk_ids = set(pr[pr['team'] == 'NYK']['pid'].tolist())
sas_ids = set(pr[pr['team'] == 'SAS']['pid'].tolist())
all_target_ids = nyk_ids | sas_ids

id_to_team = dict(zip(pr['pid'], pr['team']))

# ============================================================
# BLOCK A: MATCHUP PAIR ROWS (entity_type = matchup_pair)
# One row per (off_player, def_player) cross-team pair.
# Source: defender_matchup.parquet (season-pooled => in_season)
# ============================================================
nyk_off_vs_sas_def = dm[dm['off_id'].isin(nyk_ids) & dm['def_id'].isin(sas_ids)].copy()
nyk_off_vs_sas_def['context'] = 'NYK_off_vs_SAS_def'
sas_off_vs_nyk_def = dm[dm['off_id'].isin(sas_ids) & dm['def_id'].isin(nyk_ids)].copy()
sas_off_vs_nyk_def['context'] = 'SAS_off_vs_NYK_def'

mp = pd.concat([nyk_off_vs_sas_def, sas_off_vs_nyk_def], ignore_index=True)
mp['off_team'] = mp['off_id'].map(id_to_team)
mp['def_team'] = mp['def_id'].map(id_to_team)

# Join defender int_d/perim_d (in_season ratings)
pr_def = pr[['pid', 'INTERIOR_D', 'PERIMETER_D']].rename(
    columns={'pid': 'def_id', 'INTERIOR_D': 'def_int_d', 'PERIMETER_D': 'def_perim_d'})
mp = mp.merge(pr_def, on='def_id', how='left')

# Join physical attributes (leak_free)
pa_def = pa[['pid', 'height_in', 'is_rim_protector']].rename(
    columns={'pid': 'def_id', 'height_in': 'def_height_in', 'is_rim_protector': 'def_is_rim_prot'})
mp = mp.merge(pa_def, on='def_id', how='left')
pa_off = pa[['pid', 'height_in']].rename(
    columns={'pid': 'off_id', 'height_in': 'off_height_in'})
mp = mp.merge(pa_off, on='off_id', how='left')

# entity tag
mp['entity_type'] = 'matchup_pair'

# Leak flag columns
mp['leak__poss'] = 'in_season'
mp['leak__eff_resid'] = 'in_season'
mp['leak__size_gap'] = 'leak_free'
mp['leak__resid_shrunk'] = 'in_season'
mp['leak__def_int_d'] = 'in_season'
mp['leak__def_perim_d'] = 'in_season'
mp['leak__def_height_in'] = 'leak_free'
mp['leak__def_is_rim_prot'] = 'leak_free'
mp['leak__off_height_in'] = 'leak_free'

# Standardize column set for concat
mp_cols = [
    'entity_type', 'context', 'off_id', 'off', 'off_team', 'def_id', 'deff', 'def_team',
    'poss', 'eff_resid', 'size_gap', 'resid_shrunk',
    'def_int_d', 'def_perim_d', 'def_height_in', 'def_is_rim_prot', 'off_height_in',
    'leak__poss', 'leak__eff_resid', 'leak__size_gap', 'leak__resid_shrunk',
    'leak__def_int_d', 'leak__def_perim_d', 'leak__def_height_in',
    'leak__def_is_rim_prot', 'leak__off_height_in',
]
for c in mp_cols:
    if c not in mp.columns:
        mp[c] = None
mp = mp[mp_cols].copy()

print("Block A (matchup_pair) shape:", mp.shape)

# ============================================================
# BLOCK B: DEFENDER ENTITY ROWS (entity_type = defender)
# One row per NYK/SAS defender with all per-player defense fields.
# ============================================================
nyk_p = pr[pr['team'] == 'NYK'][['pid', 'player', 'team', 'INTERIOR_D', 'PERIMETER_D', 'OVERALL']].copy()
sas_p = pr[pr['team'] == 'SAS'][['pid', 'player', 'team', 'INTERIOR_D', 'PERIMETER_D', 'OVERALL']].copy()
all_p = pd.concat([nyk_p, sas_p], ignore_index=True)

# Suppression fields (in_season - season-pooled)
ds_sub = ds[['def_id', 'poss', 'supp', 'cov_def_rating']].rename(columns={
    'def_id': 'pid', 'poss': 'supp_poss', 'supp': 'supp_ppp_delta'})
all_p = all_p.merge(ds_sub, on='pid', how='left')

# Physical (leak_free)
pa_phys = pa[['pid', 'height_in', 'weight_lb', 'is_rim_protector', 'size_z', 'agility_proxy']].copy()
all_p = all_p.merge(pa_phys, on='pid', how='left')

# blk_pg from pbp_attributes (in_season - season-pooled box stats)
pba_sub = pba[pba['pid'].isin(all_target_ids)][['pid', 'blk_pg']].copy()
all_p = all_p.merge(pba_sub, on='pid', how='left')

all_p['entity_type'] = 'defender'
# context = which side of matchup
all_p['context'] = all_p['team'].apply(
    lambda t: 'NYK_defender' if t == 'NYK' else 'SAS_defender')

# Leak flags
all_p['leak__INTERIOR_D'] = 'in_season'
all_p['leak__PERIMETER_D'] = 'in_season'
all_p['leak__OVERALL'] = 'in_season'
all_p['leak__supp_poss'] = 'in_season'
all_p['leak__supp_ppp_delta'] = 'in_season'
all_p['leak__cov_def_rating'] = 'in_season'
all_p['leak__height_in'] = 'leak_free'
all_p['leak__weight_lb'] = 'leak_free'
all_p['leak__is_rim_protector'] = 'leak_free'
all_p['leak__size_z'] = 'leak_free'
all_p['leak__agility_proxy'] = 'leak_free'
all_p['leak__blk_pg'] = 'in_season'

print("Block B (defender) shape:", all_p.shape)

# ============================================================
# BLOCK C: TEAM DEFENSE ROWS (entity_type = team_defense)
# Walk-forward = regular season aggregate (leak_free)
# H2H = 4 NYK/SAS games in pbp_possessions (in_season)
# team_defense.parquet tov_force/ft_force (in_season)
# ============================================================
ltg['date_dt'] = pd.to_datetime(ltg['date'])
ltg = ltg.sort_values('date_dt')
nyk_reg = ltg[ltg['team'] == 'NYK']
sas_reg = ltg[ltg['team'] == 'SAS']

# H2H
nyk_sas_p = poss[(poss['off'].isin(['NYK', 'SAS'])) & (poss['deff'].isin(['NYK', 'SAS']))]

team_def_rows = []
for team, tdf in [('NYK', nyk_reg), ('SAS', sas_reg)]:
    against = 'SAS' if team == 'NYK' else 'NYK'
    h2h_d = nyk_sas_p[(nyk_sas_p['deff'] == team) & (nyk_sas_p['off'] == against)]

    td_row = td[td['team'] == team]
    tov_force_val = float(td_row['tov_force'].values[0]) if len(td_row) else None
    ft_force_val = float(td_row['ft_force'].values[0]) if len(td_row) else None
    oreb_strength_val = float(td_row['oreb_strength'].values[0]) if len(td_row) else None

    row = {
        'entity_type': 'team_defense',
        'context': f'{team}_team_defense',
        'team': team,
        # walk-forward (leak_free)
        'wf_n_games': len(tdf),
        'wf_def_ppp': tdf['opp_pts'].sum() / tdf['opp_poss'].sum(),
        'wf_def_tov_force': tdf['opp_tov'].sum() / tdf['opp_poss'].sum(),
        'wf_def_ft_force': tdf['opp_fta'].sum() / tdf['opp_fga'].sum(),
        'wf_def_oreb_pct': tdf['oreb'].sum() / (tdf['oreb'].sum() + tdf['opp_oreb'].sum()),
        # H2H (in_season)
        'h2h_poss': len(h2h_d),
        'h2h_ppp_allowed': float(h2h_d['pts'].sum() / len(h2h_d)) if len(h2h_d) > 0 else None,
        'h2h_n_games': int(h2h_d['gid'].nunique()),
        # team_defense.parquet (in_season)
        'td_tov_force': tov_force_val,
        'td_ft_force': ft_force_val,
        'td_oreb_strength': oreb_strength_val,
        # leak flags
        'leak__wf_def_ppp': 'leak_free',
        'leak__wf_def_tov_force': 'leak_free',
        'leak__wf_def_ft_force': 'leak_free',
        'leak__wf_def_oreb_pct': 'leak_free',
        'leak__h2h_ppp_allowed': 'in_season',
        'leak__h2h_poss': 'in_season',
        'leak__td_tov_force': 'in_season',
        'leak__td_ft_force': 'in_season',
        'leak__td_oreb_strength': 'in_season',
    }
    team_def_rows.append(row)

td_df = pd.DataFrame(team_def_rows)
print("Block C (team_defense) shape:", td_df.shape)
print(td_df[['team', 'wf_def_ppp', 'h2h_ppp_allowed', 'td_tov_force', 'td_ft_force']].to_string())

# ============================================================
# CONCAT all blocks with common columns
# Use a wide union via pd.concat with fill_value=None
# ============================================================
output = pd.concat([mp, all_p, td_df], ignore_index=True, sort=False)
output = output.reset_index(drop=True)

print("\nFinal shape:", output.shape)
print("Columns:", list(output.columns))

out_path = os.path.join(ROOT, 'data/cache/team_system/defender_matchups.parquet')
output.to_parquet(out_path, index=False)
print(f"\nWritten to {out_path}")

# Verify read-back
verify = pd.read_parquet(out_path)
print("Verified read-back shape:", verify.shape)
print("entity_type counts:", verify['entity_type'].value_counts().to_dict())
