"""
INT-37: AI Chat Ground Truth Package
=====================================
Converts the 14+ intelligence atlases into queryable Q&A facts
for the CourtVision AI Chat product surface.

Outputs:
  data/intelligence/ai_chat_facts.json   -- pre-computed facts (top-25 players + 30 teams)
  data/intelligence/ai_chat_index.json   -- query_pattern -> atlas + lookup key

Usage:
  python scripts/build_ai_chat_corpus.py
"""

import json
import os
import sys
import re
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(r'C:\Users\neelj\nba-ai-system')
INTEL = BASE / 'data' / 'intelligence'
INTEL.mkdir(parents=True, exist_ok=True)

OUT_FACTS = INTEL / 'ai_chat_facts.json'
OUT_INDEX = INTEL / 'ai_chat_index.json'

# ---------------------------------------------------------------------------
# Atlas registry
# ---------------------------------------------------------------------------
ATLAS_REGISTRY = {
    'player_fingerprints':          INTEL / 'player_fingerprints.parquet',
    'similar_neighbors':            INTEL / 'similar_neighbors.json',
    'matchup_deviations':           INTEL / 'matchup_deviations.parquet',
    'opponent_imposed_profiles':    INTEL / 'opponent_imposed_profiles.json',
    'anomaly_log':                  INTEL / 'anomaly_log.parquet',
    'streak_signatures_summary':    INTEL / 'streak_signatures_summary.json',
    'rolling_trends':               INTEL / 'rolling_trends.parquet',
    'active_trend_signals':         INTEL / 'active_trend_signals.json',
    'current_form_profiles':        INTEL / 'current_form_profiles.parquet',
    'form_vs_baseline_deltas':      INTEL / 'form_vs_baseline_deltas.json',
    'defensive_schemes':            INTEL / 'defensive_schemes.parquet',
    'archetype_scheme_advantages':  INTEL / 'archetype_scheme_advantages.json',
    'trade_profile_shifts':         INTEL / 'trade_profile_shifts.parquet',
    'ingame_momentum':              INTEL / 'ingame_momentum.parquet',
    'lineup_chemistry':             INTEL / 'lineup_chemistry.parquet',
    'lineup_signatures':            INTEL / 'lineup_signatures.json',
    'similarity_matrix':            INTEL / 'similarity_matrix.parquet',
    'game_similarity_index':        INTEL / 'game_similarity_index.parquet',
    'game_neighbors':               INTEL / 'game_neighbors.json',
    'per_player_confidence':        INTEL / 'per_player_confidence.parquet',
    'player_development':           INTEL / 'player_development.parquet',
    'breakout_signals':             INTEL / 'breakout_signals.json',
    'archetype_scheme_interactions':INTEL / 'archetype_scheme_interactions.parquet',
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v, ndigits=3):
    """Round float, return None for NaN/None."""
    if v is None:
        return None
    try:
        fv = float(v)
        return None if (np.isnan(fv) or np.isinf(fv)) else round(fv, ndigits)
    except (TypeError, ValueError):
        return None


def _pid_str(pid_val) -> str:
    """Normalize player_id to integer string (strips .0 from floats)."""
    try:
        return str(int(float(pid_val)))
    except (TypeError, ValueError):
        return str(pid_val)


def _load_parquet(key: str) -> pd.DataFrame | None:
    path = ATLAS_REGISTRY[key]
    if not path.exists():
        print(f"  [SKIP] {key} not found at {path}")
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        print(f"  [ERROR] loading {key}: {e}")
        return None


def _load_json(key: str) -> Any:
    path = ATLAS_REGISTRY[key]
    if not path.exists():
        print(f"  [SKIP] {key} not found at {path}")
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  [ERROR] loading {key}: {e}")
        return None


def _pct_label(v):
    """Format a fraction as '12.3%'."""
    if v is None:
        return 'N/A'
    return f"{v * 100:.1f}%"


def _z_label(z):
    if z is None:
        return 'neutral'
    z = float(z)
    if z >= 2.0:
        return f"+{z:.2f}σ (unusually HIGH)"
    elif z <= -2.0:
        return f"{z:.2f}σ (unusually LOW)"
    elif z >= 1.0:
        return f"+{z:.2f}σ (above average)"
    elif z <= -1.0:
        return f"{z:.2f}σ (below average)"
    else:
        return f"{z:.2f}σ (typical)"


# ---------------------------------------------------------------------------
# Step 1 — Load all atlases
# ---------------------------------------------------------------------------
print("=== Step 1: Loading atlases ===")

