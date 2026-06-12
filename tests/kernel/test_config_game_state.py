"""Tests for kernel.config.game_state.GameStateConfig.

Hermetic and offline — stdlib + dataclasses + typing only (no numpy, pandas,
torch, nba_api).

Coverage:
  (1) NBA instance instantiates frozen with all primary fields populated.
  (2) legacy_overrides preserves BOTH sides of every disagreement:
        - blowout  : game_models=15.0  vs  garbage_time_detector/live_game_simulator=18.0
        - clutch   : live_game_simulator.clutch_margin=6.0  vs  game_clock_sim=5.0
        - clutch-sec: live_game_simulator=360.0  vs  game_clock_sim=300.0
  (3) Every primary field carries a value (not None, > 0).
  (4) Frozen-ness: field re-assignment raises FrozenInstanceError/AttributeError.
  (5) Validation: bad values raise ValueError.
  (6) Helper predicates is_blowout / is_clutch / is_competitive work correctly.
"""
from __future__ import annotations

import dataclasses
import types

import pytest

from kernel.config.game_state import GameStateConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def nba_game_state() -> GameStateConfig:
    """Standard NBA game-state config using the canonical primary values."""
    return GameStateConfig(
        blowout_margin=15.0,
        clutch_margin=6.0,
        clutch_remaining_sec=360.0,
        garbage_margin=18.0,
        competitive_margin=12.0,
        final_margin_sigma=13.5,
        winprob_promotion_period=4,
    )


# ---------------------------------------------------------------------------
# Case 1 — NBA instance instantiates, primary fields populated
# ---------------------------------------------------------------------------

