"""
build_team_cv.py — Step 1-3 of channel C3: team-level CV aggregates as opponent context features.

Creates cv_team_features table in nba_ai.db with per-team, per-season CV aggregates.
Features aggregated: paint_dwell_pct, touches_per_game, potential_assists,
shots_per_possession, possession_duration_avg, shot_zone_paint_pct,
shot_zone_3pt_pct, play_type_transition_pct.

Usage:
    python scripts/build_team_cv.py
    python scripts/build_team_cv.py --report-only   (skip DB write, just print stats)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR      = PROJECT_DIR / "data"
TRACKING_DIR  = DATA_DIR / "tracking"
NBA_CACHE_DIR = DATA_DIR / "nba"
DB_PATH       = str(DATA_DIR / "nba_ai.db")

# Features we aggregate at team level (reliable — NOT defender_distance)
TEAM_CV_FEATURES = [
    "paint_dwell_pct",
    "touches_per_game",
    "potential_assists",
    "shots_per_possession",
    "possession_duration_avg",
    "shot_zone_paint_pct",
    "shot_zone_3pt_pct",
    "play_type_transition_pct",
]


# ---------------------------------------------------------------------------
# Step 1: Build player_id -> team_abbrev mapping
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _load_player_team_map() -> Dict[int, str]:
    """
    Build {player_id: team_abbrev} from player_full_*.json files.
    Tries 2025-26 first (most recent), then 2024-25.
    Caveat: this is season-level team assignment; mid-season trades are not captured.
    """
    pid_to_team: Dict[int, str] = {}
    season_files = ["player_full_2025-26.json", "player_full_2024-25.json"]
    for fname in season_files:
        fpath = NBA_CACHE_DIR / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
            continue
        if isinstance(data, dict):
            for _name, info in data.items():
                if isinstance(info, dict):
                    pid = info.get("player_id") or info.get("PLAYER_ID")
                    team = info.get("team") or info.get("TEAM_ABBREVIATION")
                    if pid and team:
                        # Only overwrite if not already assigned (newer season wins)
                        pid_int = int(pid)
                        if pid_int not in pid_to_team:
                            pid_to_team[pid_int] = str(team).upper()
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    pid = row.get("player_id") or row.get("PLAYER_ID")
                    team = row.get("team") or row.get("TEAM_ABBREVIATION")
                    if pid and team:
                        pid_int = int(pid)
                        if pid_int not in pid_to_team:
                            pid_to_team[pid_int] = str(team).upper()
    return pid_to_team


def _load_shot_log_team_map(game_id: str) -> Dict[int, str]:
    """
    Parse shot_log.csv for a game and return {slot_player_id: team_abbrev}.
    This maps SLOT ids (1-10), not NBA player_ids.
    """
    path = TRACKING_DIR / game_id / "shot_log.csv"
    if not path.exists():
        return {}
    result: Dict[int, str] = {}
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    pid = int(row.get("player_id", 0))
                    ta = row.get("team_abbrev", "").strip().upper()
                    if pid and ta and ta not in ("", "UNK"):
                        result[pid] = ta
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return result


def _load_jersey_name_map(game_id: str) -> Dict[str, str]:
    """Load jersey_name_map.json: {slot_str: player_name}."""
    path = TRACKING_DIR / game_id / "jersey_name_map.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_game_date_map() -> Dict[str, str]:
    """Return {game_id: 'YYYY-MM-DD'} from all season_games_*.json files."""
    gd: Dict[str, str] = {}
    import glob
    for fpath in glob.glob(str(NBA_CACHE_DIR / "season_games_*.json")):
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("rows", data) if isinstance(data, dict) else data
            for row in rows:
                if isinstance(row, dict) and "game_id" in row and "game_date" in row:
                    gd[str(row["game_id"])] = row["game_date"]
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
    return gd


def _season_prefix(game_id: str) -> str:
    """
    Extract season prefix from game_id.
    '0022400625' -> '00224' (2024-25)
    '0022500003' -> '00225' (2025-26)
    """
    return game_id[:5]


def _season_label(prefix: str) -> str:
    """'00224' -> '2024-25', '00225' -> '2025-26'."""
    year_suffix = prefix[3:5]  # '24' or '25'
    year = 2000 + int(year_suffix)
    return f"{year}-{str(year + 1)[-2:]}"


# ---------------------------------------------------------------------------
# Step 2: Load cv_features, map players to teams, aggregate per (team, season)
# ---------------------------------------------------------------------------

def build_team_cv_aggregates(
    report_only: bool = False,
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """
    Core aggregation logic.
    Returns: {(team_abbrev, season_prefix): {feature_name: value, 'n_obs': int}}
    """
    print("\n=== C3 build_team_cv: Loading data ===")

    # 1. Load player_id -> team map
    pid_to_team = _load_player_team_map()
    print(f"  player_id -> team: {len(pid_to_team)} players loaded from player_full JSON")

    # 2. Load game -> date map
    game_date_map = _load_game_date_map()
    print(f"  game_date_map: {len(game_date_map)} games")

    # 3. Load all cv_features from DB
    conn = sqlite3.connect(DB_PATH)
    cv_rows = conn.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features"
        " WHERE player_id != 0"
    ).fetchall()
    conn.close()
    print(f"  cv_features rows: {len(cv_rows)}")

    # 4. Build {(game_id, player_id): team_abbrev}
    # Strategy A: use shot_log.csv slot->team_abbrev + jersey_name_map slot->player_name
    #             + player_full name->player_id chain  (most accurate)
    # Strategy B: fallback — use player_full pid->team directly
    #
    # In practice most shot_log.csv files have team_abbrev='UNK' for the 2024-25
    # games because the backfill was run before the PBP-enrichment pass.
    # We use Strategy B (player_full season team) as PRIMARY, and
    # Strategy A as a cross-check where available.

    # Collect all (game_id, player_id) pairs from cv_features
    game_player_pairs: set = set()
    for pid, gid, _fn, _fv in cv_rows:
        game_player_pairs.add((gid, pid))

    print(f"  Unique (game, player) pairs: {len(game_player_pairs)}")

    # Build team mapping via Strategy B (player_full pid -> team)
    # Limitation: this gives season-final team, not team at game date
    gp_to_team: Dict[Tuple[str, int], str] = {}
    unmapped = 0
    for (gid, pid) in game_player_pairs:
        team = pid_to_team.get(int(pid))
        if team:
            gp_to_team[(gid, int(pid))] = team
        else:
            unmapped += 1

    print(f"  Mapped {len(gp_to_team)} / {len(game_player_pairs)} player-games to team")
    print(f"  Unmapped: {unmapped} (players not in player_full JSON — may be trades/rookies)")

    # Cross-check with shot_log where team_abbrev != UNK
    shot_log_check: Dict[Tuple[str, int], str] = {}
    games_with_shot_log = 0
    for (gid, pid) in game_player_pairs:
        # shot_log uses slot IDs, not NBA player_ids; skip for now
        # (would require the full name-resolution chain)
        pass

    # 5. Aggregate features per (team_abbrev, season_prefix, feature_name)
    # {(team, season_prefix): {feature_name: [values]}}
    team_season_feats: Dict[Tuple[str, str], Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for pid, gid, feature_name, feature_value in cv_rows:
        if feature_name not in TEAM_CV_FEATURES:
            continue
        if feature_value is None:
            continue
        team = gp_to_team.get((gid, int(pid)))
        if not team:
            continue
        season = _season_prefix(gid)
        team_season_feats[(team, season)][feature_name].append(float(feature_value))

    # Compute means
    result: Dict[Tuple[str, str], Dict[str, float]] = {}
    for (team, season), feat_dict in team_season_feats.items():
        agg: Dict[str, float] = {}
        n_obs_vals = []
        for fname in TEAM_CV_FEATURES:
            vals = feat_dict.get(fname, [])
            if vals:
                agg[fname] = float(sum(vals) / len(vals))
                n_obs_vals.append(len(vals))
            else:
                agg[fname] = 0.0
        agg["n_obs"] = float(int(sum(n_obs_vals) / len(n_obs_vals)) if n_obs_vals else 0)
        result[(team, season)] = agg

    print(f"\n  Teams aggregated: {len(result)} (team, season) combos")
    by_season: Dict[str, int] = defaultdict(int)
    for (team, season) in result:
        by_season[season] += 1
    for season, count in sorted(by_season.items()):
        label = _season_label(season)
        print(f"    Season {label} ({season}): {count} teams")

    # Print coverage stats
    all_n_obs = [int(v["n_obs"]) for v in result.values()]
    if all_n_obs:
        print(f"  Mean n_obs per team-feature: {sum(all_n_obs)/len(all_n_obs):.1f}")
        print(f"  Min n_obs: {min(all_n_obs)}, Max n_obs: {max(all_n_obs)}")

    # Sort by n_obs descending
    sorted_teams = sorted(result.items(), key=lambda x: -x[1]["n_obs"])
    print("\n  Top 5 most-tracked teams:")
    for (team, season), agg in sorted_teams[:5]:
        print(f"    {team} ({_season_label(season)}): n_obs={int(agg['n_obs'])}")
    print("\n  Bottom 5 least-tracked teams:")
    for (team, season), agg in sorted_teams[-5:]:
        print(f"    {team} ({_season_label(season)}): n_obs={int(agg['n_obs'])}")

    # Sample profiles
    print("\n  Sample team profiles:")
    for target_team in ["BOS", "LAL", "MIL"]:
        for (team, season), agg in result.items():
            if team == target_team:
                print(f"    {team} ({_season_label(season)}): "
                      f"paint_dwell={agg.get('paint_dwell_pct', 0):.3f}, "
                      f"pace={1/agg['possession_duration_avg'] if agg.get('possession_duration_avg', 0) > 0 else 0:.3f}, "
                      f"pot_ast={agg.get('potential_assists', 0):.2f}, "
                      f"3pt_pct={agg.get('shot_zone_3pt_pct', 0):.3f}")
                break

    return result


# ---------------------------------------------------------------------------
# Step 3: Write cv_team_features table
# ---------------------------------------------------------------------------

def write_to_db(
    aggregates: Dict[Tuple[str, str], Dict[str, float]],
) -> None:
    """Create cv_team_features table and insert aggregated rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cv_team_features (
            team_abbrev  TEXT,
            season_prefix TEXT,
            feature_name  TEXT,
            feature_value REAL,
            n_obs         INTEGER,
            PRIMARY KEY (team_abbrev, season_prefix, feature_name)
        )"""
    )
    conn.commit()

    # Clear existing rows and re-insert (idempotent)
    conn.execute("DELETE FROM cv_team_features")

    rows_inserted = 0
    for (team, season), feat_dict in aggregates.items():
        n_obs = int(feat_dict.get("n_obs", 0))
        for fname in TEAM_CV_FEATURES:
            fval = feat_dict.get(fname, 0.0)
            conn.execute(
                "INSERT OR REPLACE INTO cv_team_features "
                "(team_abbrev, season_prefix, feature_name, feature_value, n_obs) "
                "VALUES (?, ?, ?, ?, ?)",
                (team, season, fname, fval, n_obs),
            )
            rows_inserted += 1

    conn.commit()
    conn.close()
    print(f"\n  Wrote {rows_inserted} rows to cv_team_features")


# ---------------------------------------------------------------------------
# Public API: load aggregates as a lookup dict
# ---------------------------------------------------------------------------

def load_team_cv_lookup(db_path: str = DB_PATH) -> Dict[Tuple[str, str, str], Tuple[float, int]]:
    """
    Load cv_team_features into a lookup dict.
    Returns: {(team_abbrev, season_prefix, feature_name): (feature_value, n_obs)}
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT team_abbrev, season_prefix, feature_name, feature_value, n_obs "
            "FROM cv_team_features"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return {(r[0], r[1], r[2]): (r[3], r[4]) for r in rows}