fp_df      = _load_parquet('player_fingerprints')
sn_data    = _load_json('similar_neighbors')
md_df      = _load_parquet('matchup_deviations')
oip_data   = _load_json('opponent_imposed_profiles')
al_df      = _load_parquet('anomaly_log')
sss_data   = _load_json('streak_signatures_summary')
rt_df      = _load_parquet('rolling_trends')
ats_data   = _load_json('active_trend_signals')
cfp_df     = _load_parquet('current_form_profiles')
fvb_data   = _load_json('form_vs_baseline_deltas')
ds_df      = _load_parquet('defensive_schemes')
asa_data   = _load_json('archetype_scheme_advantages')
tps_df     = _load_parquet('trade_profile_shifts')
im_df      = _load_parquet('ingame_momentum')
lc_df      = _load_parquet('lineup_chemistry')
ppc_df     = _load_parquet('per_player_confidence')
pd_df      = _load_parquet('player_development')
bs_data    = _load_json('breakout_signals')
asi_df     = _load_parquet('archetype_scheme_interactions')

loaded = [k for k, v in ATLAS_REGISTRY.items() if v.exists()]
print(f"  Loaded {len(loaded)}/{len(ATLAS_REGISTRY)} atlases\n")

# ---------------------------------------------------------------------------
# Step 2 — Build player name resolver
# ---------------------------------------------------------------------------
print("=== Step 2: Building name resolver ===")

# Primary: player_fingerprints index (player_id -> name)
id_to_name: dict[str, str] = {}
name_to_id: dict[str, str] = {}

if fp_df is not None:
    for pid, row in fp_df.iterrows():
        pname = str(row.get('player_name', '') or '')
        if pname:
            id_to_name[str(pid)] = pname
            name_to_id[pname.lower()] = str(pid)

# Also from per_player_confidence for broader coverage
if ppc_df is not None:
    for _, row in ppc_df.iterrows():
        pid = str(int(row['player_id'])) if pd.notna(row.get('player_id')) else None
        pname = str(row.get('player_name', '') or '')
        if pid and pname:
            id_to_name.setdefault(pid, pname)
            name_to_id.setdefault(pname.lower(), pid)

print(f"  Name resolver: {len(name_to_id)} players\n")


def resolve_player(name: str) -> tuple[str | None, str | None]:
    """Returns (player_id, canonical_name) or (None, None)."""
    key = name.lower().strip()
    if key in name_to_id:
        pid = name_to_id[key]
        return pid, id_to_name.get(pid, name)
    # partial match
    for k, pid in name_to_id.items():
        if key in k or k in key:
            return pid, id_to_name.get(pid, k)
    return None, None


# ---------------------------------------------------------------------------
# Step 3 — Pick top 25 players by CV game count
# ---------------------------------------------------------------------------
print("=== Step 3: Selecting top 25 players ===")

if fp_df is not None:
    top25_ids = fp_df.sort_values('n_cv_games', ascending=False).head(25).index.astype(str).tolist()
    top25_names = [id_to_name.get(pid, f'ID:{pid}') for pid in top25_ids]
    print(f"  Top 25: {', '.join(top25_names[:5])} ...")
else:
    top25_ids = []
    top25_names = []
print()

# ---------------------------------------------------------------------------
# Helper: build player fact bundle
# ---------------------------------------------------------------------------

