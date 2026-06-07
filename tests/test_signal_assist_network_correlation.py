"""Tests for signals/assist_network_correlation.py.

Tests cover:
  1. Leak-safety: build() MUST NOT return data from *after* decision_time.
  2. Value sanity: returned dict has valid sub-feature names + numeric / None values.
  3. None-player graceful handling.
  4. Atlas fallback path (when tracking is absent).
  5. validate_output() accepts the dict signal shape.
"""
from __future__ import annotations

import datetime as _dt
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Ensure repo root is on path (mirrors the build-agent rule)
sys.path.insert(0, ".")

import pandas as pd

from signals.assist_network_correlation import (
    AssistNetworkCorrelation,
    _rolling_ast_pct,
    _safe_float,
    _seasonal_tracking_features,
)
from src.loop.signal import AsOfContext, Hypothesis, TARGETS, SCOPES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    player_id=1628983,
    decision_time=_dt.datetime(2025, 3, 1, 12, 0, 0),
    season="2024-25",
    team="OKC",
    opp="DAL",
    scope="pregame",
) -> AsOfContext:
    return AsOfContext(
        decision_time=decision_time,
        player_id=player_id,
        team=team,
        opp=opp,
        season=season,
        scope=scope,
    )


def _make_adv_df() -> pd.DataFrame:
    """Small synthetic adv_stats dataframe with a few dates around the decision_time."""
    dates = pd.to_datetime([
        "2025-01-10", "2025-01-15", "2025-01-20", "2025-01-25",
        "2025-02-01", "2025-02-08", "2025-02-15",
        # These are AFTER decision_time 2025-03-01 and must NOT be used:
        "2025-03-05", "2025-03-15",
    ])
    ast_pcts = [0.30, 0.35, 0.28, 0.40, 0.32, 0.38, 0.36, 0.99, 0.99]
    return pd.DataFrame({
        "player_id": [1628983] * 9,
        "game_id": [f"00224000{i:02d}" for i in range(9)],
        "game_date": dates,
        "assistpercentage": ast_pcts,
        "assistratio": [20.0] * 9,
        "assisttoturnover": [2.0] * 9,
    })


def _make_tracking_df() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [1628983],
        "season": ["2024-25"],
        "trk_pas_passes_made": [50.0],
        "trk_pas_potential_ast": [12.0],
        "trk_pas_ast_points_created": [20.0],
        "trk_pas_secondary_ast": [1.0],
        "trk_pas_ft_ast": [0.5],
        "trk_drv_count": [5.0],
        "trk_drv_pts": [8.0],
        "trk_drv_fg_pct": [0.55],
        "trk_drv_passes": [3.0],
        "trk_drv_ast": [2.0],
        "trk_drv_tov_pct": [0.1],
        "trk_cs_fga": [10.0],
        "trk_cs_fg_pct": [0.45],
        "trk_cs_efg_pct": [0.50],
        "trk_cs_pts": [15.0],
        "trk_ast_creation_rate": [12.0 / 50.0],  # pre-computed
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLeakSafety(unittest.TestCase):
    """Assertion: no information after decision_time leaks into build()."""

    def test_rolling_ast_pct_excludes_future_games(self):
        """_rolling_ast_pct must exclude games on or after before_date."""
        df = _make_adv_df()
        before_date = _dt.datetime(2025, 3, 1)
        result = _rolling_ast_pct(df, player_id=1628983, before_date=before_date)

        # The two future rows have ast_pct=0.99; if they leaked in, mean would be >0.45
        self.assertIsNotNone(result)
        self.assertLess(result, 0.50,
            f"Leak detected: future games with ast_pct=0.99 contaminated result={result:.3f}")
        # Correct mean of the 7 historical rows: (0.30+0.35+0.28+0.40+0.32+0.38+0.36)/7 ≈ 0.341
        self.assertAlmostEqual(result, 0.3414, places=2)

    def test_build_with_synthetic_data_no_future_contamination(self):
        """build() must produce a playmaker_role that excludes post-decision rows."""
        import signals.assist_network_correlation as mod
        original_adv = mod._ADV_STATS
        original_trk = mod._TRACKING
        try:
            mod._ADV_STATS = _make_adv_df()
            # Add trk_ast_creation_rate column to tracking
            trk = _make_tracking_df()
            mod._TRACKING = trk

            sig = AssistNetworkCorrelation()
            ctx = _make_ctx(decision_time=_dt.datetime(2025, 3, 1))
            result = sig.build(ctx)

            self.assertIsNotNone(result)
            self.assertIsInstance(result, dict)
            role = result.get("playmaker_role")
            self.assertIsNotNone(role)
            self.assertLess(role, 0.50,
                f"Leak: playmaker_role={role:.3f} contaminated by future 0.99 rows")
        finally:
            mod._ADV_STATS = original_adv
            mod._TRACKING = original_trk


