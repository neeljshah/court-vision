"""Tests for signals/opponent_rate_allowed.py.

Two mandatory assertions:
  1. Leak-safety — build() never uses game rows on or after ctx.decision_time.
  2. Value sanity — the returned dict has the correct keys, all finite floats,
     and the direction of known strong defenses (OKC/BOS) is captured correctly
     in the positional-defense sub-features.

Run with:
    NBA_OFFLINE=1 python -m pytest tests/test_signal_opponent_rate_allowed.py -v
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

# ---- path setup (mirror CLAUDE.md: sys.path.insert(0,'.') at repo root) ----
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signals.opponent_rate_allowed import (
    OpponentRateAllowedSignal,
    _rolling_opp_stats,
    _positional_defense_stats,
    _LEAGUE_AVG_DEF_RTG,
    _LEAGUE_AVG_TOV_RATIO,
)
from src.loop.signal import AsOfContext
from src.loop.store import PointInTimeStore


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_adv_row(game_date: str, team_tricode: str,
                  def_rtg: float = 112.0, tov_ratio: float = 13.5) -> dict:
    """Build a fake team_advanced_stats row."""
    return {
        "game_id": f"test_{game_date}_{team_tricode}",
        "game_date": game_date,
        "team_tricode": team_tricode,
        "def_rtg": def_rtg,
        "tov_ratio": tov_ratio,
    }


def _make_ctx(opp: str, decision_date: str,
              scope: str = "pregame") -> AsOfContext:
    year, month, day = [int(x) for x in decision_date.split("-")]
    return AsOfContext(
        decision_time=_dt.datetime(year, month, day),
        team="DAL",
        opp=opp,
        scope=scope,
        game_date=decision_date,
    )


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY ASSERTION
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must not incorporate game rows on or after ctx.decision_time."""

    def test_no_future_rows_used(self, monkeypatch) -> None:
        """Rows with game_date >= decision_time must be excluded from rolling stats."""
        import signals.opponent_rate_allowed as mod

        # Construct a fake DataFrame: 5 past games (low def_rtg=90) +
        # 5 future games (high def_rtg=130). If future rows leaked in,
        # the rolling mean would be significantly above 90.
        past_rows = [
            _make_adv_row(f"2024-01-0{i}", "BOS", def_rtg=90.0)
            for i in range(1, 6)  # 2024-01-01 .. 2024-01-05
        ]
        future_rows = [
            _make_adv_row(f"2024-02-0{i}", "BOS", def_rtg=130.0)
            for i in range(1, 6)  # 2024-02-01 .. 2024-02-05 (after decision_time)
        ]
        fake_df = pd.DataFrame(past_rows + future_rows)
        fake_df["game_date"] = fake_df["game_date"].astype(str)

        monkeypatch.setattr(mod, "_adv_df", fake_df)

        # Decision date: 2024-01-10 → only past_rows qualify
        before_date = "2024-01-10"
        result = _rolling_opp_stats("BOS", before_date)

        opp_def = result["opp_def_rtg_l10"]
        assert abs(opp_def - 90.0) < 0.1, (
            f"Future rows appear to have leaked: opp_def_rtg_l10={opp_def:.2f}, "
            f"expected ~90.0"
        )

    def test_build_uses_as_of_iso(self, monkeypatch) -> None:
        """Signal.build() must read game rows strictly before decision_time."""
        import signals.opponent_rate_allowed as mod

        past_rows = [
            _make_adv_row(f"2024-01-{i:02d}", "OKC", def_rtg=95.0, tov_ratio=12.0)
            for i in range(1, 8)
        ]
        future_rows = [
            _make_adv_row(f"2024-03-{i:02d}", "OKC", def_rtg=125.0, tov_ratio=20.0)
            for i in range(1, 8)
        ]
        fake_df = pd.DataFrame(past_rows + future_rows)
        fake_df["game_date"] = fake_df["game_date"].astype(str)
        monkeypatch.setattr(mod, "_adv_df", fake_df)

        # No positional defense parquet needed — monkeypatch to empty
        empty_pos = pd.DataFrame(columns=[
            "team_abbreviation", "perim_3pt_d_fga",
            "perim_3pt_pct_plusminus", "rim_lt6_pct_plusminus"
        ])
        monkeypatch.setattr(mod, "_pos_def_df", empty_pos)

        ctx = _make_ctx("OKC", "2024-02-01")
        sig = OpponentRateAllowedSignal(store=None)
        result = sig.build(ctx)

        assert result is not None
        # Rolling mean of past_rows (def_rtg=95) should be ~95, not 125
        assert result["opp_def_rtg_l10"] < 110.0, (
            f"Future rows may have leaked: opp_def_rtg_l10={result['opp_def_rtg_l10']:.2f}"
        )
        assert result["opp_def_rtg_l10"] > 80.0, "Sanity: should be near 95"