def _build_player_fact(player_id: str, player_name: str) -> dict:
    fact = {
        'player_id': player_id,
        'player_name': player_name,
    }

    # -- Fingerprint --
    if fp_df is not None and player_id in fp_df.index.astype(str):
        row = fp_df.loc[fp_df.index.astype(str) == player_id].iloc[0]
        fact['fingerprint'] = {
            'archetype': row.get('archetype_name', 'Unknown'),
            'n_cv_games': int(row.get('n_cv_games', 0)),
            'paint_dwell_pct': _safe_float(row.get('paint_dwell_pct')),
            'avg_shot_distance': _safe_float(row.get('avg_shot_distance')),
            'touches_per_game': _safe_float(row.get('touches_per_game')),
            'potential_assists': _safe_float(row.get('potential_assists')),
            'play_type_isolation_pct': _safe_float(row.get('play_type_isolation_pct')),
            'play_type_transition_pct': _safe_float(row.get('play_type_transition_pct')),
            'contested_shot_rate': _safe_float(row.get('contested_shot_rate')),
            'avg_defender_distance': _safe_float(row.get('avg_defender_distance')),
            'catch_shoot_pct': _safe_float(row.get('catch_shoot_pct')),
            'pca_x': _safe_float(row.get('pca_x')),
            'pca_y': _safe_float(row.get('pca_y')),
        }
    else:
        fact['fingerprint'] = None

    # -- Similar players --
    if sn_data is not None:
        # Keys are "player_id_Name" format
        sn_key = next((k for k in sn_data if k.startswith(player_id + '_')), None)
        if sn_key:
            entry = sn_data[sn_key]
            top10 = entry.get('top_10_euclidean', [])
            fact['similar_players'] = [
                {
                    'name': n.get('name', f"ID:{n.get('player_id','')}"),
                    'archetype': n.get('archetype', ''),
                    'distance': _safe_float(n.get('distance')),
                }
                for n in top10[:5]
            ]
        else:
            fact['similar_players'] = []
    else:
        fact['similar_players'] = []

    # -- Current form (INT-29) --
    form_record = None
    if cfp_df is not None:
        mask = cfp_df['player_id'].apply(_pid_str) == player_id
        if mask.any():
            form_record = cfp_df[mask].iloc[0]

    if form_record is not None:
        fact['current_form'] = {
            'trend_tag': form_record.get('trend_tag', 'UNKNOWN'),
            'max_abs_z': _safe_float(form_record.get('max_abs_z')),
            'top_driver': form_record.get('top_driver', ''),
            'int18_tag': form_record.get('int18_tag'),
            'int18_disagreement': form_record.get('int18_disagreement'),
            'latest_game_date': str(form_record.get('latest_game_date', '')),
            'n_cv_games': int(form_record.get('n_cv_games', 0)) if pd.notna(form_record.get('n_cv_games')) else 0,
            'paint_dwell_pct_z': _safe_float(form_record.get('paint_dwell_pct_z')),
            'near_basket_pct_z': _safe_float(form_record.get('near_basket_pct_z')),
            'fatigue_score_z': _safe_float(form_record.get('fatigue_score_z')),
            'defender_dist_z': _safe_float(form_record.get('defender_dist_z')),
            'minutes_proxy_z': _safe_float(form_record.get('minutes_proxy_z')),
        }
    else:
        fact['current_form'] = None

    # -- Rolling trend (INT-18) --
    trend_record = None
    if rt_df is not None:
        mask = rt_df['player_id'].apply(_pid_str) == player_id
        if mask.any():
            trend_record = rt_df[mask].iloc[0]

    if trend_record is not None:
        try:
            drivers = json.loads(trend_record['top_3_drivers']) if isinstance(trend_record['top_3_drivers'], str) else trend_record['top_3_drivers']
        except Exception:
            drivers = []
        fact['rolling_trend'] = {
            'trend_tag': trend_record.get('trend_tag', 'UNKNOWN'),
            'max_abs_z': _safe_float(trend_record.get('max_abs_z')),
            'n_games_recent': int(trend_record.get('n_games_recent', 0)),
            'n_games_prior': int(trend_record.get('n_games_prior', 0)),
            'latest_game_date': str(trend_record.get('latest_game_date', '')),
            'top_3_drivers': [
                {
                    'feature': d.get('feature_label', d.get('feature', '')),
                    'z': _safe_float(d.get('z')),
                    'recent_mean': _safe_float(d.get('recent_mean')),
                    'prior_mean': _safe_float(d.get('prior_mean')),
                }
                for d in (drivers if isinstance(drivers, list) else [])[:3]
            ],
        }
    else:
        fact['rolling_trend'] = None

    # -- Anomaly history --
    if al_df is not None:
        player_al = al_df[al_df['player_id'].apply(_pid_str) == player_id]
        if len(player_al) > 0:
            try:
                all_features = []
                for feat_str in player_al['top_3_features']:
                    try:
                        feats = json.loads(feat_str) if isinstance(feat_str, str) else feat_str
                        for f in feats:
                            all_features.append(f.get('feature', ''))
                    except Exception:
                        pass
                from collections import Counter
                most_common = Counter(all_features).most_common(1)
                most_common_feat = most_common[0][0] if most_common else 'N/A'
            except Exception:
                most_common_feat = 'N/A'

            fact['anomaly_history'] = {
                'n_anomalous_games': len(player_al),
                'max_z_ever': _safe_float(player_al['max_abs_z'].max()),
                'most_common_anomaly_feature': most_common_feat,
                'avg_anomalous_features_per_game': _safe_float(player_al['n_anomalous_features'].mean()),
            }
        else:
            fact['anomaly_history'] = {'n_anomalous_games': 0}
    else:
        fact['anomaly_history'] = None

    # -- Per-player confidence / Kelly mult --
    if ppc_df is not None:
        mask = ppc_df['player_id'].apply(_pid_str) == player_id
        if mask.any():
            conf_row = ppc_df[mask].iloc[0]
            fact['confidence'] = {
                'cv_volatility': _safe_float(conf_row.get('cv_volatility_mean')),
                'segment': str(conf_row.get('segment', '')),
                'overall_confidence_mult': _safe_float(conf_row.get('overall_confidence_mult')),
                'by_stat': {
                    'pts': {'cv': _safe_float(conf_row.get('pts_cv')), 'kelly_mult': _safe_float(conf_row.get('pts_confidence_mult'))},
                    'reb': {'cv': _safe_float(conf_row.get('reb_cv')), 'kelly_mult': _safe_float(conf_row.get('reb_confidence_mult'))},
                    'ast': {'cv': _safe_float(conf_row.get('ast_cv')), 'kelly_mult': _safe_float(conf_row.get('ast_confidence_mult'))},
                    'fg3m': {'cv': _safe_float(conf_row.get('fg3m_cv')), 'kelly_mult': _safe_float(conf_row.get('fg3m_confidence_mult'))},
                    'stl': {'cv': _safe_float(conf_row.get('stl_cv')), 'kelly_mult': _safe_float(conf_row.get('stl_confidence_mult'))},
                    'blk': {'cv': _safe_float(conf_row.get('blk_cv')), 'kelly_mult': _safe_float(conf_row.get('blk_confidence_mult'))},
                    'tov': {'cv': _safe_float(conf_row.get('tov_cv')), 'kelly_mult': _safe_float(conf_row.get('tov_confidence_mult'))},
                },
            }
        else:
            fact['confidence'] = None
    else:
        fact['confidence'] = None

    # -- Season development --
    if pd_df is not None:
        mask = pd_df['player_id'].apply(_pid_str) == player_id
        if mask.any():
            dev_row = pd_df[mask].iloc[0]
            fact['season_evolution'] = {
                'dev_tag': str(dev_row.get('dev_tag', '')),
                'dev_score': _safe_float(dev_row.get('dev_score')),
                'season1': str(dev_row.get('season1', '')),
                'season2': str(dev_row.get('season2', '')),
                'top_shift': _get_top_dev_shift(dev_row),
            }
        else:
            fact['season_evolution'] = None
    else:
        fact['season_evolution'] = None

    # -- Matchup highlights (notable deviations vs any opponent) --
    if md_df is not None:
        player_md = md_df[(md_df['player_id'].apply(_pid_str) == player_id) & (md_df['notable_flag'] == True)]
        highlights = []
        for _, mrow in player_md.iterrows():
            dev_flags = str(mrow.get('deviation_flags', ''))
            highlights.append({
                'opp': mrow.get('opp_team', ''),
                'n_games': int(mrow.get('n_games_vs_opp', 0)),
                'max_abs_z': _safe_float(mrow.get('max_abs_z')),
                'deviation_flags': dev_flags,
            })
        highlights.sort(key=lambda x: x['max_abs_z'] or 0, reverse=True)
        fact['matchup_highlights'] = highlights[:5]
    else:
        fact['matchup_highlights'] = []

    # -- Trade profile shift --
    if tps_df is not None:
        player_tps = tps_df[(tps_df['player_id'].apply(_pid_str) == player_id) & (tps_df['reliable'] == True)]
        if len(player_tps) > 0:
            trow = player_tps.sort_values('max_shift_z', ascending=False).iloc[0]
            try:
                top3 = json.loads(trow['top_3_shifted_features']) if isinstance(trow['top_3_shifted_features'], str) else trow['top_3_shifted_features']
            except Exception:
                top3 = []
            fact['trade_shift'] = {
                'from_team': str(trow.get('from_team', '')),
                'to_team': str(trow.get('to_team', '')),
                'max_shift_z': _safe_float(trow.get('max_shift_z')),
                'top_shifted_features': top3,
                'n_pre_games': int(trow.get('n_pre_games', 0)),
                'n_post_games': int(trow.get('n_post_games', 0)),
            }
        else:
            fact['trade_shift'] = None
    else:
        fact['trade_shift'] = None

    return fact


