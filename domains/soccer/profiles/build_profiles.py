"""domains.soccer.profiles.build_profiles -- registry-driven soccer TEAM
ATTRIBUTE ENGINE. Builds data/cache/profiles/soccer_team_profiles.parquet
(long format: entity_id, entity_name, window, attribute, raw_value,
percentile, rating_2k, n, ingredients, status, sources) from the statsbomb
400-match event corpus (5 attributes) + the footballdata ~25.8k-match season
corpus (2 attributes), per attribute_registry.REGISTRY. Also emits top-10
ranking claims (data/cache/intel_claims/soccer_profile_claims.jsonl) over the
SAME materialized snapshot parquets so the independent validator
(claims_validator_batch) recomputes every ranking from scratch.

press_resistance is declared BLOCKED in attribute_registry.BLOCKED_ATTRIBUTES
and never produces rows -- see that module for why.

CLI: python -m domains.soccer.profiles.build_profiles
Per-file test: python -m pytest domains/soccer/profiles/test_build_profiles.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from domains.soccer.prereg_possession_chains import build_possessions
from domains.soccer.profiles.attribute_registry import BLOCKED_ATTRIBUTES, REGISTRY
from domains.soccer.profiles.claims import _CLAIMS_PATH, build_claims, write_claims, write_snapshots
from domains.soccer.profiles.ingredients_expanded import (
    _away_goal_rate,
    _away_strength,
    _clean_sheet_rate,
    _comeback_rate,
    _corner_rate,
    _defensive_counter_threat,
    _defensive_set_piece_threat,
    _discipline_rate,
    _first_half_xg_share,
    _foul_rate,
    _formation_primary_xg,
    _formation_secondary_xg,
    _home_goal_rate,
    _possessions_per_match,
    _second_half_xg_share,
    _shot_accuracy,
    _shot_conversion_rate,
    _shots_per_possession,
)
from domains.soccer.profiles.row_shape import _entity_names, _rows
from domains.soccer.profiles.snapshots_expanded import EXPANDED_SOURCES_SB, EXPANDED_SOURCES_SEASON, build_expanded_snapshots
from domains.soccer.profiles.source_builders import (
    build_defensive_snapshot,
    build_formation_snapshot,
    build_possession_snapshot,
    build_season_snapshots,
    load_statsbomb_context,
)
from scripts.platformkit.intel_validation.validate_store import validate_and_write

REPO_ROOT = Path(__file__).resolve().parents[3]
_PROFILES_DIR = REPO_ROOT / "data" / "cache" / "profiles"
_PROFILES_PATH = _PROFILES_DIR / "soccer_team_profiles.parquet"

_SB_WINDOW = "statsbomb_2015_2021"
_SB_SOURCES = ["data/cache/statsbomb/events", "data/cache/statsbomb/matches"]
_SEASON_SOURCES = ["data/domains/soccer/match_stats.parquet", "data/domains/soccer/matches.parquet"]
SOURCES = {a: _SB_SOURCES for a in
           ("counter_threat", "buildup_quality", "set_piece_threat", "formation_flexibility", "defensive_solidity")}
SOURCES.update({"finishing_overperformance": _SEASON_SOURCES, "home_strength": ["data/domains/soccer/matches.parquet"]})
# 07-08 expansion
SOURCES.update({a: _SB_SOURCES for a in EXPANDED_SOURCES_SB})
SOURCES.update({a: _SEASON_SOURCES for a in EXPANDED_SOURCES_SEASON})


def _counter_threat(poss_snap: pd.DataFrame) -> pd.DataFrame:
    agg = poss_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"), total_n=("xg", "count"),
        counter_n=("counter_xg", "count"), counter_xg_sum=("counter_xg", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(_entity_names(poss_snap))
    agg["counter_share"] = agg["counter_n"] / agg["total_n"]
    agg["counter_xg_per_poss"] = (agg["counter_xg_sum"] / agg["counter_n"]).where(agg["counter_n"] > 0, 0.0)
    # counter_share * counter_xg_per_poss simplifies to counter_xg_sum/total_n -- avoids
    # a 0*NaN edge case if a team never counters, and matches the claim formula exactly.
    agg["raw_value"] = agg["counter_xg_sum"] / agg["total_n"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["counter_share", "counter_xg_per_poss", "counter_n", "total_n"], _SB_WINDOW)


def _buildup_quality(poss_snap: pd.DataFrame) -> pd.DataFrame:
    agg = poss_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"),
        regular_poss_n=("regular_xg", "count"), regular_xg_sum=("regular_xg", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(_entity_names(poss_snap))
    agg["raw_value"] = agg["regular_xg_sum"] / agg["regular_poss_n"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["regular_xg_sum", "regular_poss_n"], _SB_WINDOW)


def _set_piece_threat(poss_snap: pd.DataFrame) -> pd.DataFrame:
    agg = poss_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"),
        set_piece_xg_sum=("set_piece_xg", "sum"), total_xg_sum=("xg", "sum"), total_n=("xg", "count"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(_entity_names(poss_snap))
    agg["raw_value"] = agg["set_piece_xg_sum"] / agg["total_xg_sum"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["set_piece_xg_sum", "total_xg_sum", "total_n"], _SB_WINDOW)


def _defensive_solidity(def_snap: pd.DataFrame, names: pd.Series) -> pd.DataFrame:
    agg = def_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"),
        opponent_poss_n=("poss", "sum"), opponent_regular_xg_conceded_sum=("xg", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(names)
    agg["raw_value"] = agg["opponent_regular_xg_conceded_sum"] / agg["opponent_poss_n"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["opponent_regular_xg_conceded_sum", "opponent_poss_n"], _SB_WINDOW)


def _formation_flexibility(form_snap: pd.DataFrame) -> pd.DataFrame:
    if form_snap.empty:
        return form_snap
    agg = form_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"),
        n_distinct_formations=("formation", "nunique"), share_primary=("is_primary", "mean"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(_entity_names(form_snap))
    primary = form_snap[form_snap["is_primary"] == 1.0].groupby("entity_id")["formation"].first()
    agg["primary_formation"] = agg["entity_id"].map(primary)
    agg["raw_value"] = 1.0 - agg["share_primary"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["n_distinct_formations", "primary_formation", "share_primary"], _SB_WINDOW)


def _finishing_overperformance(finishing_snap: pd.DataFrame) -> pd.DataFrame:
    agg = finishing_snap.groupby(["entity_id", "season"]).agg(
        match_n=("diff", "count"), goals_minus_proxy_xg_sum=("diff", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"]
    agg["raw_value"] = agg["goals_minus_proxy_xg_sum"] / agg["match_n"]
    agg["n"] = agg["match_n"]
    agg["window"] = "footballdata_" + agg["season"].astype(str)
    return _rows(agg, ["goals_minus_proxy_xg_sum", "match_n"], None)


def _home_strength(homestrength_snap: pd.DataFrame) -> pd.DataFrame:
    agg = homestrength_snap.groupby(["entity_id", "season"]).agg(
        home_match_n=("pts", "count"), home_points_sum=("pts", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"]
    agg["raw_value"] = agg["home_points_sum"] / agg["home_match_n"] / 3.0
    agg["n"] = agg["home_match_n"]
    agg["window"] = "footballdata_" + agg["season"].astype(str)
    return _rows(agg, ["home_points_sum", "home_match_n"], None)


def add_percentile_rating(df: pd.DataFrame) -> pd.DataFrame:
    """percentile/rating_2k computed WITHIN each (attribute, window) group.
    rating_2k = 25 + percentile*0.74 (presentation only, range ~25-99)."""
    parts = []
    for (attr, _window), g in df.groupby(["attribute", "window"], sort=False):
        higher = REGISTRY[attr]["higher_is_better"]
        basis = g["raw_value"] if higher else -g["raw_value"]
        g = g.copy()
        g["percentile"] = (basis.rank(pct=True) * 100.0).round(2)
        g["rating_2k"] = (25 + g["percentile"] * 0.74).round(2)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def build_snapshots() -> dict[str, pd.DataFrame]:
    match_lookup, match_teams = load_statsbomb_context()
    possessions = build_possessions(match_lookup=match_lookup)
    poss_snap = build_possession_snapshot(possessions)
    def_snap = build_defensive_snapshot(possessions, match_teams)
    form_snap = build_formation_snapshot(match_lookup)
    finishing_snap, homestrength_snap = build_season_snapshots()
    def_names = poss_snap.drop_duplicates("entity_id").set_index("entity_id")["entity_name"]

    snaps = {
        "counter_threat": poss_snap, "buildup_quality": poss_snap, "set_piece_threat": poss_snap,
        "defensive_solidity": def_snap, "formation_flexibility": form_snap,
        "finishing_overperformance": finishing_snap, "home_strength": homestrength_snap,
        "_def_names": def_names,
    }
    snaps.update(build_expanded_snapshots(match_teams, possessions, poss_snap, form_snap))
    return snaps


def build_profile_frames(snaps: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {
        "counter_threat": _counter_threat(snaps["counter_threat"]),
        "buildup_quality": _buildup_quality(snaps["buildup_quality"]),
        "set_piece_threat": _set_piece_threat(snaps["set_piece_threat"]),
        "defensive_solidity": _defensive_solidity(snaps["defensive_solidity"], snaps["_def_names"]),
        "formation_flexibility": _formation_flexibility(snaps["formation_flexibility"]),
        "finishing_overperformance": _finishing_overperformance(snaps["finishing_overperformance"]),
        "home_strength": _home_strength(snaps["home_strength"]),
        # 07-08 expansion
        "defensive_counter_threat": _defensive_counter_threat(snaps["defensive_counter_threat"], snaps["_def_names"]),
        "defensive_set_piece_threat": _defensive_set_piece_threat(snaps["defensive_set_piece_threat"], snaps["_def_names"]),
        "first_half_xg_share": _first_half_xg_share(snaps["first_half_xg_share"]),
        "second_half_xg_share": _second_half_xg_share(snaps["second_half_xg_share"]),
        "possessions_per_match": _possessions_per_match(snaps["possessions_per_match"]),
        "shots_per_possession": _shots_per_possession(*snaps["shots_per_possession"]),
        "formation_primary_xg": _formation_primary_xg(*snaps["formation_primary_xg"]),
        "formation_secondary_xg": _formation_secondary_xg(*snaps["formation_secondary_xg"]),
        "home_goal_rate": _home_goal_rate(snaps["home_goal_rate"]),
        "away_goal_rate": _away_goal_rate(snaps["away_goal_rate"]),
        "away_strength": _away_strength(snaps["away_strength"]),
        "clean_sheet_rate": _clean_sheet_rate(snaps["clean_sheet_rate"]),
        "comeback_rate": _comeback_rate(snaps["comeback_rate"]),
        "shot_conversion_rate": _shot_conversion_rate(snaps["shot_conversion_rate"]),
        "shot_accuracy": _shot_accuracy(snaps["shot_accuracy"]),
        "discipline_rate": _discipline_rate(snaps["discipline_rate"]),
        "foul_rate": _foul_rate(snaps["foul_rate"]),
        "corner_rate": _corner_rate(snaps["corner_rate"]),
    }


def build_profile_table(frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (raw_df, profile_df): raw_df is every computed entity-window
    row BEFORE the registry floor (used for honest n_excluded_below_floor in
    claims); profile_df is floor-qualifying rows with percentile/rating_2k,
    the exact shape written to soccer_team_profiles.parquet."""
    raw_parts = []
    for attr, rows in frames.items():
        if rows.empty:
            continue
        rows = rows.copy()
        rows["attribute"] = attr
        raw_parts.append(rows)
    raw_df = pd.concat(raw_parts, ignore_index=True)
    floor = raw_df["attribute"].map(lambda a: REGISTRY[a]["floor"])
    profile_df = raw_df[raw_df["n"] >= floor].reset_index(drop=True)
    profile_df = add_percentile_rating(profile_df)
    profile_df["status"] = profile_df["attribute"].map(lambda a: REGISTRY[a]["status"])
    profile_df["sources"] = profile_df["attribute"].map(lambda a: json.dumps(SOURCES[a]))
    profile_df["ingredients"] = profile_df["ingredients"].map(json.dumps)
    cols = ["entity_id", "entity_name", "window", "attribute", "raw_value",
            "percentile", "rating_2k", "n", "ingredients", "status", "sources"]
    return raw_df, profile_df[cols]


