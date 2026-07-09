"""PLAYER foul/free-throw attribute computation: pf_per36 (box-derived,
already-verified boxscore 'pf' column -- no PBP text-parsing needed) +
opp_ft_rate_allowed_on/off (PBP freethrow events, defending-team tagged the
same way zone_onoff.py tags shots, merged against zone_onoff's own
opp_fga_on/off so the free-points-conceded rate shares that file's
qualified population).

NETWORK: zero.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_nba.lineups.pbp_lineups import _elapsed_s
from domains.basketball_nba.lineups.zone_onoff import _PBP_BY_SEASON
from domains.basketball_nba.profiles.player_rebounding import _dedup_trade, _on_off_by_player
from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_BOX_SEASONS = {"2024_25", "2025_26"}


def _window(season: str) -> str:
    return f"season_{season}"


def load_defense_tagged_freethrows(game_json: dict[str, Any]) -> pd.DataFrame:
    """One row per FT ATTEMPT, keyed on the DEFENDING team_id -- same
    get-the-side-right convention as zone_onoff.load_shot_events."""
    game_id = game_json["game"]["gameId"]
    actions = game_json["game"]["actions"]
    team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
    rows = []
    for a in actions:
        if a.get("actionType") != "freethrow" or not a.get("teamId"):
            continue
        offense = a["teamId"]
        defense = next((t for t in team_ids if t != offense), None)
        if defense is None:
            continue
        rows.append({
            "game_id": game_id, "team_id": defense, "period": a["period"],
            "elapsed_s": _elapsed_s(a["period"], a["clock"]), "fta": 1,
        })
    return pd.DataFrame(rows)


def build_player_fouls_per36(season: str) -> list[dict]:
    if season not in _BOX_SEASONS or not _BOX.exists():
        return []
    box = pd.read_parquet(_BOX)
    box = box[box["season"] == season.replace("_", "-")]
    box = exclude_negative_ids(box, "player_id")
    grp = box.groupby("player_id").agg(
        pf=("pf", "sum"), min=("min", "sum"), entity_name=("player_name", "first"),
    ).reset_index()
    grp = grp[grp["min"] >= 200.0].copy()
    grp["raw_value"] = grp["pf"] / grp["min"] * 36.0
    return finalize_rows(
        grp, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="pf_per36", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["pf", "min"], higher_is_better=False,  # fewer fouls is "better" for a rating direction
    )


def build_opp_ft_rate_allowed(season: str) -> list[dict]:
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    zone_src = _LINEUPS / f"zone_onoff_{season}.parquet"
    if not stints_src.exists() or not zone_src.exists():
        return []
    stints = pd.read_parquet(stints_src)
    pbp_dir = _PBP_BY_SEASON[season]

    frames = []
    for gid in stints["game_id"].unique():
        fp = pbp_dir / f"{gid}.json"
        if fp.exists():
            frames.append(load_defense_tagged_freethrows(json.loads(fp.read_text(encoding="utf-8"))))
    fts = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["game_id", "team_id", "period", "elapsed_s", "fta"])
    if fts.empty:
        return []
    fts = attach_lineup_to_shots(stints, fts)
    ft_agg = _dedup_trade(_on_off_by_player(stints, fts, "fta"))

    zone = pd.read_parquet(zone_src).sort_values("min_on", ascending=False).drop_duplicates("player_id", keep="first")
    d = ft_agg.merge(zone[["player_id", "player_name", "opp_fga_on", "opp_fga_off"]], on="player_id", how="inner")
    d = d[(d["min_on"] >= 750.0) & (d["min_off"] >= 750.0)].copy()
    if d.empty:
        return []
    d["opp_ft_rate_allowed_on"] = d["fta_on"] / d["opp_fga_on"]
    d["opp_ft_rate_allowed_off"] = d["fta_off"] / d["opp_fga_off"]

    rows: list[dict] = []
    for side in ("on", "off"):
        n_col = f"min_{side}"
        rows.extend(finalize_rows(
            d, entity_col="player_id", name_col="player_name", raw_col=f"opp_ft_rate_allowed_{side}", n_col=n_col,
            window=_window(season), attribute=f"opp_ft_rate_allowed_{side}", status="DESCRIPTIVE",
            sources=rel_sources(stints_src, zone_src), ingredient_cols=[f"fta_{side}", f"opp_fga_{side}"],
            higher_is_better=False,
        ))
    return rows


BUILDERS = [build_player_fouls_per36, build_opp_ft_rate_allowed]


def build_all_player_fouls_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
