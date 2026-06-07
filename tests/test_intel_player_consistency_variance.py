"""Tests for intel/player_consistency_variance.py.

Tests verify:
  1. LEAK-SAFETY: build() must not return data stamped after the requested as_of.
  2. SCHEMA CONFORMANCE: artifact contains all required sub_fields, all cv_fields
     are present with value=None, and validate() passes.
  3. METRICS SANITY: CV non-negative, boom_rate in [0,1], floor <= median <= ceiling,
     composite_cv matches per-stat CVs.
  4. MISSING DATA: build() returns None when player has no rows before as_of.

These tests run fully offline (NBA_OFFLINE=1) using a minimal synthetic in-memory
parquet that is injected into the module-level cache.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Ensure the repo root is on sys.path for offline imports
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Lazy import so we can mock the cache before the module runs any IO
import intel.player_consistency_variance as _mod
from intel.player_consistency_variance import (
    PlayerConsistencyVariance,
    _STATS,
    _BOOM_MULT,
    _BUST_MULT,
    _compute_per_stat_metrics,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Fixtures: synthetic parquets injected into the module-level _SRC_CACHE
# ---------------------------------------------------------------------------

def _make_oof_df(player_id: int, n_games: int = 40, seed: int = 42) -> pd.DataFrame:
    """Synthetic pregame_oof rows for one player across all 7 stats."""
    rng = np.random.default_rng(seed)
    rows = []
    base_date = _dt.date(2025, 1, 1)
    for i in range(n_games):
        game_date = (base_date + _dt.timedelta(days=i)).isoformat()
        game_id = f"00250{i:04d}"
        for stat in _STATS:
            # Use distinct means so most/least consistent stats are deterministic
            stat_means = {
                "pts": 25.0, "reb": 5.0, "ast": 6.0,
                "fg3m": 2.0, "stl": 1.0, "blk": 0.5, "tov": 2.5
            }
            stat_stds = {
                "pts": 5.0, "reb": 2.0, "ast": 1.0,
                "fg3m": 1.5, "stl": 0.8, "blk": 0.4, "tov": 1.0
            }
            mean = stat_means[stat]
            std = stat_stds[stat]
            actual = max(0.0, rng.normal(mean, std))
            rows.append({
                "game_id": game_id,
                "player_id": player_id,
                "stat": stat,
                "oof_pred": actual + rng.normal(0, 0.5),
                "actual": round(actual),
                "game_date": game_date,
                "fold": 1,
                "season": "2024-25",
            })
    return pd.DataFrame(rows)


def _make_propcal_df(player_id: int) -> pd.DataFrame:
    """Synthetic prop_calibration_history rows for one player."""
    rows = []
    for stat in _STATS:
        rows.append({
            "player_id": player_id,
            "stat": stat,
            "n": 40,
            "mean_pred": 5.0,
            "mean_actual": 4.8,
            "bias": 0.2,
            "mae": 1.2,
            "rmse": 1.6,
            "n_interval": 40,
            "interval_coverage": 0.88,
            "interval_nominal": 0.9,
        })
    return pd.DataFrame(rows)


def _inject_cache(oof_df: pd.DataFrame, propcal_df: pd.DataFrame) -> None:
    """Inject synthetic DataFrames directly into the module-level _SRC_CACHE."""
    _mod._SRC_CACHE["oof"] = oof_df
    _mod._SRC_CACHE["propcal"] = propcal_df


def _clear_cache() -> None:
    """Clear the module-level cache so tests are isolated."""
    _mod._SRC_CACHE.clear()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_PLAYER_ID = 9999901
_AS_OF = _dt.datetime(2025, 6, 15, 0, 0, 0)  # well after synthetic game dates


def _build_artifact(
    player_id: int = _PLAYER_ID,
    as_of: _dt.datetime = _AS_OF,
    n_games: int = 40,
) -> Optional[AtlasArtifact]:
    """Build a consistency_variance artifact using synthetic data."""
    _clear_cache()
    oof_df = _make_oof_df(player_id, n_games=n_games)
    propcal_df = _make_propcal_df(player_id)
    _inject_cache(oof_df, propcal_df)
    section = PlayerConsistencyVariance()
    return section.build(player_id, as_of)


# ===========================================================================
# 1. LEAK-SAFETY ASSERTION
# ===========================================================================

class TestLeakSafety:
    """build() must only use game data that was available at as_of."""

    def test_no_future_games_returned(self):
        """Games with game_date > as_of must be excluded from the computation."""
        _clear_cache()
        player_id = _PLAYER_ID

        # Create two sets: 20 past games + 20 future games
        past_oof = _make_oof_df(player_id, n_games=20)
        future_oof = _make_oof_df(player_id, n_games=20, seed=99)

        # Shift future games 1 year past the as_of boundary
        future_oof["game_date"] = pd.to_datetime(future_oof["game_date"]) + pd.DateOffset(years=2)
        future_oof["game_date"] = future_oof["game_date"].dt.date.astype(str)

        all_oof = pd.concat([past_oof, future_oof], ignore_index=True)
        propcal_df = _make_propcal_df(player_id)
        _inject_cache(all_oof, propcal_df)

        # as_of is between past and future
        as_of = _dt.datetime(2025, 6, 15)
        section = PlayerConsistencyVariance()
        artifact = section.build(player_id, as_of)

        assert artifact is not None, "Expected an artifact from the past-only data"

        per_stat = artifact.sub_fields["per_stat"]
        for stat in _STATS:
            stat_metrics = per_stat.get(stat)
            if stat_metrics is not None:
                n = stat_metrics.get("n_games", 0)
                # Must reflect only the 20 past games (not 40 total)
                assert n <= 20, (
                    f"stat={stat}: n_games={n} exceeds 20 past games. "
                    "Future game rows are leaking into the artifact."
                )

    def test_all_future_returns_none(self):
        """When as_of predates all game_dates, build() must return None."""
        _clear_cache()
        player_id = _PLAYER_ID
        oof_df = _make_oof_df(player_id, n_games=20)
        propcal_df = _make_propcal_df(player_id)
        _inject_cache(oof_df, propcal_df)

        # as_of before any synthetic game
        as_of = _dt.datetime(2020, 1, 1)
        section = PlayerConsistencyVariance()
        artifact = section.build(player_id, as_of)
        assert artifact is None, (
            "build() must return None when all game_dates are after as_of (leak boundary)."
        )

    def test_artifact_as_of_matches_requested(self):
        """Artifact.as_of must equal the requested as_of date (not a future date)."""
        artifact = _build_artifact()
        assert artifact is not None
        expected = _AS_OF.date().isoformat()
        assert artifact.as_of == expected, (
            f"artifact.as_of={artifact.as_of!r} != requested as_of={expected!r}"
        )


# ===========================================================================
# 2. SCHEMA CONFORMANCE
# ===========================================================================

class TestSchemaConformance:
    """AtlasArtifact must match the documented sub_fields + cv_fields schema."""

    def test_required_sub_fields_present(self):
        """All required top-level sub_fields must be present."""
        artifact = _build_artifact()
        assert artifact is not None
        required = {"per_stat", "headline", "calibration",
                    "consistency_trend", "opponent_adjusted_cv"}
        missing = required - set(artifact.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_per_stat_fields_present(self):
        """per_stat must contain entries for at least some stats; each with required keys."""
        artifact = _build_artifact()
        assert artifact is not None
        per_stat = artifact.sub_fields["per_stat"]
        assert len(per_stat) > 0, "per_stat must have at least one stat entry"

        required_metric_keys = {
            "n_games", "mean", "std", "cv",
            "floor_p10", "floor_p25", "median",
            "ceiling_p75", "ceiling_p90",
            "iqr", "boom_rate", "bust_rate",
        }
        for stat, metrics in per_stat.items():
            missing = required_metric_keys - set(metrics.keys())
            assert not missing, (
                f"stat={stat!r} is missing metric keys: {missing}"
            )

    def test_headline_fields_present(self):
        """headline must contain most_consistent_stat, least_consistent_stat, composite_cv."""
        artifact = _build_artifact()
        assert artifact is not None
        headline = artifact.sub_fields["headline"]
        assert "most_consistent_stat" in headline
        assert "least_consistent_stat" in headline
        assert "composite_cv" in headline

    def test_cv_fields_present_and_null(self):
        """All 4 CV slots must be present in artifact.cv_fields with value=None."""
        artifact = _build_artifact()
        assert artifact is not None

        expected_slots = {
            "cv_shot_quality_cv",
            "cv_velocity_cv",
            "cv_spacing_cv",
            "cv_paint_touches_cv",
        }
        actual_slots = set(artifact.cv_fields.keys())
        assert expected_slots == actual_slots, (
            f"CV slot mismatch. Expected: {expected_slots}. Got: {actual_slots}"
        )
        for slot_name, slot in artifact.cv_fields.items():
            assert isinstance(slot, CVSlot), f"{slot_name} is not a CVSlot"
            assert slot.value is None, (
                f"CV slot {slot_name!r} has value={slot.value!r}; "
                "CV branch has not run yet, so value must be None."
            )

    def test_cv_fields_class_method_returns_all_slots(self):
        """cv_fields() static output must have all 4 slots."""
        section = PlayerConsistencyVariance()
        slots = section.cv_fields()
        expected = {"cv_shot_quality_cv", "cv_velocity_cv",
                    "cv_spacing_cv", "cv_paint_touches_cv"}
        assert set(slots.keys()) == expected

    def test_profile_payload_shape(self):
        """to_profile_payload() must return (data, prov) matching the factory schema."""
        artifact = _build_artifact()
        assert artifact is not None
        data, prov = artifact.to_profile_payload()

        # _cv_fields embedded in data
        assert "_cv_fields" in data
        for slot_name in ("cv_shot_quality_cv", "cv_velocity_cv",
                           "cv_spacing_cv", "cv_paint_touches_cv"):
            assert slot_name in data["_cv_fields"], (
                f"CV slot {slot_name!r} missing from _cv_fields in profile payload"
            )
            slot_payload = data["_cv_fields"][slot_name]
            assert slot_payload["value"] is None

        # prov shape
        assert "source" in prov
        assert "n" in prov
        assert "confidence" in prov
        assert "as_of" in prov
        assert prov["confidence"] in ("low", "med", "high")

    def test_section_and_entity_attributes(self):
        """Section name, entity, parquet_name, sec_fn_name must be set correctly."""
        section = PlayerConsistencyVariance()
        assert section.name == "consistency_variance"
        assert section.entity == "player"
        assert section.parquet_name() == "atlas_player_consistency_variance.parquet"
        assert section.sec_fn_name() == "sec_consistency_variance"


# ===========================================================================
# 3. METRICS SANITY
# ===========================================================================

class TestMetricsSanity:
    """Computed metric values must be internally self-consistent."""

    def test_cv_non_negative(self):
        """Coefficient of variation must be >= 0 for all stats."""
        artifact = _build_artifact()
        assert artifact is not None
        for stat, metrics in artifact.sub_fields["per_stat"].items():
            cv = metrics.get("cv")
            if cv is not None:
                assert cv >= 0.0, f"stat={stat}: cv={cv} is negative"

    def test_boom_bust_rates_in_unit_interval(self):
        """boom_rate and bust_rate must be in [0, 1]."""
        artifact = _build_artifact()
        assert artifact is not None
        for stat, metrics in artifact.sub_fields["per_stat"].items():
            for rate_key in ("boom_rate", "bust_rate"):
                r = metrics.get(rate_key)
                if r is not None:
                    assert 0.0 <= r <= 1.0, (
                        f"stat={stat}: {rate_key}={r} out of [0, 1]"
                    )

    def test_floor_lte_median_lte_ceiling(self):
        """floor_p10 <= median <= ceiling_p90 must hold for all stats."""
        artifact = _build_artifact()
        assert artifact is not None
        for stat, metrics in artifact.sub_fields["per_stat"].items():
            f10 = metrics.get("floor_p10")
            med = metrics.get("median")
            c90 = metrics.get("ceiling_p90")
            if all(v is not None for v in (f10, med, c90)):
                assert f10 <= med, f"stat={stat}: floor_p10={f10} > median={med}"
                assert med <= c90, f"stat={stat}: median={med} > ceiling_p90={c90}"

    def test_composite_cv_is_mean_of_per_stat_cvs(self):
        """composite_cv in headline must be close to the mean of per-stat CVs."""
        artifact = _build_artifact()
        assert artifact is not None
        per_stat = artifact.sub_fields["per_stat"]
        per_stat_cvs = [
            v["cv"] for v in per_stat.values() if v.get("cv") is not None
        ]
        if per_stat_cvs:
            expected_composite = round(float(np.mean(per_stat_cvs)), 4)
            actual_composite = artifact.sub_fields["headline"]["composite_cv"]
            assert actual_composite is not None
            assert abs(actual_composite - expected_composite) < 1e-3, (
                f"composite_cv={actual_composite} != mean of per-stat CVs={expected_composite}"
            )

    def test_n_games_positive(self):
        """n_games in per_stat must be a positive integer."""
        artifact = _build_artifact()
        assert artifact is not None
        for stat, metrics in artifact.sub_fields["per_stat"].items():
            n = metrics.get("n_games", 0)
            assert isinstance(n, int) and n > 0, (
                f"stat={stat}: n_games={n} is not a positive integer"
            )

    def test_confidence_ladder(self):
        """Confidence must be 'high' for >= 20 games (our synthetic fixture uses 40)."""
        artifact = _build_artifact(n_games=40)
        assert artifact is not None
        assert artifact.confidence == "high", (
            f"Expected 'high' confidence for 40 games; got {artifact.confidence!r}"
        )

    def test_low_confidence_for_few_games(self):
        """Confidence must be 'low' for < 5 games."""
        artifact = _build_artifact(n_games=3)
        assert artifact is not None
        assert artifact.confidence == "low", (
            f"Expected 'low' confidence for 3 games; got {artifact.confidence!r}"
        )

    def test_validate_passes_on_good_artifact(self):
        """validate() must return True for a well-formed artifact."""
        artifact = _build_artifact()
        assert artifact is not None
        section = PlayerConsistencyVariance()
        assert section.validate(artifact), "validate() returned False on a valid artifact"

    def test_validate_fails_on_wrong_section(self):
        """validate() must fail if artifact.section is wrong."""
        artifact = _build_artifact()
        assert artifact is not None
        artifact.section = "wrong_section"
        section = PlayerConsistencyVariance()
        assert not section.validate(artifact)

    def test_validate_fails_if_cv_slot_has_value(self):
        """validate() must fail if any CV slot has been pre-filled."""
        artifact = _build_artifact()
        assert artifact is not None
        # Manually fill a slot (simulating a spurious write)
        first_slot = next(iter(artifact.cv_fields))
        artifact.cv_fields[first_slot].value = 0.42
        section = PlayerConsistencyVariance()
        assert not section.validate(artifact), (
            "validate() should fail when a CV slot has a non-None value before CV branch runs"
        )


# ===========================================================================
# 4. MISSING DATA HANDLING
# ===========================================================================

class TestMissingDataHandling:
    """build() must gracefully handle absent or sparse data."""

    def test_unknown_player_returns_none(self):
        """A player not in the OOF parquet must return None, not raise."""
        _clear_cache()
        oof_df = _make_oof_df(_PLAYER_ID, n_games=40)
        propcal_df = _make_propcal_df(_PLAYER_ID)
        _inject_cache(oof_df, propcal_df)

        section = PlayerConsistencyVariance()
        result = section.build(999999, _AS_OF)
        assert result is None

    def test_empty_oof_returns_none(self):
        """Empty OOF parquet must yield None (graceful degrades)."""
        _clear_cache()
        empty_oof = pd.DataFrame(
            columns=["game_id", "player_id", "stat", "actual", "game_date", "fold", "season"]
        )
        propcal_df = _make_propcal_df(_PLAYER_ID)
        _inject_cache(empty_oof, propcal_df)

        section = PlayerConsistencyVariance()
        result = section.build(_PLAYER_ID, _AS_OF)
        assert result is None

    def test_missing_propcal_still_produces_artifact(self):
        """Missing prop_calibration_history is non-fatal; calibration section is empty."""
        _clear_cache()
        oof_df = _make_oof_df(_PLAYER_ID, n_games=40)
        empty_propcal = pd.DataFrame(
            columns=["player_id", "stat", "n", "mae", "bias",
                     "interval_coverage", "interval_nominal"]
        )
        _inject_cache(oof_df, empty_propcal)

        section = PlayerConsistencyVariance()
        artifact = section.build(_PLAYER_ID, _AS_OF)
        assert artifact is not None, "Missing propcal should not prevent artifact creation"
        # calibration section should be empty dict (no stats)
        calibration = artifact.sub_fields.get("calibration", {})
        assert isinstance(calibration, dict)


# ===========================================================================
# 5. UNIT TEST FOR _compute_per_stat_metrics helper
# ===========================================================================

class TestComputePerStatMetrics:
    """Unit tests for the _compute_per_stat_metrics helper."""

    def test_basic_series(self):
        """Basic correctness for a known series."""
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = _compute_per_stat_metrics(series)
        assert result["n_games"] == 5
        assert result["mean"] == pytest.approx(30.0, abs=1e-3)
        assert result["median"] == pytest.approx(30.0, abs=1e-3)
        assert result["floor_p10"] <= 16.0  # 10th pct of [10..50] ~= 14 (pandas linear interp)
        assert result["ceiling_p90"] >= 44.0
        # CV = std / mean
        assert result["cv"] is not None
        assert result["cv"] > 0.0
        # No values >= 1.5 * 30 = 45 except 50
        assert 0.0 <= result["boom_rate"] <= 1.0

    def test_zero_mean_produces_none_cv(self):
        """A series of zeros must produce cv=None (avoid division by zero)."""
        series = pd.Series([0.0, 0.0, 0.0])
        result = _compute_per_stat_metrics(series)
        assert result["cv"] is None
        assert result["boom_rate"] is None
        assert result["bust_rate"] is None

    def test_single_game(self):
        """A single-game series must not raise; std=0, cv=0."""
        series = pd.Series([15.0])
        result = _compute_per_stat_metrics(series)
        assert result["n_games"] == 1
        assert result["std"] == pytest.approx(0.0, abs=1e-6)
        assert result["cv"] == pytest.approx(0.0, abs=1e-6)
