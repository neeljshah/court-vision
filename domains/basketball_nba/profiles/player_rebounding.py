"""PLAYER rebounding attribute computation: OREB%/DREB% while on-floor
(opportunity proxy = team's-own-misses / opponent's-misses while the player
was on-court, per the lane brief) + team_dreb_pct_swing (a boxout-adjacent
proxy: this player's team DREB-rate on-court minus off-court, the player-
level expression of the replicated h7 stint-continuity-x-DREB mechanism).

Reuses on_off.py's + zone_onoff.py's shot loaders/attach_lineup_to_shots and
nba_hypotheses.py's miss->rebound linker verbatim -- nothing here re-derives
a shot loader or the roster on/off mask loop from scratch except the ONE
generic `_on_off_by_player` aggregator (same roster/mask shape as
on_off.compute_on_off / zone_onoff.compute_zone_onoff, parameterized on a
single summed event column instead of hardcoded shot buckets).

NETWORK: zero.
"""
from __future__ import annotations

import json
from collections import defaultdict

import pandas as pd

from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_nba.lineups.on_off import load_shot_events as _load_own_tagged_shots
from domains.basketball_nba.lineups.zone_onoff import _PBP_BY_SEASON
from domains.basketball_nba.lineups.zone_onoff import load_shot_events as _load_defense_tagged_shots
from domains.basketball_nba.prereg.nba_hypotheses import _load_missed_shots_and_rebounds, _other_team
from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_BOX_SEASONS = {"2024_25", "2025_26"}  # player_boxscores.parquet has no 2023-24 rows


def _window(season: str) -> str:
    return f"season_{season}"


def _on_off_by_player(stints_df: pd.DataFrame, events_df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Generic per-(player,team) on/off sum of `value_col` + event count,
    matched to stints_df's clean (n_on_court==5) lineup membership."""
    clean = stints_df[stints_df["n_on_court"] == 5].copy()
    clean["players"] = clean["lineup_key"].astype(str).str.split(",")
    ev = events_df[events_df.get("n_on_court", 5) == 5].copy()
    ev["players"] = ev["lineup_key"].astype(str).str.split(",")

    acc: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for (gid, tid), grp in clean.groupby(["game_id", "team_id"]):
        roster = set().union(*grp["players"]) if len(grp) else set()
        ev_gt = ev[(ev["game_id"] == gid) & (ev["team_id"] == tid)]
        on_masks = {p: grp["players"].apply(lambda ps, p=p: p in ps) for p in roster}
        ev_masks = {p: ev_gt["players"].apply(lambda ps, p=p: p in ps) for p in roster} if len(ev_gt) else {}
        for p_str in roster:
            if not p_str.lstrip("-").isdigit():
                continue
            player_id = int(p_str)
            if player_id < 0:
                continue
            on_rows, off_rows = grp[on_masks[p_str]], grp[~on_masks[p_str]]
            key = (player_id, tid)
            acc[key]["min_on"] += on_rows["elapsed_s"].sum() / 60.0
            acc[key]["min_off"] += off_rows["elapsed_s"].sum() / 60.0
            if not len(ev_gt):
                continue
            mask = ev_masks[p_str]
            on_ev, off_ev = ev_gt[mask], ev_gt[~mask]
            acc[key][f"{value_col}_on"] += on_ev[value_col].sum()
            acc[key][f"{value_col}_off"] += off_ev[value_col].sum()
            acc[key]["n_events_on"] += len(on_ev)
            acc[key]["n_events_off"] += len(off_ev)
    return pd.DataFrame([{"player_id": pid, "team_id": tid, **v} for (pid, tid), v in acc.items()])


def _dedup_trade(df: pd.DataFrame) -> pd.DataFrame:
    """Same trade-dedup precedent as player_attributes.py: keep the team a
    player logged the most on-court minutes with this season."""
    return df.sort_values("min_on", ascending=False).drop_duplicates("player_id", keep="first")


def _load_game_events(stints: pd.DataFrame, pbp_dir, loader) -> pd.DataFrame:
    frames = []
    for gid in stints["game_id"].unique():
        fp = pbp_dir / f"{gid}.json"
        if fp.exists():
            frames.append(loader(json.loads(fp.read_text(encoding="utf-8"))))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["game_id", "team_id", "period", "elapsed_s", "person_id", "fgm", "fga"]
    )


