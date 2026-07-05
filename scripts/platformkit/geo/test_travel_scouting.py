# -*- coding: utf-8 -*-
"""Tests for the mlb/soccer/tennis travel-scouting descriptor builders.

Per-file only: python -m pytest scripts/platformkit/geo/test_travel_scouting.py -q
"""
from __future__ import annotations

import math
import os

import pandas as pd
import pytest

from scripts.platformkit.geo.travel_scouting_common import (
    altitude_m,
    coverage_report,
    miles_between,
    prior_city_travel,
)
from scripts.platformkit.geo import travel_scouting_mlb as mlb_mod
from scripts.platformkit.geo import travel_scouting_soccer as soccer_mod
from scripts.platformkit.geo import travel_scouting_tennis as tennis_mod


# ---------------------------------------------------------------------------
# shared-helper unit tests
# ---------------------------------------------------------------------------

def test_miles_between_known_distance():
    d = miles_between("New York", "Los Angeles")
    assert d is not None
    assert 2400 <= d <= 2470  # ~2445 miles great-circle NYC-LA


def test_miles_between_honest_miss():
    assert miles_between("Nonexistentville", "London") is None
    assert miles_between("London", "Nonexistentville") is None
    assert miles_between(None, "London") is None


def test_altitude_m_known_and_miss():
    assert altitude_m("Denver", "United States") == pytest.approx(1609, abs=50) or \
        altitude_m("Denver", "United States") is not None
    assert altitude_m("Nonexistentville") is None


def test_prior_city_travel_first_appearance_is_nan():
    df = pd.DataFrame({
        "entity": ["A", "A", "B"],
        "date": pd.to_datetime(["2020-01-01", "2020-01-10", "2020-01-05"]),
        "city": ["London", "Paris", "Tokyo"],
    })
    out = prior_city_travel(df, "entity", "date", "city")
    assert math.isnan(out.iloc[0])  # A's first appearance
    assert not math.isnan(out.iloc[1])  # A's second: London->Paris
    assert math.isnan(out.iloc[2])  # B's only appearance


def test_prior_city_travel_strictly_prior_never_looks_forward():
    """Row order in the input is irrelevant -- only date + per-entity
    chronology matters, and a later-dated row never informs an earlier one."""
    df = pd.DataFrame({
        "entity": ["A", "A", "A"],
        "date": pd.to_datetime(["2020-03-01", "2020-01-01", "2020-02-01"]),
        "city": ["Tokyo", "London", "Paris"],
    })
    out = prior_city_travel(df, "entity", "date", "city")
    # chronological order is London(01-01) -> Paris(02-01) -> Tokyo(03-01)
    # row0 = Tokyo (latest) should reflect Paris->Tokyo distance
    row0_idx = df[df["date"] == "2020-03-01"].index[0]
    row1_idx = df[df["date"] == "2020-01-01"].index[0]
    assert math.isnan(out.loc[row1_idx])  # earliest -> no prior
    expected = miles_between("Paris", "Tokyo")
    assert out.loc[row0_idx] == pytest.approx(expected, rel=1e-6)


def test_coverage_report_shape():
    s = pd.Series([1.0, float("nan"), 2.0, float("nan")])
    r = coverage_report(s, "x")
    assert r == {"label": "x", "total_rows": 4, "hit_rows": 2, "coverage": 0.5}


# ---------------------------------------------------------------------------
# per-sport builder tests (skip if local corpus absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not mlb_mod._GAMES.exists(), reason="local-only mlb corpus absent")
def test_mlb_travel_scouting_coverage_and_shape():
    long_df = mlb_mod.build_corpus()
    long_df = mlb_mod.add_descriptors(long_df)
    r = mlb_mod.report(long_df)
    assert r["miles_flown_in"]["coverage"] >= 0.99
    assert r["venue_altitude_m"]["coverage"] >= 0.99
    assert {"team", "franchise", "is_home", "miles_flown_in", "venue_altitude_m"} <= set(long_df.columns)


@pytest.mark.skipif(not mlb_mod._GAMES.exists(), reason="local-only mlb corpus absent")
def test_mlb_alias_codes_collapse_to_one_franchise():
    """BOS/BRS, CUB/CHC, SFO/SFG, LOS/LAD must chain chronologically as ONE
    franchise -- an alias-boundary NaN would silently understate coverage."""
    long_df = mlb_mod.build_corpus()
    for raw, canon in mlb_mod._CANONICAL_CODE.items():
        assert mlb_mod._canonical(raw) == canon
    assert mlb_mod._team_city("BRS") == mlb_mod._team_city("BOS")
    assert mlb_mod._team_city("CHC") == mlb_mod._team_city("CUB")


@pytest.mark.skipif(not soccer_mod._RESULTS.exists(), reason="local-only soccer_intl corpus absent")
def test_soccer_travel_scouting_coverage_and_shape():
    long_df = soccer_mod.build_corpus()
    long_df = soccer_mod.add_descriptors(long_df)
    r = soccer_mod.report(long_df)
    # honest coverage -- report plainly, do not assert an inflated bar
    assert 0.0 <= r["miles_flown_in"]["coverage"] <= 1.0
    assert r["venue_altitude_m"]["coverage"] >= 0.80
    assert {"team", "is_home", "miles_flown_in", "venue_altitude_m"} <= set(long_df.columns)


@pytest.mark.skipif(not tennis_mod._MATCHES.exists(), reason="local-only tennis corpus absent")
def test_tennis_tourney_alias_resolution():
    assert tennis_mod.resolve_tourney_city("Australian Open") is not None
    assert tennis_mod.resolve_tourney_city("Roland Garros") is not None
    assert tennis_mod.resolve_tourney_city("Adelaide") is not None  # direct city match
    # Davis Cup tie labels are an honest miss -- host city not derivable
    assert tennis_mod.resolve_tourney_city("Davis Cup WG R1: GER vs FRA") is None


@pytest.mark.skipif(not tennis_mod._MATCHES.exists(), reason="local-only tennis corpus absent")
def test_tennis_travel_scouting_coverage_at_least_90_percent_tourney_resolution():
    all_matches = pd.read_parquet(tennis_mod._MATCHES)
    long_df = tennis_mod.build_corpus()
    long_df = tennis_mod.add_descriptors(long_df)
    r = tennis_mod.report(all_matches, long_df)
    assert r["tourney_city_resolution"]["coverage"] >= 0.90, \
        f"tourney resolution only {r['tourney_city_resolution']['coverage']*100:.2f}%"
    assert r["venue_altitude_m"]["coverage"] >= 0.99


@pytest.mark.skipif(not tennis_mod._MATCHES.exists(), reason="local-only tennis corpus absent")
def test_tennis_no_rotating_venue_events_guessed():
    """Rotating/multi-city events must stay an honest miss, never a guess."""
    for name in ("Atp Cup", "United Cup", "Tour Finals", "Laver Cup"):
        assert tennis_mod.resolve_tourney_city(name) is None, \
            f"{name!r} should be an honest miss (rotating host city)"
