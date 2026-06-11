# Phase 1 miner: clutch_fatigue.parquet
# Writes ONLY to data/cache/team_system/clutch_fatigue.parquet
# No production .py files edited.
import pandas as pd
import json
import numpy as np
import os

CUTOFF = pd.Timestamp('2026-06-09')  # pre-G4 cutoff

ROOT = 'C:/Users/neelj/nba-ai-system'
os.chdir(ROOT)

# ---- Load sources ----
pbp = pd.read_parquet('data/cache/team_system/pbp_possessions.parquet')
pbp['is_clutch'] = ((pbp['period'] >= 4) & (pbp['grem'] <= 300) & (pbp['abs_margin'] <= 5))
pbp['is_playoff'] = pbp['gid'].str.startswith('004')
pbp['is_finals'] = pbp['gid'].isin(['0042500401', '0042500402'])

player_rates = pd.read_parquet('data/cache/team_system/player_rates.parquet')
player_ratings = pd.read_parquet('data/cache/team_system/player_ratings.parquet')
player_effects = pd.read_parquet('data/cache/team_system/player_effects_full.parquet')
player_attrs = pd.read_parquet('data/cache/team_system/player_attributes.parquet')
gamelog = pd.read_parquet('data/cache/team_system/nyksas_full_gamelog.parquet')
gamelog['date'] = pd.to_datetime(gamelog['date'])
gamelog = gamelog.sort_values(['pid', 'date'])

qshape_atlas = pd.read_parquet('data/cache/atlas_player_quarter_shape_fatigue.parquet')
restb2b_atlas = pd.read_parquet('data/cache/atlas_player_rest_b2b_splits.parquet')
clutch_player_atlas = pd.read_parquet('data/cache/atlas_player_clutch_scoring.parquet')
clutch_team_atlas = pd.read_parquet('data/cache/atlas_team_clutch_team.parquet')

# ============================================================
# SECTION 1: TEAM-LEVEL ROWS
# ============================================================
team_rows = []

