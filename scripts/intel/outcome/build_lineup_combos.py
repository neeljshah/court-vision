"""
build_lineup_combos.py
======================
Compute 2-man and 3-man lineup combination chemistry for each team,
driving from CV-derived pair_chemistry and lineup_chemistry parquets.

SOURCES
-------
- data/intelligence/pair_chemistry.parquet       → 2-man "together vs apart" CV swing
- data/intelligence/lineup_chemistry.parquet     → per-player/lineup/game CV shift scores
- data/cache/lineup_features.parquet             → per-player best-lineup net ratings (2024-25)
- data/nba/boxscore_*.json                       → player → team_abbreviation mapping
- data/cache/on_off_features.parquet             → fallback player → team mapping

METRIC DEFINITIONS
------------------
pairs:
  net_swing = chemistry_score (composite CV z-score: weighted sum of |z| for features that
               shifted when A & B play together vs apart; positive = more beneficial shift,
               chemistry_score = 0.0 means no measurable CV shift detected)
  unit: composite z-score (dimensionless), sourced from max_abs_z and dominant feature z
  CAVEAT: chemistry_score >= 0 always (it is sum of |z|), so "worst" pairs = lowest
           absolute swing (neutral, not explicitly harmful).
           Actual direction of swing is encoded in delta_* / z_* columns per feature.
           We separately derive a SIGNED net_swing from the z-scores of positive features
           (avg_spacing, fast_break_rate, potential_assists) minus negative features
           (contested_shot_rate, possession_duration_avg, isolation_rate).

trios:
  net_swing = mean max_z across all players in the lineup, aggregated over lineup appearances.
  unit: z-score (dimensionless)

MINIMUM THRESHOLDS (stated for transparency)
--------------------------------------------
Pairs:  n_frames_together >= 500  (~8-9 minutes of co-floor CV footage at 10fps capture rate)
Trios:  lineup n_frames >= 200 per player-game, and >= 3 distinct game appearances for the
        same 5-player set (to reduce single-game flukes).
        Relaxed to >= 1 game appearance if fewer than 5 trios per team pass the 3-game threshold.

OUTPUT
------
data/cache/intel_outcome/lineup_combos.json

SCHEMA
------
{
  "meta": {
    "generated": "<ISO timestamp>",
    "pair_threshold_frames": 500,
    "trio_threshold_frames_per_player_game": 200,
    "trio_threshold_min_games": 3,
    "trio_threshold_min_games_fallback": 1,
    "metric_pair": "signed_chemistry_score (composite CV z-score, together-vs-apart)",
    "metric_trio": "mean_max_z (mean lineup CV shift z-score per player-game)",
    "n_teams": <int>,
    "n_players_with_partner_data": <int>,
    "n_pairs_total": <int>,
    "n_trios_total": <int>
  },
  "by_team": {
    "<TRI>": {
      "best_pairs": [
        {
          "players": [<int player_id>, <int player_id>],
          "names": [<str>, <str>],
          "net_swing": <float>,     // signed_chemistry_score, higher = better together
          "minutes": <float>,       // estimated shared minutes (n_frames / 600 at 10fps)
          "n_games": <int>,
          "dominant_feature": <str>
        }
      ],
      "worst_pairs": [...],         // same schema, lowest net_swing (most neutral/harmful)
      "best_trios": [
        {
          "players": [<int>, <int>, <int>],
          "names": [<str>, <str>, <str>],
          "net_swing": <float>,     // mean_max_z across player-lineup appearances
          "minutes": <float>,       // estimated shared minutes
          "n_games": <int>
        }
      ],
      "worst_trios": [...]
    }
  },
  "by_player": {
    "<player_id str>": {
      "player_name": <str>,
      "team": <str>,
      "best_partners": [
        {
          "partner_id": <int>,
          "name": <str>,
          "net_swing": <float>,
          "n_games": <int>,
          "minutes": <float>,
          "dominant_feature": <str>
        }
      ],
      "worst_partners": [...]
    }
  },
  "league_best_pairs": [...],   // top 10 pairs league-wide by net_swing
  "league_worst_pairs": [...]   // bottom 10 pairs league-wide by net_swing
}
"""

