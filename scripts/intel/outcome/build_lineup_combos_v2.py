"""
build_lineup_combos_v2.py  --  OUTCOME-IMPACT campaign, lineup-combo artifact (v2)

WHY v2 (vs v1): v1 (build_lineup_combos.py) used CV-behavioral PAIR data -- mostly
1-game samples, no real net rating. This rebuild uses REAL BOX NET-RATING lineup
data from NBA Stats LeagueDashLineups (data/nba/lineups/lineup_splits_<TRI>_<season>.json).

SOURCE & SEASON
---------------
  data/nba/lineups/lineup_splits_<TRI>_2024-25.json  (all 30 teams)
  Each file = a team's tracked 5-man lineups for the 2024-25 regular season with
  real possessions (`poss`), minutes (`min`), and box net rating (`net_rating`,
  off/def rating, etc). The `group_id` field encodes the real NBA player_ids,
  e.g. "-2544-203076-1629060-1630559-1631108-".

  We use 2024-25 (PRIOR SEASON) because only GSW + LAL have a 2025-26 lineup file,
  and those 2025-26 files are a DIFFERENT, thinner schema (10 name-only lineups, no
  `poss`, no player_ids) -- unusable for a 30-team league view. So this artifact is
  explicitly labelled prior-season (season="2024-25").

DERIVING 2-MAN / 3-MAN FROM 5-MAN
---------------------------------
  The source has ONLY 5-man lineups (2000 rows, all lineup_size==5). There are no
  native 2-/3-man records. We derive on-court-together net ratings by:
    - For each team, expand every tracked 5-man lineup into its C(5,2)=10 pairs and
      C(5,3)=10 trios.
    - For each pair/trio, possession-weight the 5-man net_rating across every tracked
      lineup the combo co-appears in, and sum `poss` / `min`.
    - net = sum(net_rating_i * poss_i) / sum(poss_i)   [possessions-weighted]
  This is the standard "lineups they share the floor in" net rating. It is NOT a
  strict on/off (together-vs-apart) differential -- see CAVEATS.

METRIC & UNITS
--------------
  net  = possessions-weighted on-court NET RATING (points per 100 possessions),
         positive = team outscores opponents while the combo is on the floor.
  poss = total possessions the combo shared across tracked 5-man lineups (int).
  min  = total floor minutes the combo shared across tracked 5-man lineups (float).
  THRESHOLD: pairs >= 150 poss, trios >= 150 poss (stated in meta).

LEAK-SAFETY
-----------
  Descriptive, within-season, prior-season aggregate. No prediction, no future leak,
  no betting logic. Pure box-score lineup summary of 2024-25.

OUTPUT
------
  data/cache/intel_outcome/lineup_combos_v2.json
  Schema mirrors v1 so it drops into the fold writer; see SCHEMA string below.
"""
import json
import os
import re
import glob
import itertools
from collections import defaultdict

import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
LINEUP_GLOB = os.path.join(REPO_ROOT, 'data', 'nba', 'lineups', 'lineup_splits_*_2024-25.json')
VAULT_PLAYERS = os.path.join(REPO_ROOT, 'vault', 'Intelligence', 'Players', '*.md')
PROFILE_PARQUET = os.path.join(REPO_ROOT, 'data', 'cache', 'player_profile_features.parquet')
OUTPUT_PATH = os.path.join(REPO_ROOT, 'data', 'cache', 'intel_outcome', 'lineup_combos_v2.json')

SEASON = '2024-25'
PAIR_MIN_POSS = 150
TRIO_MIN_POSS = 150
TOP_N_TEAM_PAIRS = 5      # best/worst pairs per team
TOP_N_TEAM_TRIOS = 5      # best/worst trios per team
TOP_N_PARTNERS = 3        # best/worst partners per player
TOP_N_LEAGUE = 5          # league top/bottom for the report