for team in ['NYK', 'SAS']:
    off_all = pbp[pbp['off'] == team]
    def_all = pbp[pbp['deff'] == team]
    clutch_off = pbp[(pbp['is_clutch']) & (pbp['off'] == team)]
    clutch_def = pbp[(pbp['is_clutch']) & (pbp['deff'] == team)]

    off_ppp_all = off_all['pts'].mean() * 100
    def_ppp_all = def_all['pts'].mean() * 100
    net_overall = off_ppp_all - def_ppp_all

    clutch_off_ppp = clutch_off['pts'].mean() * 100 if len(clutch_off) > 0 else np.nan
    clutch_def_ppp = clutch_def['pts'].mean() * 100 if len(clutch_def) > 0 else np.nan
    clutch_net = clutch_off_ppp - clutch_def_ppp if not np.isnan(clutch_off_ppp) else np.nan
    clutch_net_vs_overall = clutch_net - net_overall if not np.isnan(clutch_net) else np.nan

    n_clutch_off = len(clutch_off)
    n_clutch_def = len(clutch_def)

    # Playoff clutch
    po_clutch_off = pbp[(pbp['is_clutch']) & (pbp['is_playoff']) & (pbp['off'] == team)]
    po_clutch_def = pbp[(pbp['is_clutch']) & (pbp['is_playoff']) & (pbp['deff'] == team)]
    po_clutch_off_ppp = po_clutch_off['pts'].mean() * 100 if len(po_clutch_off) > 0 else np.nan
    po_clutch_def_ppp = po_clutch_def['pts'].mean() * 100 if len(po_clutch_def) > 0 else np.nan
    po_clutch_net = po_clutch_off_ppp - po_clutch_def_ppp if not np.isnan(po_clutch_off_ppp) else np.nan

    # Finals clutch G1+G2 (small n)
    finals_clutch_off = pbp[(pbp['is_clutch']) & (pbp['is_finals']) & (pbp['off'] == team)]
    finals_clutch_def = pbp[(pbp['is_clutch']) & (pbp['is_finals']) & (pbp['deff'] == team)]
    finals_clutch_off_ppp = finals_clutch_off['pts'].mean() * 100 if len(finals_clutch_off) > 0 else np.nan
    finals_clutch_def_ppp = finals_clutch_def['pts'].mean() * 100 if len(finals_clutch_def) > 0 else np.nan
    finals_clutch_net = finals_clutch_off_ppp - finals_clutch_def_ppp if not np.isnan(finals_clutch_off_ppp) else np.nan
    n_finals_clutch = len(finals_clutch_off)

    # Quarter-shape from PBP
    q_off = {}
    q_def = {}
    for q in [1, 2, 3, 4]:
        q_off[q] = pbp[(pbp['off'] == team) & (pbp['period'] == q)]['pts'].mean() * 100
        q_def[q] = pbp[(pbp['deff'] == team) & (pbp['period'] == q)]['pts'].mean() * 100
    early_off = (q_off[1] + q_off[2] + q_off[3]) / 3
    q4_off_fade_ratio = q_off[4] / early_off if early_off > 0 else np.nan
    early_def = (q_def[1] + q_def[2] + q_def[3]) / 3
    q4_def_fade_ratio = q_def[4] / early_def if early_def > 0 else np.nan

    # Fatigue: playoff game count (leak_free: physical schedule fact)
    team_playoff_games = gamelog[
        gamelog['gid'].str.startswith('004') & (gamelog['team'] == team) & (gamelog['date'] < CUTOFF)
    ]['gid'].nunique()

    team_playoff_mins = gamelog[
        gamelog['gid'].str.startswith('004') & (gamelog['team'] == team) & (gamelog['date'] < CUTOFF)
    ]['mins'].sum()

    # Season-level ratings from clutch_team atlas
    ct_match = clutch_team_atlas[clutch_team_atlas['team_tricode'] == team]
    team_off_rtg = np.nan
    team_def_rtg = np.nan
    team_net_rtg_season = np.nan
    if len(ct_match) > 0:
        ct_row = ct_match.iloc[0]
        ratings = json.loads(ct_row['ratings']) if isinstance(ct_row['ratings'], str) else ct_row['ratings']
        team_off_rtg = float(ratings.get('off_rtg', np.nan))
        team_def_rtg = float(ratings.get('def_rtg', np.nan))
        team_net_rtg_season = float(ratings.get('net_rtg', np.nan))

    row = {
        'entity_type': 'team',
        'entity_id': team,
        'entity_name': team,
        'team': team,
        # Clutch fields (in_season: season-pooled PBP)
        'clutch_off_ppp100': clutch_off_ppp,
        'clutch_def_ppp100': clutch_def_ppp,
        'clutch_net_rtg': clutch_net,
        'clutch_net_vs_overall': clutch_net_vs_overall,
        'n_clutch_off_poss': n_clutch_off,
        'n_clutch_def_poss': n_clutch_def,
        'po_clutch_off_ppp100': po_clutch_off_ppp,
        'po_clutch_def_ppp100': po_clutch_def_ppp,
        'po_clutch_net_rtg': po_clutch_net,
        'finals_clutch_off_ppp100': finals_clutch_off_ppp,
        'finals_clutch_def_ppp100': finals_clutch_def_ppp,
        'finals_clutch_net': finals_clutch_net,
        'n_finals_clutch_off_poss': n_finals_clutch,
        # Quarter shape (in_season)
        'q1_off_ppp100': q_off[1],
        'q2_off_ppp100': q_off[2],
        'q3_off_ppp100': q_off[3],
        'q4_off_ppp100': q_off[4],
        'q4_off_fade_ratio': q4_off_fade_ratio,
        'q1_def_ppp100': q_def[1],
        'q2_def_ppp100': q_def[2],
        'q3_def_ppp100': q_def[3],
        'q4_def_ppp100': q_def[4],
        'q4_def_fade_ratio': q4_def_fade_ratio,
        # Season ratings (in_season)
        'team_off_rtg_season': team_off_rtg,
        'team_def_rtg_season': team_def_rtg,
        'team_net_rtg_season': team_net_rtg_season,
        # Fatigue / rest (leak_free: physical/schedule facts)
        'playoff_games_pre_g4': int(team_playoff_games),
        'playoff_mins_total_pre_g4': float(team_playoff_mins),
        'g4_days_rest': 2,
        'g4_is_b2b': 0,
        # Leak flags as JSON string sidecar
        '__leak_flags__': json.dumps({
            'clutch_off_ppp100': 'in_season',
            'clutch_def_ppp100': 'in_season',
            'clutch_net_rtg': 'in_season',
            'clutch_net_vs_overall': 'in_season',
            'n_clutch_off_poss': 'in_season',
            'n_clutch_def_poss': 'in_season',
            'po_clutch_off_ppp100': 'in_season',
            'po_clutch_def_ppp100': 'in_season',
            'po_clutch_net_rtg': 'in_season',
            'finals_clutch_off_ppp100': 'in_season',
            'finals_clutch_def_ppp100': 'in_season',
            'finals_clutch_net': 'in_season',
            'n_finals_clutch_off_poss': 'in_season',
            'q1_off_ppp100': 'in_season',
            'q2_off_ppp100': 'in_season',
            'q3_off_ppp100': 'in_season',
            'q4_off_ppp100': 'in_season',
            'q4_off_fade_ratio': 'in_season',
            'q1_def_ppp100': 'in_season',
            'q2_def_ppp100': 'in_season',
            'q3_def_ppp100': 'in_season',
            'q4_def_ppp100': 'in_season',
            'q4_def_fade_ratio': 'in_season',
            'team_off_rtg_season': 'in_season',
            'team_def_rtg_season': 'in_season',
            'team_net_rtg_season': 'in_season',
            'playoff_games_pre_g4': 'leak_free',
            'playoff_mins_total_pre_g4': 'leak_free',
            'g4_days_rest': 'leak_free',
            'g4_is_b2b': 'leak_free',
        })
    }
    team_rows.append(row)