import pandas as pd
import numpy as np
import os
import json
import glob
from datetime import datetime, timezone
from itertools import combinations


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
PAIR_CHEM_PATH    = os.path.join(REPO_ROOT, 'data', 'intelligence', 'pair_chemistry.parquet')
LINEUP_CHEM_PATH  = os.path.join(REPO_ROOT, 'data', 'intelligence', 'lineup_chemistry.parquet')
LINEUP_FEAT_PATH  = os.path.join(REPO_ROOT, 'data', 'cache', 'lineup_features.parquet')
ON_OFF_PATH       = os.path.join(REPO_ROOT, 'data', 'cache', 'on_off_features.parquet')
BOXSCORE_DIR      = os.path.join(REPO_ROOT, 'data', 'nba')
OUTPUT_PATH       = os.path.join(REPO_ROOT, 'data', 'cache', 'intel_outcome', 'lineup_combos.json')

# Thresholds
PAIR_MIN_FRAMES   = 500    # ~8-9 shared minutes at 10fps
TRIO_MIN_FRAMES   = 200    # per player-game minimum
TRIO_MIN_GAMES    = 3      # minimum distinct game appearances for same trio
TRIO_MIN_GAMES_FB = 1      # fallback if < 5 trios pass TRIO_MIN_GAMES per team

# Positive / negative CV features for signed net_swing in pairs
POSITIVE_FEATURES = {
    'avg_spacing',       # more floor spacing = better offense
    'fast_break_rate',   # more transition opportunities
    'potential_assists', # more playmaking
    'drive_rate',        # more aggression
    'velocity_mean',     # higher team pace/energy
}
NEGATIVE_FEATURES = {
    'contested_shot_rate',    # more contested = worse shot quality
    'possession_duration_avg', # longer possessions = stagnant offense
    'isolation_rate',          # more iso = less ball movement
}
TOP_N_RESULTS = 5  # best/worst to keep per team


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def frames_to_minutes(frames: float) -> float:
    """Estimate shared minutes from CV frame count (10fps assumed)."""
    return round(float(frames) / 600, 1)


def build_player_team_map() -> dict:
    """
    Build player_id -> team_abbreviation mapping from boxscores (2024-25 season).
    Falls back to on_off_features for any players not in boxscores.
    Returns: {int(player_id): str(team_abbr)}
    """
    pid_team = {}

    # Primary: scan boxscores (most recent team wins)
    bs_files = sorted(glob.glob(os.path.join(BOXSCORE_DIR, 'boxscore_*.json')))
    print(f"  Scanning {len(bs_files)} boxscore files for player-team mapping...")
    for bsf in bs_files:
        try:
            with open(bsf) as f:
                bs = json.load(f)
            for p in bs.get('players', []):
                pid = p.get('player_id')
                team = p.get('team_abbreviation')
                if pid and team:
                    pid_team[int(pid)] = team
        except Exception:
            continue
    print(f"  -> {len(pid_team)} players mapped from boxscores")

    # Fallback: on_off_features (2024-25)
    if os.path.exists(ON_OFF_PATH):
        oo = pd.read_parquet(ON_OFF_PATH)
        for _, row in oo.iterrows():
            pid = int(row['player_id'])
            if pid not in pid_team and pd.notna(row.get('team_abbreviation', None)):
                pid_team[pid] = row['team_abbreviation']
        print(f"  -> {len(pid_team)} players mapped after on_off fallback")

    return pid_team


def compute_signed_chemistry(row: pd.Series) -> float:
    """
    Derive a signed net_swing from per-feature z-scores.
    Positive features (spacing, fast_break, etc.) contribute +z;
    negative features (contested shot, iso, etc.) contribute -z.
    If all z-scores are NaN (1-game artifact), fall back to chemistry_score / 2.
    """
    score = 0.0
    has_signal = False
    for feat in POSITIVE_FEATURES:
        z_col = f'z_{feat}'
        if z_col in row.index and pd.notna(row[z_col]):
            score += float(row[z_col])
            has_signal = True
    for feat in NEGATIVE_FEATURES:
        z_col = f'z_{feat}'
        if z_col in row.index and pd.notna(row[z_col]):
            score -= float(row[z_col])  # flip sign: lower = better for these
            has_signal = True
    if not has_signal:
        # Use chemistry_score as magnitude proxy; direction unknown -> treat as positive
        return float(row.get('chemistry_score', 0.0)) / 2.0
    return round(score, 4)


