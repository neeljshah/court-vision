"""Lineup/synergy/gravity, concession-matchup, and shooting-luck sections.
Same not_available contract as sections_team.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.gamebrief import sources, team_ids

_NA = {"status": "not_available"}
_MIN_LINEUP_MIN = 24.0  # >=~half a game of shared minutes before citing a lineup


def gravity_leaders(team_id: Optional[int], top_n: int = 3) -> Dict:
    df = sources.gravity_proxy()
    if df is None or team_id is None:
        return dict(_NA, reason="gravity_proxy parquet or team_id missing")
    d = df[df["team_id"] == team_id].sort_values("gravity_proxy", ascending=False).head(top_n)
    if d.empty:
        return dict(_NA, reason="no gravity rows for this team")
    return {"status": "ok", "leaders": [
        {"player_name": r.player_name, "gravity_proxy": round(float(r.gravity_proxy), 4),
         "teammate_efg_on": round(float(r.teammate_efg_on), 4),
         "teammate_efg_off": round(float(r.teammate_efg_off), 4)}
        for r in d.itertuples()
    ]}


def lineup_synergy_top(team_id: Optional[int], top_n: int = 3) -> Dict:
    df = sources.lineup_synergy()
    if df is None or team_id is None:
        return dict(_NA, reason="lineup_synergy parquet or team_id missing")
    d = df[(df["team_id"] == team_id) & (df["min"] >= _MIN_LINEUP_MIN)]
    if d.empty:
        return dict(_NA, reason=f"no lineup with >={_MIN_LINEUP_MIN} shared minutes")
    d = d.sort_values("synergy_residual", ascending=False).head(top_n)
    return {"status": "ok", "lineups": [
        {"lineup_key": r.lineup_key, "minutes": round(float(r.min), 1),
         "net_per48": round(float(r.net_per48), 2),
         "synergy_residual": round(float(r.synergy_residual), 2)}
        for r in d.itertuples()
    ]}


def on_off_top(team_id: Optional[int], top_n: int = 3) -> Dict:
    df = sources.on_off()
    if df is None or team_id is None:
        return dict(_NA, reason="on_off parquet or team_id missing")
    d = df[(df["team_id"] == team_id) & (df["min_on"] >= 200) & (df["min_off"] >= 50)].copy()
    if d.empty:
        return dict(_NA, reason="no player clears the minutes floor for on/off")
    d["net_swing"] = d["net_rating_on_per48"] - d["net_rating_off_per48"]
    d = d.sort_values("net_swing", ascending=False).head(top_n)
    return {"status": "ok", "players": [
        {"player_name": r.player_name, "net_on_per48": round(float(r.net_rating_on_per48), 2),
         "net_off_per48": round(float(r.net_rating_off_per48), 2),
         "net_swing": round(float(r.net_swing), 2)}
        for r in d.itertuples()
    ]}


def _concession_row(team_id: Optional[int]) -> Optional[pd.Series]:
    df = sources.concession()
    if df is None or team_id is None:
        return None
    d = df[df["defense_team_id"] == team_id]
    return None if d.empty else d.iloc[0]


def _rank_desc(df: pd.DataFrame, col: str, team_id: int) -> Optional[int]:
    """1 = worst (highest allowed) defense in the league on `col`."""
    ranked = df.sort_values(col, ascending=False).reset_index(drop=True)
    hit = ranked.index[ranked["defense_team_id"] == team_id]
    return None if len(hit) == 0 else int(hit[0]) + 1


def concession_matchup(home: str, away: str, home_id: Optional[int], away_id: Optional[int]) -> Dict:
    df = sources.concession()
    if df is None:
        return dict(_NA, reason="concession parquet not found")
    n = len(df)
    out: Dict[str, Any] = {"status": "ok", "league_size": n, "sides": {}}
    for label, team, tid in ((home, home, home_id), (away, away, away_id)):
        row = _concession_row(tid)
        if row is None:
            out["sides"][team] = {"status": "not_available", "reason": "no concession row for this team_id"}
            continue
        out["sides"][team] = {
            "status": "ok",
            "overall_efg_allowed": round(float(row["overall_efg_allowed"]), 4),
            "overall_efg_allowed_rank_worst_to_best": _rank_desc(df, "overall_efg_allowed", tid),
            "rim_efg_allowed": round(float(row["rim_efg_allowed"]), 4),
            "rim_efg_allowed_rank_worst_to_best": _rank_desc(df, "rim_efg_allowed", tid),
            "rim_share_allowed": round(float(row["rim_share_allowed"]), 4),
            "above_break_3_efg_allowed": round(float(row["above_break_3_efg_allowed"]), 4),
        }
    # Shot-diet half of the matchup: only available where the narrow team_game
    # zone sample happens to cover this team (verified: NYK/SAS only) -- an
    # honest, explicit gap rather than a fabricated league-wide diet number.
    zone = sources.team_game_zone_sample()
    diets: Dict[str, Any] = {}
    for team in (home, away):
        if zone is None or team not in set(zone["team"].unique()):
            diets[team] = {"status": "not_available",
                           "reason": "shot-zone attempt data only covers a narrow team_game sample"}
            continue
        d = zone[zone["team"] == team]
        fga = d["fga"].sum()
        diets[team] = {"status": "ok", "n_games": int(len(d)),
                       "rim_share": round(float(d["rim_fga"].sum() / fga), 4) if fga else None,
                       "mid_share": round(float(d["mid_fga"].sum() / fga), 4) if fga else None,
                       "fg3_share": round(float(d["fg3a"].sum() / fga), 4) if fga else None}
    out["shot_diet"] = diets
    return out


def shooting_luck(team_id: Optional[int], games_df: Optional[pd.DataFrame], asof_date: Any, n: int = 5) -> Dict:
    df = sources.shot_xpts()
    if df is None or team_id is None or games_df is None:
        return dict(_NA, reason="shot_xpts parquet, team_id, or games.parquet missing")
    date_by_gid = dict(zip(games_df["game_id"].astype(str), games_df["date"]))
    d = df[df["team_id"] == team_id].copy()
    d["date"] = d["game_id"].astype(str).map(date_by_gid)
    d = d.dropna(subset=["date"])
    d = d[d["date"] < pd.Timestamp(asof_date)].sort_values("date", ascending=False).head(n)
    if d.empty:
        return dict(_NA, reason=f"no shot_xpts games before {asof_date} for this team")
    return {
        "status": "ok", "n_games": int(len(d)),
        "avg_xpts": round(float(d["xpts"].mean()), 2),
        "avg_actual_pts": round(float(d["actual_pts"].mean()), 2),
        "avg_luck": round(float(d["luck"].mean()), 2),
    }
