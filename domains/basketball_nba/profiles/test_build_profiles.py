"""Per-file test: real build against the on-disk 2025-26 corpus (fast subset --
single season) -- schema shape, floor enforcement (no sub-floor entity leaks
through), and negative-placeholder-id exclusion on the actual output.

Run: python -m pytest domains/basketball_nba/profiles/test_build_profiles.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.basketball_nba.profiles.build_profiles import _SCHEMA_COLS, build


@pytest.fixture(scope="module")
def frames(tmp_path_factory):
    # out_dir MUST be a tmp dir: build() writes its parquets unconditionally,
    # and the default out_dir is the PRODUCTION data/cache/profiles/ -- a
    # single-season test run silently clobbered the 3-season parquets once.
    return build(seasons=["2025_26"], out_dir=tmp_path_factory.mktemp("profiles"))


def test_schema_columns_present(frames):
    for label, df in frames.items():
        assert list(df.columns) == _SCHEMA_COLS, label


def test_no_negative_placeholder_player_ids(frames):
    player_df = frames["player"]
    numeric_ids = pd.to_numeric(player_df["entity_id"], errors="coerce")
    assert (numeric_ids >= 0).all()


def test_gravity_floor_enforced(frames):
    """Every gravity row must have n (min_on) >= the registry floor (300)."""
    gravity = frames["player"][frames["player"]["attribute"] == "gravity"]
    assert not gravity.empty
    assert (gravity["n"] >= 300.0).all()


def test_lineup_synergy_floor_enforced(frames):
    synergy = frames["lineup"][frames["lineup"]["attribute"] == "synergy_residual"]
    assert not synergy.empty
    assert (synergy["n"] >= 100.0).all()


def test_ingredients_are_valid_json_for_every_row(frames):
    for df in frames.values():
        for s in df["ingredients"]:
            json.loads(s)  # raises if malformed


def test_percentile_and_rating_2k_in_range(frames):
    for df in frames.values():
        if df.empty:
            continue
        assert df["percentile"].between(0.0, 100.0).all()
        assert df["rating_2k"].between(25.0, 99.0).all()


def test_status_is_one_of_the_three_declared_values(frames):
    valid = {"VALIDATED_MECHANISM", "VALIDATED_CLAIM", "DESCRIPTIVE"}
    for df in frames.values():
        assert set(df["status"].unique()) <= valid