def _get_top_dev_shift(row) -> dict | None:
    best_z = 0
    best_feat = None
    for col in row.index:
        if col.startswith('z_') and pd.notna(row[col]):
            try:
                z = float(row[col])
                if abs(z) > abs(best_z):
                    best_z = z
                    best_feat = col[2:]  # strip 'z_'
            except (TypeError, ValueError):
                pass
    if best_feat:
        return {'feature': best_feat, 'z': round(best_z, 3)}
    return None


# ---------------------------------------------------------------------------
# Step 4 — Build team fact bundle
# ---------------------------------------------------------------------------

def _build_team_fact(team_abbrev: str) -> dict:
    fact = {'team': team_abbrev}

    # -- Defensive scheme --
    if ds_df is not None:
        mask = ds_df['team'] == team_abbrev
        if mask.any():
            drow = ds_df[mask].iloc[0]
            fact['defensive_scheme'] = {
                'primary_tag': str(drow.get('dominant_tag', '')),
                'all_tags': str(drow.get('all_tags', '')).split('|'),
                'confidence': str(drow.get('confidence', '')),
                'n_opposing_player_games': int(drow.get('n_opposing_player_games', 0)),
                'axis_scores': {
                    'drop_score': _safe_float(drow.get('drop_score')),
                    'paint_protection': _safe_float(drow.get('paint_protection_score')),
                    'perimeter_denial': _safe_float(drow.get('perimeter_denial_score')),
                    'pace_control': _safe_float(drow.get('pace_control_score')),
                    'iso_force': _safe_float(drow.get('iso_force_score')),
                    'closeout': _safe_float(drow.get('closeout_score')),
                },
            }
        else:
            fact['defensive_scheme'] = None
    else:
        fact['defensive_scheme'] = None

    # -- Opponent-imposed profile --
    if oip_data is not None and team_abbrev in oip_data:
        entry = oip_data[team_abbrev]
        devs = entry.get('imposed_deviations', {})
        # Sort by absolute z (already z-scores)
        sorted_devs = sorted(devs.items(), key=lambda x: abs(x[1]), reverse=True)
        fact['imposed_on_opponents'] = {
            'n_player_games': entry.get('n_player_games_observed', 0),
            'top_5_deviations': [
                {'feature': k, 'z': _safe_float(v), 'direction': 'INCREASES' if v > 0 else 'DECREASES'}
                for k, v in sorted_devs[:5]
            ],
            'all_deviations': {k: _safe_float(v) for k, v in devs.items()},
        }
    else:
        fact['imposed_on_opponents'] = None

    # -- Most affected opposing players --
    if md_df is not None:
        team_md = md_df[(md_df['opp_team'] == team_abbrev) & (md_df['notable_flag'] == True)]
        affected = []
        for _, mrow in team_md.iterrows():
            affected.append({
                'player': mrow.get('player_name', ''),
                'max_abs_z': _safe_float(mrow.get('max_abs_z')),
                'deviation_flags': str(mrow.get('deviation_flags', '')),
            })
        affected.sort(key=lambda x: x['max_abs_z'] or 0, reverse=True)
        fact['most_affected_opponents'] = affected[:10]
    else:
        fact['most_affected_opponents'] = []

    return fact


