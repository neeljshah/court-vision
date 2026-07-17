"""TEAM attribute expansion, part 2: clutch net/off/def points per game
(period>=4, remaining<=300s, |margin|<=10 -- same clutch definition the
sibling player_offense_zones.py lane uses for its clutch_* player
attributes). A points-per-game proxy, NOT a true per-48 rate: computing
actual clutch on-court minutes needs joint roster+running-score tracking
this lane does not have time to build (documented honestly, not silently
approximated as more precise than it is).

NETWORK: zero.
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.lineups.pbp_lineups import _elapsed_s, _period_length_s
from domains.basketball_nba.lineups.zone_onoff import _PBP_BY_SEASON
from domains.basketball_nba.profiles.profile_compute import REPO_ROOT, finalize_rows, rel_sources
from domains.basketball_nba.profiles.team_attributes import _team_id_to_name

_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
CLUTCH_REMAINING_S = 300.0  # 5 min
CLUTCH_MARGIN = 10.0


def _window(season: str) -> str:
    return f"season_{season}"


def _pts_value(action_type: str) -> int:
    return 3 if action_type == "3pt" else (1 if action_type == "freethrow" else 2)


def build_clutch(season: str) -> list[dict]:
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    if not stints_src.exists():
        return []
    stints = pd.read_parquet(stints_src)
    pbp_dir = _PBP_BY_SEASON[season]

    scoring_rows, game_team_ids = [], {}
    for gid in stints["game_id"].unique():
        fp = pbp_dir / f"{gid}.json"
        if not fp.exists():
            continue
        actions = json.loads(fp.read_text(encoding="utf-8"))["game"]["actions"]
        team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
        game_team_ids[gid] = team_ids
        for a in actions:
            if (a.get("actionType") not in ("2pt", "3pt", "freethrow") or a.get("shotResult") != "Made"
                    or not a.get("teamId") or a.get("scoreHome") is None):
                continue
            period = a["period"]
            remaining = _period_length_s(period) - _elapsed_s(period, a["clock"])
            margin = abs(int(a["scoreHome"]) - int(a["scoreAway"]))
            if period >= 4 and remaining <= CLUTCH_REMAINING_S and margin <= CLUTCH_MARGIN:
                scoring_rows.append({"game_id": gid, "team_id": a["teamId"], "pts": _pts_value(a["actionType"])})

    if not game_team_ids:
        return []
    grid = pd.DataFrame([(gid, tid) for gid, tids in game_team_ids.items() for tid in tids],
                        columns=["game_id", "team_id"])
    per_game_team = pd.DataFrame(scoring_rows, columns=["game_id", "team_id", "pts"])
    if not per_game_team.empty:
        per_game_team = per_game_team.groupby(["game_id", "team_id"])["pts"].sum().reset_index()
    grid = grid.merge(per_game_team, on=["game_id", "team_id"], how="left")
    grid["pts"] = grid["pts"].fillna(0.0)

    paired = grid.merge(grid, on="game_id", suffixes=("_for", "_against"))
    paired = paired[paired["team_id_for"] != paired["team_id_against"]]
    if paired.empty:
        return []
    agg = paired.groupby("team_id_for").agg(
        pts_for=("pts_for", "mean"), pts_against=("pts_against", "mean"), n_games=("game_id", "nunique"),
    ).reset_index().rename(columns={"team_id_for": "team_id"})
    agg = agg[agg["n_games"] >= 10.0].copy()
    if agg.empty:
        return []
    agg["net"] = agg["pts_for"] - agg["pts_against"]
    agg["entity_name"] = agg["team_id"].map(_team_id_to_name()).fillna("")

    rows: list[dict] = []
    for attr, col, higher_better in (
        ("clutch_net_pts_per_game", "net", True),
        ("clutch_off_pts_per_game", "pts_for", True),
        ("clutch_def_pts_per_game", "pts_against", False),
    ):
        rows.extend(finalize_rows(
            agg, entity_col="team_id", name_col="entity_name", raw_col=col, n_col="n_games",
            window=_window(season), attribute=attr, status="DESCRIPTIVE",
            sources=rel_sources(stints_src), ingredient_cols=["pts_for", "pts_against"],
            higher_is_better=higher_better,
        ))
    return rows


BUILDERS = [build_clutch]


def build_all_team_clutch_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
