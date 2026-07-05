"""NBA full-population claim-dimension registry + per-player snapshot flatten
(companion to basketball_claims.py; split out per the <=300 LOC/file rail).

WHY A FLATTENED SIDE SNAPSHOT: every atlas_player_*.parquet in
docs/research/intel-layer/basketball_truth_spec.json is one row per player,
but most spec leaf fields live INSIDE a struct/JSON-string column (e.g.
atlas_player_spacing_gravity.parquet's cs_gravity is a JSON string of
{"catch_shoot_efg_pct": ..., ...}). claims_validator's whitelist formula
grammar (safe_formula.py) can only reference a PLAIN scalar column -- it
cannot reach into a nested dict/JSON string. So, like tennis_hold_claims.py's
wide->long reshape, this module extracts every spec leaf field into its OWN
plain column on a per-player snapshot parquet; every claim cites THAT
snapshot as source_files, so the validator recomputes independently.

QUALIFYING POPULATION (frozen per spec): season 2024-25, n_games>=20 AND
fga_sum>=200, from player_boxscores.parquet -- verified 329 of 569 (matches
spec's n_qualifying exactly). Floor gate for the boxscore-aggregate dims;
each atlas dimension's OWN per-source floor layers on top via min_sample.

DIMENSION CORPUS AVAILABILITY: every spec `factors` entry is built here
except leaf fields that are themselves DEFER stubs inside an otherwise-
present source (shot_clock early/mid, gravity_radius, off_ball_cut_rate, ft
streak/pressure/home-road) -- dropped from DIM_SPECS, reported via
dims_corpus_absent, never fabricated.

NETWORK: zero. Pure pandas/json over already-materialized parquets.
DESCRIPTIVE ONLY -- NO MARKET/$ EDGE CLAIMED.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]

_BOXSCORES = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_USAGE_ROLE = REPO_ROOT / "data" / "cache" / "atlas_player_usage_role.parquet"
_SCORING_CREATION = REPO_ROOT / "data" / "cache" / "atlas_player_scoring_creation.parquet"
_CATCH_SHOOT_PULLUP = REPO_ROOT / "data" / "cache" / "atlas_player_catch_shoot_vs_pullup.parquet"
_SPACING_GRAVITY = REPO_ROOT / "data" / "cache" / "atlas_player_spacing_gravity.parquet"
_VS_SCHEME = REPO_ROOT / "data" / "cache" / "atlas_player_vs_scheme_splits.parquet"
_SCORE_MARGIN = REPO_ROOT / "data" / "cache" / "atlas_player_score_margin_splits.parquet"
_CLUTCH_SCORING = REPO_ROOT / "data" / "cache" / "atlas_player_clutch_scoring.parquet"
_FT_PROFILE = REPO_ROOT / "data" / "cache" / "atlas_player_ft_profile.parquet"
_SHOT_CLOCK = REPO_ROOT / "data" / "cache" / "atlas_player_shot_clock_scoring.parquet"
_PLAYER_ROLES = REPO_ROOT / "data" / "cache" / "team_system" / "player_roles.parquet"

SEASON = "2024-25"
POP_MIN_GAMES = 20
POP_MIN_FGA = 200


def _load_json(cell: Any) -> dict[str, Any]:
    """A struct leaf is either an already-parsed dict or a JSON string (the
    on-disk shape for every atlas_player_*.parquet struct column). Returns
    {} for null/unparseable (fails closed, never raises)."""
    if isinstance(cell, dict):
        return cell
    if isinstance(cell, str):
        try:
            parsed = json.loads(cell)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def qualifying_population() -> pd.DataFrame:
    """Frozen 2024-25 n_games>=20 AND fga_sum>=200 population (329 per spec).
    Returns player_id, n_games, fga_sum -- the floor gate every other
    dimension's snapshot is inner-joined against."""
    box = pd.read_parquet(_BOXSCORES, columns=["player_id", "game_id", "season", "fga"])
    season_rows = box[box["season"] == SEASON]
    agg = season_rows.groupby("player_id").agg(
        n_games=("game_id", "count"), fga_sum=("fga", "sum")
    ).reset_index()
    return agg[(agg["n_games"] >= POP_MIN_GAMES) & (agg["fga_sum"] >= POP_MIN_FGA)].copy()