# ---------------------------------------------------------------------------
# Step 5 — Build global trend facts
# ---------------------------------------------------------------------------

def _build_global_trends() -> dict:
    out = {}

    # Active trend signals
    if ats_data is not None:
        signals = ats_data.get('signals', [])
        hot = [s for s in signals if s.get('trend_tag') in ('HOT_BREAKOUT', 'HEATING_UP')]
        cold = [s for s in signals if s.get('trend_tag') in ('COLD_STREAK', 'COOLING_DOWN')]
        out['active_hot'] = [
            {
                'player': s['player_name'],
                'tag': s['trend_tag'],
                'max_z': _safe_float(s.get('max_abs_z')),
                'n_games_recent': s.get('n_games_recent', 0),
                'latest_date': s.get('latest_game_date', ''),
                'top_drivers': [d.get('feature_label', d.get('feature', '')) for d in s.get('hot_drivers', [])[:3]],
            }
            for s in hot[:10]
        ]
        out['active_cold'] = [
            {
                'player': s['player_name'],
                'tag': s['trend_tag'],
                'max_z': _safe_float(s.get('max_abs_z')),
            }
            for s in cold[:10]
        ]
        out['generated'] = ats_data.get('generated', '')

    # Breakout signals
    if bs_data is not None:
        breakouts = bs_data.get('breakouts', [])
        declines = bs_data.get('declines', [])
        role_shifts = bs_data.get('role_shifts', [])
        out['breakouts'] = [
            {
                'player': b['name'],
                'score': _safe_float(b.get('score')),
                'top_shift': b.get('top_shift', {}),
            }
            for b in breakouts[:10]
        ]
        out['declines'] = [
            {
                'player': d['name'],
                'score': _safe_float(d.get('score')),
                'top_shift': d.get('top_shift', {}),
            }
            for d in declines[:10]
        ]
        out['role_shifts'] = [
            {
                'player': r['name'],
                'score': _safe_float(r.get('score')),
                'top_shift': r.get('top_shift', {}),
            }
            for r in role_shifts[:10]
        ]

    # Volatility ranking from anomaly_log
    if al_df is not None:
        vol_rank = (
            al_df.groupby(['player_id', 'player_name'])['max_abs_z']
            .agg(['count', 'mean', 'max'])
            .rename(columns={'count': 'n_anomalies', 'mean': 'avg_z', 'max': 'max_z'})
            .sort_values('n_anomalies', ascending=False)
        )
        try:
            out['most_volatile_players'] = [
                {
                    'player': idx[1],
                    'player_id': str(idx[0]),
                    'n_anomalous_games': int(row['n_anomalies']),
                    'avg_z': _safe_float(row['avg_z']),
                    'max_z': _safe_float(row['max_z']),
                }
                for idx, row in vol_rank.head(10).iterrows()
            ]
        except Exception:
            out['most_volatile_players'] = []

    # Archetype-scheme advantages summary
    if asa_data is not None:
        out['archetype_scheme_advantages'] = {}
        for stat, v in asa_data.items():
            adv_list = v.get('advantages', [])
            out['archetype_scheme_advantages'][stat] = [
                {
                    'archetype': a['archetype'],
                    'scheme': a['scheme'],
                    'recommendation': a.get('recommendation', ''),
                    'mean_dev': _safe_float(a.get('mean_dev')),
                    'n_games': a.get('n_games', 0),
                }
                for a in adv_list
            ]

    return out


