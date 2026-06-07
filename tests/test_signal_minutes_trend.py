"""Tests for signals/minutes_trend.py.

Two mandatory assertion groups:
  1. Leak-safety  -- build() never reads rows with game_date >= ctx.decision_time.
  2. Value-sanity -- the returned slope is a float in a reasonable range, None
                     when data is insufficient, and the linear direction is correct.

Run with:
    NBA_OFFLINE=1 python -m pytest tests/test_signal_minutes_trend.py -v
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import List

import pandas as pd
import pytest

# ---- path setup (mirror CLAUDE.md: sys.path.insert(0,'.') at repo root) -----
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import signals.minutes_trend as mod
from signals.minutes_trend import (
    MinutesTrendSignal,
    _compute_l3_slope,
    _player_minutes_before,
    _MIN_GAMES,
    _SLOPE_CLIP_LO,
    _SLOPE_CLIP_HI,
)
from src.loop.signal import AsOfContext
from src.loop.store import PointInTimeStore


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_df(rows: List[dict]) -> pd.DataFrame:
    """Build a minimal player_adv_stats-shaped DataFrame from a list of dicts."""
    df = pd.DataFrame(rows, columns=["player_id", "game_date", "minutes"])
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    return df


def _ctx(decision_time: _dt.datetime, player_id: int = 1) -> AsOfContext:
    return AsOfContext(
        decision_time=decision_time,
        player_id=player_id,
        team="BOS",
        opp="MIL",
        scope="pregame",
    )


# ---------------------------------------------------------------------------
# 1. Leak-safety assertions
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that build() is strictly as-of the decision timestamp."""

    def test_future_rows_excluded_from_series(self) -> None:
        """_player_minutes_before must exclude rows on or after before_date."""
        df = _make_df([
            {"player_id": 1, "game_date": "2024-01-10", "minutes": 32.0},
            {"player_id": 1, "game_date": "2024-01-20", "minutes": 30.0},  # decision date
            {"player_id": 1, "game_date": "2024-01-25", "minutes": 28.0},  # future
            {"player_id": 1, "game_date": "2024-02-01", "minutes": 26.0},  # future
        ])
        series = _player_minutes_before(1, "2024-01-20", df=df)
        assert len(series) == 1, (
            f"Expected 1 row (before 2024-01-20), got {len(series)}: {series.tolist()}"
        )
        assert series.iloc[0] == 32.0

    def test_build_slope_ignores_future_minutes(self, monkeypatch) -> None:
        """build() slope must not be influenced by rows on/after decision_time.

        Strategy: past 3 games have high minutes (+35); future game has very low
        minutes (5).  If the future row leaked in, the slope would be sharply
        negative; without it, slope should be near zero or positive.
        """
        past_rows = [
            {"player_id": 99, "game_date": f"2024-01-0{i}", "minutes": 35.0}
            for i in range(1, 4)  # 3 games, all 35 min (slope=0)
        ]
        future_row = {"player_id": 99, "game_date": "2024-01-10", "minutes": 5.0}
        injected_df = _make_df(past_rows + [future_row])

        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        decision_time = _dt.datetime(2024, 1, 10)
        ctx = _ctx(decision_time, player_id=99)

        sig = MinutesTrendSignal(store=None)
        slope = sig.build(ctx)

        # Without the future row (5 min), slope over [35,35,35] = 0.0
        # If the future row leaked in, slope would be heavily negative
        assert slope is not None, "Expected a slope, got None"
        assert isinstance(slope, float)
        assert slope > -5.0, (
            f"Slope={slope} is unexpectedly negative; future row may have leaked."
        )

    def test_decision_date_row_itself_excluded(self, monkeypatch) -> None:
        """A row with game_date == as_of_iso() must be excluded (strict <)."""
        rows = [
            {"player_id": 7, "game_date": "2024-03-01", "minutes": 36.0},
            {"player_id": 7, "game_date": "2024-03-03", "minutes": 34.0},
            # The decision date row — must NOT be used
            {"player_id": 7, "game_date": "2024-03-05", "minutes": 10.0},
        ]
        injected_df = _make_df(rows)
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        decision_time = _dt.datetime(2024, 3, 5)
        ctx = _ctx(decision_time, player_id=7)
        sig = MinutesTrendSignal(store=None)
        slope = sig.build(ctx)

        # Only 2 rows qualify (< 2024-03-05) => fewer than _MIN_GAMES => None
        assert slope is None, (
            f"Expected None (only 2 qualifying rows), got slope={slope}.  "
            "The decision-date row may have been included."
        )


