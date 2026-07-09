"""PLAYER attribute computation -- one function per ATTRIBUTES key (see
attribute_registry.py for the formula/floor/ingredients each one documents).
Each function returns SHARED-SCHEMA row dicts for ONE season.

NETWORK: zero.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, compose_rim_pressure as _compose_rim_pressure, exclude_negative_ids,
    finalize_rows, rel_sources, zscore as _zscore,
)

_TS = REPO_ROOT / "data" / "cache" / "team_system"
_LINEUPS = _TS / "lineups"
_INTERACTIONS = _TS / "interactions"
_COMPOSITION = _TS / "composition"
_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"


def _window(season: str) -> str:
    return f"season_{season}"


def build_gravity(season: str) -> list[dict]:
    src = _LINEUPS / f"gravity_proxy_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    df = exclude_negative_ids(df, "player_id")
    df = df[df["min_on"] >= 300.0].copy()
    return finalize_rows(
        df, entity_col="player_id", name_col="player_name", raw_col="gravity_proxy", n_col="min_on",
        window=_window(season), attribute="gravity", status="VALIDATED_CLAIM", sources=rel_sources(src),
        ingredient_cols=["teammate_efg_on", "teammate_efg_off", "min_on"],
    )


def build_usage_absorption(season: str) -> list[dict]:
    src = _INTERACTIONS / f"usage_redistribution_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    df = exclude_negative_ids(df, "teammate_id", "player_id")
    grp = df.groupby("teammate_id").agg(
        raw_value=("share_delta", "mean"),
        n=("teammate_fga_joint", "sum"),
        n_pairs=("share_delta", "count"),
        entity_name=("teammate_name", "first"),
    ).reset_index()
    grp = grp[grp["n"] >= 100.0]
    return finalize_rows(
        grp, entity_col="teammate_id", name_col="entity_name", raw_col="raw_value", n_col="n",
        window=_window(season), attribute="usage_absorption", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["raw_value", "n_pairs"],
    )


def build_creation(season: str) -> list[dict]:
    src = _INTERACTIONS / f"assist_network_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    df = exclude_negative_ids(df, "assister_id", "scorer_id")
    grp = df.groupby("assister_id").agg(
        raw_value=("efg_delta", "mean"),
        n=("n_assists", "sum"),
        entity_name=("assister_name", "first"),
    ).reset_index()
    grp = grp[grp["n"] >= 20.0]
    return finalize_rows(
        grp, entity_col="assister_id", name_col="entity_name", raw_col="raw_value", n_col="n",
        window=_window(season), attribute="creation", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["raw_value", "n"],
    )


def build_spacing_contribution(season: str) -> list[dict]:
    """'Without' is scoped to the SAME team_id's own lineups -- comparing
    against a DIFFERENT team's lineups would be meaningless (the player was
    never eligible to be in them). A trade mid-season would otherwise emit
    two rows for the same player_id (one per team) -- ponytail: keep only
    the team with more 'with' shot-volume (his primary team that season),
    documented rather than adding a (player,team) composite key the SHARED
    SCHEMA doesn't have room for."""
    src = _LINEUPS / f"lineup_spacing_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src).dropna(subset=["spacing_mean_dist"])
    df["members"] = df["lineup_key"].astype(str).str.split(",")
    rows = []
    for team_id, team_df in df.groupby("team_id"):
        players = sorted({int(p) for m in team_df["members"] for p in m if p.lstrip("-").isdigit()})
        for pid in players:
            if pid < 0:
                continue
            in_mask = team_df["members"].apply(lambda m, pid=pid: str(pid) in m)
            with_df, without_df = team_df[in_mask], team_df[~in_mask]
            w_with, w_without = with_df["n_shots"].sum(), without_df["n_shots"].sum()
            if w_with < 200.0 or w_without <= 0:
                continue
            mean_with = (with_df["spacing_mean_dist"] * with_df["n_shots"]).sum() / w_with
            mean_without = (without_df["spacing_mean_dist"] * without_df["n_shots"]).sum() / w_without
            rows.append({
                "player_id": pid, "raw_value": float(mean_with - mean_without), "n": float(w_with),
                "mean_with": float(mean_with), "mean_without": float(mean_without),
            })
    if not rows:
        return []
    d = pd.DataFrame(rows).sort_values("n", ascending=False).drop_duplicates("player_id", keep="first")
    return finalize_rows(
        d, entity_col="player_id", name_col=None, raw_col="raw_value", n_col="n",
        window=_window(season), attribute="spacing_contribution", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["mean_with", "mean_without"],
    )