def write_profiles(profile_df: pd.DataFrame, out_path: Path = _PROFILES_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile_df.to_parquet(out_path, index=False)
    return out_path


def main() -> int:
    snaps = build_snapshots()
    frames = build_profile_frames(snaps)
    raw_df, profile_df = build_profile_table(frames)
    write_profiles(profile_df)
    print(f"wrote {len(profile_df)} profile rows -> {_PROFILES_PATH}")
    for attr in REGISTRY:
        sub = profile_df[profile_df["attribute"] == attr]
        pre = raw_df[raw_df["attribute"] == attr]
        print(f"  {attr:<26} status={REGISTRY[attr]['status']:<18} "
              f"windows={sub['window'].nunique():<4} rows={len(sub):<5} (considered={len(pre)})")
    for attr, blocked in BLOCKED_ATTRIBUTES.items():
        print(f"  {attr:<26} BLOCKED: {blocked['reason'][:90]}...")

    snapshot_paths = write_snapshots(snaps)
    claims = build_claims(raw_df, profile_df, snapshot_paths)
    out_path = write_claims(claims)
    print(f"wrote {len(claims)} claims -> {out_path}")
    for c in claims:
        print(f"  {c['claim_id']}: n_considered={c['n_considered']} "
              f"n_excluded={c['n_excluded_below_floor']} n_ranked={len(c['ranking'])}")

    result = validate_and_write(str(_CLAIMS_PATH))
    print(f"validate_store: {result['n_verified']}/{result['n_claims']} verified, "
          f"{result['n_mismatch']} mismatch, {result['n_unverifiable']} unverifiable -> {result['out']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