SCHEMA = (
    "lineup_combos_v2.json: {"
    "meta:{season,source,metric_net,units,pair_min_poss,trio_min_poss,derivation,...}, "
    "by_team:{'<TRI>':{best_pairs:[{players:[id,id],names:[..],net,poss,min,n_lineups}], "
    "worst_pairs:[...], best_trios:[{players:[id,id,id],names:[..],net,poss,min,n_lineups}], "
    "worst_trios:[...]}}, "
    "by_player:{'<pid_str>':{player_name,team,best_partners:[{partner_id,name,net,poss,min}], "
    "worst_partners:[...]}}, "
    "league_best_pairs:[{team,players,names,net,poss,min}], league_worst_pairs:[...]}. "
    "player_id keys are string NBA ids matching vault Players/<pid>_*.md; net in pts/100poss."
)


def build_name_map():
    """id(int) -> full name. vault filenames (preferred) + profile parquet fallback."""
    name_map = {}
    # profile parquet (broad, 850 players)
    if os.path.exists(PROFILE_PARQUET):
        df = pd.read_parquet(PROFILE_PARQUET, columns=['player_id', 'player_name'])
        for pid, nm in zip(df['player_id'], df['player_name']):
            if pd.notna(pid) and isinstance(nm, str) and nm.strip():
                name_map[int(pid)] = nm.strip()
    # vault filenames (preferred -- exact match to vault Players/<pid>_*.md)
    for fp in glob.glob(VAULT_PLAYERS):
        base = os.path.basename(fp)[:-3]
        m = re.match(r'^(\d+)_(.+)$', base)
        if m:
            pid = int(m.group(1))
            nm = ' '.join(w.capitalize() for w in m.group(2).split('_'))
            name_map[pid] = nm  # vault wins ties
    return name_map


def load_lineups():
    """Return list of dicts: {team, ids(sorted tuple), net, poss, min}."""
    rows = []
    abbrev_name = {}  # id -> abbreviated source name (last-resort fallback)
    files = sorted(glob.glob(LINEUP_GLOB))
    for fp in files:
        team = os.path.basename(fp).split('_')[-2]
        with open(fp) as f:
            data = json.load(f)
        for r in data:
            gid = r.get('group_id', '')
            ids = tuple(sorted(int(x) for x in gid.split('-') if x))
            if len(ids) != 5:
                continue
            net = r.get('net_rating')
            poss = r.get('poss')
            mins = r.get('min')
            if net is None or poss is None or not poss:
                continue
            rows.append({'team': team, 'ids': ids, 'net': float(net),
                         'poss': float(poss), 'min': float(mins or 0.0)})
            for pid, nm in zip(ids, r.get('lineup', [])):
                abbrev_name.setdefault(pid, nm)
    return rows, abbrev_name, len(files)


def aggregate(rows, k):
    """Possession-weighted net rating for every k-combo. Returns
    {(team, ids_tuple): {net, poss, min, n_lineups}}."""
    acc = defaultdict(lambda: {'wnet': 0.0, 'poss': 0.0, 'min': 0.0, 'n': 0})
    for r in rows:
        team, ids, net, poss, mins = r['team'], r['ids'], r['net'], r['poss'], r['min']
        for combo in itertools.combinations(ids, k):
            a = acc[(team, combo)]
            a['wnet'] += net * poss
            a['poss'] += poss
            a['min'] += mins
            a['n'] += 1
    out = {}
    for key, a in acc.items():
        if a['poss'] <= 0:
            continue
        out[key] = {
            'net': round(a['wnet'] / a['poss'], 2),
            'poss': int(round(a['poss'])),
            'min': round(a['min'], 1),
            'n_lineups': a['n'],
        }
    return out


def names_for(ids, name_map, abbrev_name):
    res = []
    for pid in ids:
        res.append(name_map.get(pid) or abbrev_name.get(pid) or str(pid))
    return res


