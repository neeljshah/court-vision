"""TEAM attribute expansion, part 3: box-derived splits (no PBP walk) --
bench_min_share, oreb_pct_team, dreb_pct_team, ft_rate_team, pf_per_game_team.
All from player_boxscores.parquet (2024-25/2025-26 only, box has no 2023-24
rows -- same caveat as player_attributes.py's shot_zone_profile). Entities
are keyed by numeric team_id (via team_attributes._tricode_to_team_id, the
same franchise-stable crosswalk the rest of the profile layer uses), not the
box's own tricode, to keep entity_id int64 like every other team attribute.

NETWORK: zero.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import REPO_ROOT, finalize_rows, rel_sources
from domains.basketball_nba.profiles.team_attributes import _team_id_to_name, _tricode_to_team_id

_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_BOX_SEASONS = {"2024_25", "2025_26"}


def _window(season: str) -> str:
    return f"season_{season}"


def _load_box(season: str) -> pd.DataFrame | None:
    if season not in _BOX_SEASONS or not _BOX.exists():
        return None
    box = pd.read_parquet(_BOX)
    box = box[box["season"] == season.replace("_", "-")]
    if box.empty:
        return None
    crosswalk = _tricode_to_team_id()
    box = box.copy()
    box["team_id"] = box["team"].map(crosswalk)
    return box.dropna(subset=["team_id"])


def build_bench_min_share(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    grp = box.groupby("team_id").agg(
        bench_min=("min", lambda s: s[~box.loc[s.index, "starter"]].sum()),
        total_min=("min", "sum"), n_games=("game_id", "nunique"),
    ).reset_index()
    grp = grp[(grp["n_games"] >= 10.0) & (grp["total_min"] > 0)].copy()
    grp["raw_value"] = grp["bench_min"] / grp["total_min"]
    grp["entity_name"] = grp["team_id"].map(_team_id_to_name()).fillna("")
    return finalize_rows(
        grp, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="bench_min_share", status="DESCRIPTIVE",
        sources=rel_sources(_BOX), ingredient_cols=["bench_min", "total_min"],
    )


def _opponent_missed_fga(box: pd.DataFrame) -> pd.Series:
    """Per-team season sum of the OPPONENT's missed FGA in the same games --
    a real per-game self-join on box's own 'opp' tricode column, not a
    league-mean proxy."""
    team_game = box.groupby(["game_id", "team"]).agg(fga=("fga", "sum"), fgm=("fgm", "sum")).reset_index()
    team_game["missed"] = team_game["fga"] - team_game["fgm"]
    opp_missed = team_game.rename(columns={"team": "opp", "missed": "opp_missed"})[["game_id", "opp", "opp_missed"]]
    own_opp = box[["game_id", "team", "opp"]].drop_duplicates()
    merged = own_opp.merge(opp_missed, on=["game_id", "opp"], how="left")
    return merged.groupby("team")["opp_missed"].sum()


def build_team_reb_ft(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    opp_missed = _opponent_missed_fga(box)
    grp = box.groupby(["team", "team_id"]).agg(
        oreb=("oreb", "sum"), dreb=("dreb", "sum"), fga=("fga", "sum"), fgm=("fgm", "sum"),
        fta=("fta", "sum"), pf=("pf", "sum"), n_games=("game_id", "nunique"),
    ).reset_index()
    grp["opp_missed_fga"] = grp["team"].map(opp_missed)
    grp = grp[grp["n_games"] >= 10.0].copy()
    grp["entity_name"] = grp["team_id"].map(_team_id_to_name()).fillna("")

    rows: list[dict] = []
    o = grp.copy()
    o["raw_value"] = o["oreb"] / (o["fga"] - o["fgm"])
    rows.extend(finalize_rows(
        o, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="oreb_pct_team", status="DESCRIPTIVE",
        sources=rel_sources(_BOX), ingredient_cols=["oreb", "fga", "fgm"],
    ))

    d = grp.dropna(subset=["opp_missed_fga"]).copy()
    d = d[d["opp_missed_fga"] > 0]
    d["raw_value"] = d["dreb"] / d["opp_missed_fga"]
    rows.extend(finalize_rows(
        d, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="dreb_pct_team", status="DESCRIPTIVE",
        sources=rel_sources(_BOX), ingredient_cols=["dreb", "opp_missed_fga"],
    ))

    f = grp.copy()
    f["raw_value"] = f["fta"] / f["fga"]
    rows.extend(finalize_rows(
        f, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="ft_rate_team", status="DESCRIPTIVE",
        sources=rel_sources(_BOX), ingredient_cols=["fta", "fga"],
    ))

    p = grp.copy()
    p["raw_value"] = p["pf"] / p["n_games"]
    rows.extend(finalize_rows(
        p, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="pf_per_game_team", status="DESCRIPTIVE",
        sources=rel_sources(_BOX), ingredient_cols=["pf"], higher_is_better=False,
    ))
    return rows


BUILDERS = [build_bench_min_share, build_team_reb_ft]


def build_all_team_box_split_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
