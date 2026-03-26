"""
tracking_feature_extractor.py — CV-derived per-player per-game feature extractor.

Reads data/tracking/{game_id}/ CSV outputs and returns a feature dict suitable
for injection into the ML feature pipeline (feature_pipeline.py).

Computed features per player (all float, 0.0 when insufficient data):
  avg_defender_distance    mean defender distance from shot_log
  shot_zone_paint_pct      % of shots from paint zone
  shot_zone_mid_range_pct  % from mid_range
  shot_zone_3pt_pct        % from 3pt_arc or corner_3
  contested_shot_rate      % of shots with defender_distance < 4 feet (approx 48px)
  avg_spacing              mean team_spacing from shot_log
  shots_per_possession     total shots / total possessions
  made_pct                 % of shots with made == 1 (when enriched)
  avg_shot_clock_at_shot   mean shot_clock_est at shot frames (from scoreboard_log)
  possession_duration_avg  mean possession duration in sec
  play_type_transition_pct % of possessions that are transition/fast_break
  play_type_drive_pct      % of possessions that are drive
  play_type_isolation_pct  % of possessions that are isolation-type (half_court)
  play_type_post_pct       % of possessions that are post_up

Public API
----------
    extract(game_id, data_root) -> Dict[player_id, Dict[str, float]]
    merge_into_features(features_df, cv_dict) -> pd.DataFrame
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from typing import Dict, Optional

_DEFENDER_DIST_CONTESTED_PX = 150   # pixels ≈ 4 feet on 940×500 court map

# Default data root (override via data_root parameter)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DATA_ROOT = os.path.join(_PROJECT_ROOT, "data")


def extract(
    game_id: str,
    data_root: Optional[str] = None,
) -> Dict[int, Dict[str, float]]:
    """
    Extract CV-derived per-player features for one processed game.

    Args:
        game_id:   NBA game ID (e.g. "0022400625").
        data_root: Root of the data directory tree. Defaults to project data/.
                   The function looks for files under {data_root}/tracking/{game_id}/.

    Returns:
        Dict mapping player_id (int) → dict of feature_name → float.
        Returns {} if no tracking data found for this game.
    """
    root   = data_root or _DEFAULT_DATA_ROOT
    gdir   = os.path.join(root, "tracking", game_id)
    if not os.path.isdir(gdir):
        # Also try flat layout (legacy: data/tracking_data.csv without game subdir)
        gdir = root

    shot_path  = os.path.join(gdir, "shot_log.csv")
    poss_path  = os.path.join(gdir, "possessions.csv")
    sb_path    = os.path.join(gdir, "scoreboard_log.csv")

    if not os.path.exists(shot_path) and not os.path.exists(poss_path):
        return {}

    # ── Shot log features ─────────────────────────────────────────────────────
    shot_stats: Dict[int, dict] = defaultdict(lambda: {
        "def_dists": [], "zones": [], "made": [], "spacings": [],
    })

    if os.path.exists(shot_path):
        with open(shot_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    pid_raw = row.get("player_id", "")
                    if not str(pid_raw).strip().lstrip("-").isdigit():
                        continue
                    pid = int(pid_raw)
                    s   = shot_stats[pid]
                    dd  = row.get("defender_distance", "")
                    if dd not in ("", None):
                        s["def_dists"].append(float(dd))
                    zone = str(row.get("court_zone", "")).strip()
                    if zone:
                        s["zones"].append(zone)
                    made_val = row.get("made", "")
                    if made_val not in ("", None):
                        s["made"].append(int(made_val))
                    sp = row.get("team_spacing", "")
                    if sp not in ("", None):
                        s["spacings"].append(float(sp))
                except (ValueError, TypeError):
                    continue

    # ── Possession features ───────────────────────────────────────────────────
    poss_by_team: Dict[str, list] = defaultdict(list)

    if os.path.exists(poss_path):
        with open(poss_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                team = str(row.get("team", "")).strip()
                if not team:
                    continue
                dur = row.get("duration_sec", "")
                ptype = str(row.get("play_type", row.get("possession_type", ""))).strip()
                if dur not in ("", None):
                    try:
                        poss_by_team[team].append({
                            "dur": float(dur),
                            "play_type": ptype,
                        })
                    except (ValueError, TypeError):
                        pass

    # ── Scoreboard log: shot-clock at shot frames ─────────────────────────────
    # Build frame → shot_clock lookup
    sb_clock: Dict[int, float] = {}
    if os.path.exists(sb_path):
        with open(sb_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    sc = row.get("shot_clock", "")
                    fr = row.get("frame", "")
                    if sc not in ("", None) and fr not in ("", None):
                        sb_clock[int(fr)] = float(sc)
                except (ValueError, TypeError):
                    pass

    # Map shot frames to shot_clock values
    shot_clocks_by_pid: Dict[int, list] = defaultdict(list)
    if os.path.exists(shot_path) and sb_clock:
        with open(shot_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    pid = int(row.get("player_id", 0) or 0)
                    fr  = int(row.get("frame", 0) or 0)
                    # Find nearest scoreboard reading
                    if sb_clock:
                        nearest_fr = min(sb_clock.keys(), key=lambda k: abs(k - fr))
                        if abs(nearest_fr - fr) <= 90:   # within 3 seconds at 30fps
                            shot_clocks_by_pid[pid].append(sb_clock[nearest_fr])
                except (ValueError, TypeError):
                    pass

    # Count total shots per team (for shots_per_possession)
    shots_by_team: Dict[str, int] = defaultdict(int)
    if os.path.exists(shot_path):
        with open(shot_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                team = str(row.get("team", "")).strip()
                if team:
                    shots_by_team[team] += 1

    # ── Build per-player feature dict ─────────────────────────────────────────
    result: Dict[int, Dict[str, float]] = {}

    all_pids = set(shot_stats.keys()) | set(shot_clocks_by_pid.keys())

    # For possession-level features, we average across all team possessions.
    # Build a mapping: tracker team (green/white) → possession stats.
    team_poss_feats: Dict[str, dict] = {}
    for team, poss_list in poss_by_team.items():
        durs = [p["dur"] for p in poss_list]
        types = [p["play_type"] for p in poss_list]
        n = len(poss_list)
        team_poss_feats[team] = {
            "possession_duration_avg":   round(sum(durs) / n, 2) if durs else 0.0,
            "play_type_transition_pct":  round(sum(1 for t in types if t in
                                              ("transition", "fast_break")) / n, 3)
                                          if n else 0.0,
            "play_type_drive_pct":       round(sum(1 for t in types if t == "drive") / n, 3)
                                          if n else 0.0,
            "play_type_isolation_pct":   round(sum(1 for t in types if t in
                                              ("half_court", "isolation")) / n, 3)
                                          if n else 0.0,
            "play_type_post_pct":        round(sum(1 for t in types if t == "post_up") / n, 3)
                                          if n else 0.0,
            "total_possessions":         n,
        }

    for pid in all_pids:
        s    = shot_stats.get(pid, {})
        dds  = s.get("def_dists", [])
        zones = s.get("zones",   [])
        made  = s.get("made",    [])
        spcs  = s.get("spacings",[])
        scks  = shot_clocks_by_pid.get(pid, [])

        n_shots = len(zones)
        zone_counts = defaultdict(int)
        for z in zones:
            zone_counts[z] += 1

        feats: Dict[str, float] = {
            "avg_defender_distance":   round(sum(dds) / len(dds), 1) if dds else 0.0,
            "shot_zone_paint_pct":     round(zone_counts.get("paint", 0) / n_shots, 3) if n_shots else 0.0,
            "shot_zone_mid_range_pct": round(zone_counts.get("mid_range", 0) / n_shots, 3) if n_shots else 0.0,
            "shot_zone_3pt_pct":       round((zone_counts.get("3pt_arc", 0)
                                              + zone_counts.get("corner_3", 0)) / n_shots, 3) if n_shots else 0.0,
            "contested_shot_rate":     round(sum(1 for d in dds if d < _DEFENDER_DIST_CONTESTED_PX) / len(dds), 3)
                                       if dds else 0.0,
            "avg_spacing":             round(sum(spcs) / len(spcs), 1) if spcs else 0.0,
            "made_pct":                round(sum(made) / len(made), 3) if made else 0.0,
            "avg_shot_clock_at_shot":  round(sum(scks) / len(scks), 1) if scks else 0.0,
            "n_shots_tracked":         float(n_shots),
        }

        # We need the player's team to look up possession features.
        # Best guess: from shot_log (tracker uses green/white team labels).
        player_team = ""
        if os.path.exists(shot_path):
            with open(shot_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        if int(row.get("player_id", -1) or -1) == pid:
                            player_team = str(row.get("team", "")).strip()
                            break
                    except (ValueError, TypeError):
                        pass

        pf = team_poss_feats.get(player_team, {})
        n_poss = pf.get("total_possessions", 0)
        feats.update({
            "shots_per_possession":     round(n_shots / n_poss, 3) if n_poss else 0.0,
            "possession_duration_avg":  pf.get("possession_duration_avg", 0.0),
            "play_type_transition_pct": pf.get("play_type_transition_pct", 0.0),
            "play_type_drive_pct":      pf.get("play_type_drive_pct", 0.0),
            "play_type_isolation_pct":  pf.get("play_type_isolation_pct", 0.0),
            "play_type_post_pct":       pf.get("play_type_post_pct", 0.0),
        })

        result[pid] = feats

    return result


def merge_into_features(
    features_df: "object",   # pd.DataFrame
    cv_dict: Dict[int, Dict[str, float]],
    player_id_col: str = "player_id",
) -> "object":
    """
    Merge CV feature dict into a features DataFrame.

    Args:
        features_df:   Existing features DataFrame.
        cv_dict:       Output of extract().
        player_id_col: Column in features_df holding integer player_id.

    Returns:
        DataFrame with new CV feature columns added (NaN where player not in cv_dict).
    """
    try:
        import pandas as pd
    except ImportError:
        return features_df

    if not cv_dict or features_df is None or len(features_df) == 0:
        return features_df

    cv_df = pd.DataFrame.from_dict(cv_dict, orient="index")
    cv_df.index.name = player_id_col
    cv_df = cv_df.reset_index()
    cv_df[player_id_col] = cv_df[player_id_col].astype(int)

    # Add cv_ prefix to distinguish from existing features
    rename_map = {c: f"cv_{c}" for c in cv_df.columns if c != player_id_col}
    cv_df = cv_df.rename(columns=rename_map)

    merged = features_df.merge(cv_df, on=player_id_col, how="left")
    n_with = merged[[c for c in merged.columns if c.startswith("cv_")]].notna().any(axis=1).sum()
    print(f"[tracking_feature_extractor] Merged {len(cv_dict)} CV feature sets "
          f"({n_with} feature rows enriched with CV data)")
    return merged