# ---------------------------------------------------------------------------
# Step 6 — Assemble all facts
# ---------------------------------------------------------------------------
print("=== Step 4: Pre-computing player facts (top 25) ===")
player_facts = {}
for pid, pname in zip(top25_ids, top25_names):
    print(f"  Building facts for {pname} ({pid}) ...")
    player_facts[pname] = _build_player_fact(pid, pname)

print(f"\n=== Step 5: Pre-computing team facts (30 teams) ===")
# Get all teams from defensive_schemes
if ds_df is not None:
    all_teams = sorted(ds_df['team'].unique().tolist())
else:
    all_teams = ['ATL','BKN','BOS','CHA','CHI','CLE','DAL','DEN','DET','GSW',
                 'HOU','IND','LAC','LAL','MEM','MIA','MIL','MIN','NOP','NYK',
                 'OKC','ORL','PHI','PHX','POR','SAC','SAS','TOR','UTA','WAS']

team_facts = {}
for team in all_teams:
    print(f"  Building facts for {team} ...")
    team_facts[team] = _build_team_fact(team)

print(f"\n=== Step 6: Building global trend facts ===")
global_facts = _build_global_trends()

# Assemble final facts document
all_facts = {
    'meta': {
        'generated_at': pd.Timestamp.now().isoformat(),
        'n_players': len(player_facts),
        'n_teams': len(team_facts),
        'atlases_loaded': loaded,
        'n_atlases_loaded': len(loaded),
    },
    'players': player_facts,
    'teams': team_facts,
    'global_trends': global_facts,
}

print(f"\n=== Writing {OUT_FACTS} ===")
with open(OUT_FACTS, 'w', encoding='utf-8') as f:
    json.dump(all_facts, f, indent=2, default=str)
print(f"  Written: {OUT_FACTS}")

# ---------------------------------------------------------------------------
# Step 7 — Build query index
# ---------------------------------------------------------------------------
print(f"\n=== Building query index ===")

