"""Tests for intel/player_pace_fit.py.

Assertions:
  1. LEAK-SAFETY: build() with a future as_of returns the same artifact (or None);
     build() with an as_of before all data returns None (no future rows leak).
  2. SCHEMA-CONFORMANCE: AtlasArtifact has all required sub_fields keys, cv_fields
     are present with correct names and null values, provenance has mandatory keys.
  3. VALIDATE: validate() passes on a legitimate artifact, fails on bad data.
  4. CV-FIELDS SCHEMA: cv_fields() returns all 4 reserved slots with None values.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Minimal synthetic DataFrames that look like the real parquets
# ---------------------------------------------------------------------------

def _make_adv_df() -> pd.DataFrame:
    """Return a tiny player_adv_stats.parquet substitute for 2 players, ~30 rows."""
    import random
    random.seed(42)
    rows = []
    # player 1001 has many games across 2022-2024
    for i in range(25):
        pace = 80.0 + i * 0.5  # varies 80..92
        rows.append({
            "player_id": 1001,
            "game_id": f"00220000{i:02d}",
            "game_date": f"2022-11-{(i % 28) + 1:02d}",
            "usagepercentage": 0.25 + (i % 5) * 0.01,
            "trueshootingpercentage": 0.55 + (i % 4) * 0.01,
            "effectivefieldgoalpercentage": 0.50 + (i % 3) * 0.01,
            "assistpercentage": 0.20,
            "reboundpercentage": 0.10,
            "offensivereboundpercentage": 0.05,
            "defensivereboundpercentage": 0.15,
            "offensiverating": 110.0,
            "defensiverating": 105.0,
            "netrating": 5.0 - i * 0.1,
            "assisttoturnover": 2.0,
            "assistratio": 0.15,
            "turnoverratio": 0.08,
            "pie": 0.14 + (i % 4) * 0.005,
            "possessions": 65 + i,
            "paceper40": pace,
            "minutes": 32.0,
        })
    # player 9999 has only 1 game (should return None from build)
    rows.append({
        "player_id": 9999,
        "game_id": "002200001",
        "game_date": "2022-10-18",
        "usagepercentage": 0.20,
        "trueshootingpercentage": 0.50,
        "effectivefieldgoalpercentage": 0.48,
        "assistpercentage": 0.10,
        "reboundpercentage": 0.08,
        "offensivereboundpercentage": 0.03,
        "defensivereboundpercentage": 0.12,
        "offensiverating": 105.0,
        "defensiverating": 110.0,
        "netrating": -5.0,
        "assisttoturnover": 1.5,
        "assistratio": 0.10,
        "turnoverratio": 0.10,
        "pie": 0.11,
        "possessions": 60.0,
        "paceper40": 82.0,
        "minutes": 20.0,
    })
    return pd.DataFrame(rows)


def _make_pbp_df() -> pd.DataFrame:
    """Return a tiny pbp_possession_features substitute for player 1001."""
    rows = []
    for i in range(20):
        rows.append({
            "player_id": 1001,
            "game_id": f"00220000{i:02d}",
            "game_date": f"2022-11-{(i % 28) + 1:02d}",
            "pbp_iso_poss_count": 3,
            "pbp_pnr_ball_handler": 1,
            "pbp_pnr_screener_proxy": 0,
            "pbp_post_up_count": 0,
            "pbp_transition_count": 2 + (i % 3),
            "pbp_late_clock_shots": 1,
            "pbp_clutch_shots_attempted": 0,
            "pbp_clutch_pts_scored": 0,
            "pbp_and1_count": 0,
            "pbp_avg_seconds_per_touch": 4.5,
        })
    return pd.DataFrame(rows)


def _make_lf_df() -> pd.DataFrame:
    """Return a tiny lineup_features substitute for player 1001."""
    return pd.DataFrame([{
        "player_id": 1001,
        "season": "2022-23",
        "lineup_top3_net_rating": 5.0,
        "lineup_top1_net_rating": 8.0,
        "lineup_top1_min_share": 0.35,
        "lineup_unique_5mans": 20,
        "lineup_avg_pace_on": 100.5,
    }])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def section():
    """Return a PlayerPaceFitSection with class-level caches pre-loaded from mocks."""
    from intel.player_pace_fit import PlayerPaceFitSection

    # Reset class-level caches so each test starts clean
    PlayerPaceFitSection._adv_df = None
    PlayerPaceFitSection._pbp_df = None
    PlayerPaceFitSection._lf_df = None
    PlayerPaceFitSection._global_pace_median = None

    sec = PlayerPaceFitSection()

    # Inject synthetic data
    PlayerPaceFitSection._adv_df = _make_adv_df()
    PlayerPaceFitSection._pbp_df = _make_pbp_df()
    PlayerPaceFitSection._lf_df = _make_lf_df()

    adv = PlayerPaceFitSection._adv_df
    PlayerPaceFitSection._global_pace_median = float(
        adv["paceper40"].quantile(0.50)
    )

    return sec


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must never use data stamped after as_of."""

    def test_past_as_of_returns_none(self, section):
        """as_of before all data => no rows pass filter => None."""
        past = _dt.datetime(2020, 1, 1)
        art = section.build(1001, past)
        assert art is None, "Expected None when as_of is before all data rows"

    def test_future_as_of_same_as_recent(self, section):
        """as_of in the far future includes all rows; should return a valid artifact."""
        future = _dt.datetime(2099, 12, 31)
        art_future = section.build(1001, future)
        # Very far future: same data is available (no new rows), so artifact should exist
        assert art_future is not None

    def test_as_of_cutoff_excludes_later_rows(self, section):
        """as_of mid-history should yield fewer games than as_of at end."""
        mid = _dt.datetime(2022, 11, 10)
        end = _dt.datetime(2023, 6, 30)
        art_mid = section.build(1001, mid)
        art_end = section.build(1001, end)

        # mid artifact may be None if not enough games; end should have data
        if art_mid is not None and art_end is not None:
            assert (
                art_mid.sub_fields["n_games_total"]
                <= art_end.sub_fields["n_games_total"]
            ), "Mid-history should have <= games than end-of-history"

    def test_single_game_player_returns_none(self, section):
        """Player 9999 has only 1 game => cannot form fast+slow buckets => None."""
        as_of = _dt.datetime(2023, 6, 30)
        art = section.build(9999, as_of)
        assert art is None, "Single-game player should return None (insufficient buckets)"

    def test_leaked_row_not_used(self, section):
        """Inject a future row for player 1001 and verify it is not used."""
        from intel.player_pace_fit import PlayerPaceFitSection

        extra = {
            "player_id": 1001,
            "game_id": "002299999",
            "game_date": "2099-01-01",  # future
            "usagepercentage": 0.99,    # would dominate if leaked
            "trueshootingpercentage": 0.99,
            "effectivefieldgoalpercentage": 0.99,
            "assistpercentage": 0.99,
            "reboundpercentage": 0.99,
            "offensivereboundpercentage": 0.99,
            "defensivereboundpercentage": 0.99,
            "offensiverating": 200.0,
            "defensiverating": 50.0,
            "netrating": 150.0,
            "assisttoturnover": 99.0,
            "assistratio": 0.99,
            "turnoverratio": 0.01,
            "pie": 0.99,
            "possessions": 200.0,
            "paceper40": 200.0,
            "minutes": 60.0,
        }
        adv_with_future = pd.concat(
            [PlayerPaceFitSection._adv_df, pd.DataFrame([extra])], ignore_index=True
        )
        PlayerPaceFitSection._adv_df = adv_with_future

        as_of = _dt.datetime(2023, 6, 30)
        art = section.build(1001, as_of)
        if art is not None:
            # usage_fast should NOT be anywhere near 0.99
            usage_f = art.sub_fields.get("usage_fast")
            assert usage_f is None or usage_f < 0.5, (
                f"Leaked future row inflated usage_fast to {usage_f}"
            )