class TestInstantiation:
    def test_instantiates_without_error(self, nba_game_state: GameStateConfig) -> None:
        """The NBA config must construct without raising."""
        assert nba_game_state is not None

    def test_blowout_margin_is_set(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.blowout_margin == pytest.approx(15.0)

    def test_clutch_margin_is_set(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.clutch_margin == pytest.approx(6.0)

    def test_clutch_remaining_sec_is_set(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.clutch_remaining_sec == pytest.approx(360.0)

    def test_garbage_margin_is_set(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.garbage_margin == pytest.approx(18.0)

    def test_competitive_margin_is_set(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.competitive_margin == pytest.approx(12.0)

    def test_final_margin_sigma_is_set(self, nba_game_state: GameStateConfig) -> None:
        """SIGMA_FULL_DEFAULT=13.5 from universal_winprob.py:28."""
        assert nba_game_state.final_margin_sigma == pytest.approx(13.5)

    def test_winprob_promotion_period_is_set(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """MIN_PERIOD_FOR_UNIVERSAL=4 from universal_winprob.py:33."""
        assert nba_game_state.winprob_promotion_period == 4

    def test_all_float_fields_positive(self, nba_game_state: GameStateConfig) -> None:
        """Every numeric field must be strictly positive."""
        float_fields = [
            nba_game_state.blowout_margin,
            nba_game_state.clutch_margin,
            nba_game_state.clutch_remaining_sec,
            nba_game_state.garbage_margin,
            nba_game_state.competitive_margin,
            nba_game_state.final_margin_sigma,
        ]
        for val in float_fields:
            assert val > 0.0, f"Expected positive field, got {val}"

    def test_winprob_promotion_period_is_int_gte_1(
        self, nba_game_state: GameStateConfig
    ) -> None:
        assert isinstance(nba_game_state.winprob_promotion_period, int)
        assert nba_game_state.winprob_promotion_period >= 1


# ---------------------------------------------------------------------------
# Case 2 — legacy_overrides preserves disagreements
# ---------------------------------------------------------------------------

class TestLegacyOverrides:
    """The honesty mechanism: BOTH sides of every disagreement are preserved."""

    def test_legacy_overrides_is_mapping(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """legacy_overrides must be a Mapping."""
        from collections.abc import Mapping
        assert isinstance(nba_game_state.legacy_overrides, Mapping)

    def test_legacy_overrides_is_read_only(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """The default is a MappingProxyType — mutations must raise TypeError."""
        with pytest.raises(TypeError):
            nba_game_state.legacy_overrides["new_key"] = 99.0  # type: ignore[index]

    # --- blowout disagreements ---

    def test_game_models_blowout_margin_is_15(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """game_models.py:100 uses 15.0 — the conservative training threshold."""
        val = nba_game_state.legacy_overrides["game_models.blowout_margin"]
        assert val == pytest.approx(15.0)

    def test_garbage_time_detector_blowout_margin_is_18(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """garbage_time_detector.py:157 live path uses 18.0."""
        val = nba_game_state.legacy_overrides["garbage_time_detector.blowout_margin"]
        assert val == pytest.approx(18.0)

    def test_live_game_simulator_blowout_margin_is_18(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """live_game_simulator.py:185 uses 18.0."""
        val = nba_game_state.legacy_overrides["live_game_simulator.blowout_margin"]
        assert val == pytest.approx(18.0)

    def test_blowout_disagreement_15_vs_18_preserved(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """The 15 vs 18 disagreement must survive; both are retrievable."""
        overrides = nba_game_state.legacy_overrides
        game_models_val = overrides["game_models.blowout_margin"]
        live_sim_val = overrides["live_game_simulator.blowout_margin"]
        assert game_models_val == pytest.approx(15.0)
        assert live_sim_val == pytest.approx(18.0)
        # Confirm they genuinely differ — the disagreement is not collapsed.
        assert game_models_val != live_sim_val

    # --- clutch margin disagreements ---

    def test_live_game_simulator_clutch_margin_is_6(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """live_game_simulator.py:279 uses margin<=6."""
        val = nba_game_state.legacy_overrides["live_game_simulator.clutch_margin"]
        assert val == pytest.approx(6.0)

    def test_game_clock_sim_clutch_margin_is_5(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """game_clock_sim.py:171 uses margin<=5."""
        val = nba_game_state.legacy_overrides["game_clock_sim.clutch_margin"]
        assert val == pytest.approx(5.0)

    def test_clutch_margin_disagreement_6_vs_5_preserved(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """The 6.0 vs 5.0 clutch-margin disagreement must not be collapsed."""
        overrides = nba_game_state.legacy_overrides
        lgs_val = overrides["live_game_simulator.clutch_margin"]
        gcs_val = overrides["game_clock_sim.clutch_margin"]
        assert lgs_val == pytest.approx(6.0)
        assert gcs_val == pytest.approx(5.0)
        assert lgs_val != gcs_val

    # --- clutch remaining-seconds disagreements ---

    def test_live_game_simulator_clutch_remaining_sec_is_360(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """live_game_simulator.py:279 uses sec<=360."""
        val = nba_game_state.legacy_overrides["live_game_simulator.clutch_remaining_sec"]
        assert val == pytest.approx(360.0)

    def test_game_clock_sim_clutch_remaining_sec_is_300(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """game_clock_sim.py:171 uses clock<300."""
        val = nba_game_state.legacy_overrides["game_clock_sim.clutch_remaining_sec"]
        assert val == pytest.approx(300.0)

    def test_clutch_remaining_sec_disagreement_360_vs_300_preserved(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """The 360.0 vs 300.0 remaining-sec disagreement must not be collapsed."""
        overrides = nba_game_state.legacy_overrides
        lgs_sec = overrides["live_game_simulator.clutch_remaining_sec"]
        gcs_sec = overrides["game_clock_sim.clutch_remaining_sec"]
        assert lgs_sec == pytest.approx(360.0)
        assert gcs_sec == pytest.approx(300.0)
        assert lgs_sec != gcs_sec

    # --- training threshold also captured ---

    def test_garbage_time_detector_training_threshold_captured(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """garbage_time_detector.py:35 training threshold of 15.0 must be in overrides."""
        val = nba_game_state.legacy_overrides[
            "garbage_time_detector.blowout_margin_training"
        ]
        assert val == pytest.approx(15.0)

    def test_minimum_required_keys_present(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """The 5 minimum required keys from spec P0-D-005 must be present."""
        required = {
            "game_models.blowout_margin",
            "garbage_time_detector.blowout_margin",
            "live_game_simulator.blowout_margin",
            "live_game_simulator.clutch_margin",
            "game_clock_sim.clutch_margin",
        }
        overrides = nba_game_state.legacy_overrides
        missing = required - set(overrides.keys())
        assert not missing, f"Missing required legacy_overrides keys: {missing}"


# ---------------------------------------------------------------------------
# Case 3 — every primary field carries a value
# ---------------------------------------------------------------------------

class TestPrimaryFields:
    """Cross-check via dataclasses.fields that every field is populated."""

    def test_all_fields_populated(self, nba_game_state: GameStateConfig) -> None:
        """All fields must have a non-None value after construction."""
        for f in dataclasses.fields(nba_game_state):
            val = getattr(nba_game_state, f.name)
            assert val is not None, f"Field {f.name!r} is None"

    def test_field_count(self, nba_game_state: GameStateConfig) -> None:
        """The dataclass must have exactly 8 fields (7 primary + legacy_overrides)."""
        assert len(dataclasses.fields(nba_game_state)) == 8


# ---------------------------------------------------------------------------
# Case 4 — frozen-ness
# ---------------------------------------------------------------------------

class TestFrozenness:
    def test_cannot_mutate_blowout_margin(
        self, nba_game_state: GameStateConfig
    ) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_game_state.blowout_margin = 20.0  # type: ignore[misc]

    def test_cannot_mutate_clutch_margin(
        self, nba_game_state: GameStateConfig
    ) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_game_state.clutch_margin = 10.0  # type: ignore[misc]

    def test_cannot_mutate_winprob_promotion_period(
        self, nba_game_state: GameStateConfig
    ) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_game_state.winprob_promotion_period = 3  # type: ignore[misc]

    def test_cannot_replace_legacy_overrides(
        self, nba_game_state: GameStateConfig
    ) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_game_state.legacy_overrides = {}  # type: ignore[misc]

    def test_is_frozen_dataclass(self, nba_game_state: GameStateConfig) -> None:
        """Verify the __dataclass_params__ frozen flag is True."""
        params = nba_game_state.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen is True


# ---------------------------------------------------------------------------
# Case 5 — validation (bad values raise ValueError)
# ---------------------------------------------------------------------------

class TestValidation:
    def _valid_kwargs(self):  # type: ignore[return]
        return dict(
            blowout_margin=15.0,
            clutch_margin=6.0,
            clutch_remaining_sec=360.0,
            garbage_margin=18.0,
            competitive_margin=12.0,
            final_margin_sigma=13.5,
            winprob_promotion_period=4,
        )

    def test_negative_blowout_margin_raises(self) -> None:
        kw = self._valid_kwargs()
        kw["blowout_margin"] = -1.0
        with pytest.raises(ValueError, match="blowout_margin"):
            GameStateConfig(**kw)

    def test_zero_clutch_margin_raises(self) -> None:
        kw = self._valid_kwargs()
        kw["clutch_margin"] = 0.0
        with pytest.raises(ValueError, match="clutch_margin"):
            GameStateConfig(**kw)

    def test_zero_clutch_remaining_sec_raises(self) -> None:
        kw = self._valid_kwargs()
        kw["clutch_remaining_sec"] = 0.0
        with pytest.raises(ValueError, match="clutch_remaining_sec"):
            GameStateConfig(**kw)

    def test_negative_garbage_margin_raises(self) -> None:
        kw = self._valid_kwargs()
        kw["garbage_margin"] = -5.0
        with pytest.raises(ValueError, match="garbage_margin"):
            GameStateConfig(**kw)

    def test_negative_final_margin_sigma_raises(self) -> None:
        kw = self._valid_kwargs()
        kw["final_margin_sigma"] = -0.1
        with pytest.raises(ValueError, match="final_margin_sigma"):
            GameStateConfig(**kw)

    def test_winprob_promotion_period_zero_raises(self) -> None:
        kw = self._valid_kwargs()
        kw["winprob_promotion_period"] = 0
        with pytest.raises(ValueError, match="winprob_promotion_period"):
            GameStateConfig(**kw)

    def test_valid_min_values_do_not_raise(self) -> None:
        """Boundary-legal values must not raise."""
        cfg = GameStateConfig(
            blowout_margin=0.1,
            clutch_margin=0.1,
            clutch_remaining_sec=0.1,
            garbage_margin=0.1,
            competitive_margin=0.1,
            final_margin_sigma=0.1,
            winprob_promotion_period=1,
        )
        assert cfg.winprob_promotion_period == 1


# ---------------------------------------------------------------------------
# Case 6 — helper predicates
# ---------------------------------------------------------------------------

class TestPredicates:
    def test_is_blowout_true_above_threshold(
        self, nba_game_state: GameStateConfig
    ) -> None:
        assert nba_game_state.is_blowout(15.0) is True
        assert nba_game_state.is_blowout(20.0) is True

    def test_is_blowout_false_below_threshold(
        self, nba_game_state: GameStateConfig
    ) -> None:
        assert nba_game_state.is_blowout(14.9) is False
        assert nba_game_state.is_blowout(0.0) is False

    def test_is_blowout_uses_abs(self, nba_game_state: GameStateConfig) -> None:
        """Negative margins (trailing team's perspective) are also detected."""
        assert nba_game_state.is_blowout(-15.0) is True
        assert nba_game_state.is_blowout(-14.9) is False

    def test_is_clutch_true_in_window(self, nba_game_state: GameStateConfig) -> None:
        """margin<=6, remaining<=360, period>=4 → clutch."""
        assert nba_game_state.is_clutch(margin=3.0, remaining_sec=120.0, period=4) is True

    def test_is_clutch_false_margin_too_large(
        self, nba_game_state: GameStateConfig
    ) -> None:
        assert nba_game_state.is_clutch(margin=7.0, remaining_sec=120.0, period=4) is False

    def test_is_clutch_false_too_early_in_game(
        self, nba_game_state: GameStateConfig
    ) -> None:
        """Period < winprob_promotion_period (4) → not clutch."""
        assert nba_game_state.is_clutch(margin=2.0, remaining_sec=60.0, period=3) is False

    def test_is_clutch_false_too_much_time_left(
        self, nba_game_state: GameStateConfig
    ) -> None:
        assert nba_game_state.is_clutch(margin=2.0, remaining_sec=400.0, period=4) is False

    def test_is_competitive_true(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.is_competitive(12.0) is True
        assert nba_game_state.is_competitive(5.0) is True

    def test_is_competitive_false(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.is_competitive(12.1) is False
        assert nba_game_state.is_competitive(25.0) is False

    def test_is_competitive_uses_abs(self, nba_game_state: GameStateConfig) -> None:
        assert nba_game_state.is_competitive(-10.0) is True
        assert nba_game_state.is_competitive(-13.0) is False


# ---------------------------------------------------------------------------
# Case 7 — custom legacy_overrides (non-default mapping)
# ---------------------------------------------------------------------------

class TestCustomLegacyOverrides:
    def test_custom_overrides_accepted(self) -> None:
        """A caller can supply their own Mapping for legacy_overrides."""
        import types as _types
        custom = _types.MappingProxyType({"my_module.blowout": 20.0})
        cfg = GameStateConfig(
            blowout_margin=20.0,
            clutch_margin=8.0,
            clutch_remaining_sec=300.0,
            garbage_margin=25.0,
            competitive_margin=15.0,
            final_margin_sigma=14.0,
            winprob_promotion_period=3,
            legacy_overrides=custom,
        )
        assert cfg.legacy_overrides["my_module.blowout"] == pytest.approx(20.0)

    def test_plain_dict_accepted_as_mapping(self) -> None:
        """A plain dict (Mapping) is also accepted for legacy_overrides."""
        cfg = GameStateConfig(
            blowout_margin=10.0,
            clutch_margin=5.0,
            clutch_remaining_sec=240.0,
            garbage_margin=12.0,
            competitive_margin=8.0,
            final_margin_sigma=11.0,
            winprob_promotion_period=2,
            legacy_overrides={"sport.val": 42.0},
        )
        assert cfg.legacy_overrides["sport.val"] == pytest.approx(42.0)
