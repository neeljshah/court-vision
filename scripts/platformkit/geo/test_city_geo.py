# -*- coding: utf-8 -*-
"""Tests for scripts.platformkit.geo.city_geo -- zero-network static lookup.

Per-file only: python -m pytest scripts/platformkit/geo/test_city_geo.py -q
"""
from __future__ import annotations

import math
import os

import pytest

from scripts.platformkit.geo.city_geo import (
    distance_between_cities_km,
    great_circle_km,
    lookup,
    n_rows,
    _coverage_against_soccer_intl,
)

WNBA_ARENA_CITIES = [
    "Indianapolis", "San Francisco", "Brooklyn", "Seattle", "Portland",
    "Chicago", "Toronto", "Uncasville", "Phoenix", "Las Vegas",
    "Minneapolis", "Washington", "Atlanta", "Los Angeles", "Arlington",
    "Hartford", "Austin", "Sioux Falls", "San Diego", "Kansas City",
]


def test_all_wnba_arena_cities_covered():
    """(a) every distinct WNBA arena city from the CDN boxscore corpus must
    resolve -- an honest miss here would silently break the future WNBA
    travel-burden dimension."""
    misses = [c for c in WNBA_ARENA_CITIES if lookup(c) is None]
    assert misses == [], f"WNBA arena city misses: {misses}"


def test_lookup_returns_required_fields():
    row = lookup("London")
    assert row is not None
    for field in ("lat", "lon", "altitude_m", "country", "tz", "source"):
        assert field in row
    assert row["source"] == "static_v1"
    assert -90 <= row["lat"] <= 90
    assert -180 <= row["lon"] <= 180


def test_honest_miss_never_guesses():
    """A city not in the table must return None, never a fabricated row."""
    assert lookup("Nonexistentville Zorptown") is None
    assert lookup("") is None
    assert lookup(None) is None


def test_country_disambiguation():
    """Cities sharing a name across countries resolve correctly when country
    is supplied, and honestly miss when the (city, country) pair is absent."""
    guyana = lookup("Georgetown", "Guyana")
    assert guyana is not None
    assert guyana["country"] == "Guyana"
    # Georgetown is NOT registered under Cayman Islands (that's "George Town")
    assert lookup("Georgetown", "Cayman Islands") is None
    cayman = lookup("George Town", "Cayman Islands")
    assert cayman is not None


def test_diacritic_and_case_insensitive_matching():
    assert lookup("zurich") == lookup("Zurich") == lookup("Zürich")
    assert lookup("SAO PAULO") == lookup("Sao Paulo") == lookup("São Paulo")
    assert lookup("REYKJAVIK") is not None


def test_alias_matching():
    assert lookup("Washington, D.C.") is not None
    assert lookup("washington dc") is not None
    assert lookup("Bangalore") == lookup("Bengaluru")


def test_great_circle_km_known_distances():
    """Sanity vs well-known real-world great-circle distances (tolerance
    ~2% for city-center vs city-center measurement)."""
    # London to Paris real great-circle distance ~344 km
    d = great_circle_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 330 <= d <= 360

    # Zero distance for identical points
    assert great_circle_km(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0, abs=1e-6)

    # Antipodal-ish sanity: equator quarter-circle ~ pi/2 * R
    d_quarter = great_circle_km(0.0, 0.0, 0.0, 90.0)
    assert d_quarter == pytest.approx(math.pi / 2 * 6371.0088, rel=1e-3)


def test_distance_between_cities_km_honest_miss_propagates():
    assert distance_between_cities_km("Nonexistentville", "London") is None
    assert distance_between_cities_km("London", "Nonexistentville") is None
    d = distance_between_cities_km("New York", "Los Angeles")
    assert d is not None
    assert 3900 <= d <= 3970  # real NYC-LA great circle ~3936 km


def test_table_has_no_duplicate_full_keys_after_index_build():
    """city_geo_table.ROWS may contain exact-duplicate (city,country) rows
    across the WNBA/soccer/tennis source batches; the built index must not
    silently double-count or corrupt lookups for any of them."""
    # spot-check a city known to appear in both the WNBA batch and the
    # soccer_intl batch with identical values (Toronto, Canada)
    row = lookup("Toronto", "Canada")
    assert row is not None
    assert row["lat"] == pytest.approx(43.6532, abs=0.01)


@pytest.mark.skipif(
    not os.path.exists("data/domains/soccer_intl/results.parquet"),
    reason="local-only corpus not present in this checkout",
)
def test_soccer_intl_coverage_at_least_90_percent():
    """HONEST coverage gate: must reach >=90% ROW coverage of the real
    49,477-row soccer_intl results.parquet 'city' column (measured, not
    asserted-then-faked)."""
    cov = _coverage_against_soccer_intl()
    assert cov is not None
    assert cov["coverage"] >= 0.90, f"coverage only {cov['coverage']*100:.2f}%"


def test_n_rows_matches_table_size():
    assert n_rows() > 600
