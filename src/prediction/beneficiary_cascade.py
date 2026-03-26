"""
beneficiary_cascade.py — M08: Minutes/stat boost when star sits.

HIGH PRIORITY — Best repeatable edge in the system.
Books lag 30-90 min on beneficiary prop lines.

Method: For each star player, scan historical DNP games in gamelogs.
        Measure actual minutes increase for each teammate.
        Build per-team lookup table.
        When star dnp_prob > 0.3, distribute expected minutes to beneficiaries.

Public API
----------
    build_cascade_table(seasons)                               -> dict
    predict_beneficiary_boost(team_abbrev, missing_player_ids) -> dict {player_id: min_boost}
    get_beneficiary_boost(player_id, team, dnp_star_id)        -> float
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sys
from collections import defaultdict
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "beneficiary_cascade.pkl")

log = logging.getLogger(__name__)

# Star threshold: players who avg >= N min/game are "stars"
_STAR_MIN_THRESHOLD = 28.0
_DNP_THRESHOLD = 0.3  # if dnp_prob > this, distribute minutes


def _parse_min(val) -> float:
    if val is None:
        return float("nan")
    s = str(val).strip()
    if s in ("", "None", "null"):
        return float("nan")
    if s in ("0", "0:00"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def _load_all_gamelogs(season: str) -> dict[int, list[dict]]:
    """Load all gamelog files for a season. Returns {player_id: [game_rows]}.

    Uses gamelog_full_{pid}_{season}.json files which have lowercase keys
    (game_id, min, pts, etc.) compatible with this module's parsing.
    """
    result: dict[int, list[dict]] = {}
    pattern = os.path.join(_NBA_CACHE, f"gamelog_full_*_{season}.json")
    for fpath in glob.glob(pattern):
        try:
            fname = os.path.basename(fpath)
            # gamelog_full_{pid}_{season}.json → split gives ['gamelog','full',pid,season]
            parts = fname.replace(".json", "").split("_")
            pid_str = parts[2]
            pid = int(pid_str)
            logs = json.load(open(fpath))
            if isinstance(logs, list) and logs:
                result[pid] = sorted(logs, key=lambda g: g.get("game_date", ""))
        except Exception:
            continue
    return result


def build_cascade_table(seasons: Optional[list[str]] = None) -> dict:
    """
    Build {star_player_id: {beneficiary_player_id: {avg_min_boost, games_dnp}}}.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    cascade: dict[str, dict] = {}  # star_id → {bene_id → {min_boost, pts_boost, ...}}

    for season in seasons:
        all_logs = _load_all_gamelogs(season)
        if not all_logs:
            continue

        # Identify stars by season avg minutes
        star_ids: set[int] = set()
        player_season_avg: dict[int, float] = {}
        for pid, logs in all_logs.items():
            played = [g for g in logs if _parse_min(g.get("min", 0)) > 0]
            if len(played) >= 20:
                avg_min = np.mean([_parse_min(g["min"]) for g in played])
                player_season_avg[pid] = float(avg_min)
                if avg_min >= _STAR_MIN_THRESHOLD:
                    star_ids.add(pid)

        log.debug("Season %s: %d stars identified", season, len(star_ids))

        # Group gamelogs by game_id
        # Build game → {player_id: min} lookup
        game_player_min: dict[str, dict[int, float]] = defaultdict(dict)
        game_player_pts: dict[str, dict[int, float]] = defaultdict(dict)
        for pid, logs in all_logs.items():
            for g in logs:
                gid = g.get("game_id", "")
                if gid:
                    m = _parse_min(g.get("min", 0))
                    game_player_min[gid][pid] = m if m == m else 0.0
                    game_player_pts[gid][pid] = float(g.get("pts", 0) or 0)

        # Build team → set of game_ids lookup so we can infer absences
        # matchup field: "GSW vs. LAL" or "GSW @ LAL" — first token is player's team
        team_games: dict[str, set[str]] = defaultdict(set)
        for pid, logs in all_logs.items():
            for g in logs:
                gid = g.get("game_id", "")
                matchup = str(g.get("matchup", "") or "")
                team = matchup.split(" ")[0] if matchup else ""
                if gid and team:
                    team_games[team].add(gid)

        # For each star, find games they played vs DNP
        for star_id in star_ids:
            star_logs = all_logs.get(star_id, [])
            if not star_logs:
                continue

            # Identify star's team from last game matchup
            played_games  = [(g, _parse_min(g.get("min", 0))) for g in star_logs]
            played_only   = [g for g, m in played_games if m > 0]
            dnp_only      = [g for g, m in played_games if m == 0.0 or m != m]  # 0.0 or NaN (min=None = DNP)

            # Fallback: infer DNPs from team schedule when explicit min=0 entries are absent
            if len(dnp_only) < 3 and played_only:
                star_team = str(played_only[-1].get("matchup", "")).split(" ")[0]
                played_gids = {g.get("game_id", "") for g in played_only if g.get("game_id")}
                team_gid_set = team_games.get(star_team, set())
                inferred_dnp_gids = team_gid_set - played_gids
                # Build stub game dicts for inferred DNPs (only game_id needed downstream)
                dnp_only = dnp_only + [{"game_id": gid} for gid in inferred_dnp_gids]

            if len(played_only) < 10 or len(dnp_only) < 3:
                continue

            star_avg_min = float(np.mean([_parse_min(g.get("min", 1)) for g in played_only]))

            # Average teammate minutes on played vs DNP games
            bene_gains: dict[int, list[float]] = defaultdict(list)
            bene_pts_gains: dict[int, list[float]] = defaultdict(list)

            for dnp_game in dnp_only:
                gid = dnp_game.get("game_id", "")
                if not gid:
                    continue
                # Get all players who played in this game
                game_mins = game_player_min.get(gid, {})
                game_pts  = game_player_pts.get(gid, {})

                for pid, actual_min in game_mins.items():
                    if pid == star_id or actual_min <= 0:
                        continue
                    # What does this player avg on normal played games?
                    normal_avg = player_season_avg.get(pid, 15.0)
                    gain = actual_min - normal_avg
                    if abs(gain) < 20:  # sanity filter
                        bene_gains[pid].append(gain)
                        pts_gain = game_pts.get(pid, 0.0) - float(
                            np.mean([float(g.get("pts", 0) or 0)
                                     for g in all_logs.get(pid, [])[-20:]]) or 0
                        )
                        bene_pts_gains[pid].append(pts_gain)

            if not bene_gains:
                continue

            star_key = str(star_id)
            cascade[star_key] = {}
            for bene_id, gains in bene_gains.items():
                if len(gains) < 2:
                    continue
                avg_gain = float(np.mean(gains))
                if avg_gain > 0.5:  # only record positive beneficiaries
                    cascade[star_key][str(bene_id)] = {
                        "min_boost":   round(avg_gain, 1),
                        "pts_boost":   round(float(np.mean(bene_pts_gains.get(bene_id, [0]))), 2),
                        "games_dnp":   len(gains),
                        "star_avg_min": round(star_avg_min, 1),
                    }

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"cascade": cascade, "version": "1.0"}, f)

    total_stars = len(cascade)
    total_benes = sum(len(v) for v in cascade.values())
    log.info("Beneficiary cascade built: %d stars, %d beneficiary relationships",
             total_stars, total_benes)
    return {"stars": total_stars, "beneficiaries": total_benes}


