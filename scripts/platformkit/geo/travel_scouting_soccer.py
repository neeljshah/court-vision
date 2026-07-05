# -*- coding: utf-8 -*-
"""scripts.platformkit.geo.travel_scouting_soccer -- international soccer
per-match SCOUTING travel/altitude descriptors (NEVER a model feature).

Builds two descriptor columns per team-appearance-row (both home and away
appearances of every national team in domains/soccer_intl/results.parquet,
chronologically ordered by date):
  - miles_flown_in: great-circle miles from the team's PREVIOUS match city
    (home, away, or neutral-site) to THIS match's host city. Strictly-prior;
    first appearance in the corpus -> NaN.
  - venue_altitude_m: this match's host-city altitude in meters (the one
    non-trivial travel mechanism worth a gate arm -- high-altitude Andean
    venues like La Paz/Quito).

SCOUTING ONLY, descriptive/scouting layer. Optionally gates venue_altitude_m
(soccer_intl only) against a simple Elo-style base with the identical style
of leak-free walk-forward gate the NBA travel layer used, A-PRIORI EXPECTING
REJECT (soccer_intl pregame is documented efficient; see JOB_EVIDENCE_PACKET).

Output: data/domains/soccer_intl/travel_scouting.parquet, one row per
(row index, team, is_home) appearance, with as_of/corpus_id/season provenance.
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
_RESULTS = _REPO / "data" / "domains" / "soccer_intl" / "results.parquet"
_OUT = _REPO / "data" / "domains" / "soccer_intl" / "travel_scouting.parquet"
_CORPUS_ID = "soccer_intl_travel_scouting_v1"


def build_corpus(results_path: Optional[Path] = None) -> pd.DataFrame:
    """Long-form team-appearance rows: one per team per match (home + away),
    each carrying the MATCH's host city/country (works for neutral-site
    matches too, since 'city'/'country' in results.parquet are always the
    actual host, not the home team's home city)."""
    df = pd.read_parquet(results_path or _RESULTS)
    df = df.dropna(subset=["home_team", "away_team", "date", "city"]).copy()
    df = df.reset_index(drop=True)
    df["match_row"] = df.index

    home_rows = df[["match_row", "date", "home_team", "city", "country"]].rename(
        columns={"home_team": "team"})
    home_rows["is_home"] = True
    away_rows = df[["match_row", "date", "away_team", "city", "country"]].rename(
        columns={"away_team": "team"})
    away_rows["is_home"] = False

    long_df = pd.concat([home_rows, away_rows], ignore_index=True)
    long_df = long_df.rename(columns={"city": "venue_city", "country": "venue_country"})
    long_df = long_df.dropna(subset=["team", "venue_city"])
    return long_df


def add_descriptors(long_df: pd.DataFrame) -> pd.DataFrame:
    out = long_df.copy()
    out["miles_flown_in"] = prior_city_travel(
        out, entity_col="team", date_col="date", city_col="venue_city",
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
    df["season"] = pd.to_datetime(df["date"]).dt.year
    df.to_parquet(dest, index=False)
    return str(dest)


def report(df: pd.DataFrame) -> dict:
    return {
        "sport": "soccer_intl",
        "n_rows": int(len(df)),
        "n_teams": int(df["team"].nunique()),
        "miles_flown_in": coverage_report(df["miles_flown_in"], "miles_flown_in"),
        "venue_altitude_m": coverage_report(df["venue_altitude_m"], "venue_altitude_m"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build soccer_intl travel/altitude SCOUTING descriptors.")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if not _RESULTS.exists():
        print(json.dumps({"sport": "soccer_intl", "error": "results.parquet not on disk"}))
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