def get_team_cv_features(
    team_abbrev: str,
    season_prefix: str,
    lookup: Dict[Tuple[str, str, str], Tuple[float, int]],
    prefix: str = "",
    fallback_lookup: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Build a feature dict for a team in a given season.
    Returns feature_name -> value for all TEAM_CV_FEATURES.
    Falls back to fallback_lookup values (season means) when no data.

    Args:
        prefix: string prefix for output feature names (e.g. 'opp_cv_' or 'team_cv_')
    """
    feats: Dict[str, float] = {}
    n_obs = 0
    any_found = False

    for fname in TEAM_CV_FEATURES:
        key = (team_abbrev.upper(), season_prefix, fname)
        val_obs = lookup.get(key)
        if val_obs is not None:
            feats[f"{prefix}{fname}"] = val_obs[0]
            n_obs = val_obs[1]
            any_found = True
        else:
            # fallback
            fb = fallback_lookup.get(fname, 0.0) if fallback_lookup else 0.0
            feats[f"{prefix}{fname}"] = fb

    feats[f"{prefix}n_obs"] = float(n_obs) if any_found else 0.0
    return feats


def compute_season_means(
    lookup: Dict[Tuple[str, str, str], Tuple[float, int]],
) -> Dict[str, Dict[str, float]]:
    """
    Compute per-season mean for each feature (for fallback when team has no CV data).
    Returns: {season_prefix: {feature_name: mean_value}}
    """
    from collections import defaultdict
    sums: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for (team, season, fname), (val, _n_obs) in lookup.items():
        sums[season][fname] += val
        counts[season][fname] += 1

    result: Dict[str, Dict[str, float]] = {}
    for season, feat_sums in sums.items():
        result[season] = {
            fname: feat_sums[fname] / counts[season][fname]
            for fname in feat_sums
            if counts[season][fname] > 0
        }
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Build team-level CV aggregates for C3 opp-context features.")
    ap.add_argument("--report-only", action="store_true", help="Skip DB write, print stats only")
    args = ap.parse_args()

    aggregates = build_team_cv_aggregates(report_only=args.report_only)

    if not args.report_only:
        print("\n=== Writing to cv_team_features table ===")
        write_to_db(aggregates)
        print("  Done.")

    # Summarize
    total_team_feature_rows = len(aggregates) * len(TEAM_CV_FEATURES)
    all_n_obs = [int(v.get("n_obs", 0)) for v in aggregates.values()]
    mean_n_obs = sum(all_n_obs) / len(all_n_obs) if all_n_obs else 0

    print("\n=== C3 Team CV Aggregates — Summary ===")
    print(f"  Total (team, season) combos: {len(aggregates)}")
    print(f"  Total feature rows in DB: {total_team_feature_rows}")
    print(f"  Mean n_obs per team-feature: {mean_n_obs:.1f}")
    print(f"  Features: {TEAM_CV_FEATURES}")

    # Count teams per season
    from collections import Counter
    season_team_counts = Counter(_season_prefix(gid) for (team, season) in aggregates for gid in [season])
    # Fix: count by season directly
    season_teams: Dict[str, set] = defaultdict(set)
    for (team, season) in aggregates:
        season_teams[season].add(team)
    for season, teams in sorted(season_teams.items()):
        print(f"  {_season_label(season)}: {len(teams)}/30 teams covered: {sorted(teams)}")


if __name__ == "__main__":
    main()
