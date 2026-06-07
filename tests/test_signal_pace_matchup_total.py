"""Tests for signals/pace_matchup_total.py.

Tests
-----
1. Leak-safety: when team_advanced_stats rows have game_date > decision_time,
   build() must return None (no future data consumed).
2. Value-sanity: valid in-sample rows produce a dict with combined_pace in
   [85, 115] and pace_adj_total in NBA range [180, 280].
3. Tier interaction: both-FAST teams yield tier_interaction=+1.0; both-SLOW
   yields -1.0; asymmetric yields 0.0.
4. Missing team data (opp not in parquet) returns None.
5. validate_output() passes for a valid dict and for None.
6. hypothesis() returns correct name/target/scope.
7. feature_names() matches emits list.
8. Atlas-store path: when the store returns pace_identity data for both teams,
   combined_pace reflects the atlas values rather than the parquet.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loop.signal import AsOfContext, Hypothesis, Verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(
    decision_date: str = "2024-10-22",
    home: str = "OKC",
    away: str = "BOS",
    game_id: str = "0022400001",
    extra: Optional[Dict[str, Any]] = None,
) -> AsOfContext:
    return AsOfContext(
        decision_time=dt.datetime.strptime(decision_date, "%Y-%m-%d"),
        game_id=game_id,
        team=home,
        opp=away,
        game_date=decision_date,
        season="2024-25",
        is_home=True,
        scope="pregame",
        extra=extra or {},
    )


def _adv_df_for(home: str, away: str, game_date: str = "2024-10-01"):
    """Build a minimal team_advanced_stats-style DataFrame."""
    import pandas as pd
    return pd.DataFrame([
        {
            "team_tricode": home,
            "game_date": pd.Timestamp(game_date),
            "pace": 103.5,
            "off_rtg": 115.2,
        },
        {
            "team_tricode": away,
            "game_date": pd.Timestamp(game_date),
            "pace": 104.1,
            "off_rtg": 113.8,
        },
    ])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPaceMatchupTotal:

    def _import_signal(self):
        from signals.pace_matchup_total import PaceMatchupTotal
        return PaceMatchupTotal

    # ------------------------------------------------------------------ #
    # 1. Leak-safety: future-dated rows must be invisible                  #
    # ------------------------------------------------------------------ #
    def test_leak_safety_future_data_returns_none(self):
        """build() returns None when all adv_stats rows have game_date > decision_time."""
        import pandas as pd
        PaceMatchupTotal = self._import_signal()
        import signals.pace_matchup_total as mod

        # Only future rows: game_date 2024-11-01 > decision_time 2024-10-22
        future_df = _adv_df_for("OKC", "BOS", game_date="2024-11-01")
        ctx = _ctx(decision_date="2024-10-22", home="OKC", away="BOS")

        sig = PaceMatchupTotal(store=None)
        with patch.object(mod, "_load_adv", return_value=future_df):
            result = sig.build(ctx)

        assert result is None, (
            f"Leak-safety violation: build() returned {result!r} for future-only data"
        )

    # ------------------------------------------------------------------ #
    # 2. Value-sanity: valid rows produce reasonable combined_pace + total  #
    # ------------------------------------------------------------------ #
    def test_value_sanity_combined_pace_and_total(self):
        """combined_pace in [85, 115] and pace_adj_total in [180, 280]."""
        import pandas as pd
        PaceMatchupTotal = self._import_signal()
        import signals.pace_matchup_total as mod

        good_df = _adv_df_for("OKC", "BOS", game_date="2024-10-01")
        ctx = _ctx(decision_date="2024-10-22", home="OKC", away="BOS")

        sig = PaceMatchupTotal(store=None)
        with patch.object(mod, "_load_adv", return_value=good_df):
            result = sig.build(ctx)

        assert result is not None, "build() returned None for valid in-sample data"
        assert isinstance(result, dict)
        cp = result["combined_pace"]
        assert 85.0 <= cp <= 115.0, f"combined_pace={cp} outside [85, 115]"
        pat = result["pace_adj_total"]
        assert 180.0 <= pat <= 280.0, f"pace_adj_total={pat} outside [180, 280]"

    # ------------------------------------------------------------------ #
    # 3. Tier interaction dummy values                                     #
    # ------------------------------------------------------------------ #
    def test_tier_interaction_both_fast(self):
        """Both FAST teams: pace_tier_interaction == +1.0."""
        import pandas as pd
        PaceMatchupTotal = self._import_signal()
        import signals.pace_matchup_total as mod

        # pace 104 → FAST label for both
        df = pd.DataFrame([
            {"team_tricode": "OKC", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 104.0, "off_rtg": 115.0},
            {"team_tricode": "MEM", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 104.5, "off_rtg": 113.0},
        ])
        ctx = _ctx(decision_date="2024-10-22", home="OKC", away="MEM")
        sig = PaceMatchupTotal(store=None)
        with patch.object(mod, "_load_adv", return_value=df):
            result = sig.build(ctx)
        assert result is not None
        assert result["pace_tier_interaction"] == 1.0, (
            f"Expected +1.0 for fast-vs-fast, got {result['pace_tier_interaction']}"
        )

    def test_tier_interaction_both_slow(self):
        """Both SLOW teams: pace_tier_interaction == -1.0."""
        import pandas as pd
        PaceMatchupTotal = self._import_signal()
        import signals.pace_matchup_total as mod

        # pace 95 → SLOW label for both
        df = pd.DataFrame([
            {"team_tricode": "MIA", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 95.0, "off_rtg": 108.0},
            {"team_tricode": "CLE", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 96.0, "off_rtg": 109.0},
        ])
        ctx = _ctx(decision_date="2024-10-22", home="MIA", away="CLE")
        sig = PaceMatchupTotal(store=None)
        with patch.object(mod, "_load_adv", return_value=df):
            result = sig.build(ctx)
        assert result is not None
        assert result["pace_tier_interaction"] == -1.0, (
            f"Expected -1.0 for slow-vs-slow, got {result['pace_tier_interaction']}"
        )

    def test_tier_interaction_asymmetric(self):
        """Fast home vs slow away: pace_tier_interaction == 0.0."""
        import pandas as pd
        PaceMatchupTotal = self._import_signal()
        import signals.pace_matchup_total as mod

        df = pd.DataFrame([
            {"team_tricode": "OKC", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 104.0, "off_rtg": 115.0},  # FAST
            {"team_tricode": "MIA", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 95.0, "off_rtg": 108.0},   # SLOW
        ])
        ctx = _ctx(decision_date="2024-10-22", home="OKC", away="MIA")
        sig = PaceMatchupTotal(store=None)
        with patch.object(mod, "_load_adv", return_value=df):
            result = sig.build(ctx)
        assert result is not None
        assert result["pace_tier_interaction"] == 0.0, (
            f"Expected 0.0 for asymmetric matchup, got {result['pace_tier_interaction']}"
        )

    # ------------------------------------------------------------------ #
    # 4. Missing opp data: build() returns None                           #
    # ------------------------------------------------------------------ #
    def test_missing_opp_returns_none(self):
        """build() returns None when the opp team has no rows in the parquet."""
        import pandas as pd
        PaceMatchupTotal = self._import_signal()
        import signals.pace_matchup_total as mod

        # Only home team present
        df = pd.DataFrame([
            {"team_tricode": "OKC", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 104.0, "off_rtg": 115.0},
        ])
        ctx = _ctx(decision_date="2024-10-22", home="OKC", away="PHX")
        sig = PaceMatchupTotal(store=None)
        with patch.object(mod, "_load_adv", return_value=df):
            result = sig.build(ctx)
        assert result is None, f"Expected None when opp is missing; got {result!r}"

    # ------------------------------------------------------------------ #
    # 5. validate_output() passes for dict and for None                   #
    # ------------------------------------------------------------------ #
    def test_validate_output_valid_dict(self):
        PaceMatchupTotal = self._import_signal()
        sig = PaceMatchupTotal()
        good = {"combined_pace": 103.8, "pace_adj_total": 228.5,
                "pace_tier_interaction": 1.0}
        assert sig.validate_output(good) is True

    def test_validate_output_none(self):
        PaceMatchupTotal = self._import_signal()
        sig = PaceMatchupTotal()
        assert sig.validate_output(None) is True

    # ------------------------------------------------------------------ #
    # 6. hypothesis() metadata                                             #
    # ------------------------------------------------------------------ #
    def test_hypothesis_metadata(self):
        PaceMatchupTotal = self._import_signal()
        sig = PaceMatchupTotal()
        h = sig.hypothesis()
        assert isinstance(h, Hypothesis)
        assert h.name == "pace_matchup_total"
        assert h.target == "total"
        assert h.scope == "pregame"
        assert h.expected_verdict == Verdict.DEFER
        assert "pace_identity" in h.atlas_fields

    # ------------------------------------------------------------------ #
    # 7. feature_names() matches emits                                    #
    # ------------------------------------------------------------------ #
    def test_feature_names_matches_emits(self):
        PaceMatchupTotal = self._import_signal()
        sig = PaceMatchupTotal()
        expected = [f"pace_matchup_total__{k}" for k in sig.emits]
        assert sig.feature_names() == expected

    # ------------------------------------------------------------------ #
    # 8. Atlas-store path overrides parquet pace values                   #
    # ------------------------------------------------------------------ #
    def test_atlas_store_overrides_parquet(self):
        """When the store returns pace_identity data, atlas pace is used."""
        import pandas as pd
        PaceMatchupTotal = self._import_signal()
        import signals.pace_matchup_total as mod

        # Parquet has SLOW pace
        slow_df = pd.DataFrame([
            {"team_tricode": "OKC", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 95.0, "off_rtg": 108.0},
            {"team_tricode": "BOS", "game_date": pd.Timestamp("2024-10-01"),
             "pace": 96.0, "off_rtg": 109.0},
        ])

        # Atlas returns FAST pace
        atlas_home = {
            "tempo": {"pace_pg": 104.0, "pace_identity_label": "FAST"},
            "efficiency": {"off_rtg": 116.0},
        }
        atlas_away = {
            "tempo": {"pace_pg": 103.5, "pace_identity_label": "FAST"},
            "efficiency": {"off_rtg": 114.0},
        }

        mock_store = MagicMock()
        mock_store.read.side_effect = lambda entity, section, as_of: (
            atlas_home if entity == "OKC" else atlas_away
        )

        ctx = _ctx(decision_date="2024-10-22", home="OKC", away="BOS")
        sig = PaceMatchupTotal(store=mock_store)

        with patch.object(mod, "_load_adv", return_value=slow_df):
            result = sig.build(ctx)

        # Should produce combined_pace from atlas (103.75), NOT 95.5 from parquet
        assert result is not None
        assert result["combined_pace"] > 100.0, (
            f"Expected atlas pace (~103.75), got {result['combined_pace']}"
        )
        assert result["pace_tier_interaction"] == 1.0, (
            "Both FAST atlas labels should yield tier_interaction=+1.0"
        )

    # ------------------------------------------------------------------ #
    # 9. No ctx.team or no ctx.opp returns None                           #
    # ------------------------------------------------------------------ #
    def test_missing_team_context_returns_none(self):
        PaceMatchupTotal = self._import_signal()
        sig = PaceMatchupTotal(store=None)
        ctx = AsOfContext(
            decision_time=dt.datetime(2024, 10, 22),
            team=None,   # missing
            opp="BOS",
            scope="pregame",
        )
        result = sig.build(ctx)
        assert result is None
