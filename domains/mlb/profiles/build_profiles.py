"""domains.mlb.profiles.build_profiles -- registry-driven builder: for every
attribute in attribute_registry.ATTRIBUTES, dispatch to its builder function
(ingredients_batter/pitcher/catcher.BUILDERS), apply the registry's floor,
rank-percentile the qualified population, attach rating_2k, and write the
SHARED SCHEMA long-format parquet.

ONE frame per season is loaded (savant_hitcoords__{season}.parquet -- verified
live: a strict COLUMN superset of savant_full__{season}.parquet, same row
count both seasons, see module test) and passed to every builder; no double
load, no schema drift between "pitches" and "hitcoords" builders.

entity_name resolved via data/domains/mlb/player_gamelogs.parquet's
player_id/player columns (same MLBAM id scheme as batter/pitcher/fielder_2 --
precedent: catcher_framing_index.py). Unresolvable ids fall back to the
str(id) sentinel per the SHARED SCHEMA spec, never silently dropped.

CLI: python -m domains.mlb.profiles.build_profiles
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.profiles.attribute_registry import ATTRIBUTES, rating_2k
from domains.mlb.profiles.ingredients_batter import BUILDERS as BATTER_BUILDERS
from domains.mlb.profiles.ingredients_batter_grid import BUILDERS as BATTER_GRID_BUILDERS
from domains.mlb.profiles.ingredients_batter_zones import BUILDERS as BATTER_ZONE_BUILDERS
from domains.mlb.profiles.ingredients_catcher import BUILDERS as CATCHER_BUILDERS
from domains.mlb.profiles.ingredients_leaderboard import ATTR_TO_FAMILY as LEADERBOARD_FAMILY
from domains.mlb.profiles.ingredients_leaderboard import BUILDERS as LEADERBOARD_BUILDERS
from domains.mlb.profiles.ingredients_pitcher import BUILDERS as PITCHER_BUILDERS
from domains.mlb.profiles.ingredients_pitcher_grid import BUILDERS as PITCHER_GRID_BUILDERS
from domains.mlb.profiles.ingredients_pitcher_zones import BUILDERS as PITCHER_ZONE_BUILDERS

REPO_ROOT = Path(__file__).resolve().parents[3]
_STATCAST_DIR = REPO_ROOT / "data" / "cache" / "statcast"
_LEADERBOARD_DIR = REPO_ROOT / "data" / "cache" / "statcast" / "leaderboards"
_GAMELOGS = REPO_ROOT / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
_OUT_PATH = REPO_ROOT / "data" / "cache" / "profiles" / "mlb_player_profiles.parquet"

SEASONS = ("2023", "2024")
# bat-tracking didn't exist before 2024; all 3 leaderboard families are pulled
# 2024-2026 (see scripts/platformkit/data_frontier/savant_bat_tracking.py).
LEADERBOARD_YEARS = ("2024", "2025", "2026")

# pitch-frame builders ONLY (Callable[[pd.DataFrame], pd.DataFrame], one shared
# season frame per season -- see build_all's first loop). LEADERBOARD_BUILDERS
# (Callable[[str], pd.DataFrame], one CSV read per year) are dispatched
# separately below -- different input shape, different season set.
_BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    **BATTER_BUILDERS, **PITCHER_BUILDERS, **CATCHER_BUILDERS,
    **BATTER_GRID_BUILDERS, **PITCHER_GRID_BUILDERS,
    **BATTER_ZONE_BUILDERS, **PITCHER_ZONE_BUILDERS,
}
_ALL_BUILDER_ATTRS = set(_BUILDERS) | set(LEADERBOARD_BUILDERS)
assert _ALL_BUILDER_ATTRS == set(ATTRIBUTES), (
    f"builder/registry mismatch: {set(ATTRIBUTES) ^ _ALL_BUILDER_ATTRS}")


def load_season(season: str) -> pd.DataFrame:
    return pd.read_parquet(_STATCAST_DIR / f"savant_hitcoords__{season}.parquet")


def load_name_lookup() -> dict[int, str]:
    if not _GAMELOGS.exists():
        return {}
    names = pd.read_parquet(_GAMELOGS, columns=["player_id", "player"])
    return dict(names.drop_duplicates(subset=["player_id"], keep="last").set_index("player_id")["player"])


def _percentile_and_rating(df: pd.DataFrame) -> pd.DataFrame:
    """Percentile in [0,100] = rank-pct within the QUALIFIED (floor-passing)
    population for this attribute+window; rating_2k from attribute_registry's
    formula. NaN raw_value never ranks (dropped upstream by the floor already,
    but guarded again here so a stray NaN can't produce a fabricated rank)."""
    out = df.dropna(subset=["raw_value"]).copy()
    out["percentile"] = out["raw_value"].rank(pct=True, method="average") * 100.0
    out["rating_2k"] = out["percentile"].map(rating_2k)
    return out


def build_attribute_window(attr: str, season: str, frame: pd.DataFrame,
                            name_lookup: dict[int, str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    spec = ATTRIBUTES[attr]
    raw = _BUILDERS[attr](frame)
    n_considered = len(raw)
    qualified = raw[raw["n"] >= spec["floor"]].copy()
    n_excluded = n_considered - len(qualified)
    scored = _percentile_and_rating(qualified)

    scored["entity_id"] = scored["entity_id"].astype(int)
    scored["entity_name"] = scored["entity_id"].map(lambda eid: name_lookup.get(eid, str(eid)))
    scored["window"] = f"season_{season}"
    scored["attribute"] = attr
    scored["ingredients"] = scored["ingredients"].map(json.dumps)
    scored["status"] = spec["status"]
    scored["sources"] = json.dumps([f"data/cache/statcast/savant_hitcoords__{season}.parquet"])

    coverage = {
        "attribute": attr, "season": season, "entity": spec["entity"],
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "n_qualifying": len(scored), "floor": spec["floor"], "status": spec["status"],
    }
    cols = ["entity_id", "entity_name", "window", "attribute", "raw_value", "percentile",
            "rating_2k", "n", "ingredients", "status", "sources"]
    return scored[cols], coverage


def build_leaderboard_attribute_window(attr: str, year: str,
                                        name_lookup: dict[int, str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Same shape as build_attribute_window, but for a LEADERBOARD_BUILDERS
    attribute: no shared pitch-frame, builder reads its own per-year CSV."""
    spec = ATTRIBUTES[attr]
    raw = LEADERBOARD_BUILDERS[attr](year)
    n_considered = len(raw)
    qualified = raw[raw["n"] >= spec["floor"]].copy()
    n_excluded = n_considered - len(qualified)
    scored = _percentile_and_rating(qualified)

    scored["entity_id"] = scored["entity_id"].astype(int)
    scored["entity_name"] = scored["entity_id"].map(lambda eid: name_lookup.get(eid, str(eid)))
    scored["window"] = f"season_{year}"
    scored["attribute"] = attr
    scored["ingredients"] = scored["ingredients"].map(json.dumps)
    scored["status"] = spec["status"]
    family = LEADERBOARD_FAMILY[attr]
    scored["sources"] = json.dumps([f"data/cache/statcast/leaderboards/{family}_{year}.csv"])

    coverage = {
        "attribute": attr, "season": year, "entity": spec["entity"],
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "n_qualifying": len(scored), "floor": spec["floor"], "status": spec["status"],
    }
    cols = ["entity_id", "entity_name", "window", "attribute", "raw_value", "percentile",
            "rating_2k", "n", "ingredients", "status", "sources"]
    return scored[cols], coverage


def build_all() -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    name_lookup = load_name_lookup()
    frames, coverage_rows = [], []
    for season in SEASONS:
        frame = load_season(season)
        for attr in _BUILDERS:
            scored, coverage = build_attribute_window(attr, season, frame, name_lookup)
            frames.append(scored)
            coverage_rows.append(coverage)
    for year in LEADERBOARD_YEARS:
        for attr in LEADERBOARD_BUILDERS:
            scored, coverage = build_leaderboard_attribute_window(attr, year, name_lookup)
            frames.append(scored)
            coverage_rows.append(coverage)
    profiles = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return profiles, coverage_rows


def write_profiles(profiles: pd.DataFrame, out_path: Path = _OUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(profiles, preserve_index=False), out_path)
    return out_path


def main() -> int:
    profiles, coverage_rows = build_all()
    out_path = write_profiles(profiles)
    print(f"{'attribute':<22}{'season':<8}{'entity':<9}{'status':<20}"
          f"{'n_consid':>9}{'n_qual':>9}{'floor':>7}")
    for c in coverage_rows:
        print(f"{c['attribute']:<22}{c['season']:<8}{c['entity']:<9}{c['status']:<20}"
              f"{c['n_considered']:>9}{c['n_qualifying']:>9}{c['floor']:>7}")
    print(f"wrote {len(profiles)} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
