"""TEAM attribute computation -- shot_diet/concession are pass-through
column families (SHOT_DIET_COLS/CONCESSION_COLS in attribute_registry.py);
transition_rate/lineup_continuity/pace_proxy are one-off compositions.

NETWORK: zero.
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from domains.basketball_nba.profiles.attribute_registry import (
    CONCESSION_COLS, CONCESSION_LOWER_IS_BETTER, SHOT_DIET_COLS,
)
from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, direct_column_rows, finalize_rows, rel_sources,
)

_TS = REPO_ROOT / "data" / "cache" / "team_system"
_LINEUPS = _TS / "lineups"
_COMPOSITION = _TS / "composition"
_ATLAS_TRANSITION = REPO_ROOT / "data" / "cache" / "atlas_team_transition_defense.parquet"
_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"

# Static tricode -> franchise display name table (30 entries, never changes
# mid-season) -- every team builder below stamps entity_name off this via
# _team_id_to_name(); before this fix every row from this file wrote
# entity_name="" (name_col=None everywhere), which silently broke
# matchup_preview's NBA team-name fuzzy match (docs/research/
# resolver_coverage_2026_07_17.md gap 4).
_TRICODE_TEAM_NAME = {
    "ATL": "Atlanta Hawks", "BKN": "Brooklyn Nets", "BOS": "Boston Celtics",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}


def _window(season: str) -> str:
    return f"season_{season}"


def _tricode_to_team_id(season_label: str = "2025-26") -> dict[str, int]:
    """team_tricode -> numeric team_id crosswalk, DERIVED (not hardcoded)
    by joining player_boxscores.parquet's tricode-keyed 'team' column to
    on_off_2025_26.parquet's numeric team_id on the shared player_id -- the
    only two artifacts on disk that each carry one half of this mapping."""
    if not (_BOX.exists() and (_LINEUPS / "on_off_2025_26.parquet").exists()):
        return {}
    box = pd.read_parquet(_BOX, columns=["player_id", "team", "season"])
    box = box[box["season"] == season_label][["player_id", "team"]].drop_duplicates()
    onoff = pd.read_parquet(_LINEUPS / "on_off_2025_26.parquet", columns=["player_id", "team_id"]).drop_duplicates()
    merged = box.merge(onoff, on="player_id")
    return merged.groupby("team")["team_id"].agg(lambda s: int(s.mode().iat[0])).to_dict()


@lru_cache(maxsize=4)
def _team_id_to_name(season_label: str = "2025-26") -> dict[int, str]:
    """team_id -> franchise display name, layering the tricode crosswalk
    above onto the static _TRICODE_TEAM_NAME table. lru_cache: every builder
    below calls this once per season; the crosswalk itself reads 2 small
    parquets, no need to re-read them per attribute."""
    return {tid: _TRICODE_TEAM_NAME.get(tri, "") for tri, tid in _tricode_to_team_id(season_label).items()}


def build_shot_diet(season: str) -> list[dict]:
    if season != "2025_26":
        return []
    src = _COMPOSITION / "shot_diet_2025_26.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    grp = df.groupby("team_id").agg(**{c: (c, "mean") for c in SHOT_DIET_COLS},
                                     n_games=("game_id", "count")).reset_index()
    grp = grp[grp["n_games"] >= 10.0]
    grp["entity_name"] = grp["team_id"].map(_team_id_to_name()).fillna("")
    rows = []
    for col in SHOT_DIET_COLS:
        rows.extend(finalize_rows(
            grp, entity_col="team_id", name_col="entity_name", raw_col=col, n_col="n_games",
            window=_window(season), attribute=f"shot_diet_{col}", status="DESCRIPTIVE", sources=rel_sources(src),
            ingredient_cols=[col],
        ))
    return rows


def build_concession(season: str) -> list[dict]:
    if season != "2025_26":
        return []
    src = _COMPOSITION / "concession_2025_26.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    df = df[df["n_shots_faced"] >= 500.0].rename(columns={"defense_team_id": "team_id"})
    df["entity_name"] = df["team_id"].map(_team_id_to_name()).fillna("")
    rows = []
    for col in CONCESSION_COLS:
        rows.extend(direct_column_rows(
            df, entity_col="team_id", name_col="entity_name", cols=[col], n_col="n_shots_faced",
            window=_window(season), status="DESCRIPTIVE", sources=rel_sources(src),
            attr_prefix="concession_", higher_is_better=col not in CONCESSION_LOWER_IS_BETTER,
        ))
    return rows


def build_transition_rate(season: str) -> list[dict]:
    if season != "2025_26" or not _ATLAS_TRANSITION.exists():
        return []
    crosswalk = _tricode_to_team_id()
    df = pd.read_parquet(_ATLAS_TRANSITION)
    rows = []
    for r in df.itertuples(index=False):
        team_id = crosswalk.get(r.team_tricode)
        if team_id is None:
            continue
        try:
            payload = json.loads(getattr(r, "transition_freq"))
            n_games = payload.get("n_games_pbp")
            opp_pg = payload.get("opp_transition_pg")
        except (TypeError, ValueError):
            continue
        if n_games is None or opp_pg is None or n_games < 50.0:
            continue
        rows.append({"team_id": team_id, "entity_name": _TRICODE_TEAM_NAME.get(r.team_tricode, ""),
                     "raw_value": float(opp_pg), "n": float(n_games)})
    if not rows:
        return []
    d = pd.DataFrame(rows)
    return finalize_rows(
        d, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n",
        window=_window(season), attribute="transition_rate_allowed", status="DESCRIPTIVE",
        sources=rel_sources(_ATLAS_TRANSITION, _BOX, _LINEUPS / "on_off_2025_26.parquet"),
        ingredient_cols=["raw_value", "n"], higher_is_better=False,
    )


def build_lineup_continuity(season: str) -> list[dict]:
    src = _LINEUPS / f"stints_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    grp = df.groupby("team_id").agg(
        raw_value=("elapsed_s", "mean"), n_stints=("elapsed_s", "count"), n_games=("game_id", "nunique"),
    ).reset_index()
    grp = grp[grp["n_games"] >= 10.0]
    grp["entity_name"] = grp["team_id"].map(_team_id_to_name()).fillna("")
    return finalize_rows(
        grp, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="lineup_continuity_avg_stint_s", status="VALIDATED_MECHANISM",
        sources=rel_sources(src), ingredient_cols=["n_stints"],
    )


def build_pace_proxy(season: str) -> list[dict]:
    if season != "2025_26":
        return []
    src = _COMPOSITION / "shot_diet_2025_26.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    grp = df.groupby("team_id").agg(raw_value=("total_fga", "mean"), n_games=("game_id", "count")).reset_index()
    grp = grp[grp["n_games"] >= 10.0]
    grp["entity_name"] = grp["team_id"].map(_team_id_to_name()).fillna("")
    return finalize_rows(
        grp, entity_col="team_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="pace_proxy_fga_per_game", status="DESCRIPTIVE",
        sources=rel_sources(src), ingredient_cols=["raw_value"],
    )


BUILDERS = [
    build_shot_diet, build_concession, build_transition_rate, build_lineup_continuity, build_pace_proxy,
]


def build_all_team_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