def name_lookup() -> dict[int, str]:
    """player_id -> name, from player_roles cache (READ-only; its builder
    script is human-gated) falling back to player_boxscores' player_name."""
    lookup: dict[int, str] = {}
    if _PLAYER_ROLES.exists():
        roles = pd.read_parquet(_PLAYER_ROLES, columns=["pid", "player"])
        lookup.update(dict(zip(roles["pid"].astype("int64"), roles["player"])))
    box_names = pd.read_parquet(_BOXSCORES, columns=["player_id", "player_name"])
    box_names = box_names.drop_duplicates(subset=["player_id"], keep="last")
    for pid, name in zip(box_names["player_id"], box_names["player_name"]):
        lookup.setdefault(int(pid), str(name))
    return lookup


# Per-dimension extractors: each takes the qualifying player_id set and
# returns a DataFrame with player_id + the dimension's plain numeric column
# + its floor-support column. A dimension whose source parquet is absent is
# never registered (see DIM_SPECS) -- reported via dims_corpus_absent.

def _extract_usage_role(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_USAGE_ROLE, columns=["player_id", "usage_rate", "minutes_pg", "n_games"])
    return df[df["player_id"].isin(pop_ids)].copy()


def _extract_scoring_creation(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(
        _SCORING_CREATION,
        columns=["player_id", "drives_per_game", "unassisted_share_3pm",
                  "unassisted_share_2pm", "and_one_rate", "n"],
    )
    return df[df["player_id"].isin(pop_ids)].copy()


def _extract_spacing_gravity(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_SPACING_GRAVITY, columns=["player_id", "gravity_score", "cs_gravity",
                                                       "playtypes_gravity", "n"])
    df = df[df["player_id"].isin(pop_ids)].copy()
    df["cs_gravity_efg"] = df["cs_gravity"].map(lambda c: _load_json(c).get("catch_shoot_efg_pct"))
    df["spotup_ppp"] = df["playtypes_gravity"].map(lambda c: _load_json(c).get("spotup_ppp"))
    return df.drop(columns=["cs_gravity", "playtypes_gravity"])


def _extract_catch_shoot_pullup(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_CATCH_SHOOT_PULLUP, columns=["player_id", "pull_up", "time_to_shot", "n"])
    df = df[df["player_id"].isin(pop_ids)].copy()
    df["pullup_combined_freq"] = df["pull_up"].map(lambda c: _load_json(c).get("pullup_combined_freq_pct"))
    df["late_clock_shots_pg"] = df["time_to_shot"].map(lambda c: _load_json(c).get("late_clock_shots_pg"))
    return df.drop(columns=["pull_up", "time_to_shot"])


def _extract_shot_clock(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_SHOT_CLOCK, columns=["player_id", "shot_quality", "n"])
    df = df[df["player_id"].isin(pop_ids)].copy()
    df["shot_quality_ts"] = df["shot_quality"].map(lambda c: _load_json(c).get("ts_pct"))
    return df.drop(columns=["shot_quality"])


def _extract_vs_scheme(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_VS_SCHEME, columns=["player_id", "scheme_ts_pct_best_minus_worst", "n_games_total"])
    df = df[df["player_id"].isin(pop_ids)].copy()
    # INVERTED per spec note: smaller best-minus-worst spread = MORE robust.
    df["scheme_robustness"] = 1.0 - df["scheme_ts_pct_best_minus_worst"]
    df = df.rename(columns={"n_games_total": "n"})
    return df.drop(columns=["scheme_ts_pct_best_minus_worst"])


def _extract_score_margin(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_SCORE_MARGIN, columns=["player_id", "leading", "trailing", "n"])
    df = df[df["player_id"].isin(pop_ids)].copy()

    def _spread(row: pd.Series) -> float | None:
        # INVERTED: smaller |leading - trailing| eFG spread = MORE consistent.
        lead = _load_json(row["leading"]).get("efg_pct")
        trail = _load_json(row["trailing"]).get("efg_pct")
        return None if lead is None or trail is None else 1.0 - abs(float(lead) - float(trail))

    df["score_margin_consistency"] = df.apply(_spread, axis=1)
    return df.drop(columns=["leading", "trailing"])


def _extract_clutch_scoring(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_CLUTCH_SCORING, columns=["player_id", "scoring", "n"])
    df = df[df["player_id"].isin(pop_ids)].copy()
    df["clutch_scoring"] = df["scoring"].map(lambda c: _load_json(c).get("pts_per36"))
    return df.drop(columns=["scoring"])


def _extract_ft_profile(pop_ids: set[int]) -> pd.DataFrame:
    df = pd.read_parquet(_FT_PROFILE, columns=["player_id", "stability", "n"])
    df = df[df["player_id"].isin(pop_ids)].copy()
    df["ft_reliability"] = df["stability"].map(lambda c: _load_json(c).get("ft_pct"))
    return df.drop(columns=["stability"])


@dataclass(frozen=True)
class DimSpec:
    """One buildable dimension: extractor, metric column, direction, floor."""

    name: str
    pillar: str
    source_file: Path
    extractor: Callable[[set[int]], pd.DataFrame]
    metric_col: str
    floor_col: str
    floor_value: float
    direction: str
    question: str
    caveat: str


# Computed via group-by AGGREGATE straight off player_boxscores (validator's
# criteria.aggregate path) -- handled in basketball_claims.build_boxscore_
# aggregate_claim, NOT listed here.
BOXSCORE_AGGREGATE_DIMS = ("ts_pct", "efg_pct", "fga_per_game", "fg3a_per_game")

DIM_SPECS: list[DimSpec] = [
    DimSpec("usage_rate", "VOLUME", _USAGE_ROLE, _extract_usage_role, "usage_rate",
            "n_games", 20, "desc",
            "Which qualifying NBA players have the highest offensive usage rate (2024-25)?",
            "usage_rate from atlas_player_usage_role.parquet; n_games is that atlas "
            "row's own tracked-game count (its floor-support column, separate from the "
            "329-population n_games>=20 gate)."),
    DimSpec("minutes_pg", "VOLUME", _USAGE_ROLE, _extract_usage_role, "minutes_pg",
            "n_games", 20, "desc",
            "Which qualifying NBA players play the most minutes per game (2024-25)?",
            "minutes_pg from atlas_player_usage_role.parquet."),
    DimSpec("drives_per_game", "VOLUME", _SCORING_CREATION, _extract_scoring_creation,
            "drives_per_game", "n", 20, "desc",
            "Which qualifying NBA players drive to the basket most per game (2024-25)?",
            "drives_per_game from atlas_player_scoring_creation.parquet (89% coverage over "
            "the 329-pop per spec; see counts.n_excluded_below_floor for the honest gap)."),
    DimSpec("unassisted_share_3pm", "DIFFICULTY", _SCORING_CREATION, _extract_scoring_creation,
            "unassisted_share_3pm", "n", 20, "desc",
            "Which qualifying NBA players create their own 3-point makes most (2024-25)?",
            "unassisted_share_3pm = share of made 3s that were self-created (no assist)."),
    DimSpec("unassisted_share_2pm", "DIFFICULTY_scorer", _SCORING_CREATION, _extract_scoring_creation,
            "unassisted_share_2pm", "n", 20, "desc",
            "Which qualifying NBA players create their own 2-point makes most (2024-25)?",
            "unassisted_share_2pm = share of made 2s that were self-created (no assist)."),
    DimSpec("and_one_rate", "DIFFICULTY_scorer", _SCORING_CREATION, _extract_scoring_creation,
            "and_one_rate", "n", 20, "desc",
            "Which qualifying NBA players draw the most and-one plays (2024-25)?",
            "and_one_rate from atlas_player_scoring_creation.parquet."),
    DimSpec("gravity_score", "GRAVITY", _SPACING_GRAVITY, _extract_spacing_gravity,
            "gravity_score", "n", 20, "desc",
            "Which qualifying NBA players generate the most shooting gravity (2024-25)?",
            "gravity_score from atlas_player_spacing_gravity.parquet; per spec, CV-derived "
            "sub-fields are sparse (median ~2 games) but gravity_score itself is the "
            "modeled composite, populated for all 329 qualifying."),
    DimSpec("cs_gravity_efg", "GRAVITY", _SPACING_GRAVITY, _extract_spacing_gravity,
            "cs_gravity_efg", "n", 20, "desc",
            "Which qualifying NBA players shoot best on catch-and-shoot gravity looks (2024-25)?",
            "cs_gravity_efg = cs_gravity.catch_shoot_efg_pct, flattened from a nested struct "
            "column in atlas_player_spacing_gravity.parquet."),
    DimSpec("spotup_ppp", "GRAVITY", _SPACING_GRAVITY, _extract_spacing_gravity,
            "spotup_ppp", "n", 20, "desc",
            "Which qualifying NBA players are most efficient on spot-up looks (2024-25)?",
            "spotup_ppp = playtypes_gravity.spotup_ppp, flattened from a nested struct "
            "column in atlas_player_spacing_gravity.parquet."),
    DimSpec("pullup_combined_freq", "DIFFICULTY", _CATCH_SHOOT_PULLUP, _extract_catch_shoot_pullup,
            "pullup_combined_freq", "n", 20, "desc",
            "Which qualifying NBA players take the highest share of pull-up shots (2024-25)?",
            "pullup_combined_freq = pull_up.pullup_combined_freq_pct, flattened from a "
            "nested struct column in atlas_player_catch_shoot_vs_pullup.parquet."),
    DimSpec("late_clock_shots_pg", "DIFFICULTY", _CATCH_SHOOT_PULLUP, _extract_catch_shoot_pullup,
            "late_clock_shots_pg", "n", 20, "desc",
            "Which qualifying NBA players take the most late-shot-clock shots per game (2024-25)?",
            "late_clock_shots_pg = time_to_shot.late_clock_shots_pg, flattened from a "
            "nested struct column in atlas_player_catch_shoot_vs_pullup.parquet."),
    DimSpec("shot_quality_ts", "EFFICIENCY", _SHOT_CLOCK, _extract_shot_clock,
            "shot_quality_ts", "n", 20, "desc",
            "Which qualifying NBA players have the best modeled shot-quality TS% (2024-25)?",
            "shot_quality_ts = shot_quality.ts_pct, flattened from a nested struct column "
            "in atlas_player_shot_clock_scoring.parquet (early/mid shot-clock buckets are "
            "DEFER stubs in this source and are not claimed as separate dimensions)."),
    DimSpec("scheme_robustness", "CONTEXT_scorer", _VS_SCHEME, _extract_vs_scheme,
            "scheme_robustness", "n", 20, "desc",
            "Which qualifying NBA players are most efficiency-consistent across opposing "
            "defensive schemes (2024-25)?",
            "scheme_robustness = 1 - scheme_ts_pct_best_minus_worst (INVERTED per spec: "
            "smaller best-vs-worst-scheme TS% spread = more scheme-robust)."),
    DimSpec("score_margin_consistency", "CONTEXT_scorer", _SCORE_MARGIN, _extract_score_margin,
            "score_margin_consistency", "n", 20, "desc",
            "Which qualifying NBA players are most efficiency-consistent leading vs "
            "trailing (2024-25)?",
            "score_margin_consistency = 1 - |leading.efg_pct - trailing.efg_pct| (INVERTED: "
            "smaller leading-vs-trailing eFG spread = more consistent), flattened from "
            "nested struct columns in atlas_player_score_margin_splits.parquet."),
    DimSpec("clutch_scoring", "CONTEXT_scorer", _CLUTCH_SCORING, _extract_clutch_scoring,
            "clutch_scoring", "n", 20, "desc",
            "Which qualifying NBA players score most efficiently per-36 in clutch minutes "
            "(2024-25)?",
            "clutch_scoring = scoring.pts_per36 (the clutch-window scoring rate), flattened "
            "from a nested struct column in atlas_player_clutch_scoring.parquet (89% "
            "coverage over the 329-pop per spec)."),
    DimSpec("ft_reliability", "CONTEXT_scorer_tiebreak", _FT_PROFILE, _extract_ft_profile,
            "ft_reliability", "n", 20, "desc",
            "Which qualifying NBA players are the most reliable free-throw shooters "
            "(2024-25)?",
            "ft_reliability = stability.ft_pct, flattened from a nested struct column in "
            "atlas_player_ft_profile.parquet (94% coverage over the 329-pop per spec)."),
]

# Dimensions named in the spec whose leaf is a DEFER stub inside its OWN
# source parquet (confirmed at build time, per spec's `limits`) -- reported
# via dims_corpus_absent, never fabricated.
DIMS_DEFER_IN_SOURCE = [
    "shot_clock_early_mid (jersey-number pkey linkage unavailable, per spec limits)",
    "gravity_radius (no per-player defender-attention-radius parquet, per spec limits)",
    "off_ball_cut_rate (EventDetector cut events not pre-aggregated, per spec limits)",
    "ft_streak_analysis (needs V2 PBP EVENTMSGTYPE=3 per-player, per spec limits)",
    "ft_pressure_splits (needs PBP game-clock filtering, not pre-aggregated, per spec limits)",
    "ft_home_road_split (home/away join not pre-aggregated per player, per spec limits)",
    "blowout_shot_mix (shot-chart-by-score-state parquet does not exist, per spec limits)",
    "isolation_deep_profile (43% coverage, below spec's 60% fallback-only threshold)",
    "cv_spacing_offball (CV-sparse median ~2 games, LOW-TRUST per spec, fallback-only)",
]