def build_player_reb_pct(season: str) -> list[dict]:
    """box-only numerator (season OREB/DREB totals, already-verified boxscore
    data) over a PBP-derived on-court opportunity denominator."""
    if season not in _BOX_SEASONS or not _BOX.exists():
        return []
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    if not stints_src.exists():
        return []
    stints = pd.read_parquet(stints_src)
    pbp_dir = _PBP_BY_SEASON[season]

    own_miss = _load_game_events(stints, pbp_dir, _load_own_tagged_shots)
    own_miss = own_miss[own_miss["fgm"] == 0]
    opp_miss = _load_game_events(stints, pbp_dir, _load_defense_tagged_shots)
    opp_miss = opp_miss[opp_miss["fgm"] == 0]
    own_miss = attach_lineup_to_shots(stints, own_miss)
    opp_miss = attach_lineup_to_shots(stints, opp_miss)
    own_agg = _dedup_trade(_on_off_by_player(stints, own_miss, "fga"))
    opp_agg = _dedup_trade(_on_off_by_player(stints, opp_miss, "fga"))

    box = pd.read_parquet(_BOX)
    box = box[box["season"] == season.replace("_", "-")]
    box = exclude_negative_ids(box, "player_id")
    box_agg = box.groupby("player_id").agg(
        oreb=("oreb", "sum"), dreb=("dreb", "sum"), entity_name=("player_name", "first"),
    ).reset_index()

    rows: list[dict] = []
    o = box_agg.merge(own_agg[["player_id", "n_events_on"]], on="player_id", how="inner")
    o = o[o["n_events_on"] >= 200.0].copy()
    o["raw_value"] = o["oreb"] / o["n_events_on"]
    rows.extend(finalize_rows(
        o, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="n_events_on",
        window=_window(season), attribute="oreb_pct", status="DESCRIPTIVE",
        sources=rel_sources(_BOX, stints_src), ingredient_cols=["oreb", "n_events_on"],
    ))

    d = box_agg.merge(opp_agg[["player_id", "n_events_on"]].rename(columns={"n_events_on": "opp_missed_fga_on"}),
                       on="player_id", how="inner")
    d = d[d["opp_missed_fga_on"] >= 200.0].copy()
    d["raw_value"] = d["dreb"] / d["opp_missed_fga_on"]
    rows.extend(finalize_rows(
        d, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="opp_missed_fga_on",
        window=_window(season), attribute="dreb_pct", status="DESCRIPTIVE",
        sources=rel_sources(_BOX, stints_src), ingredient_cols=["dreb", "opp_missed_fga_on"],
    ))
    return rows


def build_team_dreb_pct_swing(season: str) -> list[dict]:
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    if not stints_src.exists():
        return []
    stints = pd.read_parquet(stints_src)
    pbp_dir = _PBP_BY_SEASON[season]

    reb = _load_missed_shots_and_rebounds(pbp_dir=pbp_dir)
    if reb.empty:
        return []
    clean = stints[stints["n_on_court"] == 5]
    team_ids_by_game = clean.groupby("game_id")["team_id"].unique().apply(list).to_dict()
    reb["defending_team_id"] = reb.apply(
        lambda r: _other_team(team_ids_by_game.get(r["game_id"], []), r["team_id"]), axis=1)
    reb = reb.dropna(subset=["defending_team_id"])
    reb = reb.drop(columns=["team_id"]).rename(columns={"defending_team_id": "team_id"})
    reb["team_id"] = reb["team_id"].astype("int64")  # Windows astype(int) trap

    reb = attach_lineup_to_shots(stints, reb[["game_id", "team_id", "period", "elapsed_s", "is_dreb"]])
    agg = _dedup_trade(_on_off_by_player(stints, reb, "is_dreb"))
    agg = agg[(agg["min_on"] >= 750.0) & (agg["min_off"] >= 750.0) &
              (agg["n_events_on"] > 0) & (agg["n_events_off"] > 0)].copy()
    if agg.empty:
        return []
    agg["dreb_pct_on"] = agg["is_dreb_on"] / agg["n_events_on"]
    agg["dreb_pct_off"] = agg["is_dreb_off"] / agg["n_events_off"]
    agg["raw_value"] = agg["dreb_pct_on"] - agg["dreb_pct_off"]
    return finalize_rows(
        agg, entity_col="player_id", name_col=None, raw_col="raw_value", n_col="min_on",
        window=_window(season), attribute="team_dreb_pct_swing", status="DESCRIPTIVE",
        sources=rel_sources(stints_src), ingredient_cols=["dreb_pct_on", "dreb_pct_off", "min_on", "min_off"],
    )


BUILDERS = [build_player_reb_pct, build_team_dreb_pct_swing]


def build_all_player_rebounding_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
