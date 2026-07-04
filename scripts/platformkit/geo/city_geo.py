# -*- coding: utf-8 -*-
"""scripts.platformkit.geo.city_geo -- zero-network static city geo lookup.

lookup(city, country=None) -> dict with {lat, lon, altitude_m, country, tz,
source} or None on an HONEST MISS (never a silent guess).

great_circle_km(lat1, lon1, lat2, lon2) -> haversine distance in km, stdlib
math only.

No network calls anywhere in this module. All static facts are tagged
source="static_v1" (see city_geo_table.ROWS docstring for provenance/coverage).
"""
from __future__ import annotations

import math
import unicodedata
from typing import Optional

from scripts.platformkit.geo.city_geo_table import ROWS

EARTH_RADIUS_KM = 6371.0088  # mean Earth radius (IUGG)
SOURCE_TAG = "static_v1"


def _fold(s: str) -> str:
    """Lowercase + strip diacritics + collapse punctuation/whitespace for
    normalized matching (case/diacritic/alias-insensitive)."""
    if s is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = stripped.lower().strip()
    for ch in (",", ".", "'", "-"):
        stripped = stripped.replace(ch, " ")
    return " ".join(stripped.split())


def _build_index() -> dict:
    """city-only index: folded_city -> list of row dicts (first-wins on an
    exact duplicate (city, country) key -- source rows can legitimately repeat
    across corpora with identical values; later exact dupes are skipped)."""
    index: dict[str, list[dict]] = {}
    seen_full_keys: set[tuple[str, str]] = set()
    for city, country, lat, lon, alt_m, tz, aliases in ROWS:
        full_key = (_fold(city), _fold(country))
        if full_key in seen_full_keys:
            continue
        seen_full_keys.add(full_key)
        row = {
            "city": city,
            "country": country,
            "lat": lat,
            "lon": lon,
            "altitude_m": alt_m,
            "tz": tz,
            "source": SOURCE_TAG,
        }
        keys = {_fold(city)} | {_fold(a) for a in aliases}
        for k in keys:
            index.setdefault(k, []).append(row)
    return index


_INDEX = _build_index()


def lookup(city: str, country: Optional[str] = None) -> Optional[dict]:
    """Normalized city (+ optional country) -> geo dict, or None on a miss.

    Matching is case/diacritic/alias-insensitive. When multiple rows share a
    folded city key (e.g. "Georgetown" in Guyana vs Cayman Islands) and no
    country is given, the highest-frequency (first-registered) row wins; pass
    country to disambiguate. Never guesses -- returns None on a true miss.
    """
    if not city:
        return None
    candidates = _INDEX.get(_fold(city))
    if not candidates:
        return None
    if country:
        folded_country = _fold(country)
        for row in candidates:
            if _fold(row["country"]) == folded_country:
                return dict(row)
        return None  # named country not found under this city -> honest miss
    return dict(candidates[0])


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine great-circle distance in km. stdlib math only."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def distance_between_cities_km(
    city_a: str, city_b: str, country_a: Optional[str] = None, country_b: Optional[str] = None
) -> Optional[float]:
    """Convenience wrapper: lookup both cities, return great-circle km, or
    None if either city is a miss."""
    row_a = lookup(city_a, country_a)
    row_b = lookup(city_b, country_b)
    if row_a is None or row_b is None:
        return None
    return great_circle_km(row_a["lat"], row_a["lon"], row_b["lat"], row_b["lon"])


def n_distinct_cities() -> int:
    """Distinct folded-city keys in the index (informational)."""
    return len(_INDEX)


def n_rows() -> int:
    """Total data rows loaded from city_geo_table.ROWS."""
    return len(ROWS)


def _coverage_against_soccer_intl() -> Optional[dict]:
    """Compute row-coverage of this table against the LOCAL
    domains/soccer_intl/results.parquet 'city' column, if present.
    Returns None if the parquet is not on disk (no network fetch -- this is
    a local, optional diagnostic only). Coverage = fraction of ROWS (not
    distinct cities) whose city resolves via lookup()."""
    import os

    path = "data/domains/soccer_intl/results.parquet"
    if not os.path.exists(path):
        return None
    try:
        import pandas as pd
    except ImportError:
        return None
    df = pd.read_parquet(path)
    total = len(df)
    hit = df["city"].apply(lambda c: lookup(c) is not None).sum()
    return {"total_rows": int(total), "hit_rows": int(hit), "coverage": hit / total if total else 0.0}


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="city_geo static lookup CLI")
    parser.add_argument("--lookup", help="city name to look up")
    parser.add_argument("--country", help="optional country to disambiguate", default=None)
    parser.add_argument("--coverage", action="store_true", help="print soccer_intl coverage stats")
    parser.add_argument("--stats", action="store_true", help="print table size stats")
    args = parser.parse_args()

    if args.lookup:
        result = lookup(args.lookup, args.country)
        print(result if result is not None else f"MISS: {args.lookup!r} (country={args.country!r})")
    if args.stats:
        print(f"rows={n_rows()} distinct_city_keys={n_distinct_cities()}")
    if args.coverage:
        cov = _coverage_against_soccer_intl()
        if cov is None:
            print("coverage: data/domains/soccer_intl/results.parquet not found locally")
        else:
            print(
                f"soccer_intl coverage: {cov['hit_rows']}/{cov['total_rows']} rows "
                f"= {cov['coverage']*100:.2f}%"
            )


if __name__ == "__main__":
    _cli()
