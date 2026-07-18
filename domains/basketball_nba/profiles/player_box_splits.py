"""PLAYER venue splits (coverage_stress Family B) + rest splits (Family C) --
both a plain player_boxscores.parquet groupby-and-diff, same shape as
team_expansion.py's build_home_away_net_rating (home/away diff at team grain,
now applied at player grain). NETWORK: zero.

Family B (home/away): ppg_home, ppg_away, ppg_home_minus_away. Floor >=15
home AND >=15 away games (player_boxscores.is_home is 0/1, zero nulls).

Family C (rest): rest_days = this player's own date minus his prior game's
own date (shift(1) within player_id, same season -- no cross-season leak).
short_rest = rest_days<=1 (b2b/1-day gap); long_rest = rest_days>=3. Floor
>=8 games in EACH bucket. ppg_short_rest, ppg_long_rest,
ppg_short_minus_long_rest.

ROOT-CAUSE NOTE (rest): scripts/platformkit/intel_validation/
nba_rest_context_claims.py ALREADY ships a player-grain rest-conditioned
claim (b2b_pts36_delta = pts_per36(b2b) - pts_per36(rest>=2)) in the CLAIMS
store -- checked before building this, per the "small derivation, not a new
heavy producer" standard. That existing claim uses a DIFFERENT metric
(pts_per36, a minutes-normalized rate) and a DIFFERENT long-rest cut
(rest>=2, not >=3) than this module's ppg_short_minus_long_rest (raw
per-game scoring average, rest>=3) -- a distinct, non-redundant fact, so
still built here per spec sec 31. The existing b2b_pts36_delta claim is
wired into ask_index.py's _METRIC_SYNONYMS as an immediate additional
answer for "rest split"-shaped questions (zero new code, real data already
on disk) -- see that file's routing block.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_BOX_SEASONS = {"2024_25", "2025_26"}

VENUE_FLOOR = 15.0
REST_FLOOR = 8.0
SHORT_REST_MAX_DAYS = 1
LONG_REST_MIN_DAYS = 3


def _window(season: str) -> str:
    return f"season_{season}"


def _load_box(season: str) -> pd.DataFrame | None:
    if season not in _BOX_SEASONS or not _BOX.exists():
        return None
    box = pd.read_parquet(_BOX)
    box = box[box["season"] == season.replace("_", "-")]
    if box.empty:
        return None
    return exclude_negative_ids(box, "player_id")


def _side_ppg(box: pd.DataFrame, mask: pd.Series, floor: float) -> pd.DataFrame:
    g = box[mask].groupby("player_id").agg(
        pts=("pts", "sum"), n_games=("game_id", "nunique"),
        entity_name=("player_name", "first"),
    ).reset_index()
    g = g[g["n_games"] >= floor].copy()
    g["raw_value"] = g["pts"] / g["n_games"]
    return g


def _diff_rows(box: pd.DataFrame, splits: dict[str, pd.Series], both_mask: pd.Series,
               window: str, attribute: str) -> list[dict]:
    left, right = splits.values()
    if left.empty or right.empty:
        return []
    diff = (left - right).dropna().rename("raw_value").reset_index()
    names = box.groupby("player_id")["player_name"].first()
    n_both = box[both_mask].groupby("player_id")["game_id"].nunique().rename("n_games").reset_index()
    diff = diff.merge(n_both, on="player_id", how="left")
    diff["entity_name"] = diff["player_id"].map(names).fillna("")
    return finalize_rows(
        diff, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=window, attribute=attribute, status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=[],
    )


def build_venue_split(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    rows: list[dict] = []
    splits: dict[str, pd.Series] = {}
    for side, eq in (("home", 1), ("away", 0)):
        g = _side_ppg(box, box["is_home"] == eq, VENUE_FLOOR)
        splits[side] = g.set_index("player_id")["raw_value"]
        rows.extend(finalize_rows(
            g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
            window=_window(season), attribute=f"ppg_{side}", status="DESCRIPTIVE",
            sources=rel_sources(_BOX), ingredient_cols=["pts", "n_games"],
        ))
    rows.extend(_diff_rows(box, splits, box["is_home"].isin([0, 1]),
                            _window(season), "ppg_home_minus_away"))
    return rows


def _rest_days(box: pd.DataFrame) -> pd.Series:
    b = box.sort_values(["player_id", "date"])
    prior_date = b.groupby("player_id")["date"].shift(1)
    rest = (pd.to_datetime(b["date"]) - pd.to_datetime(prior_date)).dt.days
    return rest.reindex(box.index)


def build_rest_split(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    box = box.copy()
    box["rest_days"] = _rest_days(box)
    short_mask = box["rest_days"] <= SHORT_REST_MAX_DAYS
    long_mask = box["rest_days"] >= LONG_REST_MIN_DAYS
    both_mask = short_mask | long_mask

    rows: list[dict] = []
    splits: dict[str, pd.Series] = {}
    for side, mask in (("short_rest", short_mask), ("long_rest", long_mask)):
        g = _side_ppg(box, mask, REST_FLOOR)
        splits[side] = g.set_index("player_id")["raw_value"]
        rows.extend(finalize_rows(
            g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
            window=_window(season), attribute=f"ppg_{side}", status="DESCRIPTIVE",
            sources=rel_sources(_BOX), ingredient_cols=["pts", "n_games"],
        ))
    rows.extend(_diff_rows(box, splits, both_mask, _window(season), "ppg_short_minus_long_rest"))
    return rows


BUILDERS = [build_venue_split, build_rest_split]


def build_all_player_box_split_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