def process_pairs(pc: pd.DataFrame, pid_team: dict) -> pd.DataFrame:
    """
    Filter pairs by minimum frames, compute signed net_swing, attach teams.
    Returns deduped (canonical A<B by ID) DataFrame.
    """
    # Filter by minimum shared frames
    pc = pc[pc['n_frames_together'] >= PAIR_MIN_FRAMES].copy()
    print(f"  Pairs after n_frames_together >= {PAIR_MIN_FRAMES}: {len(pc)}")

    # Ensure IDs are int
    pc['player_A_id'] = pc['player_A_id'].astype(int)
    pc['player_B_id'] = pc['player_B_id'].astype(int)

    # Compute signed chemistry
    pc['net_swing'] = pc.apply(compute_signed_chemistry, axis=1)

    # Canonicalize: keep A<B pairs only (pair_chemistry has "symmetric" duplicates)
    pc['pid_lo'] = np.minimum(pc['player_A_id'], pc['player_B_id'])
    pc['pid_hi'] = np.maximum(pc['player_A_id'], pc['player_B_id'])
    # When A<B already, use A's name; else swap
    mask_swap = pc['player_A_id'] > pc['player_B_id']
    pc.loc[mask_swap, ['player_A_id', 'player_A_name', 'player_B_id', 'player_B_name']] = \
        pc.loc[mask_swap, ['player_B_id', 'player_B_name', 'player_A_id', 'player_A_name']].values

    # Deduplicate: keep highest |net_swing| per canonical pair (some pairs appear multiple
    # times because pair_chemistry has both directions)
    pc = pc.sort_values('net_swing', ascending=False)
    pc = pc.drop_duplicates(subset=['pid_lo', 'pid_hi'], keep='first')
    print(f"  Pairs after dedup: {len(pc)}")

    # Attach teams
    pc['team_A'] = pc['player_A_id'].map(pid_team)
    pc['team_B'] = pc['player_B_id'].map(pid_team)

    # Estimated shared minutes
    pc['minutes'] = pc['n_frames_together'].apply(frames_to_minutes)

    return pc


