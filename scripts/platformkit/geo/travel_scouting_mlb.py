# -*- coding: utf-8 -*-
"""scripts.platformkit.geo.travel_scouting_mlb -- MLB per-game SCOUTING
travel/altitude descriptors (NEVER a model feature).

Builds two descriptor columns per team-appearance-row (both home and away
appearances of every team, chronologically ordered by date):
  - miles_flown_in: great-circle miles from the team's PREVIOUS appearance's
    city (whether that appearance was home or away) to THIS game's city.
    Strictly-prior (only looks backward in time); first appearance -> NaN.
  - venue_altitude_m: this game's host-park city altitude in meters.

SCOUTING ONLY. The NBA travel gate (nba_travel_gate_run.py) already ran an
identical-style leak-free walk-forward gate on schedule-derived travel miles
vs an Elo win-prob base and the honest, pre-registered result was REJECT
(Elo + schedule rest/HFA already subsume travel). MLB pregame markets are
independently documented as efficient (docs/JOB_EVIDENCE_PACKET.md). Per the
program instruction for this wave, MLB gets NO gate arm here -- descriptors
only, reported with honest coverage.

Output: data/domains/mlb/travel_scouting.parquet, one row per (event_id,
team, is_home) team-appearance, with as_of/corpus_id/season provenance.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from scripts.platformkit.geo.travel_scouting_common import (
    altitude_m,
    coverage_report,
    prior_city_travel,
)

_REPO = Path(__file__).resolve().parents[3]
_GAMES = _REPO / "data" / "domains" / "mlb" / "games.parquet"
_OUT = _REPO / "data" / "domains" / "mlb" / "travel_scouting.parquet"
_CORPUS_ID = "mlb_travel_scouting_v1"

# Some team codes are alias/rename duplicates of one franchise within this
# corpus (BOS/BRS, CUB/CHC, SFO/SFG all mean the same team; LOS->LAD is a
# mid-corpus code rename, not two teams). Normalize to ONE canonical code
# BEFORE building chronology so the "previous appearance" walk is per
# FRANCHISE, not broken at the alias-switch boundary.
_CANONICAL_CODE = {
    "BRS": "BOS", "CHC": "CUB", "SFG": "SFO", "LOS": "LAD",
}


def _canonical(code: str) -> str:
    return _CANONICAL_CODE.get(code, code)


# team code -> (city, country). Keyed by CANONICAL code (post-normalization).
_TEAM_CITY = {
    "ARI": ("Phoenix", "United States"), "ATL": ("Atlanta", "United States"),
    "BAL": ("Baltimore", "United States"), "BOS": ("Boston", "United States"),
    "CUB": ("Chicago", "United States"),
    "CIN": ("Cincinnati", "United States"), "CLE": ("Cleveland", "United States"),
    "COL": ("Denver", "United States"),
    "CWS": ("Chicago", "United States"), "DET": ("Detroit", "United States"),
    "HOU": ("Houston", "United States"), "KAN": ("Kansas City", "United States"),
    "LAA": ("Anaheim", "United States"),
    "LAD": ("Los Angeles", "United States"),
    "MIA": ("Miami", "United States"), "MIL": ("Milwaukee", "United States"),
    "MIN": ("Minneapolis", "United States"), "NYM": ("New York", "United States"),
    "NYY": ("New York", "United States"), "OAK": ("Oakland", "United States"),
    "PHI": ("Philadelphia", "United States"), "PIT": ("Pittsburgh", "United States"),
    "SDG": ("San Diego", "United States"), "SEA": ("Seattle", "United States"),
    "SFO": ("San Francisco", "United States"),
    "STL": ("St. Louis", "United States"), "TAM": ("St. Petersburg", "United States"),
    "TEX": ("Arlington", "United States"), "TOR": ("Toronto", "Canada"),
    "WAS": ("Washington", "United States"),
}


def _team_city(code: str) -> str:
    row = _TEAM_CITY.get(_canonical(code))
    return row[0] if row else None


def _team_country(code: str) -> str:
    row = _TEAM_CITY.get(_canonical(code))
    return row[1] if row else None


def build_corpus(games_path: Optional[Path] = None) -> pd.DataFrame:
    """Long-form team-appearance rows (one per team per game, both home+away),
    each carrying the GAME's host city (= home team's city -- MLB has no
    neutral-site rows in this corpus) so away teams show the venue they flew
    INTO, not their own home city."""
    df = pd.read_parquet(games_path or _GAMES)
    df = df.dropna(subset=["home_team", "away_team", "date"]).copy()
    df["venue_city"] = df["home_team"].map(_team_city)
    df["venue_country"] = df["home_team"].map(_team_country)

    home_rows = df[["event_id", "date", "season", "home_team", "venue_city", "venue_country"]].rename(
        columns={"home_team": "team"})
    home_rows["is_home"] = True
    away_rows = df[["event_id", "date", "season", "away_team", "venue_city", "venue_country"]].rename(
        columns={"away_team": "team"})
    away_rows["is_home"] = False

    long_df = pd.concat([home_rows, away_rows], ignore_index=True)
    long_df = long_df.dropna(subset=["team", "venue_city"])
    # per-FRANCHISE chronology key (collapses BRS->BOS, CHC->CUB, SFG->SFO,
    # LOS->LAD alias/rename duplicates); "team" itself stays the raw code
    # for reporting/display.
    long_df["franchise"] = long_df["team"].map(_canonical)
    return long_df


def add_descriptors(long_df: pd.DataFrame) -> pd.DataFrame:
    out = long_df.copy()
    out["miles_flown_in"] = prior_city_travel(
        out, entity_col="franchise", date_col="date", city_col="venue_city",
        country_col="venue_country")
    out["venue_altitude_m"] = out.apply(
        lambda r: altitude_m(r["venue_city"], r["venue_country"]), axis=1)
    return out


def write(df: pd.DataFrame, out: Optional[Path] = None) -> str:
    dest = Path(out) if out is not None else _OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["as_of"] = datetime.now(timezone.utc).isoformat()
    df["corpus_id"] = _CORPUS_ID
    df.to_parquet(dest, index=False)
    return str(dest)


def report(df: pd.DataFrame) -> dict:
    return {
        "sport": "mlb",
        "n_rows": int(len(df)),
        "n_teams": int(df["team"].nunique()),
        "miles_flown_in": coverage_report(df["miles_flown_in"], "miles_flown_in"),
        "venue_altitude_m": coverage_report(df["venue_altitude_m"], "venue_altitude_m"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build MLB travel/altitude SCOUTING descriptors.")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if not _GAMES.exists():
        print(json.dumps({"sport": "mlb", "error": "games.parquet not on disk"}))
        return 0
    long_df = build_corpus()
    long_df = add_descriptors(long_df)
    r = report(long_df)
    print(json.dumps(r, indent=2))
    if not a.no_write:
        print("wrote %s" % write(long_df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_corpus", "add_descriptors", "write", "report", "main"]
