"""Tests for signals/pace_regression_to_market.py.

Tests
-----
1. Leak-safety assertion: build() must NOT return a value when the game row
   falls AFTER the decision_time (i.e. future data must be invisible).
2. Value-sanity assertion: for a valid in-sample row, build() returns a dict
   with finite proj_total in a reasonable NBA range (180–280 pts).
3. Market-delta sub-features are NaN when ctx.extra["market_total"] is absent
   and finite when market_total is provided.
4. validate_output() passes for the returned dict and for None.
5. hypothesis() returns a Hypothesis with the correct name, target, scope.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on the path so imports resolve without install.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loop.signal import AsOfContext, Hypothesis, Verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    decision_date: str,
    game_date: str,
    game_id: str = "0022400061",
    home: str = "BOS",
    away: str = "NYK",
    market_total: float = None,
) -> AsOfContext:
    """Build a minimal AsOfContext for testing."""
    extra = {}
    if market_total is not None:
        extra["market_total"] = market_total
    return AsOfContext(
        decision_time=dt.datetime.strptime(decision_date, "%Y-%m-%d"),
        game_id=game_id,
        team=home,
        opp=away,
        game_date=game_date,
        season="2024-25",
        is_home=True,
        scope="pregame",
        extra=extra,
    )


def _minimal_season_games_df(game_date: str = "2024-10-22") -> "pd.DataFrame":
    """Build a minimal season_games-style DataFrame for mock injection."""
    import pandas as pd
    return pd.DataFrame([{
        "game_id": "0022400061",
        "game_date": game_date,
        "home_team": "BOS",
        "away_team": "NYK",
        "home_pace": 96.59,
        "away_pace": 97.64,
        "home_off_rtg_L10": 119.5,
        "away_off_rtg_L10": 117.3,
        "home_def_rtg_L10": 110.1,
        "away_def_rtg_L10": 113.3,
    }])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPaceRegressionToMarket:
    """Unit tests for the pace_regression_to_market signal."""

    def _import_signal(self):
        """Import the signal class (deferred so path is set up first)."""
        from signals.pace_regression_to_market import PaceRegressionToMarket
        return PaceRegressionToMarket

    # ------------------------------------------------------------------ #
    # 1. Leak-safety: game row AFTER decision_time must be invisible       #
    # ------------------------------------------------------------------ #
    def test_leak_safety_future_game_returns_none(self):
        """build() returns None when the game_date is AFTER decision_time.

        This is the core leak-safety contract: season_games rows with
        game_date > as_of are excluded by _find_game_row's mask, so the
        signal must return None rather than consuming future data.
        """
        import pandas as pd
        PaceRegressionToMarket = self._import_signal()
        import signals.pace_regression_to_market as mod

        # game_date is 2024-11-01, decision_time is 2024-10-31 (day BEFORE)
        future_df = _minimal_season_games_df(game_date="2024-11-01")
        ctx = _make_ctx(
            decision_date="2024-10-31",
            game_date="2024-11-01",
            game_id="0022400061",
        )

        sig = PaceRegressionToMarket(store=None)
        with patch.object(mod, "_load_season_games", return_value=future_df):
            result = sig.build(ctx)

        # Must be None — the game is in the future relative to decision_time
        assert result is None, (
            f"Leak-safety violation: build() returned {result!r} for a game "
            f"dated AFTER ctx.decision_time"
        )

    # ------------------------------------------------------------------ #
    # 2. Value-sanity: valid in-sample row returns a reasonable total      #
    # ------------------------------------------------------------------ #
    def test_value_sanity_proj_total_in_nba_range(self):
        """proj_total should be in the reasonable NBA game-total range (180–280)."""
        import pandas as pd
        PaceRegressionToMarket = self._import_signal()
        import signals.pace_regression_to_market as mod

        game_date = "2024-10-22"
        good_df = _minimal_season_games_df(game_date=game_date)
        ctx = _make_ctx(
            decision_date="2024-10-22",
            game_date=game_date,
            game_id="0022400061",
        )

        sig = PaceRegressionToMarket(store=None)
        with patch.object(mod, "_load_season_games", return_value=good_df):
            result = sig.build(ctx)

        assert result is not None, "build() returned None for a valid in-sample row"
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        proj = result["proj_total"]
        assert isinstance(proj, float), f"proj_total should be float, got {type(proj)}"
        assert 180.0 <= proj <= 280.0, (
            f"proj_total={proj:.1f} is outside the realistic NBA total range [180, 280]"
        )

    # ------------------------------------------------------------------ #
    # 3. market_delta / shrink_factor are NaN without market_total        #
    # ------------------------------------------------------------------ #
    def test_no_market_total_gives_nan_sub_features(self):
        """market_delta and shrink_factor must be NaN when market_total absent."""
        import math
        import pandas as pd
        PaceRegressionToMarket = self._import_signal()
        import signals.pace_regression_to_market as mod

        game_date = "2024-10-22"
        good_df = _minimal_season_games_df(game_date=game_date)
        ctx = _make_ctx(
            decision_date="2024-10-22",
            game_date=game_date,
            game_id="0022400061",
            # No market_total in extra
        )

        sig = PaceRegressionToMarket(store=None)
        with patch.object(mod, "_load_season_games", return_value=good_df):
            result = sig.build(ctx)

        assert result is not None
        assert math.isnan(result["market_delta"]), "market_delta must be NaN without market_total"
        assert math.isnan(result["shrink_factor"]), "shrink_factor must be NaN without market_total"
        assert math.isnan(result["abs_miss"]), "abs_miss must be NaN without market_total"

    def test_market_total_provided_gives_finite_delta(self):
        """market_delta and shrink_factor must be finite when market_total is provided."""
        import math
        import pandas as pd
        PaceRegressionToMarket = self._import_signal()
        import signals.pace_regression_to_market as mod

        game_date = "2024-10-22"
        good_df = _minimal_season_games_df(game_date=game_date)
        ctx = _make_ctx(
            decision_date="2024-10-22",
            game_date=game_date,
            game_id="0022400061",
            market_total=228.5,
        )

        sig = PaceRegressionToMarket(store=None)
        with patch.object(mod, "_load_season_games", return_value=good_df):
            result = sig.build(ctx)

        assert result is not None
        assert not math.isnan(result["market_delta"]), "market_delta should be finite"
        assert not math.isnan(result["shrink_factor"]), "shrink_factor should be finite"
        # shrink_factor must be between proj_total and market_total
        proj = result["proj_total"]
        sf = result["shrink_factor"]
        low, high = min(proj, 228.5), max(proj, 228.5)
        assert low <= sf <= high + 1e-9, (
            f"shrink_factor={sf:.2f} should be between proj={proj:.2f} and market=228.5"
        )

    # ------------------------------------------------------------------ #
    # 4. validate_output() passes for valid dict and for None              #
    # ------------------------------------------------------------------ #
    def test_validate_output_passes_for_valid_dict(self):
        """validate_output() must return True for a well-formed output dict."""
        import math
        PaceRegressionToMarket = self._import_signal()
        sig = PaceRegressionToMarket()
        good = {"proj_total": 225.4, "market_delta": float("nan"),
                "shrink_factor": float("nan"), "abs_miss": float("nan")}
        # validate_output checks all values are int/float — NaN is float, so passes
        assert sig.validate_output(good) is True

    def test_validate_output_passes_for_none(self):
        """validate_output() must return True for None (neutral signal)."""
        PaceRegressionToMarket = self._import_signal()
        sig = PaceRegressionToMarket()
        assert sig.validate_output(None) is True

    # ------------------------------------------------------------------ #
    # 5. hypothesis() metadata is correct                                 #
    # ------------------------------------------------------------------ #
    def test_hypothesis_metadata(self):
        """hypothesis() must return a Hypothesis with the correct name/target/scope."""
        PaceRegressionToMarket = self._import_signal()
        sig = PaceRegressionToMarket()
        h = sig.hypothesis()
        assert isinstance(h, Hypothesis)
        assert h.name == "pace_regression_to_market"
        assert h.target == "total"
        assert h.scope == "pregame"
        assert h.expected_verdict == Verdict.DEFER
        assert "pace_profile" in h.atlas_fields

    # ------------------------------------------------------------------ #
    # 6. feature_names() matches emits                                    #
    # ------------------------------------------------------------------ #
    def test_feature_names_matches_emits(self):
        """feature_names() must return [name__k for k in emits]."""
        PaceRegressionToMarket = self._import_signal()
        sig = PaceRegressionToMarket()
        expected = [f"pace_regression_to_market__{k}" for k in sig.emits]
        assert sig.feature_names() == expected

    # ------------------------------------------------------------------ #
    # 7. Class attributes are set correctly                               #
    # ------------------------------------------------------------------ #
    def test_class_attributes(self):
        """Signal class attributes must match the spec."""
        PaceRegressionToMarket = self._import_signal()
        assert PaceRegressionToMarket.name == "pace_regression_to_market"
        assert PaceRegressionToMarket.target == "total"
        assert PaceRegressionToMarket.scope == "pregame"
        assert "pace_profile" in PaceRegressionToMarket.reads_atlas
        assert set(PaceRegressionToMarket.emits) == {
            "proj_total", "market_delta", "shrink_factor", "abs_miss"
        }