def main():
    name_map = build_name_map()
    rows, abbrev_name, n_files = load_lineups()
    print(f"loaded {len(rows)} tracked 5-man lineups across {n_files} team-files")

    pairs = aggregate(rows, 2)
    trios = aggregate(rows, 3)
    pairs = {k: v for k, v in pairs.items() if v['poss'] >= PAIR_MIN_POSS}
    trios = {k: v for k, v in trios.items() if v['poss'] >= TRIO_MIN_POSS}
    print(f"qualifying pairs (>= {PAIR_MIN_POSS} poss): {len(pairs)}")
    print(f"qualifying trios (>= {TRIO_MIN_POSS} poss): {len(trios)}")

    # ---- resolution coverage ----
    all_ids = set()
    for (_, ids) in pairs:
        all_ids.update(ids)
    for (_, ids) in trios:
        all_ids.update(ids)
    resolved = sum(1 for pid in all_ids if pid in name_map)
    res_rate = 100.0 * resolved / len(all_ids) if all_ids else 0.0
    unresolved = sorted(pid for pid in all_ids if pid not in name_map)
    print(f"name->id resolution: {resolved}/{len(all_ids)} = {res_rate:.1f}% (vault+profile map)")
    if unresolved:
        print(f"  unresolved (abbrev fallback used): {unresolved}")

    # ---- by_team ----
    team_pairs = defaultdict(list)
    for (team, ids), v in pairs.items():
        team_pairs[team].append((ids, v))
    team_trios = defaultdict(list)
    for (team, ids), v in trios.items():
        team_trios[team].append((ids, v))

    def pack(ids, v):
        return {
            'players': [int(p) for p in ids],
            'names': names_for(ids, name_map, abbrev_name),
            'net': v['net'], 'poss': v['poss'], 'min': v['min'],
            'n_lineups': v['n_lineups'],
        }

    by_team = {}
    teams = sorted(set([t for (t, _) in pairs] + [t for (t, _) in trios]))
    for team in teams:
        tp = sorted(team_pairs.get(team, []), key=lambda x: x[1]['net'], reverse=True)
        tt = sorted(team_trios.get(team, []), key=lambda x: x[1]['net'], reverse=True)
        by_team[team] = {
            'best_pairs': [pack(ids, v) for ids, v in tp[:TOP_N_TEAM_PAIRS]],
            'worst_pairs': [pack(ids, v) for ids, v in tp[-TOP_N_TEAM_PAIRS:][::-1]] if tp else [],
            'best_trios': [pack(ids, v) for ids, v in tt[:TOP_N_TEAM_TRIOS]],
            'worst_trios': [pack(ids, v) for ids, v in tt[-TOP_N_TEAM_TRIOS:][::-1]] if tt else [],
            'n_qualifying_pairs': len(tp),
            'n_qualifying_trios': len(tt),
        }

    # ---- by_player (partner map, from pairs) ----
    player_partners = defaultdict(list)   # pid -> list of (partner_id, v, team)
    player_team = {}
    for (team, ids), v in pairs.items():
        a, b = ids
        player_partners[a].append((b, v, team))
        player_partners[b].append((a, v, team))
        player_team.setdefault(a, team)
        player_team.setdefault(b, team)

    by_player = {}
    for pid, plist in player_partners.items():
        plist_sorted = sorted(plist, key=lambda x: x[1]['net'], reverse=True)

        def pack_partner(partner_id, v):
            return {
                'partner_id': int(partner_id),
                'name': name_map.get(partner_id) or abbrev_name.get(partner_id) or str(partner_id),
                'net': v['net'], 'poss': v['poss'], 'min': v['min'],
            }

        best = [pack_partner(p, v) for p, v, _ in plist_sorted[:TOP_N_PARTNERS]]
        worst = [pack_partner(p, v) for p, v, _ in plist_sorted[-TOP_N_PARTNERS:][::-1]]
        by_player[str(pid)] = {
            'player_name': name_map.get(pid) or abbrev_name.get(pid) or str(pid),
            'team': player_team.get(pid),
            'best_partners': best,
            'worst_partners': worst,
            'n_partners': len(plist),
        }

    # ---- league extremes ----
    all_pairs_flat = [(team, ids, v) for (team, ids), v in pairs.items()]
    league_sorted = sorted(all_pairs_flat, key=lambda x: x[2]['net'], reverse=True)

    def pack_league(team, ids, v):
        return {
            'team': team,
            'players': [int(p) for p in ids],
            'names': names_for(ids, name_map, abbrev_name),
            'net': v['net'], 'poss': v['poss'], 'min': v['min'],
        }

    league_best = [pack_league(t, i, v) for t, i, v in league_sorted[:TOP_N_LEAGUE]]
    league_worst = [pack_league(t, i, v) for t, i, v in league_sorted[-TOP_N_LEAGUE:][::-1]]

    meta = {
        'generated': pd.Timestamp.utcnow().isoformat(),
        'season': SEASON,
        'season_note': 'PRIOR SEASON. Only GSW+LAL have a 2025-26 lineup file and those '
                       'use a thinner name-only schema with no possessions or player_ids, '
                       'so a 30-team league view requires 2024-25.',
        'source': 'data/nba/lineups/lineup_splits_<TRI>_2024-25.json (NBA Stats '
                  'LeagueDashLineups, 5-man, real box net rating + possessions)',
        'metric_net': 'possessions-weighted on-court NET RATING (points per 100 possessions); '
                      'positive = team outscores opponents while combo is on floor',
        'units': {'net': 'pts per 100 poss', 'poss': 'possessions (int)', 'min': 'floor minutes (float)'},
        'pair_min_poss': PAIR_MIN_POSS,
        'trio_min_poss': TRIO_MIN_POSS,
        'derivation': 'Source has only 5-man lineups. 2-man/3-man net ratings are DERIVED by '
                      'possession-weighting the 5-man net_rating across every tracked lineup the '
                      'combo co-appears in (sum poss/min). This is on-court-together net rating, '
                      'NOT a strict on/off (together-vs-apart) differential.',
        'player_id_format': 'string NBA player_id, matches vault Players/<pid>_*.md',
        'name_resolution': {
            'unique_players': len(all_ids),
            'resolved': resolved,
            'resolution_pct': round(res_rate, 1),
            'unresolved_ids': unresolved,
            'sources': 'vault Players/<pid>_*.md filenames (preferred) + '
                       'data/cache/player_profile_features.parquet fallback',
        },
        'coverage': {
            'teams': len(by_team),
            'players': len(by_player),
            'qualifying_pairs': len(pairs),
            'qualifying_trios': len(trios),
            'tracked_5man_lineups': len(rows),
        },
        'caveats': [
            'Derived pair/trio net rating is weighted over the tracked 5-man lineups the combo '
            'co-appears in -- it captures rotation combinations, not strict shared-floor minutes.',
            'Source only tracks higher-usage 5-man lineups (>=21 poss in raw data); deep-bench '
            'pairs that never logged a tracked lineup are absent.',
            'On-court net (not on/off): a high-net pair may ride a strong supporting cast rather '
            'than the pair itself. Treat as descriptive, not causal.',
            'Prior-season (2024-25): roster/role changes for 2025-26 are not reflected.',
        ],
        'leak_safety': 'Descriptive within-/prior-season box aggregate. No prediction, no future '
                       'information, no betting logic. SCOUTING only.',
        'schema': SCHEMA,
        'supersedes': 'data/cache/intel_outcome/lineup_combos.json (v1, CV-behavioral pair data, '
                      '1-game samples, no real net rating)',
    }

    out = {
        'meta': meta,
        'by_team': by_team,
        'by_player': by_player,
        'league_best_pairs': league_best,
        'league_worst_pairs': league_worst,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nWROTE {OUTPUT_PATH}")
    print(f"  teams={len(by_team)} players={len(by_player)} "
          f"pairs={len(pairs)} trios={len(trios)}")

    # console: league top/bottom 5
    print("\nLEAGUE TOP-5 DUOS (by net, pts/100):")
    for d in league_best:
        print(f"  {d['team']:3s} {d['net']:+6.1f}  poss={d['poss']:4d}  "
              f"{d['names'][0]} + {d['names'][1]}")
    print("LEAGUE BOTTOM-5 DUOS:")
    for d in league_worst:
        print(f"  {d['team']:3s} {d['net']:+6.1f}  poss={d['poss']:4d}  "
              f"{d['names'][0]} + {d['names'][1]}")


if __name__ == '__main__':
    main()