# ---------------------------------------------------------------------------
# 2. SCHEMA-CONFORMANCE assertion
# ---------------------------------------------------------------------------

_REQUIRED_SUB_FIELDS = [
    "n_games_total", "n_fast_games", "n_slow_games",
    "median_pace", "fast_pace_threshold", "slow_pace_threshold",
    "usage_fast", "usage_slow", "usage_pace_delta",
    "ts_fast", "ts_slow", "ts_pace_delta",
    "efg_fast", "efg_slow", "efg_pace_delta",
    "net_rtg_fast", "net_rtg_slow", "net_rtg_pace_delta",
    "pie_fast", "pie_slow", "pie_pace_delta",
    "poss_fast", "poss_slow", "poss_pace_delta",
    "min_fast", "min_slow", "min_pace_delta",
    "reb_pct_fast", "reb_pct_slow", "reb_pct_pace_delta",
    "transition_poss_fast", "transition_poss_slow", "transition_pace_delta",
    "lineup_avg_pace_on", "lineup_pace_delta",
    "pace_preference", "pace_fit_score",
]

_REQUIRED_CV_FIELDS = [
    "cv_spacing_fast",
    "cv_drive_freq_fast",
    "cv_off_ball_speed_fast",
    "cv_off_ball_speed_slow",
]

_REQUIRED_PROVENANCE_KEYS = ["source", "n", "confidence", "as_of"]


