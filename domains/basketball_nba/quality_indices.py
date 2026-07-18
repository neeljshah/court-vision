"""Data loading + factor extraction for shooter_quality_v1 / scorer_quality_v1.

Implements the data-side of the frozen spec in
docs/research/intel-layer/basketball_truth_spec.json (companion doc:
BASKETBALL_TRUTH_SPEC_2026-07-04.md). Weights are DECLARED, not fitted, and
are FROZEN before any player is scored -- see the narrative_fitting_ban in
the spec. Scoring/percentile logic lives in quality_indices_score.py (kept
separate to stay under the 300-LOC/file cap).

Qualifying population (season 2024-25): n_games >= 20 AND fga_sum >= 200
(330 players, re-verified live 2026-07-18 -- the prior 329 was stale).

Data sources (read-only, never rebuilt here): player_boxscores.parquet +
10 atlas_player_*.parquet files, per the factor->file->column map in the
spec's Section 1b / factors[] list. Nested atlas fields are JSON-string
structs (verified live this session) -- parsed defensively; missing/DEFER
fields degrade that sub-factor to NaN, which drops out of the pillar mean
computed downstream (never imputed).

No LLM recall: every number here is read from an on-disk parquet row.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

BOXSCORE_PATH = "data/domains/basketball_nba/player_boxscores.parquet"

ATLAS_PATHS = {
    "shot_clock_scoring": "data/cache/atlas_player_shot_clock_scoring.parquet",
    "usage_role": "data/cache/atlas_player_usage_role.parquet",
    "scoring_creation": "data/cache/atlas_player_scoring_creation.parquet",
    "catch_shoot_vs_pullup": "data/cache/atlas_player_catch_shoot_vs_pullup.parquet",
    "spacing_gravity": "data/cache/atlas_player_spacing_gravity.parquet",
    "vs_scheme_splits": "data/cache/atlas_player_vs_scheme_splits.parquet",
    "score_margin_splits": "data/cache/atlas_player_score_margin_splits.parquet",
    "clutch_scoring": "data/cache/atlas_player_clutch_scoring.parquet",
    "situational_splits": "data/cache/atlas_player_situational_splits.parquet",
    "ft_profile": "data/cache/atlas_player_ft_profile.parquet",
}

# fallback-only per spec Section 2.5 / "fallback_only_factors" -- excluded
# from default pillars, never loaded into a factor table.
FALLBACK_ONLY = {"isolation_profile_deep", "cv_spacing_offball"}

QUALIFY_MIN_GAMES = 20
QUALIFY_MIN_FGA = 200
QUALIFY_SEASON = "2024-25"

# ---------------------------------------------------------------------------
# Declared, frozen weights (basketball_truth_spec.json "indices")
# ---------------------------------------------------------------------------
SHOOTER_WEIGHTS = {
    "EFFICIENCY": 0.30,
    "DIFFICULTY": 0.30,
    "GRAVITY": 0.25,
    "VOLUME": 0.15,
}
SCORER_WEIGHTS = {
    "VOLUME_LOAD": 0.30,
    "EFFICIENCY": 0.25,
    "CREATION_DIFFICULTY": 0.25,
    "CONTEXT_ROBUSTNESS": 0.20,
}

NAIVE_WEIGHTS = {"ts_pct": 0.55, "efg_pct": 0.30, "ft_pct": 0.15}

PILLAR_FACTORS = {
    "shooter": {
        "EFFICIENCY": ["ts_pct", "efg_pct", "shot_quality_ts"],
        "DIFFICULTY": ["pullup_combined_freq", "pullup_pnr_ppp",
                        "late_clock_shots_pg", "unassisted_share_3pm",
                        "off_dribble_3_proxy"],
        "GRAVITY": ["gravity_score", "cs_gravity_efg", "spotup_ppp"],
        "VOLUME": ["fg3a_per_game", "fga_per_game"],
    },
    "scorer": {
        "VOLUME_LOAD": ["usage_rate", "fga_per_game", "drives_per_game", "minutes_pg"],
        "EFFICIENCY": ["ts_pct", "efg_pct", "shot_quality_ts"],
        "CREATION_DIFFICULTY": ["unassisted_share_2pm", "unassisted_share_3pm",
                                  "iso_poss_pg", "pnr_handler_pg",
                                  "pullup_combined_freq", "and_one_rate"],
        "CONTEXT_ROBUSTNESS": ["scheme_robustness_inv", "score_margin_consistency_inv",
                                 "clutch_scoring_pts_per36", "blowout_gt_pct_inv"],
    },
}

# factors where a HIGHER raw value means WORSE (must invert the percentile
# so higher percentile always means "better" for the pillar mean)
INVERT_FACTORS = {"scheme_robustness_inv", "score_margin_consistency_inv", "blowout_gt_pct_inv"}


def _parse_struct(val: Any) -> dict:
    """Nested atlas fields are JSON-string structs; parse defensively."""
    if isinstance(val, dict):
        return val
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return {}
    try:
        return json.loads(val)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def load_boxscores(path: str = BOXSCORE_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path)
    needed = ["game_id", "date", "season", "player_id", "player_name",
              "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pts"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"player_boxscores.parquet missing columns: {missing}")
    return df[needed].copy()


def aggregate_season(df: pd.DataFrame, season: str = QUALIFY_SEASON) -> pd.DataFrame:
    """Sum raw box counts per player over one season, derive rate stats.

    Groups by player_id ONLY (never player_id+player_name): the raw boxscore
    rows carry inconsistent name spellings for the same player_id across
    dates (e.g. "Nikola Jokic" vs "Nikola Jokic" with diacritics -- 18
    player_ids affected, verified live on player_boxscores.parquet). Grouping
    by both columns silently splits one player's games/FGA across two rows,
    which undercounts them against the qualifying floor and (once re-joined
    downstream by player_id alone) produces a duplicate player_id row --
    ranking a player twice, which is wrong regardless of whether it crashes.
    player_name is resolved separately as the most-recent spelling on file
    (rows sorted by date first)."""
    rows = df[df["season"] == season].sort_values("date")
    g = rows.groupby("player_id", as_index=False).agg(
        player_name=("player_name", "last"),
        games=("game_id", "nunique"),
        fgm=("fgm", "sum"), fga=("fga", "sum"),
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
        ftm=("ftm", "sum"), fta=("fta", "sum"),
        pts=("pts", "sum"),
    )
    g["fga_pg"] = g["fga"] / g["games"]
    g["fg3a_pg"] = g["fg3a"] / g["games"]
    g["efg_pct"] = (g["fgm"] + 0.5 * g["fg3m"]) / g["fga"].replace(0, pd.NA)
    g["ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    g["ft_pct"] = g["ftm"] / g["fta"].replace(0, pd.NA)
    g["naive_comp"] = (
        NAIVE_WEIGHTS["ts_pct"] * g["ts_pct"]
        + NAIVE_WEIGHTS["efg_pct"] * g["efg_pct"]
        + NAIVE_WEIGHTS["ft_pct"] * g["ft_pct"]
    )
    return g


def qualifying_pool(agg: pd.DataFrame, min_games: int = QUALIFY_MIN_GAMES,
                     min_fga: int = QUALIFY_MIN_FGA) -> pd.DataFrame:
    mask = (agg["games"] >= min_games) & (agg["fga"] >= min_fga)
    return agg[mask].reset_index(drop=True)


def load_atlas(name: str) -> pd.DataFrame:
    return pd.read_parquet(ATLAS_PATHS[name])


def build_factor_table(pool: pd.DataFrame) -> pd.DataFrame:
    """Join the qualifying pool to every atlas source and extract every raw
    factor value declared in the spec's factors[] list. Missing rows/fields
    become NaN (dropped from pillar means, never imputed)."""
    t = pool[["player_id", "player_name", "games", "fga", "fg3a",
              "ts_pct", "efg_pct", "ft_pct", "naive_comp"]].copy()
    t["fga_per_game"] = t["fga"] / t["games"]
    t["fg3a_per_game"] = t["fg3a"] / t["games"]

    atlas = {name: load_atlas(name).set_index("player_id") for name in ATLAS_PATHS}

    def col(df: pd.DataFrame, pid: int, c: str, default=None):
        if pid not in df.index or c not in df.columns:
            return default
        return df.loc[pid, c]

    out = {k: [] for k in (
        "shot_quality_ts", "usage_rate", "minutes_pg", "drives_per_game",
        "pullup_combined_freq", "pullup_pnr_ppp", "late_clock_shots_pg",
        "unassisted_share_3pm", "unassisted_share_2pm", "off_dribble_3_proxy",
        "iso_poss_pg", "pnr_handler_pg", "and_one_rate",
        "gravity_score", "cs_gravity_efg", "spotup_ppp", "creator_role_z",
        "scheme_robustness", "score_margin_consistency",
        "clutch_scoring_pts_per36", "blowout_gt_pct", "ft_reliability",
    )}
    for pid in t["player_id"]:
        sq = _parse_struct(col(atlas["shot_clock_scoring"], pid, "shot_quality", {}))
        out["shot_quality_ts"].append(sq.get("ts_pct"))

        ur = atlas["usage_role"]
        out["usage_rate"].append(col(ur, pid, "usage_rate"))
        out["minutes_pg"].append(col(ur, pid, "minutes_pg"))
        out["iso_poss_pg"].append(col(ur, pid, "iso_poss_pg"))
        out["pnr_handler_pg"].append(col(ur, pid, "pnr_handler_pg"))
        out["creator_role_z"].append(col(ur, pid, "on_off_impact_z"))

        sc = atlas["scoring_creation"]
        out["drives_per_game"].append(col(sc, pid, "drives_per_game"))
        out["unassisted_share_3pm"].append(col(sc, pid, "unassisted_share_3pm"))
        out["unassisted_share_2pm"].append(col(sc, pid, "unassisted_share_2pm"))
        out["and_one_rate"].append(col(sc, pid, "and_one_rate"))

        csp = atlas["catch_shoot_vs_pullup"]
        pull_up = _parse_struct(col(csp, pid, "pull_up", {}))
        out["pullup_combined_freq"].append(pull_up.get("pullup_combined_freq_pct"))
        out["pullup_pnr_ppp"].append(pull_up.get("pullup_pnr_handler_ppp"))
        time_to_shot = _parse_struct(col(csp, pid, "time_to_shot", {}))
        out["late_clock_shots_pg"].append(time_to_shot.get("late_clock_shots_pg"))
        off_dribble_3 = _parse_struct(col(csp, pid, "off_dribble_3", {}))
        out["off_dribble_3_proxy"].append(off_dribble_3.get("off_screen_freq_pct"))

        sg = atlas["spacing_gravity"]
        out["gravity_score"].append(col(sg, pid, "gravity_score"))
        cs_grav = _parse_struct(col(sg, pid, "cs_gravity", {}))
        out["cs_gravity_efg"].append(cs_grav.get("catch_shoot_efg_pct"))
        pg = _parse_struct(col(sg, pid, "playtypes_gravity", {}))
        out["spotup_ppp"].append(pg.get("spotup_ppp"))

        out["scheme_robustness"].append(col(atlas["vs_scheme_splits"], pid, "scheme_ts_pct_best_minus_worst"))

        sms = atlas["score_margin_splits"]
        leading = _parse_struct(col(sms, pid, "leading", {}))
        tied = _parse_struct(col(sms, pid, "tied", {}))
        trailing = _parse_struct(col(sms, pid, "trailing", {}))
        efgs = [v.get("efg_pct") for v in (leading, tied, trailing) if v.get("efg_pct") is not None]
        out["score_margin_consistency"].append(
            (max(efgs) - min(efgs)) if len(efgs) >= 2 else None
        )

        clutch_scoring = _parse_struct(col(atlas["clutch_scoring"], pid, "scoring", {}))
        out["clutch_scoring_pts_per36"].append(clutch_scoring.get("pts_per36"))

        blowout = _parse_struct(col(atlas["situational_splits"], pid, "blowout", {}))
        out["blowout_gt_pct"].append(blowout.get("mean_pct_min_in_gt"))

        stability = _parse_struct(col(atlas["ft_profile"], pid, "stability", {}))
        out["ft_reliability"].append(stability.get("ft_pct"))

    for k, v in out.items():
        t[k] = pd.to_numeric(pd.Series(v, index=t.index), errors="coerce")
    return t


def load_qualifying_factor_table(season: str = QUALIFY_SEASON) -> pd.DataFrame:
    """One-call convenience: load boxscores -> aggregate -> qualify -> join atlas."""
    box = load_boxscores()
    agg = aggregate_season(box, season=season)
    pool = qualifying_pool(agg)
    return build_factor_table(pool)
