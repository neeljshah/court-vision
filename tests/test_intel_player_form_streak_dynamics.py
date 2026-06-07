"""Tests for intel/player_form_streak_dynamics.py.

Covers:
  1. LEAK-SAFETY: build(pid, as_of) must not use actuals after as_of.
  2. SCHEMA CONFORMANCE: artifact has all required sub_fields, cv_fields present
     with correct slot names and null values, validate() passes.
  3. MATH SANITY: rate fields in [0,1], streak run counts >= 0, form_score finite.
  4. MISSING DATA: returns None for an unknown player or early as_of.
  5. DRY-RUN REGISTRATION: register_section with dry_run=True does not write disk.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers: build a minimal synthetic pregame_oof dataframe
# ---------------------------------------------------------------------------

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

_TEST_PID = 999901  # synthetic player — must not appear in real data
_KNOWN_PID = 1628983  # SGA — expected in real pregame_oof if parquet exists


def _make_synthetic_oof(
    pid: int,
    n_games: int,
    base_date: _dt.date = _dt.date(2024, 1, 1),
    seed: int = 42,
) -> pd.DataFrame:
    """Create a synthetic pregame_oof DataFrame for one player."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_games):
        game_date = base_date + _dt.timedelta(days=i)
        for stat in _STATS:
            # realistic values: pts~20, reb~5, ast~4, others~1
            mu = {"pts": 20, "reb": 5, "ast": 4, "fg3m": 2,
                  "stl": 1, "blk": 0.5, "tov": 2}[stat]
            val = max(0.0, float(rng.normal(mu, mu * 0.4)))
            rows.append({
                "player_id": pid,
                "game_id": f"00{i:06d}",
                "game_date": pd.Timestamp(game_date),
                "stat": stat,
                "actual": round(val, 1),
                "oof_pred": round(val * 0.9, 1),
                "fold": 1,
                "season": "2023-24",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixture: patch the data source with synthetic data
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_oof_pid() -> int:
    return _TEST_PID


@pytest.fixture()
def synthetic_oof_df(synthetic_oof_pid: int) -> pd.DataFrame:
    return _make_synthetic_oof(synthetic_oof_pid, n_games=30)


@pytest.fixture()
def section_instance():
    from intel.player_form_streak_dynamics import PlayerFormStreakDynamics
    return PlayerFormStreakDynamics()


@pytest.fixture()
def patched_build(synthetic_oof_pid: int, synthetic_oof_df: pd.DataFrame):
    """Return a build() callable that uses synthetic in-memory data."""
    import intel.player_form_streak_dynamics as mod
    with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
        yield mod


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build(pid, as_of) must not see actuals dated AFTER as_of."""

    def test_early_as_of_hides_future_games(
        self, synthetic_oof_pid: int, synthetic_oof_df: pd.DataFrame
    ):
        import intel.player_form_streak_dynamics as mod
        # Inject full 30-game synthetic dataset
        with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
            # as_of = day 10 (Jan 11) — should see only 11 games
            as_of_early = _dt.datetime(2024, 1, 11, 0, 0, 0)
            art_early = mod._build_player_form_streak(synthetic_oof_pid, as_of_early)

            # as_of = day 30 (Jan 31) — should see all 30 games
            as_of_full = _dt.datetime(2024, 1, 30, 23, 59, 59)
            art_full = mod._build_player_form_streak(synthetic_oof_pid, as_of_full)

        # art_early must have fewer games than art_full
        assert art_early is not None, "expected artifact for early as_of with 11 games"
        assert art_full is not None, "expected artifact for full as_of"

        n_early = art_early.sub_fields["summary"]["n_games"]
        n_full = art_full.sub_fields["summary"]["n_games"]
        assert n_early < n_full, (
            f"Leak-safety violation: early as_of returned {n_early} games "
            f"but full as_of returned {n_full}; they should differ."
        )

    def test_very_early_as_of_returns_none(
        self, synthetic_oof_pid: int, synthetic_oof_df: pd.DataFrame
    ):
        """as_of before any game data => build returns None (< 5 games)."""
        import intel.player_form_streak_dynamics as mod
        with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
            # Jan 3 = only 3 games; < 5 threshold => None
            as_of = _dt.datetime(2024, 1, 3, 0, 0, 0)
            art = mod._build_player_form_streak(synthetic_oof_pid, as_of)
        assert art is None, "Expected None when fewer than 5 games available"

    def test_unknown_player_returns_none(
        self, synthetic_oof_df: pd.DataFrame
    ):
        """Unknown player_id => build returns None (no rows in data)."""
        import intel.player_form_streak_dynamics as mod
        with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
            as_of = _dt.datetime(2024, 2, 1, 0, 0, 0)
            art = mod._build_player_form_streak(999999, as_of)
        assert art is None


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """AtlasArtifact must have correct section, entity, sub_field keys, cv_fields."""

    def _build_full(self, synthetic_oof_pid, synthetic_oof_df):
        import intel.player_form_streak_dynamics as mod
        with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
            as_of = _dt.datetime(2024, 2, 1, 0, 0, 0)
            return mod._build_player_form_streak(synthetic_oof_pid, as_of)

    def test_section_and_entity(
        self, synthetic_oof_pid, synthetic_oof_df, section_instance
    ):
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        assert art is not None
        assert art.section == "form_streak_dynamics"
        assert art.entity == "player"
        assert art.entity_id == synthetic_oof_pid

    def test_required_top_level_sub_fields(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        required = {"per_stat", "summary", "minute_trajectory",
                    "usage_adjusted", "opponent_adjusted"}
        missing = required - set(art.sub_fields.keys())
        assert not missing, f"Missing top-level sub_fields: {missing}"

    def test_summary_fields_present(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        summary = art.sub_fields["summary"]
        assert "n_games" in summary
        assert "active_streaks" in summary
        assert "form_score" in summary
        assert isinstance(summary["n_games"], int)
        assert summary["n_games"] >= 5

    def test_per_stat_dynamics_keys(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        """Each populated stat must have streak_rates/runs/bounce_back/hangover/regression."""
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        per_stat = art.sub_fields["per_stat"]
        assert per_stat, "per_stat should be non-empty for a 30-game player"
        for stat, dyn in per_stat.items():
            for key in ("streak_rates", "streak_runs", "bounce_back",
                        "hangover", "regression", "season_mean", "season_std"):
                assert key in dyn, f"Missing key '{key}' in per_stat['{stat}']"

    def test_cv_fields_present_and_null(
        self, synthetic_oof_pid, synthetic_oof_df, section_instance
    ):
        """cv_fields must be present with exactly the reserved slot names; values None."""
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        cv = art.cv_fields
        assert "fatigue_velocity_trend" in cv, "CV slot 'fatigue_velocity_trend' missing"
        assert "spacing_context_streak" in cv, "CV slot 'spacing_context_streak' missing"
        for slot_name, slot in cv.items():
            assert slot.value is None, (
                f"CV slot '{slot_name}' value must be None until CV branch fills it; "
                f"got {slot.value!r}"
            )

    def test_cv_fields_via_section_method(self, section_instance):
        """cv_fields() class method returns correct schema independently of build()."""
        cv = section_instance.cv_fields()
        assert set(cv.keys()) == {"fatigue_velocity_trend", "spacing_context_streak"}
        for name, slot in cv.items():
            assert slot.name == name
            assert slot.value is None
            assert isinstance(slot.description, str) and len(slot.description) > 10

    def test_validate_passes(
        self, synthetic_oof_pid, synthetic_oof_df, section_instance
    ):
        """section.validate() must return True for a well-formed artifact."""
        import intel.player_form_streak_dynamics as mod
        with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
            as_of = _dt.datetime(2024, 2, 1, 0, 0, 0)
            art = mod._build_player_form_streak(synthetic_oof_pid, as_of)
        assert section_instance.validate(art), "validate() returned False on a valid artifact"

    def test_provenance_fields(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        """Provenance must have source/n/confidence/as_of."""
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        for key in ("source", "n", "confidence", "as_of"):
            assert key in art.provenance, f"Missing provenance key: {key}"
        assert art.provenance["confidence"] in ("low", "med", "high")
        assert art.provenance["n"] >= 5

    def test_to_profile_payload_shape(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        """to_profile_payload() returns (data, prov) with _cv_fields embedded."""
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "_cv_fields missing from profile payload data"
        assert "fatigue_velocity_trend" in data["_cv_fields"]
        assert "spacing_context_streak" in data["_cv_fields"]
        assert prov["confidence"] in ("low", "med", "high")


# ---------------------------------------------------------------------------
# 3. MATH SANITY
# ---------------------------------------------------------------------------

class TestMathSanity:
    """Rate fields must be in [0,1]; run counts >= 0; form_score finite."""

    def _build_full(self, synthetic_oof_pid, synthetic_oof_df):
        import intel.player_form_streak_dynamics as mod
        with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
            as_of = _dt.datetime(2024, 2, 1, 0, 0, 0)
            return mod._build_player_form_streak(synthetic_oof_pid, as_of)

    def test_rates_in_unit_interval(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        per_stat = art.sub_fields["per_stat"]
        for stat, dyn in per_stat.items():
            sr = dyn["streak_rates"]
            for k, v in sr.items():
                assert 0.0 <= v <= 1.0, f"{stat}.streak_rates.{k}={v} out of [0,1]"
            for bb_key in ("post_dud_hot_rate", "post_dud_above_mean_rate"):
                v = dyn["bounce_back"].get(bb_key)
                if v is not None:
                    assert 0.0 <= v <= 1.0, f"{stat}.bounce_back.{bb_key}={v}"
            for ho_key in ("post_monster_cold_rate", "post_monster_below_mean_rate"):
                v = dyn["hangover"].get(ho_key)
                if v is not None:
                    assert 0.0 <= v <= 1.0, f"{stat}.hangover.{ho_key}={v}"

    def test_run_counts_non_negative(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        per_stat = art.sub_fields["per_stat"]
        for stat, dyn in per_stat.items():
            sr = dyn["streak_runs"]
            for k, v in sr.items():
                if v is not None:
                    assert v >= 0, f"{stat}.streak_runs.{k}={v} is negative"

    def test_form_score_finite_or_none(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        fs = art.sub_fields["summary"]["form_score"]
        if fs is not None:
            assert np.isfinite(fs), f"form_score={fs} is not finite"

    def test_hot_cold_rates_sum_to_at_most_one(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        """hot_game_rate + cold_game_rate <= 1 (since a game can't be both)."""
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        for stat, dyn in art.sub_fields["per_stat"].items():
            hot = dyn["streak_rates"]["hot_game_rate"]
            cold = dyn["streak_rates"]["cold_game_rate"]
            assert hot + cold <= 1.0 + 1e-6, (
                f"{stat}: hot_rate={hot} + cold_rate={cold} > 1"
            )

    def test_monster_rate_lte_hot_rate(
        self, synthetic_oof_pid, synthetic_oof_df
    ):
        """monster_game_rate (>=1.5s) must be <= hot_game_rate (>=0.5s) subset."""
        art = self._build_full(synthetic_oof_pid, synthetic_oof_df)
        for stat, dyn in art.sub_fields["per_stat"].items():
            monster = dyn["streak_rates"]["monster_game_rate"]
            hot = dyn["streak_rates"]["hot_game_rate"]
            # monster is a strict subset of hot in the labelling
            assert monster <= hot + 1e-6, (
                f"{stat}: monster_rate={monster} > hot_rate={hot}"
            )


# ---------------------------------------------------------------------------
# 4. DRY-RUN REGISTRATION
# ---------------------------------------------------------------------------

class TestDryRunRegistration:
    """register_section(dry_run=True) must not write parquet or registry."""

    def test_dry_run_does_not_write_files(
        self, synthetic_oof_pid: int, synthetic_oof_df: pd.DataFrame, tmp_path: Path
    ):
        import intel.player_form_streak_dynamics as mod
        from intel.player_form_streak_dynamics import PlayerFormStreakDynamics

        section = PlayerFormStreakDynamics()
        as_of = _dt.datetime(2024, 2, 1, 0, 0, 0)

        with patch.object(mod, "_SRC_CACHE", {"pregame_oof": synthetic_oof_df}):
            art = mod._build_player_form_streak(synthetic_oof_pid, as_of)

        assert art is not None

        # Patch CACHE and REGISTRY to temp paths so no real disk is touched
        from src.loop import profile_factory_bridge as bridge
        with (
            patch.object(bridge, "CACHE", tmp_path),
            patch.object(bridge, "REGISTRY", tmp_path / "atlas_registry.json"),
        ):
            manifest = bridge.register_section(section, [art], dry_run=True)

        # dry_run=True => parquet must NOT have been written
        pq_path = tmp_path / section.parquet_name()
        assert not pq_path.exists(), (
            f"dry_run=True but parquet was written to {pq_path}"
        )
        # Registry also must not have been written
        assert not (tmp_path / "atlas_registry.json").exists(), (
            "dry_run=True but atlas_registry.json was written"
        )

        # Manifest must still return meaningful metadata
        assert manifest["section"] == "form_streak_dynamics"
        assert manifest["n_entities"] == 1
        assert "fatigue_velocity_trend" in manifest["cv_fields"]
        assert "spacing_context_streak" in manifest["cv_fields"]