def _load_model() -> dict:
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    log.info("beneficiary_cascade.pkl not found — building now (may take 60s)")
    build_cascade_table()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            return pickle.load(f)
    return {"cascade": {}}


_MODEL_CACHE: Optional[dict] = None


def get_beneficiary_boost(player_id: int, team: str, dnp_star_id: int) -> float:
    """
    Return expected minutes boost for player_id when dnp_star_id sits.
    Returns 0.0 if no relationship found.
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _load_model()
    cascade = _MODEL_CACHE.get("cascade", {})
    star_entry = cascade.get(str(dnp_star_id), {})
    bene_entry = star_entry.get(str(player_id), {})
    return float(bene_entry.get("min_boost", 0.0))


def predict_beneficiary_boost(
    team_abbrev: str,
    dnp_player_ids: list[int],
    all_player_ids: list[int],
) -> dict[int, dict]:
    """
    Given a list of DNP players, return {player_id: {min_boost, pts_boost}}
    for all beneficiaries on the same team.

    Args:
        team_abbrev:    Team abbreviation (e.g. 'GSW').
        dnp_player_ids: List of player_ids who are expected to DNP.
        all_player_ids: All rostered player_ids to check.

    Returns:
        {player_id: {min_boost, pts_boost, source_star_ids}}
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _load_model()

    cascade = _MODEL_CACHE.get("cascade", {})
    boosts: dict[int, dict] = {}

    for star_id in dnp_player_ids:
        star_entry = cascade.get(str(star_id), {})
        for bene_id_str, info in star_entry.items():
            bene_id = int(bene_id_str)
            if bene_id not in all_player_ids:
                continue
            if bene_id not in boosts:
                boosts[bene_id] = {"min_boost": 0.0, "pts_boost": 0.0, "source_star_ids": []}
            boosts[bene_id]["min_boost"]       += info.get("min_boost", 0.0)
            boosts[bene_id]["pts_boost"]        += info.get("pts_boost", 0.0)
            boosts[bene_id]["source_star_ids"].append(star_id)

    return boosts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(build_cascade_table())