def _on_off_pts_against(stints: pd.DataFrame) -> pd.DataFrame:
    """Isolates pts_against on/off per player -- the SAME clean-stint
    (n_on_court==5) lineup-membership groupby on_off.py already does for
    net_rating, just not persisted as a standalone column there. 'Off' is
    scoped to the player's OWN team_id's stints only (on_off.py keys by
    (player_id, team_id) for exactly this reason -- pooling every OTHER
    team's stints as "off" was this module's own v1 bug, caught by a
    sanity check on Jokic's min_off coming back >100,000 minutes; fixed
    here by grouping per team_id first, same trade-dedup as
    build_spacing_contribution (keep the team with more on-court minutes)."""
    clean = stints[stints["n_on_court"] == 5].copy()
    clean["members"] = clean["lineup_key"].astype(str).str.split(",")
    rows = []
    for team_id, team_df in clean.groupby("team_id"):
        players = sorted({int(p) for m in team_df["members"] for p in m if p.lstrip("-").isdigit()})
        for pid in players:
            if pid < 0:
                continue
            in_mask = team_df["members"].apply(lambda m, pid=pid: str(pid) in m)
            on_rows, off_rows = team_df[in_mask], team_df[~in_mask]
            min_on, min_off = on_rows["elapsed_s"].sum() / 60.0, off_rows["elapsed_s"].sum() / 60.0
            if min_on < 300.0 or min_off < 300.0:
                continue
            pts_against_on_per48 = on_rows["pts_against"].sum() / min_on * 48.0
            pts_against_off_per48 = off_rows["pts_against"].sum() / min_off * 48.0
            rows.append({
                "player_id": pid, "min_on": min_on, "min_off": min_off,
                "pts_against_per48_on": pts_against_on_per48, "pts_against_per48_off": pts_against_off_per48,
            })
    if not rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(rows).sort_values("min_on", ascending=False).drop_duplicates("player_id", keep="first")


def build_rim_pressure_def(season: str) -> list[dict]:
    stints_src = _LINEUPS / f"stints_{season}.parquet"
    zone_src = _LINEUPS / f"zone_onoff_{season}.parquet"
    if not stints_src.exists() or not zone_src.exists():
        return []
    stints = pd.read_parquet(stints_src)
    pts = _on_off_pts_against(stints)
    if pts.empty:
        return []
    # trade-dedup, same precedent as _on_off_pts_against/build_spacing_contribution:
    # keep the team a player logged the most on-court minutes with this season.
    zone = pd.read_parquet(zone_src).sort_values("min_on", ascending=False).drop_duplicates("player_id", keep="first")
    if zone.empty:
        return []

    zone_cols = ["player_id", "player_name", "rim_share_allowed_on", "rim_share_allowed_off", "rim_efg_allowed_on", "rim_efg_allowed_off"]
    d = pts.merge(zone[zone_cols], on="player_id", how="inner")  # inner: drops any negative
    # placeholder id (zone.parquet can carry one) -- pts already excludes them, see _on_off_pts_against
    d = d[(d["min_on"] >= 750.0) & (d["min_off"] >= 750.0)].dropna(
        subset=["rim_share_allowed_on", "rim_share_allowed_off", "rim_efg_allowed_on", "rim_efg_allowed_off"]
    ).reset_index(drop=True)
    if d.empty:
        return []
    d["raw_value"] = _compose_rim_pressure(d)

    concession_src = _COMPOSITION / "concession_2025_26.parquet"
    sources = [stints_src, zone_src]
    if season == "2025_26" and concession_src.exists():
        # team-level context ONLY -- see registry docstring; not blended
        # into raw_value or ingredients, just a source for the human reader.
        sources.append(concession_src)
    return finalize_rows(
        d, entity_col="player_id", name_col="player_name", raw_col="raw_value", n_col="min_on",
        window=_window(season), attribute="rim_pressure_def", status="DESCRIPTIVE", sources=rel_sources(*sources),
        ingredient_cols=[
            "rim_share_allowed_on", "rim_share_allowed_off", "rim_efg_allowed_on", "rim_efg_allowed_off",
            "pts_against_per48_on", "pts_against_per48_off", "min_on",
        ],
    )


