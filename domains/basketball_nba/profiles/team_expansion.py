"""TEAM attribute expansion, part 1: offensive shot-zone diet (all 5 zones,
3 seasons, built straight from PBP x/y -- classify_zone), home/away net
rating splits, and avg_defensive_continuity_s (team-grain expression of the
replicated h7 stint-continuity-x-DREB mechanism, reusing
nba_hypotheses.build_continuity_dreb_tagged verbatim). See team_clutch.py
for the clutch-window builder and team_box_splits.py for the box-derived
bench/rebounding/foul builders -- split across files to stay under the
300-LOC/file rail.

NETWORK: zero.
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.composition.zone_geometry import ZONES, classify_zone
from domains.basketball_nba.lineups.zone_onoff import _PBP_BY_SEASON
from domains.basketball_nba.prereg.nba_hypotheses import build_continuity_dreb_tagged
from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, finalize_rows, rel_sources,
)
from domains.basketball_nba.profiles.team_attributes import _tricode_to_team_id

_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_GAMES = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_THREE_ZONES = {"corner3", "above_break_3"}


def _window(season: str) -> str:
    return f"season_{season}"


def build_zone_offense_diet(season: str) -> list[dict]:
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    if not stints_src.exists():
        return []
    stints = pd.read_parquet(stints_src)
    pbp_dir = _PBP_BY_SEASON[season]

    rows = []
    for gid in stints["game_id"].unique():
        fp = pbp_dir / f"{gid}.json"
        if not fp.exists():
            continue
        for a in json.loads(fp.read_text(encoding="utf-8"))["game"]["actions"]:
            if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId") or a.get("x") is None:
                continue
            is_3 = a["actionType"] == "3pt"
            rows.append({
                "game_id": gid, "team_id": a["teamId"],
                "zone": classify_zone(float(a["x"]), float(a["y"]), is_3),
                "fgm": 1 if a.get("shotResult") == "Made" else 0, "fga": 1,
            })
    if not rows:
        return []
    df = pd.DataFrame(rows)
    n_games = df.groupby("team_id")["game_id"].nunique().rename("n_games")
    total_fga = df.groupby("team_id")["fga"].sum().rename("total_fga")

    out_rows: list[dict] = []
    for zone in ZONES:
        mult = 1.5 if zone in _THREE_ZONES else 1.0
        zg = df[df["zone"] == zone].groupby("team_id").agg(fga=("fga", "sum"), fgm=("fgm", "sum"))
        zg = zg.reindex(n_games.index, fill_value=0)
        d = pd.concat([n_games, total_fga, zg], axis=1).reset_index()
        d = d[d["n_games"] >= 10.0].copy()
        if d.empty:
            continue
        d["share"] = d["fga"] / d["total_fga"]
        d["efg"] = (mult * d["fgm"] / d["fga"]).where(d["fga"] > 0)
        d["fga_per_game"] = d["fga"] / d["n_games"]
        for metric, col in (("share", "share"), ("efg", "efg"), ("fga_per_game", "fga_per_game")):
            sub = d.dropna(subset=[col])
            out_rows.extend(finalize_rows(
                sub, entity_col="team_id", name_col=None, raw_col=col, n_col="n_games",
                window=_window(season), attribute=f"zone_offense_{zone}_{metric}", status="DESCRIPTIVE",
                sources=rel_sources(stints_src), ingredient_cols=["fga", "fgm", "total_fga"],
            ))
    return out_rows


def build_home_away_net_rating(season: str) -> list[dict]:
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    if not stints_src.exists() or not _GAMES.exists():
        return []
    stints = pd.read_parquet(stints_src)
    crosswalk = _tricode_to_team_id()  # tricode -> team_id is franchise-stable across seasons
    label = season.replace("_", "-")
    games = pd.read_parquet(_GAMES, columns=["game_id", "season", "home_team"])
    games = games[games["season"] == label].copy()
    games["home_team_id"] = games["home_team"].map(crosswalk)
    home_by_game = dict(zip(games["game_id"].astype(str), games["home_team_id"]))
    valid_games = {gid for gid, v in home_by_game.items() if pd.notna(v)}
    if not valid_games:
        return []

    team_game = stints.groupby(["game_id", "team_id"]).agg(
        pts_for=("pts_for", "sum"), pts_against=("pts_against", "sum"), elapsed_s=("elapsed_s", "sum"),
    ).reset_index()
    team_game = team_game[team_game["game_id"].astype(str).isin(valid_games)].copy()
    team_game["is_home"] = team_game.apply(
        lambda r: home_by_game[str(r["game_id"])] == r["team_id"], axis=1)

    rows: list[dict] = []
    splits = {}
    for side, mask_val in (("home", True), ("away", False)):
        g = team_game[team_game["is_home"] == mask_val].groupby("team_id").agg(
            pts_for=("pts_for", "sum"), pts_against=("pts_against", "sum"),
            elapsed_s=("elapsed_s", "sum"), n_games=("game_id", "nunique"),
        ).reset_index()
        g = g[(g["n_games"] >= 10.0) & (g["elapsed_s"] > 0)].copy()
        g["raw_value"] = (g["pts_for"] - g["pts_against"]) / g["elapsed_s"] * 48.0 * 60.0
        splits[side] = g.set_index("team_id")["raw_value"]
        rows.extend(finalize_rows(
            g, entity_col="team_id", name_col=None, raw_col="raw_value", n_col="n_games",
            window=_window(season), attribute=f"net_rating_{side}", status="DESCRIPTIVE",
            sources=rel_sources(stints_src, _GAMES), ingredient_cols=["pts_for", "pts_against", "elapsed_s"],
        ))

    if not splits["home"].empty and not splits["away"].empty:
        diff = (splits["home"] - splits["away"]).dropna().rename("raw_value").reset_index()
        n_games_both = team_game.groupby("team_id")["game_id"].nunique().rename("n_games").reset_index()
        diff = diff.merge(n_games_both, on="team_id", how="left")
        rows.extend(finalize_rows(
            diff, entity_col="team_id", name_col=None, raw_col="raw_value", n_col="n_games",
            window=_window(season), attribute="net_rating_home_away_diff", status="DESCRIPTIVE",
            sources=rel_sources(stints_src, _GAMES), ingredient_cols=[],
        ))
    return rows


def build_defensive_continuity(season: str) -> list[dict]:
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    if not stints_src.exists():
        return []
    stints = pd.read_parquet(stints_src)
    pbp_dir = _PBP_BY_SEASON[season]
    tagged = build_continuity_dreb_tagged(stints, pbp_dir=pbp_dir)
    if tagged.empty:
        return []
    grp = tagged.groupby("team_id").agg(raw_value=("continuity_s", "mean"), n=("continuity_s", "count")).reset_index()
    grp = grp[grp["n"] >= 50.0]
    return finalize_rows(
        grp, entity_col="team_id", name_col=None, raw_col="raw_value", n_col="n",
        window=_window(season), attribute="avg_defensive_continuity_s", status="VALIDATED_MECHANISM",
        sources=rel_sources(stints_src), ingredient_cols=["n"],
    )


BUILDERS = [build_zone_offense_diet, build_home_away_net_rating, build_defensive_continuity]


def build_all_team_expansion_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
