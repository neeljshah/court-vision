"""domains.basketball_wnba.profiles.build_profiles -- registry-driven builder:
for every attribute in attribute_registry.ATTRIBUTES, dispatch to its builder
(ingredients_player/ingredients_lineup.BUILDERS), apply the registry floor,
rank-percentile the qualified population, attach rating_2k, and write the
SHARED SCHEMA long-format parquets -- one window only (season_2026, this
sport's single-season corpus).

Mirrors domains/mlb/profiles/build_profiles.py's shape; THREE output
parquets (player, lineup, team -- team added 2026-07-18 for the
wnba_schedule_rest/wnba_team_form families), since the task's SHARED SCHEMA
declares wnba_{player,lineup,team}_profiles.parquet separately (same
3-file precedent as domains/basketball_nba/profiles/build_profiles.py).

CLI: python -m domains.basketball_wnba.profiles.build_profiles
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.basketball_wnba.claims_player_form import load_boxscores
from domains.basketball_wnba.profiles.attribute_registry import ATTRIBUTES, WINDOW_OVERRIDES, rating_2k
from domains.basketball_wnba.profiles.ingredients_defzone import BUILDERS as DEFZONE_BUILDERS
from domains.basketball_wnba.profiles.ingredients_home_away import BUILDERS as HOME_AWAY_BUILDERS
from domains.basketball_wnba.profiles.ingredients_last10 import BUILDERS as LAST10_BUILDERS
from domains.basketball_wnba.profiles.ingredients_lineup import BUILDERS as LINEUP_BUILDERS
from domains.basketball_wnba.profiles.ingredients_player import BUILDERS as PLAYER_BUILDERS
from domains.basketball_wnba.profiles.ingredients_schedule_rest import BUILDERS as SCHEDULE_REST_BUILDERS
from domains.basketball_wnba.profiles.ingredients_team_form import BUILDERS as TEAM_FORM_BUILDERS
from domains.basketball_wnba.profiles.ingredients_zone import BUILDERS as ZONE_BUILDERS
from domains.basketball_wnba.profiles.source_shots import load_all_shots

REPO_ROOT = Path(__file__).resolve().parents[3]
_LINEUPS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_WNBA_DOMAIN_DIR = REPO_ROOT / "data" / "domains" / "wnba"
_OUT_DIR = REPO_ROOT / "data" / "cache" / "profiles"
_PLAYER_OUT = _OUT_DIR / "wnba_player_profiles.parquet"
_LINEUP_OUT = _OUT_DIR / "wnba_lineup_profiles.parquet"
_TEAM_OUT = _OUT_DIR / "wnba_team_profiles.parquet"

WINDOW = "season_2026"

_BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    **PLAYER_BUILDERS, **LINEUP_BUILDERS, **ZONE_BUILDERS, **DEFZONE_BUILDERS, **LAST10_BUILDERS,
    **HOME_AWAY_BUILDERS, **SCHEDULE_REST_BUILDERS, **TEAM_FORM_BUILDERS,
}
assert set(_BUILDERS) == set(ATTRIBUTES), f"builder/registry mismatch: {set(ATTRIBUTES) ^ set(_BUILDERS)}"

_load_scoreboard = lambda: pd.read_parquet(_WNBA_DOMAIN_DIR / "espn_scoreboard.parquet")

_FRAME_LOADERS: dict[str, Callable[[], pd.DataFrame]] = {
    "on_court_impact": lambda: pd.read_parquet(_LINEUPS_DIR / "on_off_wnba_2026.parquet"),
    "gravity": lambda: pd.read_parquet(_LINEUPS_DIR / "on_off_wnba_2026.parquet"),
    "scoring_per36": load_boxscores,
    "reb_per36": load_boxscores,
    "ast_per36": load_boxscores,
    "efg": load_boxscores,
    "usage_proxy_per36": load_boxscores,
    "recent_form": load_boxscores,
    "spacing": lambda: pd.read_parquet(_LINEUPS_DIR / "lineup_spacing_wnba_2026.parquet"),
    "matchup_net": lambda: pd.read_parquet(_LINEUPS_DIR / "lineup_matchups_wnba_2026.parquet"),
    "minutes_together": lambda: pd.read_parquet(_LINEUPS_DIR / "stints_wnba_2026.parquet"),
    **{attr: load_all_shots for attr in ZONE_BUILDERS},
    **{attr: (lambda: pd.read_parquet(_LINEUPS_DIR / "zone_onoff_wnba_2026.parquet")) for attr in DEFZONE_BUILDERS},
    **{attr: load_boxscores for attr in LAST10_BUILDERS},
    **{attr: load_boxscores for attr in HOME_AWAY_BUILDERS},
    **{attr: load_boxscores for attr in SCHEDULE_REST_BUILDERS},
    **{attr: _load_scoreboard for attr in TEAM_FORM_BUILDERS},
}
assert set(_FRAME_LOADERS) == set(ATTRIBUTES), f"loader/registry mismatch: {set(ATTRIBUTES) ^ set(_FRAME_LOADERS)}"


def _percentile_and_rating(df: pd.DataFrame) -> pd.DataFrame:
    """Percentile in [0,100] = rank-pct within the QUALIFIED (floor-passing)
    population for this attribute; rating_2k from attribute_registry's
    formula. NaN raw_value never ranks."""
    out = df.dropna(subset=["raw_value"]).copy()
    out["percentile"] = out["raw_value"].rank(pct=True, method="average") * 100.0
    out["rating_2k"] = out["percentile"].map(rating_2k)
    return out


def build_attribute(attr: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    spec = ATTRIBUTES[attr]
    raw = _BUILDERS[attr](_FRAME_LOADERS[attr]())
    n_considered = len(raw)
    qualified = raw[raw["n"] >= spec["floor"]].copy()
    n_excluded = n_considered - len(qualified)
    scored = _percentile_and_rating(qualified)

    scored["window"] = WINDOW_OVERRIDES.get(attr, WINDOW)
    scored["attribute"] = attr
    scored["ingredients"] = scored["ingredients"].map(json.dumps)
    scored["status"] = spec["status"]
    scored["sources"] = json.dumps(spec["source_files"])

    coverage = {
        "attribute": attr, "entity": spec["entity"], "status": spec["status"],
        "n_considered": n_considered, "n_excluded_below_floor": n_excluded,
        "n_qualifying": len(scored), "floor": spec["floor"],
    }
    cols = ["entity_id", "entity_name", "window", "attribute", "raw_value", "percentile",
            "rating_2k", "n", "ingredients", "status", "sources"]
    return scored[cols], coverage


def build_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    player_frames, lineup_frames, team_frames, coverage_rows = [], [], [], []
    _entity_bucket = {"player": player_frames, "lineup": lineup_frames, "team": team_frames}
    for attr, spec in ATTRIBUTES.items():
        scored, coverage = build_attribute(attr)
        coverage_rows.append(coverage)
        _entity_bucket[spec["entity"]].append(scored)
    players = pd.concat(player_frames, ignore_index=True) if player_frames else pd.DataFrame()
    lineups = pd.concat(lineup_frames, ignore_index=True) if lineup_frames else pd.DataFrame()
    teams = pd.concat(team_frames, ignore_index=True) if team_frames else pd.DataFrame()
    return players, lineups, teams, coverage_rows


def _write(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def main() -> int:
    players, lineups, teams, coverage_rows = build_all()
    _write(players, _PLAYER_OUT)
    _write(lineups, _LINEUP_OUT)
    _write(teams, _TEAM_OUT)
    print(f"{'attribute':<20}{'entity':<9}{'status':<16}{'n_consid':>9}{'n_qual':>9}{'floor':>7}")
    for c in coverage_rows:
        print(f"{c['attribute']:<20}{c['entity']:<9}{c['status']:<16}"
              f"{c['n_considered']:>9}{c['n_qualifying']:>9}{c['floor']:>7}")
    print(f"wrote {len(players)} player rows -> {_PLAYER_OUT}")
    print(f"wrote {len(lineups)} lineup rows -> {_LINEUP_OUT}")
    print(f"wrote {len(teams)} team rows -> {_TEAM_OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
