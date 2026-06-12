"""Conformance tests for NBA_STAT_REGISTRY (P0-D-012).

R3 ordering invariant: the registry's stat order, sigma values, calibration
slopes, and priced_order must stay byte-identical to the three live-literal
source files.  Any drift here means a positional array (routed-ensemble heads,
correlation matrices, model pickle feature order) would silently misalign.

Source-of-truth files:
    sigma_default              ← src/prediction/decision_engine.py _STAT_SIGMA
    calibration_fallback_slope ← src/prediction/edge_calibration.py _FALLBACK_SLOPES
    priced_order               ← src/prediction/betting_portfolio.py _PROP_STATS_ORDER
    loop_targets               ← src/loop/signal.py TARGETS
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Domain registry under test
# ---------------------------------------------------------------------------
from domains.basketball_nba.config import NBA_STAT_REGISTRY

# ---------------------------------------------------------------------------
# Live-literal sources (light-weight imports — no heavy deps triggered)
# ---------------------------------------------------------------------------
from src.prediction.decision_engine import _STAT_SIGMA
from src.prediction.edge_calibration import _FALLBACK_SLOPES
from src.prediction.betting_portfolio import _PROP_STATS_ORDER
from src.loop.signal import TARGETS

# ---------------------------------------------------------------------------
# Expected canonical order (the R3 constant — change here is a breaking change)
# ---------------------------------------------------------------------------
_EXPECTED_STAT_ORDER = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


# ---------------------------------------------------------------------------
# Stat-order invariant
# ---------------------------------------------------------------------------

class TestStatOrder:
    """Registry insertion order must equal the historical 7-tuple."""

    def test_stat_names_count(self) -> None:
        """Registry contains exactly 7 stats."""
        assert len(NBA_STAT_REGISTRY.stats) == 7

    def test_stat_order_exact(self) -> None:
        """target_names() == ('pts','reb','ast','fg3m','stl','blk','tov')."""
        assert NBA_STAT_REGISTRY.target_names() == _EXPECTED_STAT_ORDER

    def test_stat_order_equals_prop_stats_order(self) -> None:
        """priced_order() == tuple(_PROP_STATS_ORDER) from betting_portfolio."""
        assert NBA_STAT_REGISTRY.priced_order() == tuple(_PROP_STATS_ORDER)


# ---------------------------------------------------------------------------
# Sigma conformance — element-by-element
# ---------------------------------------------------------------------------

class TestSigmaDefaults:
    """Each stat's sigma_default must equal _STAT_SIGMA[stat]."""

    @pytest.mark.parametrize("stat", _EXPECTED_STAT_ORDER)
    def test_sigma_default(self, stat: str) -> None:
        spec = NBA_STAT_REGISTRY.spec(stat)
        assert spec.sigma_default == _STAT_SIGMA[stat], (
            f"sigma_default mismatch for '{stat}': "
            f"registry={spec.sigma_default!r}, _STAT_SIGMA={_STAT_SIGMA[stat]!r}"
        )


# ---------------------------------------------------------------------------
# Calibration-slope conformance — element-by-element
# ---------------------------------------------------------------------------

class TestCalibrationFallbackSlopes:
    """Each stat's calibration_fallback_slope must equal _FALLBACK_SLOPES[stat]."""

    @pytest.mark.parametrize("stat", _EXPECTED_STAT_ORDER)
    def test_calibration_fallback_slope(self, stat: str) -> None:
        spec = NBA_STAT_REGISTRY.spec(stat)
        assert spec.calibration_fallback_slope == _FALLBACK_SLOPES[stat], (
            f"calibration_fallback_slope mismatch for '{stat}': "
            f"registry={spec.calibration_fallback_slope!r}, "
            f"_FALLBACK_SLOPES={_FALLBACK_SLOPES[stat]!r}"
        )


# ---------------------------------------------------------------------------
# priced_order invariant
# ---------------------------------------------------------------------------