QUERY_INDEX = {
    'player_profile': {
        'description': "What is [player]'s CV profile / archetype / fingerprint?",
        'example_queries': [
            "What's Stephen Curry's CV profile?",
            "What archetype is Jayson Tatum?",
            "Give me the fingerprint for Damian Lillard",
        ],
        'keywords': ['profile', 'archetype', 'fingerprint', 'cv profile', 'what type'],
        'primary_atlas': 'player_fingerprints',
        'secondary_atlases': ['per_player_confidence'],
        'lookup_key': 'player_id',
        'facts_path': 'players[NAME].fingerprint',
        'pre_computed_for': 'top-25 by CV games',
    },
    'player_similarity': {
        'description': "Who plays like [player]? / Find players similar to [player]",
        'example_queries': [
            "Who plays like Wemby?",
            "Who's similar to Jayson Tatum?",
            "Find players similar to Damian Lillard",
        ],
        'keywords': ['plays like', 'similar to', 'comp', 'comparable', 'reminds me of', 'who else'],
        'primary_atlas': 'similar_neighbors',
        'secondary_atlases': ['player_fingerprints', 'similarity_matrix'],
        'lookup_key': 'player_id',
        'facts_path': 'players[NAME].similar_players',
        'pre_computed_for': 'top-25 by CV games',
    },
    'player_trend': {
        'description': "Is [player] trending hot or cold? / What's [player]'s recent CV form?",
        'example_queries': [
            "Is LeBron hot or cold right now?",
            "What's Tatum's trend?",
            "Is Damian Lillard in a breakout?",
        ],
        'keywords': ['trending', 'hot', 'cold', 'streak', 'form', 'recent', 'breakout', 'heating', 'cooling'],
        'primary_atlas': 'active_trend_signals',
        'secondary_atlases': ['rolling_trends', 'current_form_profiles', 'form_vs_baseline_deltas'],
        'lookup_key': 'player_name',
        'facts_path': 'players[NAME].current_form + players[NAME].rolling_trend',
        'pre_computed_for': 'top-25 by CV games',
    },
    'player_anomaly': {
        'description': "What's [player]'s anomaly history? / Has [player] had any weird CV games?",
        'example_queries': [
            "What's Jalen Green's anomaly history?",
            "Has Tatum had any anomalous CV games?",
            "What was unusual about Curry's last game?",
        ],
        'keywords': ['anomaly', 'anomalous', 'weird', 'unusual', 'outlier', 'unexpected', 'strange game'],
        'primary_atlas': 'anomaly_log',
        'secondary_atlases': ['player_fingerprints'],
        'lookup_key': 'player_id',
        'facts_path': 'players[NAME].anomaly_history',
        'pre_computed_for': 'top-25 by CV games',
    },
    'player_confidence': {
        'description': "How confident should I be betting [player] [stat]? / What's [player]'s Kelly multiplier?",
        'example_queries': [
            "How confident should I be betting Stephen Curry PTS?",
            "What's the recommended Kelly multiplier for Damian Lillard?",
            "Is Tatum a reliable bet for assists?",
        ],
        'keywords': ['confidence', 'kelly', 'reliable', 'bet', 'risk', 'volatile', 'consistent'],
        'primary_atlas': 'per_player_confidence',
        'secondary_atlases': ['player_fingerprints'],
        'lookup_key': 'player_id',
        'facts_path': 'players[NAME].confidence',
        'pre_computed_for': 'top-25 by CV games',
    },
    'player_matchup': {
        'description': "How will [player] play vs [team]? / What does [team] do to [player]'s CV?",
        'example_queries': [
            "How will Tatum play vs MEM?",
            "What does BOS do to Jayson Tatum's game?",
            "How has Curry performed against the Lakers historically?",
        ],
        'keywords': ['vs', 'against', 'matchup', 'face', 'opponent', 'when playing'],
        'primary_atlas': 'matchup_deviations',
        'secondary_atlases': ['archetype_scheme_interactions', 'current_form_profiles', 'opponent_imposed_profiles'],
        'lookup_key': '(player_id, opp_team)',
        'facts_path': 'players[NAME].matchup_highlights + teams[TEAM].imposed_on_opponents',
        'pre_computed_for': 'notable matchups only (notable_flag=True)',
    },
    'player_archetype_vs_scheme': {
        'description': "How does [player]'s archetype interact with [team]'s scheme?",
        'example_queries': [
            "How does Curry's Perimeter Shooter archetype do vs SWITCH HEAVY defenses?",
            "Which archetypes thrive vs PAINT-FIRST DEFENSE?",
        ],
        'keywords': ['archetype', 'scheme', 'interaction', 'advantage', 'exploit'],
        'primary_atlas': 'archetype_scheme_advantages',
        'secondary_atlases': ['archetype_scheme_interactions', 'defensive_schemes', 'player_fingerprints'],
        'lookup_key': '(archetype_name, scheme_name)',
        'facts_path': 'global_trends.archetype_scheme_advantages',
        'pre_computed_for': 'all archetype-scheme combos',
    },
    'team_scheme': {
        'description': "What's [team]'s defensive scheme? / How does [team] defend?",
        'example_queries': [
            "What's BOS's defensive scheme?",
            "How does MEM defend?",
            "What scheme does the Celtics run on defense?",
        ],
        'keywords': ['defensive scheme', 'defense', 'scheme', 'how does [team] defend', 'switches', 'drops'],
        'primary_atlas': 'defensive_schemes',
        'secondary_atlases': [],
        'lookup_key': 'team_abbrev',
        'facts_path': 'teams[TEAM].defensive_scheme',
        'pre_computed_for': 'all 30 teams',
    },
    'team_impact': {
        'description': "What does [team] do to opposing players' CV? / Who does [team] hurt most?",
        'example_queries': [
            "What does BOS do to opposing players' CV?",
            "Who is most affected by Memphis's defense?",
            "Which players get disrupted most by Golden State?",
        ],
        'keywords': ['what does [team] do', 'impact on', 'affect', 'hurt', 'disrupt', 'opposing players'],
        'primary_atlas': 'opponent_imposed_profiles',
        'secondary_atlases': ['matchup_deviations'],
        'lookup_key': 'team_abbrev',
        'facts_path': 'teams[TEAM].imposed_on_opponents + teams[TEAM].most_affected_opponents',
        'pre_computed_for': 'all 30 teams',
    },
    'who_is_hot': {
        'description': "Who's hot right now? / Who's breaking out this month?",
        'example_queries': [
            "Who's hot right now?",
            "Who's breaking out this month?",
            "Which players have the best CV trend signals?",
        ],
        'keywords': ["who's hot", "who is hot", "breaking out", "trending up", "top trends", "rising"],
        'primary_atlas': 'active_trend_signals',
        'secondary_atlases': ['breakout_signals', 'rolling_trends'],
        'lookup_key': 'N/A (global query)',
        'facts_path': 'global_trends.active_hot + global_trends.breakouts',
        'pre_computed_for': 'all players with CV coverage',
    },
    'who_is_volatile': {
        'description': "Who has the most volatile CV signal? / Who are the riskiest bets?",
        'example_queries': [
            "Who has the most volatile CV signal?",
            "Which players are the riskiest bets based on CV?",
            "Who shows up most in the anomaly log?",
        ],
        'keywords': ['volatile', 'risky', 'inconsistent', 'unpredictable', 'anomaly count', 'most anomalies'],
        'primary_atlas': 'anomaly_log',
        'secondary_atlases': ['per_player_confidence'],
        'lookup_key': 'N/A (global query)',
        'facts_path': 'global_trends.most_volatile_players',
        'pre_computed_for': 'all players in anomaly_log',
    },
    'season_development': {
        'description': "Which players shifted their CV profile most season-over-season?",
        'example_queries': [
            "Which players' season-over-season profile shifted most?",
            "Who developed the most between last season and this one?",
            "Show me players in decline based on CV",
        ],
        'keywords': ['season-over-season', 'development', 'changed', 'evolved', 'improved', 'declined', 'breakout'],
        'primary_atlas': 'player_development',
        'secondary_atlases': ['breakout_signals'],
        'lookup_key': 'player_id OR global',
        'facts_path': 'players[NAME].season_evolution + global_trends.breakouts',
        'pre_computed_for': 'top-25 players + global_trends',
    },
    'trade_impact': {
        'description': "How did [player]'s trade affect their CV profile?",
        'example_queries': [
            "How did Anthony Black's trade affect his game?",
            "Did Jeremiah Fears' role change after the trade?",
        ],
        'keywords': ['trade', 'traded', 'move', 'new team', 'role change', 'after joining'],
        'primary_atlas': 'trade_profile_shifts',
        'secondary_atlases': ['player_fingerprints', 'current_form_profiles'],
        'lookup_key': 'player_id',
        'facts_path': 'players[NAME].trade_shift',
        'pre_computed_for': 'top-25 players (when applicable)',
    },
    'game_comp': {
        'description': "What's the historical comp for tonight's [player] vs [team] game?",
        'example_queries': [
            "What's the historical comp for Tatum vs MEM tonight?",
            "Find past games similar to Curry's upcoming matchup",
        ],
        'keywords': ['historical comp', 'similar game', 'comparable game', "tonight's game", 'game neighbor'],
        'primary_atlas': 'game_similarity_index',
        'secondary_atlases': ['game_neighbors'],
        'lookup_key': '(player_id, game_id)',
        'facts_path': 'live atlas query required (game_similarity_index)',
        'pre_computed_for': 'requires live game_id lookup',
    },
}

print(f"  Index: {len(QUERY_INDEX)} query patterns")

print(f"\n=== Writing {OUT_INDEX} ===")
with open(OUT_INDEX, 'w', encoding='utf-8') as f:
    json.dump(QUERY_INDEX, f, indent=2)
print(f"  Written: {OUT_INDEX}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"""
=== INT-37 AI Chat Corpus Build Complete ===
Players pre-computed : {len(player_facts)}
Teams pre-computed   : {len(team_facts)}
Query patterns       : {len(QUERY_INDEX)}
Atlases loaded       : {len(loaded)}/{len(ATLAS_REGISTRY)}

Output files:
  {OUT_FACTS}
  {OUT_INDEX}
""")
