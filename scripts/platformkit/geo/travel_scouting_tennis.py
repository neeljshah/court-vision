# -*- coding: utf-8 -*-
"""scripts.platformkit.geo.travel_scouting_tennis -- ATP/WTA per-match
SCOUTING travel/altitude descriptors (NEVER a model feature).

domains/tennis/matches.parquet has no city/venue column -- only tourney_name
(e.g. "Australian Open", "Roland Garros", "Winston-Salem", many "Davis Cup
...: XXX vs YYY" tie labels). This module resolves tourney_name -> host city
via (a) a small static alias table for majors/Masters whose name is not the
literal city, then (b) a direct city_geo lookup for names that already ARE
the host city (e.g. "Adelaide", "Barcelona"). Davis Cup ties (host city not
derivable from the tie label) are an HONEST MISS -- never guessed.

Builds two descriptor columns per player-appearance-row (both p1 and p2 of
every match, chronologically ordered by date):
  - miles_flown_in: great-circle miles from the player's PREVIOUS match's
    resolved host city to THIS match's host city. Strictly-prior; a player's
    first appearance in the corpus -> NaN.
  - venue_altitude_m: this match's host-city altitude in meters.

SCOUTING ONLY -- no gate arm for tennis this wave (expected-duplicate REJECT
per program instruction; not worth the compute).

Output: data/domains/tennis/travel_scouting.parquet, one row per
(event_id, player, is_p1) appearance, with as_of/corpus_id/season provenance.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from scripts.platformkit.geo.city_geo import lookup
from scripts.platformkit.geo.travel_scouting_common import (
    altitude_m,
    coverage_report,
    prior_city_travel,
)

_REPO = Path(__file__).resolve().parents[3]
_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_OUT = _REPO / "data" / "domains" / "tennis" / "travel_scouting.parquet"
_CORPUS_ID = "tennis_travel_scouting_v1"

# tourney_name -> (city, country) for majors/Masters/events whose display
# name is NOT the literal host city (or whose literal city is spelled
# differently than the geo table / needs disambiguation). Chosen to close
# the largest-by-row misses first (see docs/research -- measured coverage).
_TOURNEY_ALIAS = {
    "australian open": ("Melbourne", "Australia"),
    "roland garros": ("Paris", "France"),
    "us open": ("Flushing Meadows", "United States"),
    "canada masters": ("Toronto", "Canada"),
    "queen's club": ("London", "England"),
    "s hertogenbosch": ("'s-Hertogenbosch", "Netherlands"),
    "mallorca": ("Palma", "Spain"),
    "st petersburg": ("St. Petersburg", "Russia"),
    "sardinia": ("Cagliari", "Italy"),
    "rio olympics": ("Rio de Janeiro", "Brazil"),
    "tokyo olympics": ("Tokyo", "Japan"),
    "paris olympics": ("Paris", "France"),
    "nur-sultan": ("Nur-Sultan", "Kazakhstan"),
    "astana": ("Nur-Sultan", "Kazakhstan"),
    "murray river open": ("Melbourne", "Australia"),      # 2021 AO-replacement event
    "great ocean road open": ("Melbourne", "Australia"),  # 2021 AO-replacement event
    "nextgen finals": ("Milan", "Italy"),
    "next gen finals": ("Milan", "Italy"),
    # ATP Cup / United Cup / Tour Finals / Laver Cup deliberately excluded:
    # host city varies materially across editions in this corpus (rotating
    # or multi-city format) -- an honest miss beats a guessed single city.
}

_STRIP_WORDS = re.compile(r"\b(Masters|Open|Cup|Finals|WTA|ATP|1000|500|250|Tour)\b",
                         re.IGNORECASE)
_TRAILING_NUM = re.compile(r"\s*\d+\s*$")
_DAVIS_CUP = re.compile(r"\bDavis Cup\b", re.IGNORECASE)


def resolve_tourney_city(tourney_name: str) -> Optional[dict]:
    """tourney_name -> city_geo row, or None on an honest miss. Davis Cup tie
    labels (host city not derivable from the name) are always a miss."""
    if not tourney_name or _DAVIS_CUP.search(tourney_name):
        return None
    key = tourney_name.strip().lower()
    if key in _TOURNEY_ALIAS:
        city, country = _TOURNEY_ALIAS[key]
        return lookup(city, country)
    row = lookup(tourney_name)
    if row is not None:
        return row
    cleaned = _TRAILING_NUM.sub("", _STRIP_WORDS.sub("", tourney_name)).strip()
    if cleaned and cleaned.lower() != key:
        row = lookup(cleaned)
        if row is not None:
            return row
    return None


def build_corpus(matches_path: Optional[Path] = None) -> pd.DataFrame:
    """Long-form player-appearance rows: one per player per match (p1 + p2),
    each carrying the match's resolved host city/country."""
    df = pd.read_parquet(matches_path or _MATCHES)
    df = df.dropna(subset=["p1_name", "p2_name", "date", "tourney_name"]).copy()
    resolved = df["tourney_name"].apply(resolve_tourney_city)
    df["venue_city"] = resolved.apply(lambda r: r["city"] if r else None)
    df["venue_country"] = resolved.apply(lambda r: r["country"] if r else None)

    p1_rows = df[["event_id", "date", "p1_name", "venue_city", "venue_country"]].rename(
        columns={"p1_name": "player"})
    p1_rows["is_p1"] = True
    p2_rows = df[["event_id", "date", "p2_name", "venue_city", "venue_country"]].rename(
        columns={"p2_name": "player"})
    p2_rows["is_p1"] = False

    long_df = pd.concat([p1_rows, p2_rows], ignore_index=True)
    long_df = long_df.dropna(subset=["player", "venue_city"])
    return long_df


def add_descriptors(long_df: pd.DataFrame) -> pd.DataFrame:
    out = long_df.copy()
    out["miles_flown_in"] = prior_city_travel(
        out, entity_col="player", date_col="date", city_col="venue_city",
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


def report(all_matches: pd.DataFrame, resolved_df: pd.DataFrame) -> dict:
    """Reports BOTH the raw tourney_name->city resolution coverage (against
    ALL match rows, before the player-appearance long-form explode) and the
    descriptor coverage on the long-form output, so a reader can see how
    much of the tourney-name miss (e.g. Davis Cup ties) drives the rest."""
    total_matches = len(all_matches)
    resolved_matches = int(all_matches["tourney_name"].apply(
        lambda n: resolve_tourney_city(n) is not None).sum())
    return {
        "sport": "tennis",
        "n_match_rows": int(total_matches),
        "tourney_city_resolution": {
            "label": "tourney_name_to_city",
            "total_rows": total_matches,
            "hit_rows": resolved_matches,
            "coverage": round(resolved_matches / total_matches, 4) if total_matches else 0.0,
        },
        "n_player_appearance_rows": int(len(resolved_df)),
        "miles_flown_in": coverage_report(resolved_df["miles_flown_in"], "miles_flown_in"),
        "venue_altitude_m": coverage_report(resolved_df["venue_altitude_m"], "venue_altitude_m"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build tennis travel/altitude SCOUTING descriptors.")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if not _MATCHES.exists():
        print(json.dumps({"sport": "tennis", "error": "matches.parquet not on disk"}))
        return 0
    all_matches = pd.read_parquet(_MATCHES)
    long_df = build_corpus()
    long_df = add_descriptors(long_df)
    r = report(all_matches, long_df)
    print(json.dumps(r, indent=2))
    if not a.no_write:
        print("wrote %s" % write(long_df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["resolve_tourney_city", "build_corpus", "add_descriptors", "write",
           "report", "main"]