class TestPricedOrder:
    """priced_order() must be byte-identical to _PROP_STATS_ORDER."""

    def test_all_stats_are_priced(self) -> None:
        """All 7 NBA stats are prop-market priced."""
        for stat in _EXPECTED_STAT_ORDER:
            assert NBA_STAT_REGISTRY.spec(stat).priced is True, (
                f"Expected priced=True for '{stat}'"
            )

    def test_priced_order_length(self) -> None:
        """priced_order() has exactly 7 elements."""
        assert len(NBA_STAT_REGISTRY.priced_order()) == 7

    def test_priced_order_equals_prop_stats_order(self) -> None:
        """priced_order() == tuple(_PROP_STATS_ORDER), element and positional."""
        assert NBA_STAT_REGISTRY.priced_order() == tuple(_PROP_STATS_ORDER)


# ---------------------------------------------------------------------------
# loop_targets invariant
# ---------------------------------------------------------------------------

class TestLoopTargets:
    """loop_targets must be byte-identical to src.loop.signal.TARGETS."""

    def test_loop_targets_equals_signal_targets(self) -> None:
        """loop_targets == TARGETS from src/loop/signal.py."""
        assert NBA_STAT_REGISTRY.loop_targets == TARGETS, (
            f"loop_targets mismatch:\n"
            f"  registry : {NBA_STAT_REGISTRY.loop_targets!r}\n"
            f"  signal.py: {TARGETS!r}"
        )

    def test_loop_targets_length(self) -> None:
        """loop_targets has exactly 12 elements (7 stats + 5 meta)."""
        assert len(NBA_STAT_REGISTRY.loop_targets) == 12

    def test_loop_targets_starts_with_stat_order(self) -> None:
        """First 7 elements of loop_targets equal the stat order."""
        assert NBA_STAT_REGISTRY.loop_targets[:7] == _EXPECTED_STAT_ORDER

    def test_loop_targets_meta_suffix(self) -> None:
        """Last 5 elements are the fixed meta-targets."""
        expected_meta = ("minutes", "total", "winprob", "usage", "sigma")
        assert NBA_STAT_REGISTRY.loop_targets[7:] == expected_meta


# ---------------------------------------------------------------------------
# sport_id and structural sanity
# ---------------------------------------------------------------------------

class TestRegistryStructure:
    """Basic structural checks on the registry object."""

    def test_sport_id(self) -> None:
        assert NBA_STAT_REGISTRY.sport_id == "basketball_nba"

    def test_score_stat(self) -> None:
        assert NBA_STAT_REGISTRY.score_stat == "pts"

    def test_minutes_equiv(self) -> None:
        assert NBA_STAT_REGISTRY.minutes_equiv == "minutes"

    def test_box_score_mapping_keys(self) -> None:
        """box_score_mapping covers all 7 stats."""
        mapped_stats = set(NBA_STAT_REGISTRY.box_score_mapping.values())
        assert set(_EXPECTED_STAT_ORDER) == mapped_stats

    def test_tov_higher_is_better_false(self) -> None:
        """Turnovers are the only stat where higher_is_better=False."""
        for stat in _EXPECTED_STAT_ORDER:
            spec = NBA_STAT_REGISTRY.spec(stat)
            if stat == "tov":
                assert spec.higher_is_better is False, "tov must be higher_is_better=False"
            else:
                assert spec.higher_is_better is True, (
                    f"'{stat}' must be higher_is_better=True"
                )

    def test_all_stats_kind_count(self) -> None:
        """All 7 NBA prop stats are counting stats (kind='count')."""
        for stat in _EXPECTED_STAT_ORDER:
            assert NBA_STAT_REGISTRY.spec(stat).kind == "count", (
                f"Expected kind='count' for '{stat}'"
            )

    def test_all_stats_settle_official_box(self) -> None:
        """All stats settle from the official box score."""
        for stat in _EXPECTED_STAT_ORDER:
            assert NBA_STAT_REGISTRY.spec(stat).settle == "official_box", (
                f"Expected settle='official_box' for '{stat}'"
            )