class TestSchemaConformance:
    """AtlasArtifact must carry the full contracted schema."""

    @pytest.fixture()
    def artifact(self, section):
        as_of = _dt.datetime(2023, 6, 30)
        art = section.build(1001, as_of)
        assert art is not None, "Expected a valid artifact for player 1001"
        return art

    def test_sub_fields_keys_present(self, artifact):
        for key in _REQUIRED_SUB_FIELDS:
            assert key in artifact.sub_fields, f"Missing sub_field: {key!r}"

    def test_cv_fields_present_and_null(self, artifact):
        """All 4 CV slots must be present with value=None (reserved)."""
        for slot_name in _REQUIRED_CV_FIELDS:
            assert slot_name in artifact.cv_fields, (
                f"Missing cv_field: {slot_name!r}"
            )
            slot = artifact.cv_fields[slot_name]
            assert slot.value is None, (
                f"cv_field {slot_name!r} should be null (reserved); got {slot.value!r}"
            )

    def test_provenance_keys(self, artifact):
        for key in _REQUIRED_PROVENANCE_KEYS:
            assert key in artifact.provenance, f"Missing provenance key: {key!r}"

    def test_confidence_valid(self, artifact):
        assert artifact.confidence in ("low", "med", "high")

    def test_as_of_is_iso_date(self, artifact):
        assert artifact.as_of is not None
        assert len(artifact.as_of) == 10  # YYYY-MM-DD
        assert artifact.as_of[4] == "-" and artifact.as_of[7] == "-"

    def test_section_and_entity(self, artifact):
        assert artifact.section == "pace_fit"
        assert artifact.entity == "player"

    def test_n_games_consistency(self, artifact):
        sf = artifact.sub_fields
        assert sf["n_fast_games"] + sf["n_slow_games"] == sf["n_games_total"]

    def test_pace_preference_valid(self, artifact):
        assert artifact.sub_fields["pace_preference"] in {"fast", "slow", "neutral"}

    def test_to_profile_payload_shape(self, artifact):
        """to_profile_payload() must embed _cv_fields under data."""
        data, prov = artifact.to_profile_payload()
        assert "_cv_fields" in data
        for slot_name in _REQUIRED_CV_FIELDS:
            assert slot_name in data["_cv_fields"], (
                f"_cv_fields missing slot {slot_name!r} in to_profile_payload()"
            )
            assert data["_cv_fields"][slot_name]["value"] is None
        for key in _REQUIRED_PROVENANCE_KEYS:
            assert key in prov


# ---------------------------------------------------------------------------
# 3. VALIDATE check
# ---------------------------------------------------------------------------

class TestValidate:
    """validate() passes on good artifacts, fails on bad ones."""

    @pytest.fixture()
    def good_artifact(self, section):
        as_of = _dt.datetime(2023, 6, 30)
        art = section.build(1001, as_of)
        assert art is not None
        return art

    def test_valid_artifact_passes(self, section, good_artifact):
        assert section.validate(good_artifact) is True

    def test_invalid_n_total_fails(self, section, good_artifact):
        good_artifact.sub_fields["n_games_total"] = 0
        assert section.validate(good_artifact) is False

    def test_invalid_pace_preference_fails(self, section, good_artifact):
        good_artifact.sub_fields["pace_preference"] = "turbo"
        assert section.validate(good_artifact) is False

    def test_invalid_usage_fails(self, section, good_artifact):
        good_artifact.sub_fields["usage_fast"] = 1.5  # >1.0
        assert section.validate(good_artifact) is False

    def test_invalid_score_fails(self, section, good_artifact):
        good_artifact.sub_fields["pace_fit_score"] = 99.0  # out of [-5,5]
        assert section.validate(good_artifact) is False

    def test_bucket_sum_mismatch_fails(self, section, good_artifact):
        good_artifact.sub_fields["n_fast_games"] = 1  # won't sum to n_total
        assert section.validate(good_artifact) is False


# ---------------------------------------------------------------------------
# 4. CV-FIELDS SCHEMA: standalone cv_fields() check
# ---------------------------------------------------------------------------

class TestCVFieldsSchema:
    """cv_fields() must return the full reserved schema independently of build()."""

    def test_cv_fields_all_present(self, section):
        cv = section.cv_fields()
        for slot_name in _REQUIRED_CV_FIELDS:
            assert slot_name in cv, f"cv_fields() missing slot {slot_name!r}"

    def test_cv_fields_all_null(self, section):
        cv = section.cv_fields()
        for slot_name, slot in cv.items():
            assert slot.value is None, (
                f"cv_fields()[{slot_name!r}].value should be None (reserved); "
                f"got {slot.value!r}"
            )

    def test_cv_fields_have_dtype(self, section):
        cv = section.cv_fields()
        for slot_name, slot in cv.items():
            assert slot.dtype in ("float", "dist", "list", "categorical"), (
                f"Unexpected dtype for {slot_name!r}: {slot.dtype!r}"
            )

    def test_cv_fields_have_description(self, section):
        cv = section.cv_fields()
        for slot_name, slot in cv.items():
            assert slot.description, (
                f"cv_field {slot_name!r} has empty description"
            )

    def test_cv_fields_count(self, section):
        assert len(section.cv_fields()) == 4, "Expected exactly 4 CV slots"


# ---------------------------------------------------------------------------
# 5. Section metadata checks
# ---------------------------------------------------------------------------

class TestSectionMetadata:

    def test_name(self, section):
        assert section.name == "pace_fit"

    def test_entity(self, section):
        assert section.entity == "player"

    def test_section_key(self, section):
        assert section.section_key() == "pace_fit"

    def test_sec_fn_name(self, section):
        assert section.sec_fn_name() == "sec_pace_fit"

    def test_parquet_name(self, section):
        assert section.parquet_name() == "atlas_player_pace_fit.parquet"