_ZONE_SPECS = [
    ("shot_zone_three_rate_per36", lambda g: g["fg3a"] / g["min"] * 36.0),
    ("shot_zone_three_efg", lambda g: g["fg3m"] * 1.5 / g["fg3a"]),
    ("shot_zone_two_rate_per36", lambda g: (g["fga"] - g["fg3a"]) / g["min"] * 36.0),
    ("shot_zone_two_fg_pct", lambda g: (g["fgm"] - g["fg3m"]) / (g["fga"] - g["fg3a"])),
]


def build_shot_zone_profile(season: str) -> list[dict]:
    """player_boxscores.parquet's season labels are hyphenated ('2024-25');
    only 2024-25/2025-26 are on disk (no 2023-24 rows)."""
    label = season.replace("_", "-")
    if not _BOX.exists():
        return []
    box = pd.read_parquet(_BOX)
    box = box[box["season"] == label]
    if box.empty:
        return []
    box = exclude_negative_ids(box, "player_id")
    grp = box.groupby("player_id").agg(
        fg3a=("fg3a", "sum"), fg3m=("fg3m", "sum"), fga=("fga", "sum"), fgm=("fgm", "sum"),
        min=("min", "sum"), entity_name=("player_name", "first"),
    ).reset_index()
    grp = grp[grp["min"] >= 200.0]
    rows: list[dict] = []
    for attr, fn in _ZONE_SPECS:
        g = grp.copy()
        g["raw_value"] = fn(g)
        rows.extend(finalize_rows(
            g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
            window=_window(season), attribute=attr, status="DESCRIPTIVE", sources=rel_sources(_BOX),
            ingredient_cols=["fg3a", "fg3m", "fga", "fgm", "min"],
        ))
    return rows


def build_stint_stamina(season: str) -> list[dict]:
    src = _LINEUPS / f"stints_{season}.parquet"
    if not src.exists():
        return []
    stints = pd.read_parquet(src)
    clean = stints[stints["n_on_court"] == 5].copy()
    clean["members"] = clean["lineup_key"].astype(str).str.split(",")
    players = sorted({int(p) for m in clean["members"] for p in m if p.lstrip("-").isdigit()})
    rows = []
    for pid in players:
        if pid < 0:
            continue
        in_mask = clean["members"].apply(lambda m, pid=pid: str(pid) in m)
        my_stints = clean[in_mask]
        if len(my_stints) < 20:
            continue
        rows.append({
            "player_id": pid, "n_stints": len(my_stints),
            "avg_stint_s": float(my_stints["elapsed_s"].mean()),
            "total_minutes": float(my_stints["elapsed_s"].sum() / 60.0),
        })
    if not rows:
        return []
    d = pd.DataFrame(rows)
    out = finalize_rows(
        d, entity_col="player_id", name_col=None, raw_col="avg_stint_s", n_col="n_stints",
        window=_window(season), attribute="stint_stamina_avg_s", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["n_stints", "total_minutes"],
    )
    out += finalize_rows(
        d, entity_col="player_id", name_col=None, raw_col="total_minutes", n_col="n_stints",
        window=_window(season), attribute="stint_minutes_load", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["n_stints", "avg_stint_s"],
    )
    return out


BUILDERS = [
    build_gravity, build_usage_absorption, build_creation, build_spacing_contribution,
    build_rim_pressure_def, build_shot_zone_profile, build_stint_stamina,
]


def build_all_player_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    # offense zone/context/clutch (24 attrs) + last20 window multipliers (2) --
    # own modules to keep this file under the 300 LOC rule, wired here so
    # build_profiles.py's existing build_all_player_rows() call picks them up.
    from domains.basketball_nba.profiles.player_offense_windows import (
        build_all_player_offense_window_rows,
    )
    from domains.basketball_nba.profiles.player_offense_zones import (
        build_all_player_offense_zone_rows,
    )
    rows.extend(build_all_player_offense_zone_rows(seasons))
    rows.extend(build_all_player_offense_window_rows(seasons))
    return rows