class TestValueSanity(unittest.TestCase):
    """Assertion: returned values are well-formed and in plausible ranges."""

    def setUp(self):
        import signals.assist_network_correlation as mod
        self.mod = mod
        self._orig_adv = mod._ADV_STATS
        self._orig_trk = mod._TRACKING
        mod._ADV_STATS = _make_adv_df()
        mod._TRACKING = _make_tracking_df()

    def tearDown(self):
        self.mod._ADV_STATS = self._orig_adv
        self.mod._TRACKING = self._orig_trk

    def test_feature_names_match_emits(self):
        sig = AssistNetworkCorrelation()
        expected = [
            "assist_network_correlation__playmaker_role",
            "assist_network_correlation__playmaker_ceiling",
            "assist_network_correlation__ast_creation_rate",
        ]
        self.assertEqual(sig.feature_names(), expected)

    def test_build_returns_dict_with_three_keys(self):
        sig = AssistNetworkCorrelation()
        ctx = _make_ctx()
        result = sig.build(ctx)
        self.assertIsInstance(result, dict)
        for k in ("playmaker_role", "playmaker_ceiling", "ast_creation_rate"):
            self.assertIn(k, result, f"Missing sub-feature '{k}'")

    def test_playmaker_role_in_unit_range(self):
        sig = AssistNetworkCorrelation()
        ctx = _make_ctx()
        result = sig.build(ctx)
        role = result["playmaker_role"]
        if role is not None:
            self.assertGreaterEqual(role, 0.0)
            self.assertLessEqual(role, 1.0, f"assistpercentage must be in [0,1]: {role}")

    def test_playmaker_ceiling_positive(self):
        sig = AssistNetworkCorrelation()
        ctx = _make_ctx()
        result = sig.build(ctx)
        ceiling = result["playmaker_ceiling"]
        if ceiling is not None:
            self.assertGreaterEqual(ceiling, 0.0)
            self.assertLessEqual(ceiling, 25.0, f"potential_ast implausibly high: {ceiling}")

    def test_ast_creation_rate_in_unit_range(self):
        sig = AssistNetworkCorrelation()
        ctx = _make_ctx()
        result = sig.build(ctx)
        rate = result["ast_creation_rate"]
        if rate is not None:
            self.assertGreaterEqual(rate, 0.0)
            self.assertLessEqual(rate, 1.0, f"creation_rate must be <= 1: {rate}")
            # 12 potential_ast / 50 passes = 0.24
            self.assertAlmostEqual(rate, 0.24, places=2)

    def test_validate_output_accepts_dict(self):
        sig = AssistNetworkCorrelation()
        ctx = _make_ctx()
        result = sig.build(ctx)
        self.assertTrue(sig.validate_output(result))

    def test_validate_output_accepts_none(self):
        sig = AssistNetworkCorrelation()
        self.assertTrue(sig.validate_output(None))

    def test_none_player_id_returns_none(self):
        sig = AssistNetworkCorrelation()
        ctx = _make_ctx(player_id=None)
        result = sig.build(ctx)
        self.assertIsNone(result)

    def test_unknown_player_returns_none(self):
        sig = AssistNetworkCorrelation()
        ctx = _make_ctx(player_id=9999999)  # not in synthetic dfs
        result = sig.build(ctx)
        # Either None or a dict with all-None values (both are valid; validate_output passes)
        self.assertTrue(sig.validate_output(result))

    def test_hypothesis_metadata(self):
        sig = AssistNetworkCorrelation()
        hyp = sig.hypothesis()
        self.assertIsInstance(hyp, Hypothesis)
        self.assertEqual(hyp.name, "assist_network_correlation")
        self.assertEqual(hyp.target, "ast")
        self.assertIn(hyp.target, TARGETS)
        self.assertIn(hyp.scope, SCOPES)
        self.assertIn("playmaking", hyp.atlas_fields)
        self.assertGreater(len(hyp.statement), 40)

    def test_class_attributes(self):
        sig = AssistNetworkCorrelation()
        self.assertEqual(sig.name, "assist_network_correlation")
        self.assertEqual(sig.target, "ast")
        self.assertEqual(sig.scope, "both")
        self.assertEqual(sig.reads_atlas, ["playmaking"])
        self.assertEqual(len(sig.emits), 3)


class TestAtlasFallback(unittest.TestCase):
    """Assertion: atlas prior is used when tracking is unavailable."""

    def test_atlas_fallback_for_ceiling(self):
        """When tracking has no row, build() falls back to atlas playmaking section."""
        import signals.assist_network_correlation as mod
        orig_adv = mod._ADV_STATS
        orig_trk = mod._TRACKING
        try:
            mod._ADV_STATS = _make_adv_df()
            # Empty tracking — forces atlas fallback
            mod._TRACKING = pd.DataFrame(columns=list(_make_tracking_df().columns))

            # Build a mock store that returns a playmaking atlas payload
            mock_store = MagicMock()
            mock_store.read.return_value = {
                "potential_ast": 11.5,
                "passes_made": 48.0,
                "ast_pts_created": 18.0,
            }

            sig = AssistNetworkCorrelation(store=mock_store)
            ctx = _make_ctx()
            result = sig.build(ctx)

            self.assertIsNotNone(result)
            ceiling = result.get("playmaker_ceiling")
            # Should use atlas potential_ast = 11.5
            self.assertIsNotNone(ceiling)
            self.assertAlmostEqual(ceiling, 11.5, places=1)
        finally:
            mod._ADV_STATS = orig_adv
            mod._TRACKING = orig_trk


class TestSafeFloat(unittest.TestCase):
    """Unit tests for the _safe_float helper."""

    def test_none_returns_none(self):
        self.assertIsNone(_safe_float(None))

    def test_nan_returns_none(self):
        import math
        self.assertIsNone(_safe_float(float("nan")))

    def test_inf_returns_none(self):
        self.assertIsNone(_safe_float(float("inf")))

    def test_valid_float(self):
        self.assertAlmostEqual(_safe_float(0.25), 0.25)

    def test_string_number(self):
        self.assertAlmostEqual(_safe_float("0.30"), 0.30)


if __name__ == "__main__":
    unittest.main()
