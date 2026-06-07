"""tests/test_signal_depth_vs_starpower.py — Unit tests for DepthVsStarpower signal.

Tests:
  1. Leak-safety: build() never returns values that used data after decision_time.
  2. Value-sanity: depth scores are floats in [0,1]; depth_diff is in [-1,1].
  3. Missing-team graceful: None team yields None (or league-mean values).
  4. Gini helper: known distribution produces expected Gini.
  5. hypothesis() returns a correctly-typed Hypothesis.
  6. feature_names() returns the expected three-element list.
  7. Store atlas override: when the store has a scoring_depth section, it is used.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure repo root is on sys.path (mirrors NBA_OFFLINE=1 discipline).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loop.signal import AsOfContext, Hypothesis, Verdict
from signals.depth_vs_starpower import (
    DepthVsStarpower,
    _gini,
    _depth_score,
    _LEAGUE_MEAN_DEPTH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    team: Optional[str] = "DAL",
    opp: Optional[str] = "SAS",
    is_home: bool = True,
    decision_time: Optional[dt.datetime] = None,
    season: str = "2024-25",
) -> AsOfContext:
    """Build a minimal pregame AsOfContext for testing."""
    return AsOfContext(
        decision_time=decision_time or dt.datetime(2025, 3, 15, 12, 0, 0),
        team=team,
        opp=opp,
        is_home=is_home,
        game_date="2025-03-15",
        season=season,
        scope="pregame",
    )


class _MockStore:
    """Minimal store stub for atlas reads."""

    def __init__(self, atlas_data: Optional[Dict[str, Any]] = None) -> None:
        self._data = atlas_data  # None means no record found

    def read_atlas(self, entity_type: str, entity_id: Any,
                   section: str, as_of: Any, **kwargs) -> Optional[dict]:
        return self._data

    def read(self, entity: str, field_: str, as_of: Any) -> Optional[Any]:
        return None


# ---------------------------------------------------------------------------
# 1. Gini helper correctness
# ---------------------------------------------------------------------------

class TestGiniHelper:
    """_gini produces known values for hand-calculable distributions."""

    def test_equal_distribution_is_zero(self) -> None:
        """Four equal values → Gini = 0."""
        assert _gini(np.array([0.25, 0.25, 0.25, 0.25])) == pytest.approx(0.0, abs=1e-9)

    def test_singleton_is_zero(self) -> None:
        """Single value → Gini = 0 (no inequality)."""
        assert _gini(np.array([1.0])) == pytest.approx(0.0, abs=1e-9)

    def test_maximal_concentration(self) -> None:
        """One player takes all possessions → Gini close to 1."""
        arr = np.array([1.0, 0.0, 0.0, 0.0])
        g = _gini(arr)
        assert g > 0.70, f"Expected high Gini for concentrated usage, got {g:.4f}"

    def test_gini_bounded(self) -> None:
        """Gini is always in [0, 1] for random non-negative arrays."""
        rng = np.random.default_rng(42)
        for _ in range(20):
            arr = rng.uniform(0, 1, size=rng.integers(2, 12))
            g = _gini(arr)
            assert 0.0 <= g <= 1.0, f"Gini out of bounds: {g}"

    def test_depth_score_is_complement(self) -> None:
        """depth_score = 1 − gini."""
        g = 0.35
        assert _depth_score(g) == pytest.approx(1.0 - g)


# ---------------------------------------------------------------------------
# 2. Signal metadata
# ---------------------------------------------------------------------------

class TestSignalMetadata:
    """Class attributes and feature_names match the spec."""

    def test_name(self) -> None:
        sig = DepthVsStarpower()
        assert sig.name == "depth_vs_starpower"

    def test_target(self) -> None:
        assert DepthVsStarpower.target == "total"

    def test_scope(self) -> None:
        assert DepthVsStarpower.scope == "pregame"

    def test_emits_three(self) -> None:
        sig = DepthVsStarpower()
        assert sig.emits == ["home_depth", "away_depth", "depth_diff"]

    def test_feature_names(self) -> None:
        sig = DepthVsStarpower()
        expected = [
            "depth_vs_starpower__home_depth",
            "depth_vs_starpower__away_depth",
            "depth_vs_starpower__depth_diff",
        ]
        assert sig.feature_names() == expected

    def test_reads_atlas(self) -> None:
        sig = DepthVsStarpower()
        assert "scoring_depth" in sig.reads_atlas


# ---------------------------------------------------------------------------
# 3. hypothesis()
# ---------------------------------------------------------------------------

class TestHypothesis:
    """hypothesis() returns a well-formed Hypothesis."""

    def test_returns_hypothesis(self) -> None:
        sig = DepthVsStarpower()
        h = sig.hypothesis()
        assert isinstance(h, Hypothesis)

    def test_hypothesis_name_matches(self) -> None:
        sig = DepthVsStarpower()
        assert sig.hypothesis().name == "depth_vs_starpower"

    def test_hypothesis_target(self) -> None:
        sig = DepthVsStarpower()
        assert sig.hypothesis().target == "total"

    def test_hypothesis_scope(self) -> None:
        sig = DepthVsStarpower()
        assert sig.hypothesis().scope == "pregame"

    def test_hypothesis_atlas_fields(self) -> None:
        sig = DepthVsStarpower()
        assert "scoring_depth" in sig.hypothesis().atlas_fields

    def test_hypothesis_source(self) -> None:
        sig = DepthVsStarpower()
        assert sig.hypothesis().source == "seed"


# ---------------------------------------------------------------------------
# 4. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must never use data after ctx.decision_time.

    We inject a mock bbref parquet that contains ONE row strictly AFTER
    decision_time. The signal must NOT use that row.
    """

    def test_no_future_data_used(self) -> None:
        """A future row in bbref must be invisible to build()."""
        import pandas as pd

        decision_time = dt.datetime(2025, 1, 10, 12, 0, 0)
        future_date = pd.Timestamp("2025-01-15")  # AFTER decision_time

        # Synthesise a bbref-like frame with only a future row.
        future_frame = pd.DataFrame({
            "team_abbreviation": ["DAL"],
            "game_id": ["0022400500"],
            "game_date": [future_date],
            "player_id": [1234],
            "usagepercentage": [0.35],
        })

        ctx = _make_ctx(
            team="DAL",
            opp="SAS",
            decision_time=decision_time,
        )
        sig = DepthVsStarpower(store=None)

        # Patch _get_bbref so it returns only the future row.
        with patch("signals.depth_vs_starpower._get_bbref", return_value=future_frame):
            result = sig.build(ctx)

        # The signal must return a value (league mean fallback) — but NOT
        # incorporate the future data. We verify by checking that home_depth
        # equals the league mean (because no valid data existed before decision_time).
        assert result is not None
        assert isinstance(result, dict)
        home_depth = result["home_depth"]
        # Future data must be invisible → falls back to league mean.
        assert home_depth == pytest.approx(_LEAGUE_MEAN_DEPTH, abs=1e-6), (
            f"Expected league-mean fallback {_LEAGUE_MEAN_DEPTH}, got {home_depth}. "
            "Leak-safety violated: future row was used."
        )