team_df = pd.DataFrame(team_rows)
print('Team rows:', len(team_df))

# ============================================================
# SECTION 2: PLAYER-LEVEL ROWS (NYK + SAS)
# ============================================================
player_rows = []

# Get NYK/SAS players from player_rates (has team, mpg, etc.)
nyk_sas_rates = player_rates[player_rates['team'].isin(['NYK', 'SAS'])].copy()

# Join ratings for CLUTCH rating
ratings_sub = player_ratings[player_ratings['team'].isin(['NYK', 'SAS'])][
    ['pid', 'CLUTCH', 'INTERIOR_D', 'PERIMETER_D', 'mpg']
].rename(columns={'mpg': 'mpg_ratings'})

# player_attrs for physical fields
attrs_sub = player_attrs[['pid', 'age', 'height_in', 'weight_lb', 'age_fatigue_w', 'prime', 'exp']]

# qshape
qshape_sub = qshape_atlas[['player_id', 'q1_pts', 'q2_pts', 'q3_pts', 'q4_pts',
                             'q4_vs_early_ratio', 'q4_fade_abs',
                             'b2b_n_games', 'b2b_q4_pts_delta', 'b2b_decay_ratio',
                             'min_per_game']].rename(columns={'player_id': 'pid'})

# restb2b
restb2b_sub = restb2b_atlas[['player_id', 'overall', 'b2b', 'one_day', 'two_plus',
                               'fatigue_proxy']].rename(columns={'player_id': 'pid'})

# player clutch atlas
clutch_sub = clutch_player_atlas[['player_id', 'scoring', 'pbp_clutch', 'value']].rename(
    columns={'player_id': 'pid', 'value': 'clutch_pts_per36_value'})

# player effects (b2b)
effects_sub = player_effects[['pid', 'b2b_n', 'b2b_raw', 'b2b_xfg', 'b2b_use',
                                'matchup_sensitivity']].copy()

