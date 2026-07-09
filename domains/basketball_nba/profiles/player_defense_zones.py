"""PLAYER defensive zone attribute computation -- one pass-through attribute
per (zone, metric, side) triple sourced straight from lineups/zone_onoff.py's
extended output (rim/paint/mid/corner3/above_break_3 x share_allowed/
efg_allowed x on/off = 20 attributes). Mirrors team_attributes.py's
shot_diet/concession pass-through pattern, just at player grain.

Floor: min_on>=750 AND min_off>=750 (both sides required, same precedent as
player_attributes.py's rim_pressure_def) -- so an "on" and "off" attribute
for the same zone/metric always share the same qualified population.

NETWORK: zero.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"

DEFENSE_ZONES = ["rim", "paint", "mid", "corner3", "above_break_3"]
DEFENSE_METRICS = ["share_allowed", "efg_allowed"]
# "share"/"efg" ALLOWED -- lower is better defense, same convention as
# attribute_registry.CONCESSION_LOWER_IS_BETTER.
DEFENSE_LOWER_IS_BETTER = True


def _window(season: str) -> str:
    return f"season_{season}"


def build_player_defense_zones(season: str) -> list[dict]:
    src = _LINEUPS / f"zone_onoff_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    df = exclude_negative_ids(df, "player_id")
    qualified = df[(df["min_on"] >= 750.0) & (df["min_off"] >= 750.0)].copy()
    if qualified.empty:
        return []

    rows: list[dict] = []
    for zone in DEFENSE_ZONES:
        for metric in DEFENSE_METRICS:
            for side, n_col in (("on", "min_on"), ("off", "min_off")):
                col = f"{zone}_{metric}_{side}"
                if col not in qualified.columns:
                    continue
                rows.extend(finalize_rows(
                    qualified, entity_col="player_id", name_col="player_name",
                    raw_col=col, n_col=n_col, window=_window(season),
                    attribute=f"zone_def_{zone}_{metric}_{side}", status="DESCRIPTIVE",
                    sources=rel_sources(src), ingredient_cols=[col, "min_on", "min_off"],
                    higher_is_better=not DEFENSE_LOWER_IS_BETTER,
                ))
    return rows


BUILDERS = [build_player_defense_zones]


def build_all_player_defense_zone_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
