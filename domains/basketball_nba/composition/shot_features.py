"""Shot-level feature frame for shot_quality.py's P(make) model -- one row
per shot ATTEMPT (2pt/3pt PBP action) across the 1192-game 2025-26 corpus.
Zone comes from zone_geometry.classify_zone (x/y position, NOT the PBP
`area` field -- see that module's docstring: `area` covers only ~12% of
shots here). assisted uses concession_profiles._is_assisted (assistPersonId
OR "assist" in description text, covering both CDN-native and ESPN-derived
shapes). Then joined with three pre-built intelligence layers:

  shooter_zone_efg          -- SEASON-LONG (whole-corpus, not as-of) eFG% for
    this shooter in this zone. ponytail: this is a DESCRIPTIVE v1 baseline,
    not leak-free -- the shot itself contributes to its own season average
    (negligible for high-volume shooters, non-negligible for low-volume
    ones). Walk-forward as-of (only prior shots) is the honest upgrade if
    this ever needs to be a predictive/OOS claim; here it is a shot-quality
    DESCRIPTOR, labelled as such.
  defense_zone_efg_allowed  -- from concession_profiles.py's own output,
    joined on (defense_team_id, zone).
  spacing_mean_dist         -- the shooter's LINEUP's season-aggregated
    shot-spacing proxy (gravity_spacing.py's lineup_spacing_2025_26.parquet),
    joined via on_off.py's attach_lineup_to_shots on (team_id, lineup_key).
    Falls back to the median spacing across all lineups when a shot's
    lineup never cleared build_spacing's own min_shots floor (ponytail:
    simple fallback, not a real spacing estimate for that lineup).

OUTPUT COLUMNS: game_id, defense_team_id, team_id (offense), person_id,
zone, subtype_class, assisted, made, points, shooter_zone_efg,
defense_zone_efg_allowed, spacing_mean_dist.

NETWORK: zero.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.composition.concession_profiles import _is_assisted
from domains.basketball_nba.composition.zone_geometry import ZONES, classify_zone
from domains.basketball_nba.lineups.on_off import attach_lineup_to_shots
from domains.basketball_nba.lineups.pbp_lineups import _elapsed_s

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "pbp"
_CONCESSION_SRC = REPO_ROOT / "data" / "cache" / "team_system" / "composition" / "concession_2025_26.parquet"
_STINTS_SRC = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_SPACING_SRC = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "lineup_spacing_2025_26.parquet"

MIN_SHOOTER_ZONE_FGA = 5  # below this, fall back to the league zone-average eFG


def load_raw_shots(pbp_dir: Path = _PBP_DIR, limit: int | None = None) -> pd.DataFrame:
    """One row per shot attempt with the raw PBP descriptors -- zero joins yet."""
    files = sorted(pbp_dir.glob("*.json"))
    if limit:
        files = files[:limit]
    rows: list[dict[str, Any]] = []
    for fp in files:
        game_json = json.loads(fp.read_text(encoding="utf-8"))
        game_id = game_json["game"]["gameId"]
        actions = game_json["game"]["actions"]
        team_ids = sorted({a["teamId"] for a in actions if a.get("teamId")})
        for a in actions:
            if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId") or a.get("x") is None:
                continue
            offense = a["teamId"]
            defense = next((t for t in team_ids if t != offense), None)
            if defense is None:
                continue
            made = a.get("shotResult") == "Made"
            is_3 = a["actionType"] == "3pt"
            rows.append({
                "game_id": game_id, "team_id": offense, "defense_team_id": defense, "person_id": a.get("personId"),
                "period": a["period"], "elapsed_s": _elapsed_s(a["period"], a["clock"]),
                "zone": classify_zone(float(a["x"]), float(a["y"]), is_3), "subtype_class": a.get("subType") or "Unknown",
                "assisted": int(_is_assisted(a, made)),
                "made": int(made), "points": 3 if is_3 else 2,
            })
    return pd.DataFrame(rows)


def add_shooter_zone_efg(df: pd.DataFrame) -> pd.DataFrame:
    """Season-long per-(person, zone) eFG (see module docstring for the
    known small in-sample leak), with a league zone-average fallback below
    MIN_SHOOTER_ZONE_FGA attempts -- via merges, not row-wise apply."""
    tmp = df.assign(fg3m=df["made"] * (df["points"] == 3).astype(int))
    per_pz = tmp.groupby(["person_id", "zone"]).agg(fga=("made", "size"), fgm=("made", "sum"), fg3m=("fg3m", "sum")).reset_index()
    per_pz["shooter_efg"] = (per_pz["fgm"] + 0.5 * per_pz["fg3m"]) / per_pz["fga"]
    league_zone = tmp.groupby("zone").agg(fgm=("made", "sum"), fg3m=("fg3m", "sum"), fga=("made", "size")).reset_index()
    league_zone["league_efg"] = (league_zone["fgm"] + 0.5 * league_zone["fg3m"]) / league_zone["fga"]

    out = df.merge(per_pz[["person_id", "zone", "fga", "shooter_efg"]], on=["person_id", "zone"], how="left")
    out = out.merge(league_zone[["zone", "league_efg"]], on="zone", how="left")
    below_floor = out["fga"].isna() | (out["fga"] < MIN_SHOOTER_ZONE_FGA)
    out["shooter_zone_efg"] = out["shooter_efg"].where(~below_floor, out["league_efg"])
    return out.drop(columns=["fga", "shooter_efg", "league_efg"])


def add_defense_zone_efg_allowed(df: pd.DataFrame, concession_src: Path = _CONCESSION_SRC) -> pd.DataFrame:
    concession = pd.read_parquet(concession_src)
    long_rows = []
    for z in ZONES:
        col = f"{z}_efg_allowed"
        if col in concession.columns:
            long_rows.append(concession[["defense_team_id", col]].rename(columns={col: "defense_zone_efg_allowed"}).assign(zone=z))
    long_df = pd.concat(long_rows, ignore_index=True)
    return df.merge(long_df, on=["defense_team_id", "zone"], how="left")


def add_spacing(df: pd.DataFrame, stints_src: Path = _STINTS_SRC, spacing_src: Path = _SPACING_SRC) -> pd.DataFrame:
    stints_df = pd.read_parquet(stints_src)
    spacing_df = pd.read_parquet(spacing_src)
    shots_for_join = df.rename(columns={}).copy()
    shots_for_join["n_on_court"] = 0
    attached = attach_lineup_to_shots(stints_df, shots_for_join)
    merged = attached.merge(spacing_df[["team_id", "lineup_key", "spacing_mean_dist"]], on=["team_id", "lineup_key"], how="left")
    fallback = float(spacing_df["spacing_mean_dist"].median())
    merged["spacing_mean_dist"] = merged["spacing_mean_dist"].fillna(fallback)
    return merged


def build_shot_frame(pbp_dir: Path = _PBP_DIR, limit: int | None = None) -> pd.DataFrame:
    df = load_raw_shots(pbp_dir, limit=limit)
    df = add_shooter_zone_efg(df)
    df = add_defense_zone_efg_allowed(df)
    df = add_spacing(df)
    keep = [
        "game_id", "team_id", "defense_team_id", "person_id", "zone", "subtype_class",
        "assisted", "made", "points", "shooter_zone_efg", "defense_zone_efg_allowed", "spacing_mean_dist",
    ]
    return df[keep]