# Compute per-player playoff load and minutes variance pre-G4
# (leak_free: calendar/physical observation facts)
pre_g4_log = gamelog[gamelog['date'] < CUTOFF].copy()
playoff_load = pre_g4_log[pre_g4_log['gid'].str.startswith('004') & pre_g4_log['team'].isin(['NYK', 'SAS'])].groupby(
    ['pid', 'player', 'team'])['mins'].agg(['sum', 'count']).reset_index()
playoff_load.columns = ['pid', 'player', 'team', 'playoff_mins_total', 'playoff_gp']
playoff_load['playoff_mpg'] = playoff_load['playoff_mins_total'] / playoff_load['playoff_gp']

# Minutes variance from all pre-G4 games
min_var = pre_g4_log[pre_g4_log['team'].isin(['NYK', 'SAS'])].groupby(
    ['pid', 'player', 'team'])['mins'].agg(['std', 'mean', 'count']).reset_index()
min_var.columns = ['pid', 'player', 'team', 'min_std', 'min_mean', 'n_games']
min_var['min_cv'] = min_var['min_std'] / (min_var['min_mean'] + 1e-6)

# Reg season MPG for comparison
reg_load = pre_g4_log[~pre_g4_log['gid'].str.startswith('004') & pre_g4_log['team'].isin(['NYK', 'SAS'])].groupby(
    ['pid', 'player', 'team'])['mins'].mean().reset_index().rename(columns={'mins': 'reg_mpg'})