def process_trios(lc: pd.DataFrame, pid_team: dict) -> pd.DataFrame:
    """
    Derive 3-man combos from lineup_chemistry.
    Strategy:
      1. Filter player-lineup rows where n_frames >= TRIO_MIN_FRAMES.
      2. Group by (game_id, lineup_id) → collect UNIQUE players (require >= 3 distinct).
      3. For each game-lineup group, compute mean max_z across the unique player rows.
      4. Generate all C(n,3) trios from the lineup's unique player set.
      5. Restrict to same-team trios (all 3 players mapped to same team abbreviation).
      6. Aggregate across appearances: mean net_swing, sum minutes, count games.
      7. Apply TRIO_MIN_GAMES threshold.
    """
    lc_filt = lc[lc['n_frames'] >= TRIO_MIN_FRAMES].copy()
    print(f"  Lineup-chemistry rows after n_frames >= {TRIO_MIN_FRAMES}: {len(lc_filt)}")

    # Group per game-lineup
    trio_records = []
    for (game_id, lineup_id), grp in lc_filt.groupby(['game_id', 'lineup_id']):
        # Deduplicate: one row per unique player_id (take max n_frames row for each)
        grp_dedup = grp.sort_values('n_frames', ascending=False).drop_duplicates('player_id')

        players = grp_dedup['player_id'].tolist()
        names   = grp_dedup['player_name'].tolist()
        mean_max_z = float(grp_dedup['max_z'].mean())
        # Shared minutes: use the minimum n_frames among players (they all need to be on court)
        min_frames = int(grp_dedup['n_frames'].min())
        shared_minutes = round(min_frames / 600, 1)  # minutes at 10fps

        if len(players) < 3:
            continue

        # All C(n,3) trios from this lineup's unique players
        player_set = list(zip(players, names))
        for trio in combinations(player_set, 3):
            trio_pids = tuple(sorted([p[0] for p in trio]))
            pid_to_name = {p[0]: p[1] for p in player_set}
            trio_names = [pid_to_name[tp] for tp in trio_pids]

            # Restrict to same-team trios
            trio_teams = [pid_team.get(int(tp)) for tp in trio_pids]
            if len(set(t for t in trio_teams if t)) > 1:
                continue  # cross-team artifact, skip

            trio_records.append({
                'trio_key': trio_pids,
                'player_ids': list(trio_pids),
                'player_names': trio_names,
                'net_swing': mean_max_z,
                'minutes': shared_minutes,
                'game_id': game_id,
            })

    if not trio_records:
        print("  WARNING: No trio records found")
        return pd.DataFrame()

    trio_df = pd.DataFrame(trio_records)
    print(f"  Total trio-game observations: {len(trio_df)}")

    # Aggregate per trio
    agg = trio_df.groupby('trio_key').agg(
        player_ids=('player_ids', 'first'),
        player_names=('player_names', 'first'),
        net_swing=('net_swing', 'mean'),
        minutes=('minutes', 'sum'),
        n_games=('game_id', 'nunique'),
    ).reset_index(drop=True)

    agg['net_swing'] = agg['net_swing'].round(4)
    agg['minutes']   = agg['minutes'].round(1)

    # Attach team (majority vote from player team memberships)
    def get_trio_team(row):
        teams = [pid_team.get(int(pid)) for pid in row['player_ids'] if pid_team.get(int(pid))]
        if not teams:
            return None
        return max(set(teams), key=teams.count)

    agg['team'] = agg.apply(get_trio_team, axis=1)

    # Apply game threshold
    agg_thresh = agg[agg['n_games'] >= TRIO_MIN_GAMES]
    print(f"  Trios after n_games >= {TRIO_MIN_GAMES}: {len(agg_thresh)}")

    # Return full df with threshold flag
    agg['passes_min_games'] = agg['n_games'] >= TRIO_MIN_GAMES
    return agg


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== build_lineup_combos.py ===")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # --- Load data ---
    print("\n[1] Loading parquets...")
    pc  = pd.read_parquet(PAIR_CHEM_PATH)
    lc  = pd.read_parquet(LINEUP_CHEM_PATH)
    lf  = pd.read_parquet(LINEUP_FEAT_PATH)
    print(f"  pair_chemistry: {pc.shape}")
    print(f"  lineup_chemistry: {lc.shape}")
    print(f"  lineup_features: {lf.shape}")

    # --- Build team map ---
    print("\n[2] Building player -> team map...")
    pid_team = build_player_team_map()

    # --- Process pairs ---
    print("\n[3] Processing 2-man pairs...")
    pairs = process_pairs(pc, pid_team)

    # --- Process trios ---
    print("\n[4] Processing 3-man trios from lineup_chemistry...")
    trios = process_trios(lc, pid_team)

    # --- Build by_team ---
    print("\n[5] Building by_team view...")
    by_team = {}

    # Collect all teams from pairs
    all_teams = set()
    for _, row in pairs.iterrows():
        if row['team_A']:
            all_teams.add(row['team_A'])
        if row['team_B']:
            all_teams.add(row['team_B'])
    if not trios.empty:
        for t in trios['team'].dropna().unique():
            all_teams.add(t)
    print(f"  Teams found: {sorted(all_teams)}")

    for team in sorted(all_teams):
        # Pairs where both players are on this team
        team_pairs = pairs[
            (pairs['team_A'] == team) & (pairs['team_B'] == team)
        ].copy()

        # Build pair records
        def pair_to_dict(row):
            return {
                'players': [int(row['player_A_id']), int(row['player_B_id'])],
                'names': [row['player_A_name'], row['player_B_name']],
                'net_swing': round(float(row['net_swing']), 4),
                'minutes': float(row['minutes']),
                'n_games': int(row['n_games']),
                'dominant_feature': str(row.get('dominant_feature', '')),
            }

        best_pairs = []
        worst_pairs = []
        if len(team_pairs) > 0:
            top = team_pairs.nlargest(TOP_N_RESULTS, 'net_swing')
            bot = team_pairs.nsmallest(TOP_N_RESULTS, 'net_swing')
            best_pairs  = [pair_to_dict(r) for _, r in top.iterrows()]
            worst_pairs = [pair_to_dict(r) for _, r in bot.iterrows()]

        # Trios for this team (use TRIO_MIN_GAMES threshold; fall back if < 5)
        best_trios = []
        worst_trios = []
        if not trios.empty:
            team_trios = trios[trios['team'] == team].copy()
            thresh_trios = team_trios[team_trios['passes_min_games']]
            if len(thresh_trios) < TOP_N_RESULTS:
                # fallback: all trios >= TRIO_MIN_GAMES_FB
                thresh_trios = team_trios[team_trios['n_games'] >= TRIO_MIN_GAMES_FB]

            def trio_to_dict(row):
                return {
                    'players': [int(p) for p in row['player_ids']],
                    'names': list(row['player_names']),
                    'net_swing': round(float(row['net_swing']), 4),
                    'minutes': round(float(row['minutes']), 1),
                    'n_games': int(row['n_games']),
                }

            if len(thresh_trios) > 0:
                top_t = thresh_trios.nlargest(TOP_N_RESULTS, 'net_swing')
                bot_t = thresh_trios.nsmallest(TOP_N_RESULTS, 'net_swing')
                best_trios  = [trio_to_dict(r) for _, r in top_t.iterrows()]
                worst_trios = [trio_to_dict(r) for _, r in bot_t.iterrows()]

        by_team[team] = {
            'best_pairs':  best_pairs,
            'worst_pairs': worst_pairs,
            'best_trios':  best_trios,
            'worst_trios': worst_trios,
        }

    # --- Build by_player ---
    print("\n[6] Building by_player view...")
    by_player = {}

    # All players appearing in filtered pairs
    all_player_ids = set(pairs['player_A_id'].tolist() + pairs['player_B_id'].tolist())
    for pid in sorted(all_player_ids):
        pid = int(pid)
        # Rows where this player is player_A
        as_A = pairs[pairs['player_A_id'] == pid]
        # Rows where this player is player_B (build partner-perspective rows)
        as_B = pairs[pairs['player_B_id'] == pid].copy()
        as_B = as_B.rename(columns={
            'player_B_id': 'player_A_id', 'player_B_name': 'player_A_name',
            'player_A_id': 'player_B_id', 'player_A_name': 'player_B_name',
        })
        player_pairs = pd.concat([as_A, as_B], ignore_index=True)

        if player_pairs.empty:
            continue

        # Get player name
        pname = player_pairs['player_A_name'].iloc[0] if len(player_pairs) > 0 else str(pid)
        team  = pid_team.get(pid, 'UNK')

        def partner_dict(row):
            return {
                'partner_id': int(row['player_B_id']),
                'name': str(row['player_B_name']),
                'net_swing': round(float(row['net_swing']), 4),
                'n_games': int(row['n_games']),
                'minutes': float(row['minutes']),
                'dominant_feature': str(row.get('dominant_feature', '')),
            }

        best_partners  = [partner_dict(r) for _, r in player_pairs.nlargest(3, 'net_swing').iterrows()]
        worst_partners = [partner_dict(r) for _, r in player_pairs.nsmallest(3, 'net_swing').iterrows()]

        by_player[str(pid)] = {
            'player_name': pname,
            'team': team,
            'best_partners':  best_partners,
            'worst_partners': worst_partners,
        }

    # --- League-wide top/bottom pairs ---
    print("\n[7] Computing league-wide best/worst pairs...")
    league_best  = pairs.nlargest(10, 'net_swing')
    league_worst = pairs.nsmallest(10, 'net_swing')

    def pair_to_dict_simple(row):
        return {
            'players': [int(row['player_A_id']), int(row['player_B_id'])],
            'names': [row['player_A_name'], row['player_B_name']],
            'net_swing': round(float(row['net_swing']), 4),
            'minutes': float(row['minutes']),
            'n_games': int(row['n_games']),
            'team': row.get('team_A') or row.get('team_B') or 'UNK',
            'dominant_feature': str(row.get('dominant_feature', '')),
        }

    league_best_list  = [pair_to_dict_simple(r) for _, r in league_best.iterrows()]
    league_worst_list = [pair_to_dict_simple(r) for _, r in league_worst.iterrows()]

    # --- Assemble output ---
    # n_trios_total = unique trios that appear in the output (fallback-qualified: n_games >= TRIO_MIN_GAMES_FB)
    n_trios_total = 0 if trios.empty else int((trios['n_games'] >= TRIO_MIN_GAMES_FB).sum())
    n_trios_3game = 0 if trios.empty else int(trios['passes_min_games'].sum())
    output = {
        'meta': {
            'generated': datetime.now(timezone.utc).isoformat(),
            'pair_threshold_frames': PAIR_MIN_FRAMES,
            'pair_threshold_minutes_approx': frames_to_minutes(PAIR_MIN_FRAMES),
            'trio_threshold_frames_per_player_game': TRIO_MIN_FRAMES,
            'trio_threshold_min_games': TRIO_MIN_GAMES,
            'trio_threshold_min_games_fallback': TRIO_MIN_GAMES_FB,
            'metric_pair': (
                'signed_chemistry_score: sum of z-scores for positive CV features '
                '(avg_spacing, fast_break_rate, potential_assists, drive_rate, velocity_mean) '
                'minus negative features (contested_shot_rate, possession_duration_avg, isolation_rate), '
                'computed from "together vs apart" deltas. Higher = better joint CV chemistry.'
            ),
            'metric_trio': (
                'mean_max_z: mean of max_z (largest CV feature shift z-score) across all '
                'player-game appearances in this lineup. Higher = more CV-detectable lineup effect.'
            ),
            'minutes_unit': 'estimated shared floor minutes (n_frames / 600, assuming 10fps)',
            'sources': [
                'data/intelligence/pair_chemistry.parquet',
                'data/intelligence/lineup_chemistry.parquet',
                'data/cache/lineup_features.parquet',
                'data/nba/boxscore_*.json (player-team map)',
                'data/cache/on_off_features.parquet (player-team fallback)',
            ],
            'caveats': [
                'CV data covers only games with tracked video (n_games typically 1-7 per pair); '
                'pairs with n_games=1 have higher variance.',
                'chemistry_score is always >= 0 (magnitude of shift), so signed_chemistry_score '
                'captures directionality but may not reflect net rating impact directly.',
                'Trios derived from lineup_chemistry lineup_ids; players not all from same team '
                'are possible if lineup_id groupings are cross-team (rare).',
                'Team assignment uses last observed team from boxscores; traded players may be '
                'mapped to their most recent team, not necessarily the one they played with in pairs.',
                'pair_chemistry n_games max is 7 (small-sample); treat all findings as CV '
                'scouting signals, not statistically validated edges.',
            ],
            'n_teams': len(by_team),
            'n_players_with_partner_data': len(by_player),
            'n_pairs_total': len(pairs),
            'n_trios_total': n_trios_total,
            'n_trios_3game_threshold': n_trios_3game,
        },
        'by_team': by_team,
        'by_player': by_player,
        'league_best_pairs': league_best_list,
        'league_worst_pairs': league_worst_list,
    }

    # --- Write output ---
    print(f"\n[8] Writing output to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"  Written: {size_kb:.1f} KB")

    # --- Summary report ---
    print("\n=== SUMMARY ===")
    print(f"Teams covered:        {len(by_team)}")
    print(f"Players with data:    {len(by_player)}")
    print(f"Pairs (post-filter):  {len(pairs)}")
    print(f"Trios (fallback>=1g): {n_trios_total}")
    print(f"Trios (>={TRIO_MIN_GAMES} games):   {n_trios_3game}")
    print(f"\n--- League BEST 5 pairs by net_swing ---")
    for item in league_best_list[:5]:
        print(f"  {item['names'][0]} + {item['names'][1]}: "
              f"net_swing={item['net_swing']:+.3f}, {item['minutes']}min, "
              f"{item['n_games']}g, feat={item['dominant_feature']}")
    print(f"\n--- League WORST 5 pairs by net_swing ---")
    for item in league_worst_list[:5]:
        print(f"  {item['names'][0]} + {item['names'][1]}: "
              f"net_swing={item['net_swing']:+.3f}, {item['minutes']}min, "
              f"{item['n_games']}g, feat={item['dominant_feature']}")
    print(f"\nOutput: {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