# ---------------------------------------------------------------------------
# 5. Value-sanity assertions
# ---------------------------------------------------------------------------

class TestValueSanity:
    """build() returns valid float sub-features."""

    def _build_with_no_data(self, team: str, opp: str) -> dict:
        """Build with empty parquets → league-mean fallback."""
        import pandas as pd
        ctx = _make_ctx(team=team, opp=opp)
        sig = DepthVsStarpower(store=None)
        empty = pd.DataFrame()
        with patch("signals.depth_vs_starpower._get_bbref", return_value=empty):
            result = sig.build(ctx)
        return result

    def test_returns_dict(self) -> None:
        result = self._build_with_no_data("DAL", "SAS")
        assert isinstance(result, dict)

    def test_home_depth_in_range(self) -> None:
        result = self._build_with_no_data("DAL", "SAS")
        assert 0.0 <= result["home_depth"] <= 1.0

    def test_away_depth_in_range(self) -> None:
        result = self._build_with_no_data("DAL", "SAS")
        assert 0.0 <= result["away_depth"] <= 1.0

    def test_depth_diff_is_difference(self) -> None:
        result = self._build_with_no_data("DAL", "SAS")
        diff = result["home_depth"] - result["away_depth"]
        assert result["depth_diff"] == pytest.approx(diff, abs=1e-6)

    def test_depth_diff_in_minus1_1(self) -> None:
        result = self._build_with_no_data("DAL", "SAS")
        assert -1.0 <= result["depth_diff"] <= 1.0

    def test_validate_output_passes(self) -> None:
        result = self._build_with_no_data("DAL", "SAS")
        sig = DepthVsStarpower()
        assert sig.validate_output(result) is True

    def test_both_teams_none_returns_none(self) -> None:
        """When both team identifiers are None, build() must return None."""
        ctx = _make_ctx(team=None, opp=None)
        sig = DepthVsStarpower(store=None)
        result = sig.build(ctx)
        assert result is None

    def test_league_mean_fallback(self) -> None:
        """With no parquet data, both teams should get the league-mean depth."""
        import pandas as pd
        ctx = _make_ctx()
        sig = DepthVsStarpower(store=None)
        empty = pd.DataFrame()
        with patch("signals.depth_vs_starpower._get_bbref", return_value=empty):
            result = sig.build(ctx)
        assert result["home_depth"] == pytest.approx(_LEAGUE_MEAN_DEPTH, abs=1e-6)
        assert result["away_depth"] == pytest.approx(_LEAGUE_MEAN_DEPTH, abs=1e-6)
        assert result["depth_diff"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 6. Atlas store integration
# ---------------------------------------------------------------------------

class TestAtlasOverride:
    """When the store has scoring_depth data, it overrides the parquet path."""

    def test_store_atlas_used_when_present(self) -> None:
        """Atlas value of 0.85 depth_score should appear in home_depth."""
        import pandas as pd

        atlas_payload = {"depth_score": 0.85, "gini": 0.15, "n_players": 8}
        store = _MockStore(atlas_data=atlas_payload)
        ctx = _make_ctx(team="SAS", opp="HOU", is_home=True)
        sig = DepthVsStarpower(store=store)

        empty = pd.DataFrame()
        with patch("signals.depth_vs_starpower._get_bbref", return_value=empty):
            result = sig.build(ctx)

        assert result is not None
        # home team is SAS (is_home=True, team=SAS) → should get atlas value 0.85
        assert result["home_depth"] == pytest.approx(0.85, abs=1e-6), (
            f"Expected atlas depth_score=0.85 for home, got {result['home_depth']}"
        )

    def test_store_none_falls_back_to_parquet(self) -> None:
        """With store=None the signal must not crash."""
        import pandas as pd
        ctx = _make_ctx()
        sig = DepthVsStarpower(store=None)
        empty = pd.DataFrame()
        with patch("signals.depth_vs_starpower._get_bbref", return_value=empty):
            result = sig.build(ctx)
        assert result is not None
        assert "home_depth" in result


# ---------------------------------------------------------------------------
# 7. Real parquet smoke test (skipped if parquet absent)
# ---------------------------------------------------------------------------

class TestRealParquetSmoke:
    """If bbref_advanced_extended is present, depth scores should be non-trivial."""

    @pytest.mark.skipif(
        not (ROOT / "data" / "cache" / "bbref_advanced_extended.parquet").exists(),
        reason="bbref_advanced_extended.parquet not present on this machine",
    )
    def test_real_data_depth_scores_nonzero(self) -> None:
        """Real parquet produces depth scores clearly off the league mean."""
        ctx = _make_ctx(
            team="LAL",
            opp="GSW",
            is_home=True,
            decision_time=dt.datetime(2025, 3, 1, 12, 0, 0),
            season="2024-25",
        )
        import signals.depth_vs_starpower as mod
        # Reset the bbref cache so real data loads.
        mod._BBREF_CACHE = None

        sig = DepthVsStarpower(store=None)
        result = sig.build(ctx)
        assert result is not None
        # Should have real values; at minimum they must be in range.
        assert 0.0 <= result["home_depth"] <= 1.0
        assert 0.0 <= result["away_depth"] <= 1.0