for _, pr_row in nyk_sas_rates.iterrows():
    pid = pr_row['pid']
    team = pr_row['team']
    player_name = pr_row['player']

    # Ratings
    rat = ratings_sub[ratings_sub['pid'] == pid]
    clutch_rating = int(rat['CLUTCH'].iloc[0]) if len(rat) > 0 else None
    int_d = int(rat['INTERIOR_D'].iloc[0]) if len(rat) > 0 else None
    perim_d = int(rat['PERIMETER_D'].iloc[0]) if len(rat) > 0 else None

    # Physical attrs
    attr = attrs_sub[attrs_sub['pid'] == pid]
    age = float(attr['age'].iloc[0]) if len(attr) > 0 else None
    age_fatigue_w = float(attr['age_fatigue_w'].iloc[0]) if len(attr) > 0 else None
    prime = int(attr['prime'].iloc[0]) if len(attr) > 0 else None
    height_in = float(attr['height_in'].iloc[0]) if len(attr) > 0 else None
    exp = float(attr['exp'].iloc[0]) if len(attr) > 0 else None

    # Quarter shape atlas
    qs = qshape_sub[qshape_sub['pid'] == pid]
    q4_vs_early = float(qs['q4_vs_early_ratio'].iloc[0]) if len(qs) > 0 else None
    q4_fade_abs = float(qs['q4_fade_abs'].iloc[0]) if len(qs) > 0 else None
    b2b_n_games_qs = float(qs['b2b_n_games'].iloc[0]) if len(qs) > 0 else None
    b2b_q4_pts_delta = float(qs['b2b_q4_pts_delta'].iloc[0]) if len(qs) > 0 else None
    b2b_decay_ratio = float(qs['b2b_decay_ratio'].iloc[0]) if len(qs) > 0 else None

    # Rest/b2b atlas - parse fatigue_proxy
    rb = restb2b_sub[restb2b_sub['pid'] == pid]
    efg_b2b_delta = None
    min_b2b_delta = None
    b2b_efg = None
    two_plus_efg = None
    overall_efg = None
    if len(rb) > 0:
        fp = rb['fatigue_proxy'].iloc[0]
        if isinstance(fp, str):
            try:
                fp = json.loads(fp)
            except Exception:
                fp = {}
        if isinstance(fp, dict):
            efg_b2b_delta = fp.get('efg_b2b_minus_2plus')
            min_b2b_delta = fp.get('min_b2b_minus_2plus')
        overall_d = rb['overall'].iloc[0]
        if isinstance(overall_d, str):
            try:
                overall_d = json.loads(overall_d)
            except Exception:
                overall_d = {}
        overall_efg = overall_d.get('efg_pct') if isinstance(overall_d, dict) else None
        b2b_d = rb['b2b'].iloc[0]
        if isinstance(b2b_d, str):
            try:
                b2b_d = json.loads(b2b_d)
            except Exception:
                b2b_d = {}
        b2b_efg = b2b_d.get('efg_pct') if isinstance(b2b_d, dict) else None
        twoplus_d = rb['two_plus'].iloc[0]
        if isinstance(twoplus_d, str):
            try:
                twoplus_d = json.loads(twoplus_d)
            except Exception:
                twoplus_d = {}
        two_plus_efg = twoplus_d.get('efg_pct') if isinstance(twoplus_d, dict) else None

    # Clutch scoring atlas
    cs = clutch_sub[clutch_sub['pid'] == pid]
    clutch_pts_pg = None
    clutch_shots_pg = None
    if len(cs) > 0:
        pbp_clutch_d = cs['pbp_clutch'].iloc[0]
        if isinstance(pbp_clutch_d, str):
            try:
                pbp_clutch_d = json.loads(pbp_clutch_d)
            except Exception:
                pbp_clutch_d = {}
        if isinstance(pbp_clutch_d, dict):
            clutch_pts_pg = pbp_clutch_d.get('clutch_pts_pg')
            clutch_shots_pg = pbp_clutch_d.get('clutch_shots_pg')

    # Player effects b2b
    eff = effects_sub[effects_sub['pid'] == pid]
    b2b_n_eff = int(eff['b2b_n'].iloc[0]) if len(eff) > 0 else None
    b2b_raw_eff = float(eff['b2b_raw'].iloc[0]) if len(eff) > 0 and not pd.isna(eff['b2b_raw'].iloc[0]) else None
    b2b_xfg_eff = float(eff['b2b_xfg'].iloc[0]) if len(eff) > 0 else None
    b2b_use_eff = float(eff['b2b_use'].iloc[0]) if len(eff) > 0 else None
    matchup_sensitivity = float(eff['matchup_sensitivity'].iloc[0]) if len(eff) > 0 else None

    # Playoff load (leak_free)
    pl = playoff_load[(playoff_load['pid'] == pid) & (playoff_load['team'] == team)]
    playoff_gp = int(pl['playoff_gp'].iloc[0]) if len(pl) > 0 else 0
    playoff_mins_total = float(pl['playoff_mins_total'].iloc[0]) if len(pl) > 0 else 0.0
    playoff_mpg_val = float(pl['playoff_mpg'].iloc[0]) if len(pl) > 0 else None

    # Minutes variance (leak_free)
    mv = min_var[(min_var['pid'] == pid) & (min_var['team'] == team)]
    min_std_val = float(mv['min_std'].iloc[0]) if len(mv) > 0 else None
    min_mean_val = float(mv['min_mean'].iloc[0]) if len(mv) > 0 else None
    min_cv_val = float(mv['min_cv'].iloc[0]) if len(mv) > 0 else None
    n_games_total = int(mv['n_games'].iloc[0]) if len(mv) > 0 else 0

    # Reg MPG
    rl = reg_load[(reg_load['pid'] == pid) & (reg_load['team'] == team)]
    reg_mpg_val = float(rl['reg_mpg'].iloc[0]) if len(rl) > 0 else None

    # Playoff vs reg MPG diff
    playoff_mpg_diff = (playoff_mpg_val - reg_mpg_val) if playoff_mpg_val and reg_mpg_val else None

    row = {
        'entity_type': 'player',
        'entity_id': str(pid),
        'entity_name': player_name,
        'team': team,
        'pid': pid,
        'mpg': float(pr_row['mpg']),
        # Physical / schedule (leak_free)
        'age': age,
        'height_in': height_in,
        'exp': exp,
        'age_fatigue_w': age_fatigue_w,  # from player_attributes = physical proxy
        'prime': prime,
        'g4_days_rest': 2,
        'g4_is_b2b': 0,
        # Minutes variance (leak_free: expanding obs pre-G4)
        'min_std': min_std_val,
        'min_mean': min_mean_val,
        'min_cv': min_cv_val,
        'n_games_total': n_games_total,
        'reg_mpg': reg_mpg_val,
        # Playoff load (leak_free: physical count)
        'playoff_gp': playoff_gp,
        'playoff_mins_total': playoff_mins_total,
        'playoff_mpg': playoff_mpg_val,
        'playoff_mpg_diff_vs_reg': playoff_mpg_diff,
        # B2B from player_effects (in_season: season-pooled)
        'b2b_n': b2b_n_eff,
        'b2b_raw': b2b_raw_eff,
        'b2b_xfg_mult': b2b_xfg_eff,
        'b2b_use_mult': b2b_use_eff,
        'matchup_sensitivity': matchup_sensitivity,
        # Rest/B2B from atlas (in_season: season-pooled)
        'overall_efg': overall_efg,
        'b2b_efg': b2b_efg,
        'two_plus_rest_efg': two_plus_efg,
        'efg_b2b_vs_2plus_delta': efg_b2b_delta,
        'min_b2b_vs_2plus_delta': min_b2b_delta,
        # Quarter shape (in_season: season-pooled)
        'q4_vs_early_pts_ratio': q4_vs_early,
        'q4_fade_abs_pts': q4_fade_abs,
        'b2b_q4_pts_delta': b2b_q4_pts_delta,
        'b2b_decay_ratio': b2b_decay_ratio,
        # Clutch scoring (scouting_only: rejected as pregame edge per llm_context_layer)
        'clutch_pts_pg': clutch_pts_pg,
        'clutch_shots_pg': clutch_shots_pg,
        # Role-aware clutch RATING (in_season: derived from season stats)
        'clutch_rating': clutch_rating,
        'int_d_rating': int_d,
        'perim_d_rating': perim_d,
        # Leak flags as JSON sidecar
        '__leak_flags__': json.dumps({
            'age': 'leak_free',
            'height_in': 'leak_free',
            'exp': 'leak_free',
            'age_fatigue_w': 'leak_free',
            'prime': 'leak_free',
            'g4_days_rest': 'leak_free',
            'g4_is_b2b': 'leak_free',
            'min_std': 'leak_free',
            'min_mean': 'leak_free',
            'min_cv': 'leak_free',
            'n_games_total': 'leak_free',
            'reg_mpg': 'leak_free',
            'playoff_gp': 'leak_free',
            'playoff_mins_total': 'leak_free',
            'playoff_mpg': 'leak_free',
            'playoff_mpg_diff_vs_reg': 'leak_free',
            'b2b_n': 'in_season',
            'b2b_raw': 'in_season',
            'b2b_xfg_mult': 'in_season',
            'b2b_use_mult': 'in_season',
            'matchup_sensitivity': 'in_season',
            'overall_efg': 'in_season',
            'b2b_efg': 'in_season',
            'two_plus_rest_efg': 'in_season',
            'efg_b2b_vs_2plus_delta': 'in_season',
            'min_b2b_vs_2plus_delta': 'in_season',
            'q4_vs_early_pts_ratio': 'in_season',
            'q4_fade_abs_pts': 'in_season',
            'b2b_q4_pts_delta': 'in_season',
            'b2b_decay_ratio': 'in_season',
            'clutch_pts_pg': 'scouting_only',
            'clutch_shots_pg': 'scouting_only',
            'clutch_rating': 'in_season',
            'int_d_rating': 'in_season',
            'perim_d_rating': 'in_season',
        })
    }
    player_rows.append(row)

player_df = pd.DataFrame(player_rows)
print('Player rows:', len(player_df))

# ============================================================
# COMBINE AND WRITE
# ============================================================
# Align columns between team and player rows
all_rows = pd.concat([team_df, player_df], ignore_index=True, sort=False)
print('Total rows:', len(all_rows))
print('Columns:', all_rows.columns.tolist())

out_path = 'data/cache/team_system/clutch_fatigue.parquet'
all_rows.to_parquet(out_path, index=False)
print('Written to', out_path)

# Verify readback
check = pd.read_parquet(out_path)
print('Readback shape:', check.shape)
print('Entity types:', check['entity_type'].value_counts().to_dict())
print('Teams covered:', check['team'].value_counts().to_dict())
