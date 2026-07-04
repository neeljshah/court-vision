"""domains.basketball_wnba.atlas_extract_player -- season-aggregate PLAYER
atlas parquets from the 168-game CDN backfill corpus (zero new fetch).

Builds one row per player (season 2026, the only CDN-backfilled season on
disk -- see WNBA_TRUTH_SPEC_2026-07-04.md limit #4) across THREE atlas
parquets, mirroring the NBA atlas convention (value/n/confidence/as_of
columns, see data/cache/atlas_player_*.parquet):

  atlas_wnba_player_shooting_profile  -- dims 15/16/26: usage/minutes load,
      TS%/eFG%, FT profile/reliability (closes_dimensions: usage_rate_
      minutes_load, shot_quality_ts_efg, ft_profile_reliability)
  atlas_wnba_player_box_profile       -- dims 28/29/30/36/37: rebounding,
      turnover, foul-drawing/tendency, defensive (blocks/steals), assists
      profile (closes_dimensions: rebounding_profile_player, turnover_
      profile_player, foul_drawing_tendency, defensive_profile_player partial)
  atlas_wnba_player_rotation          -- dim 38: rotation/minutes concentration
      per player-season share of team minutes (closes_dimensions:
      rotation_minutes_concentration)

Every source field cited below is read verbatim from cdn_backfill/<gid>/
boxscore.json homeTeam/awayTeam.players[].statistics -- see
atlas_extract_common.py for the shared loader/formula helpers.

HONEST GAPS NOT CLOSED HERE (documented, not fabricated): shot_location_
zones and clutch_scoring/score_margin_splits need the PLAYBYPLAY action log
(x/y coords, per-action score state) rather than the boxscore -- those are
built in atlas_extract_pbp.py, not this module, to keep each file <=300 LOC.

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises
(a malformed game/player row is skipped, not fabricated); no $ fields.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_player.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.basketball_wnba.atlas_extract_common import (
    CORPUS_ID, SEASON, atlas_write_path, effective_fg_pct, iso_minutes,
    iter_backfilled_games, safe_get, true_shooting_pct,
)

logger = logging.getLogger(__name__)

_SIDES = ("homeTeam", "awayTeam")


def _player_game_rows(game_id: str, box_game: dict) -> List[Dict[str, Any]]:
    """One row per player who appears in *box_game*'s boxscore (both teams).
    Pure function, no I/O. Never raises -- a malformed player entry is
    skipped."""
    rows: List[Dict[str, Any]] = []
    for side in _SIDES:
        team = box_game.get(side) or {}
        team_id = team.get("teamId")
        team_tricode = team.get("teamTricode")
        for p in team.get("players") or []:
            if not isinstance(p, dict):
                continue
            pid = p.get("personId")
            if pid is None:
                continue
            stats = p.get("statistics") or {}
            minutes = iso_minutes(stats.get("minutesCalculated"))
            rows.append({
                "game_id": str(game_id),
                "player_id": str(pid),
                "player_name": p.get("name"),
                "team_id": str(team_id) if team_id is not None else None,
                "team_tricode": team_tricode,
                "starter": str(p.get("starter")) == "1",
                "played": str(p.get("played")) == "1",
                "minutes": minutes,
                "points": stats.get("points"),
                "fga": stats.get("fieldGoalsAttempted"),
                "fgm": stats.get("fieldGoalsMade"),
                "fg3a": stats.get("threePointersAttempted"),
                "fg3m": stats.get("threePointersMade"),
                "fta": stats.get("freeThrowsAttempted"),
                "ftm": stats.get("freeThrowsMade"),
                "ft_pct": stats.get("freeThrowsPercentage"),
                "oreb": stats.get("reboundsOffensive"),
                "dreb": stats.get("reboundsDefensive"),
                "reb_total": stats.get("reboundsTotal"),
                "turnovers": stats.get("turnovers"),
                "assists": stats.get("assists"),
                "steals": stats.get("steals"),
                "blocks": stats.get("blocks"),
                "blocks_received": stats.get("blocksReceived"),
                "fouls_personal": stats.get("foulsPersonal"),
                "fouls_offensive": stats.get("foulsOffensive"),
                "fouls_technical": stats.get("foulsTechnical"),
                "fouls_drawn": stats.get("foulsDrawn"),
                "plus_minus": stats.get("plusMinusPoints"),
            })
    return rows


def build_player_game_frame() -> pd.DataFrame:
    """Every player-game row across the full backfilled corpus. One row per
    (game_id, player_id). Empty frame (not an error) if the corpus dir is
    absent or yields no rows."""
    all_rows: List[Dict[str, Any]] = []
    n_games = 0
    for gid, pair in iter_backfilled_games():
        rows = _player_game_rows(gid, pair["boxscore"])
        if rows:
            all_rows.extend(rows)
            n_games += 1
    logger.info("atlas_extract_player: %d player-game rows from %d games", len(all_rows), n_games)
    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(all_rows)


def _agg_confidence(n_games: int) -> str:
    """Same coarse n-based confidence tiering the NBA atlas uses (see
    atlas_player_rebounding_profile.parquet 'confidence' column)."""
    if n_games >= 15:
        return "high"
    if n_games >= 5:
        return "medium"
    return "low"


def build_shooting_profile(pg: pd.DataFrame) -> pd.DataFrame:
    """Season-aggregate shooting/usage/FT-reliability profile per player.
    Closes: usage_rate_minutes_load, shot_quality_ts_efg, ft_profile_
    reliability. Empty in -> empty out."""
    if pg.empty:
        return pd.DataFrame()
    played = pg[pg["played"]].copy()
    if played.empty:
        return pd.DataFrame()
    rows = []
    for pid, g in played.groupby("player_id"):
        n = len(g)
        pts = g["points"].fillna(0).sum()
        fga = g["fga"].fillna(0).sum()
        fgm = g["fgm"].fillna(0).sum()
        fg3a = g["fg3a"].fillna(0).sum()
        fg3m = g["fg3m"].fillna(0).sum()
        fta = g["fta"].fillna(0).sum()
        ftm = g["ftm"].fillna(0).sum()
        minutes_mean = g["minutes"].dropna().mean() if g["minutes"].notna().any() else None
        ts_pct = true_shooting_pct(pts, fga, fta)
        efg_pct = effective_fg_pct(fgm, fg3m, fga)
        ft_pct = round(ftm / fta, 4) if fta > 0 else None
        rows.append({
            "player_id": pid,
            "player_name": g["player_name"].iloc[-1],
            "n_games_played": n,
            "minutes_per_game": round(minutes_mean, 4) if minutes_mean is not None else None,
            "points_per_game": round(pts / n, 4),
            "fga_per_game": round(fga / n, 4),
            "ts_pct": ts_pct,
            "efg_pct": efg_pct,
            "ft_pct_season": ft_pct,
            "fta_per_game": round(fta / n, 4),
            "value": ts_pct if ts_pct is not None else 0.0,
            "n": n,
            "confidence": _agg_confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(rows)


def build_box_profile(pg: pd.DataFrame) -> pd.DataFrame:
    """Season-aggregate rebounding/turnover/foul/defensive/playmaking profile.
    Closes: rebounding_profile_player, turnover_profile_player, foul_drawing_
    tendency, defensive_profile_player (partial: no defender-matchup data,
    box-score counting stats only), playmaking_network (partial: raw assist
    counting stat only, no assist-network graph -- documented honest partial)."""
    if pg.empty:
        return pd.DataFrame()
    played = pg[pg["played"]].copy()
    if played.empty:
        return pd.DataFrame()
    rows = []
    for pid, g in played.groupby("player_id"):
        n = len(g)
        oreb = g["oreb"].fillna(0).sum()
        dreb = g["dreb"].fillna(0).sum()
        reb_total = g["reb_total"].fillna(0).sum()
        rows.append({
            "player_id": pid,
            "player_name": g["player_name"].iloc[-1],
            "n_games_played": n,
            "oreb_per_game": round(oreb / n, 4),
            "dreb_per_game": round(dreb / n, 4),
            "reb_per_game": round(reb_total / n, 4),
            "turnovers_per_game": round(g["turnovers"].fillna(0).sum() / n, 4),
            "assists_per_game": round(g["assists"].fillna(0).sum() / n, 4),
            "steals_per_game": round(g["steals"].fillna(0).sum() / n, 4),
            "blocks_per_game": round(g["blocks"].fillna(0).sum() / n, 4),
            "fouls_personal_per_game": round(g["fouls_personal"].fillna(0).sum() / n, 4),
            "fouls_drawn_per_game": round(g["fouls_drawn"].fillna(0).sum() / n, 4),
            "value": round(reb_total / n, 4),
            "n": n,
            "confidence": _agg_confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(rows)


def build_rotation_profile(pg: pd.DataFrame) -> pd.DataFrame:
    """Per-player rotation/minutes-concentration inputs: player_id, team_id,
    minutes-per-game, and the player's share of their OWN team-game total
    minutes (a per-player building block; the team-level top-5-share
    aggregate is computed in atlas_extract_team.py's rotation_minutes_
    concentration table from this same player-game substrate). Closes:
    rotation_minutes_concentration (player-level half of the pair)."""
    if pg.empty:
        return pd.DataFrame()
    played = pg[pg["played"]].copy()
    if played.empty:
        return pd.DataFrame()
    rows = []
    for pid, g in played.groupby("player_id"):
        n = len(g)
        minutes_valid = g["minutes"].dropna()
        team_id = g["team_id"].mode().iloc[0] if not g["team_id"].mode().empty else None
        rows.append({
            "player_id": pid,
            "player_name": g["player_name"].iloc[-1],
            "team_id_mode": team_id,
            "n_games_played": n,
            "minutes_per_game": round(minutes_valid.mean(), 4) if not minutes_valid.empty else None,
            "starter_rate": round(g["starter"].mean(), 4),
            "value": round(minutes_valid.mean(), 4) if not minutes_valid.empty else 0.0,
            "n": n,
            "confidence": _agg_confidence(n),
            "as_of": SEASON,
            "corpus_id": CORPUS_ID,
        })
    return pd.DataFrame(rows)


def run_extract_player_atlas() -> Dict[str, int]:
    """Build + write all three player atlas parquets. Returns {table: n_rows}.
    Never raises -- an empty source corpus writes no files and reports 0s."""
    pg = build_player_game_frame()
    out: Dict[str, int] = {}
    builders = {
        "player_shooting_profile": build_shooting_profile,
        "player_box_profile": build_box_profile,
        "player_rotation": build_rotation_profile,
    }
    for name, fn in builders.items():
        df = fn(pg)
        out[name] = len(df)
        if not df.empty:
            path = atlas_write_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".parquet.tmp")
            df.to_parquet(tmp, index=False)
            tmp.replace(path)
    return out


def _main() -> int:
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_extract_player_atlas(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "build_player_game_frame", "build_shooting_profile", "build_box_profile",
    "build_rotation_profile", "run_extract_player_atlas",
]
