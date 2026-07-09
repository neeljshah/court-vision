"""domains.soccer.profiles.source_builders -- flat, validator-recomputable
SNAPSHOT tables for the team attribute engine. Each function returns a plain
row-level DataFrame with masked/derived columns already materialized (the
validator's whitelist grammar only allows sum/mean/count/count_distinct over
a BARE column -- any "if pattern_group == X" masking has to happen here, once,
not in the claim formula). build_profiles.py both (a) aggregates these frames
directly with pandas for the presentation parquet and (b) writes them to
data/cache/intel_claims/ as the claims' declared source_files, so the
independent validator recomputes from the SAME materialized columns.

REUSES (never reimplements): prereg_possession_chains.build_possessions for
the possession table, claims_formation._load_match_lookup/_fmt_formation for
match metadata + formation codes, asof_xg_proxy.K_SOT/K_OFF/_xg/_num for the
shots-based expected-goals proxy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from domains.soccer.asof_xg_proxy import K_SOT, K_OFF, _num, _xg  # noqa: F401 (K_* re-exported for callers/tests)
from domains.soccer.claims_formation import _fmt_formation, _load_match_lookup

REPO_ROOT = Path(__file__).resolve().parents[3]
_SB_EVENTS_DIR = REPO_ROOT / "data" / "cache" / "statsbomb" / "events"
_MATCH_STATS_PATH = REPO_ROOT / "data" / "domains" / "soccer" / "match_stats.parquet"
_MATCHES_PATH = REPO_ROOT / "data" / "domains" / "soccer" / "matches.parquet"


def build_match_teams(match_lookup: dict) -> pd.DataFrame:
    """match_id -> home_id/away_id, from the statsbomb match metadata dicts."""
    rows = []
    for match_id, meta in match_lookup.items():
        home, away = meta.get("home_team") or {}, meta.get("away_team") or {}
        hid, aid = home.get("home_team_id"), away.get("away_team_id")
        if hid is None or aid is None:
            continue
        rows.append({"match_id": match_id, "home_id": hid, "away_id": aid})
    return pd.DataFrame(rows)


def build_possession_snapshot(possessions: pd.DataFrame) -> pd.DataFrame:
    """One row per statsbomb possession. counter_xg/regular_xg are NaN outside
    their pattern group (mean() skips them); set_piece_xg is 0.0 outside its
    group (sum() then equals the masked-subset sum)."""
    if possessions.empty:
        return possessions
    df = pd.DataFrame({
        "entity_id": possessions["team_id"].astype(str),
        "entity_name": possessions["team_name"],
        "match_id": possessions["match_id"],
        "xg": possessions["xg"].astype(float),
        "is_counter": possessions["is_counter"].astype(float),
    })
    is_counter = possessions["pattern_group"] == "counter"
    is_regular = possessions["pattern_group"] == "regular"
    is_set_piece = possessions["pattern_group"] == "set_piece_derived"
    df["counter_xg"] = possessions["xg"].where(is_counter)
    df["regular_xg"] = possessions["xg"].where(is_regular)
    df["set_piece_xg"] = possessions["xg"].where(is_set_piece, 0.0)
    return df


def build_defensive_snapshot(possessions: pd.DataFrame, match_teams: pd.DataFrame) -> pd.DataFrame:
    """One row per (match, attacking team) regular-play possession bundle,
    reassigned to the CONCEDING (opponent) team as entity_id -- xg/poss here
    are what that opponent conceded in that match."""
    reg = possessions[possessions["pattern_group"] == "regular"]
    if reg.empty or match_teams.empty:
        return pd.DataFrame(columns=["entity_id", "match_id", "xg", "poss"])
    per_match_team = reg.groupby(["match_id", "team_id"]).agg(
        xg=("xg", "sum"), poss=("xg", "count")
    ).reset_index()
    merged = per_match_team.merge(match_teams, on="match_id", how="inner")
    opponent_id = merged["home_id"].where(merged["team_id"] == merged["away_id"], merged["away_id"])
    return pd.DataFrame({
        "entity_id": opponent_id.astype(str),
        "match_id": merged["match_id"],
        "xg": merged["xg"].astype(float),
        "poss": merged["poss"].astype(float),
    })


def build_formation_snapshot(match_lookup: dict, events_dir: Path = _SB_EVENTS_DIR) -> pd.DataFrame:
    """One row per (match, team) with a detected Starting XI formation.
    is_primary is materialized here (validator grammar has no mode())."""
    rows = []
    for fn in os.listdir(events_dir):
        match_id = int(fn.replace(".json", ""))
        meta = match_lookup.get(match_id)
        if meta is None:
            continue
        home, away = meta.get("home_team") or {}, meta.get("away_team") or {}
        home_id, away_id = home.get("home_team_id"), away.get("away_team_id")
        if home_id is None or away_id is None:
            continue
        with open(events_dir / fn, encoding="utf-8") as f:
            events = json.load(f)
        for e in events:
            if e.get("type", {}).get("name") != "Starting XI":
                continue
            team_id = e.get("team", {}).get("id")
            formation = (e.get("tactics") or {}).get("formation")
            if formation is None or team_id not in (home_id, away_id):
                continue
            name = home.get("home_team_name") if team_id == home_id else away.get("away_team_name")
            rows.append({
                "entity_id": str(team_id), "entity_name": name,
                "match_id": match_id, "formation": _fmt_formation(formation),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    primary = df.groupby("entity_id")["formation"].agg(lambda s: s.value_counts().idxmax())
    df["is_primary"] = (df["formation"] == df["entity_id"].map(primary)).astype(float)
    return df


def build_season_snapshots(
    match_stats_path: Path = _MATCH_STATS_PATH, matches_path: Path = _MATCHES_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(finishing_source, home_strength_source) from the footballdata corpus.
    proxy_xg reuses asof_xg_proxy's realized shots-based formula verbatim."""
    mstats = pd.read_parquet(match_stats_path)
    matches = pd.read_parquet(matches_path)
    merged = matches.merge(
        mstats[["event_id", "home_shots", "home_sot", "away_shots", "away_sot"]],
        on="event_id", how="inner",
    )
    home_proxy = _xg(_num(merged["home_shots"]), _num(merged["home_sot"]))
    away_proxy = _xg(_num(merged["away_shots"]), _num(merged["away_sot"]))
    finishing = pd.concat([
        pd.DataFrame({
            "entity_id": merged["home_team"], "season": merged["season"].astype(int),
            "match_id": merged["event_id"], "diff": merged["fthg"].to_numpy(dtype=float) - home_proxy,
        }),
        pd.DataFrame({
            "entity_id": merged["away_team"], "season": merged["season"].astype(int),
            "match_id": merged["event_id"], "diff": merged["ftag"].to_numpy(dtype=float) - away_proxy,
        }),
    ], ignore_index=True)
    finishing["entity_name"] = finishing["entity_id"]

    pts = matches["ftr"].map({"H": 3.0, "D": 1.0, "A": 0.0})
    home_strength = pd.DataFrame({
        "entity_id": matches["home_team"], "entity_name": matches["home_team"],
        "season": matches["season"].astype(int), "match_id": matches["event_id"], "pts": pts,
    })
    return finishing, home_strength


def load_statsbomb_context() -> tuple[dict, pd.DataFrame]:
    """(match_lookup, match_teams) shared by the formation/defensive builders."""
    match_lookup = _load_match_lookup()
    return match_lookup, build_match_teams(match_lookup)