# ---------------------------------------------------------------------------
# 2. VALUE-SANITY ASSERTIONS
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Verify the returned dict structure, key presence, and directional correctness."""

    def test_returns_dict_with_all_keys(self, monkeypatch) -> None:
        """build() returns a dict with all 5 expected sub-feature keys."""
        import signals.opponent_rate_allowed as mod

        rows = [_make_adv_row(f"2024-01-{i:02d}", "LAL") for i in range(1, 6)]
        fake_df = pd.DataFrame(rows)
        fake_df["game_date"] = fake_df["game_date"].astype(str)
        monkeypatch.setattr(mod, "_adv_df", fake_df)

        empty_pos = pd.DataFrame(columns=[
            "team_abbreviation", "perim_3pt_d_fga",
            "perim_3pt_pct_plusminus", "rim_lt6_pct_plusminus"
        ])
        monkeypatch.setattr(mod, "_pos_def_df", empty_pos)

        ctx = _make_ctx("LAL", "2024-02-01")
        sig = OpponentRateAllowedSignal(store=None)
        result = sig.build(ctx)

        expected_keys = {
            "opp_def_rtg_l10",
            "opp_tov_ratio_l10",
            "opp_3pt_pct_plusminus",
            "opp_rim_pct_plusminus",
            "opp_3pt_volume_per_game",
        }
        assert result is not None, "Expected dict, got None"
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert set(result.keys()) == expected_keys, (
            f"Key mismatch: {set(result.keys())} != {expected_keys}"
        )
        # All values must be finite floats
        for k, v in result.items():
            assert isinstance(v, float), f"Key {k}: expected float, got {type(v)}"
            assert v == v, f"Key {k}: got NaN"  # NaN != NaN

    def test_returns_none_when_opp_missing(self) -> None:
        """build() returns None when ctx.opp is None (no opponent context)."""
        ctx = AsOfContext(
            decision_time=_dt.datetime(2024, 2, 1),
            team="DAL",
            opp=None,
            scope="pregame",
        )
        sig = OpponentRateAllowedSignal(store=None)
        result = sig.build(ctx)
        assert result is None, f"Expected None for opp=None, got {result}"

    def test_validate_output_passes(self, monkeypatch) -> None:
        """validate_output() returns True for the emitted dict."""
        import signals.opponent_rate_allowed as mod

        rows = [_make_adv_row(f"2024-01-{i:02d}", "MIA") for i in range(1, 6)]
        fake_df = pd.DataFrame(rows)
        fake_df["game_date"] = fake_df["game_date"].astype(str)
        monkeypatch.setattr(mod, "_adv_df", fake_df)

        empty_pos = pd.DataFrame(columns=[
            "team_abbreviation", "perim_3pt_d_fga",
            "perim_3pt_pct_plusminus", "rim_lt6_pct_plusminus"
        ])
        monkeypatch.setattr(mod, "_pos_def_df", empty_pos)

        ctx = _make_ctx("MIA", "2024-02-01")
        sig = OpponentRateAllowedSignal(store=None)
        result = sig.build(ctx)

        assert sig.validate_output(result), f"validate_output failed for: {result}"

    def test_positional_defense_direction_okc(self, monkeypatch) -> None:
        """OKC (elite rim defense) should have strongly negative rim_pct_plusminus.

        Verified from data/team_positional_defense_2025-26.parquet:
        OKC rim_lt6_pct_plusminus = -0.055 (league-best).
        """
        import signals.opponent_rate_allowed as mod

        # Fake adv stats for OKC (5 games needed)
        rows = [_make_adv_row(f"2024-01-{i:02d}", "OKC") for i in range(1, 6)]
        monkeypatch.setattr(mod, "_adv_df", pd.DataFrame(rows))

        # Fake positional defense with real OKC values
        fake_pos = pd.DataFrame([{
            "team_abbreviation": "OKC",
            "perim_3pt_d_fga": 38.87,
            "perim_3pt_pct_plusminus": -0.006,   # slightly below league avg
            "rim_lt6_pct_plusminus": -0.055,      # league-best rim defense
        }])
        monkeypatch.setattr(mod, "_pos_def_df", fake_pos)

        ctx = _make_ctx("OKC", "2024-02-01")
        sig = OpponentRateAllowedSignal(store=None)
        result = sig.build(ctx)

        assert result is not None
        assert result["opp_rim_pct_plusminus"] < 0.0, (
            f"OKC rim defense should be negative (elite), got "
            f"{result['opp_rim_pct_plusminus']:.4f}"
        )
        assert result["opp_rim_pct_plusminus"] < -0.04, (
            f"OKC rim_pct_plusminus should be ~-0.055, got "
            f"{result['opp_rim_pct_plusminus']:.4f}"
        )

    def test_league_avg_fallback_when_no_history(self, monkeypatch) -> None:
        """When opp has no historical games, rolling stats fall back to league avg."""
        import signals.opponent_rate_allowed as mod

        # Empty DataFrame — no rows for any team
        monkeypatch.setattr(mod, "_adv_df", pd.DataFrame(columns=[
            "game_id", "game_date", "team_tricode", "def_rtg", "tov_ratio"
        ]))

        empty_pos = pd.DataFrame(columns=[
            "team_abbreviation", "perim_3pt_d_fga",
            "perim_3pt_pct_plusminus", "rim_lt6_pct_plusminus"
        ])
        monkeypatch.setattr(mod, "_pos_def_df", empty_pos)

        ctx = _make_ctx("NOP", "2024-02-01")
        sig = OpponentRateAllowedSignal(store=None)
        result = sig.build(ctx)

        assert result is not None
        assert abs(result["opp_def_rtg_l10"] - _LEAGUE_AVG_DEF_RTG) < 0.1, (
            f"Expected league avg def_rtg={_LEAGUE_AVG_DEF_RTG}, "
            f"got {result['opp_def_rtg_l10']:.2f}"
        )
        assert abs(result["opp_tov_ratio_l10"] - _LEAGUE_AVG_TOV_RATIO) < 0.1

    def test_store_atlas_read_used_over_parquet(self, tmp_path, monkeypatch) -> None:
        """When the store has an atlas entry, positional defense reads from it."""
        import signals.opponent_rate_allowed as mod

        rows = [_make_adv_row(f"2024-01-{i:02d}", "GSW") for i in range(1, 6)]
        monkeypatch.setattr(mod, "_adv_df", pd.DataFrame(rows))

        # Positional defense parquet says 0.0 for GSW (should be overridden)
        fake_pos = pd.DataFrame([{
            "team_abbreviation": "GSW",
            "perim_3pt_d_fga": 0.0,
            "perim_3pt_pct_plusminus": 0.0,
            "rim_lt6_pct_plusminus": 0.0,
        }])
        monkeypatch.setattr(mod, "_pos_def_df", fake_pos)

        # Write a store atlas entry for GSW with a known rim value (-0.020)
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        store.write_atlas(
            "team", "GSW", "team_positional_defense", "2024-01-01",
            {
                "perim_3pt_pct_plusminus": 0.005,
                "rim_lt6_pct_plusminus": -0.020,
                "perim_3pt_d_fga": 36.5,
            },
            {"source": "test_atlas", "n": 30, "confidence": "high",
             "as_of": "2024-01-01"},
        )

        ctx = _make_ctx("GSW", "2024-02-01")
        sig = OpponentRateAllowedSignal(store=store)
        result = sig.build(ctx)

        assert result is not None
        # Should read from store, not parquet (parquet would give 0.0)
        assert abs(result["opp_rim_pct_plusminus"] - (-0.020)) < 1e-6, (
            f"Expected atlas rim value -0.020, got {result['opp_rim_pct_plusminus']:.4f}"
        )
        assert abs(result["opp_3pt_volume_per_game"] - 36.5) < 1e-6

    def test_hypothesis_metadata(self) -> None:
        """hypothesis() returns a well-formed Hypothesis with correct metadata."""
        sig = OpponentRateAllowedSignal(store=None)
        h = sig.hypothesis()

        assert h.name == "opponent_rate_allowed"
        assert h.target == "fg3m"
        assert h.scope == "pregame"
        assert h.source == "seed"
        assert "team_positional_defense" in h.atlas_fields
        assert h.expected_verdict == "DEFER"
        assert len(h.statement) > 20
        assert len(h.rationale) > 20

    def test_feature_names(self) -> None:
        """feature_names() returns the 5 namespaced sub-feature names."""
        sig = OpponentRateAllowedSignal(store=None)
        names = sig.feature_names()
        expected = [
            "opponent_rate_allowed__opp_def_rtg_l10",
            "opponent_rate_allowed__opp_tov_ratio_l10",
            "opponent_rate_allowed__opp_3pt_pct_plusminus",
            "opponent_rate_allowed__opp_rim_pct_plusminus",
            "opponent_rate_allowed__opp_3pt_volume_per_game",
        ]
        assert names == expected, f"feature_names mismatch: {names}"