# ---------------------------------------------------------------------------
# 2. Value-sanity assertions
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Verify the returned slope value is correct and well-typed."""

    def test_returns_none_for_no_player_id(self) -> None:
        """build() returns None when ctx.player_id is not set."""
        ctx = AsOfContext(
            decision_time=_dt.datetime(2024, 2, 1),
            player_id=None,
            scope="pregame",
        )
        sig = MinutesTrendSignal(store=None)
        assert sig.build(ctx) is None

    def test_returns_none_when_fewer_than_3_games(self, monkeypatch) -> None:
        """build() returns None when fewer than _MIN_GAMES prior rows exist."""
        injected_df = _make_df([
            {"player_id": 42, "game_date": "2024-01-01", "minutes": 30.0},
            {"player_id": 42, "game_date": "2024-01-03", "minutes": 28.0},
        ])
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=42)
        sig = MinutesTrendSignal(store=None)
        result = sig.build(ctx)
        assert result is None, f"Expected None with only 2 games, got {result}"

    def test_positive_slope_for_rising_trend(self, monkeypatch) -> None:
        """Rising minutes across 3 games should yield a positive slope."""
        # minutes: 20 -> 25 -> 30 → slope = +5.0
        injected_df = _make_df([
            {"player_id": 5, "game_date": "2024-01-01", "minutes": 20.0},
            {"player_id": 5, "game_date": "2024-01-03", "minutes": 25.0},
            {"player_id": 5, "game_date": "2024-01-05", "minutes": 30.0},
        ])
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=5)
        sig = MinutesTrendSignal(store=None)
        slope = sig.build(ctx)

        assert slope is not None
        assert isinstance(slope, float)
        assert slope > 0.0, f"Expected positive slope for rising trend, got {slope}"
        assert abs(slope - 5.0) < 0.01, f"Expected slope ~5.0, got {slope}"

    def test_negative_slope_for_declining_trend(self, monkeypatch) -> None:
        """Declining minutes across 3 games should yield a negative slope."""
        # minutes: 36 -> 30 -> 24 → slope = -6.0
        injected_df = _make_df([
            {"player_id": 6, "game_date": "2024-01-01", "minutes": 36.0},
            {"player_id": 6, "game_date": "2024-01-03", "minutes": 30.0},
            {"player_id": 6, "game_date": "2024-01-05", "minutes": 24.0},
        ])
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=6)
        sig = MinutesTrendSignal(store=None)
        slope = sig.build(ctx)

        assert slope is not None
        assert isinstance(slope, float)
        assert slope < 0.0, f"Expected negative slope for declining trend, got {slope}"
        assert abs(slope - (-6.0)) < 0.01, f"Expected slope ~-6.0, got {slope}"

    def test_slope_within_clip_bounds(self, monkeypatch) -> None:
        """An extreme minute shift is clipped to [_SLOPE_CLIP_LO, _SLOPE_CLIP_HI]."""
        # minutes: 0 -> 0 -> 48 → raw slope = +24, clipped to _SLOPE_CLIP_HI
        injected_df = _make_df([
            {"player_id": 8, "game_date": "2024-01-01", "minutes": 0.0},
            {"player_id": 8, "game_date": "2024-01-03", "minutes": 0.0},
            {"player_id": 8, "game_date": "2024-01-05", "minutes": 48.0},
        ])
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=8)
        sig = MinutesTrendSignal(store=None)
        slope = sig.build(ctx)

        assert slope is not None
        assert isinstance(slope, float)
        assert _SLOPE_CLIP_LO <= slope <= _SLOPE_CLIP_HI, (
            f"Slope {slope} outside clip bounds [{_SLOPE_CLIP_LO}, {_SLOPE_CLIP_HI}]"
        )
        assert slope == _SLOPE_CLIP_HI, (
            f"Expected slope to be clipped to {_SLOPE_CLIP_HI}, got {slope}"
        )

    def test_validate_output_passes(self, monkeypatch) -> None:
        """validate_output() accepts the returned float."""
        injected_df = _make_df([
            {"player_id": 3, "game_date": "2024-01-01", "minutes": 32.0},
            {"player_id": 3, "game_date": "2024-01-03", "minutes": 34.0},
            {"player_id": 3, "game_date": "2024-01-05", "minutes": 33.0},
        ])
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=3)
        sig = MinutesTrendSignal(store=None)
        slope = sig.build(ctx)

        assert sig.validate_output(slope), (
            f"validate_output failed for slope={slope}"
        )

    def test_uses_only_last_3_of_many_games(self, monkeypatch) -> None:
        """When a player has many prior games, only the last 3 drive the slope."""
        # Games 1-7 have flat 30 min; last 3 are 30->33->36 => slope +3.0
        rows = [
            {"player_id": 11, "game_date": f"2024-01-{i:02d}", "minutes": 30.0}
            for i in range(1, 8)
        ] + [
            {"player_id": 11, "game_date": "2024-01-08", "minutes": 30.0},
            {"player_id": 11, "game_date": "2024-01-09", "minutes": 33.0},
            {"player_id": 11, "game_date": "2024-01-10", "minutes": 36.0},
        ]
        injected_df = _make_df(rows)
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=11)
        sig = MinutesTrendSignal(store=None)
        slope = sig.build(ctx)

        assert slope is not None
        assert slope > 0.0, f"Expected positive slope from last 3 games, got {slope}"
        assert abs(slope - 3.0) < 0.01, f"Expected slope ~3.0, got {slope}"

    def test_store_reinforcement_degrades_gracefully(self, tmp_path: Path,
                                                      monkeypatch) -> None:
        """build() works correctly when store is bound but has no role_profile."""
        injected_df = _make_df([
            {"player_id": 20, "game_date": "2024-01-01", "minutes": 28.0},
            {"player_id": 20, "game_date": "2024-01-03", "minutes": 29.0},
            {"player_id": 20, "game_date": "2024-01-05", "minutes": 30.0},
        ])
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=20)
        sig = MinutesTrendSignal(store=store)
        slope = sig.build(ctx)

        # slope = 1.0 (30-28 over 2 steps)
        assert slope is not None
        assert isinstance(slope, float)
        assert slope > 0.0

    def test_store_reinforcement_reads_role_profile(self, tmp_path: Path,
                                                    monkeypatch) -> None:
        """build() succeeds when store has a role_profile entry (reinforcement path)."""
        injected_df = _make_df([
            {"player_id": 21, "game_date": "2024-01-01", "minutes": 32.0},
            {"player_id": 21, "game_date": "2024-01-03", "minutes": 34.0},
            {"player_id": 21, "game_date": "2024-01-05", "minutes": 36.0},
        ])
        monkeypatch.setattr(mod, "_ADV_DF", injected_df)

        store = PointInTimeStore(store_dir=tmp_path / "store2", autoload=False)
        store.write_atlas(
            "player", 21, "role_profile", "2024-01-01",
            {"avg_minutes": 33.0, "archetype": "rotation_starter", "n_games": 50},
            {"source": "arm_b_build", "n": 50, "confidence": "high",
             "as_of": "2024-01-01"},
        )

        ctx = _ctx(_dt.datetime(2024, 2, 1), player_id=21)
        sig = MinutesTrendSignal(store=store)
        slope = sig.build(ctx)

        # Slope is still the raw L3 slope; store just provides context
        assert slope is not None
        assert isinstance(slope, float)
        # Slope of [32, 34, 36] = +2.0
        assert abs(slope - 2.0) < 0.01, f"Expected slope ~2.0, got {slope}"

    def test_hypothesis_metadata(self) -> None:
        """hypothesis() returns a well-formed Hypothesis with correct fields."""
        sig = MinutesTrendSignal(store=None)
        h = sig.hypothesis()

        assert h.name == "minutes_trend"
        assert h.target == "minutes"
        assert h.scope == "pregame"
        assert h.source == "seed"
        assert "role_profile" in h.atlas_fields
        assert h.expected_verdict == "SHIP"
        assert h.priority == "P2"
        assert len(h.statement) > 30
        assert len(h.rationale) > 30

    def test_feature_names(self) -> None:
        """feature_names() returns ['minutes_trend'] (scalar signal)."""
        sig = MinutesTrendSignal(store=None)
        assert sig.feature_names() == ["minutes_trend"]

    def test_compute_l3_slope_insufficient_data(self) -> None:
        """_compute_l3_slope returns None for fewer than _MIN_GAMES entries."""
        import pandas as pd
        assert _compute_l3_slope(pd.Series([])) is None
        assert _compute_l3_slope(pd.Series([30.0])) is None
        assert _compute_l3_slope(pd.Series([30.0, 32.0])) is None

    def test_compute_l3_slope_exact_3_games(self) -> None:
        """_compute_l3_slope returns a float for exactly 3 entries."""
        import pandas as pd
        slope = _compute_l3_slope(pd.Series([20.0, 25.0, 30.0]))
        assert slope is not None
        assert isinstance(slope, float)
        assert abs(slope - 5.0) < 0.01
