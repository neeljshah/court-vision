"""tests/test_signal_comeback_pace.py — Unit tests for ComebackPaceSignal.

Two MANDATORY assertions (per spec):
  1. LEAK-SAFETY  — build() must never use information stamped after
     ctx.decision_time.  Verified by writing a future-dated team_pace atlas
     record into the store and confirming the signal returns either None or a
     value consistent with the league-average fallback, never the future value.
  2. VALUE-SANITY — sub-feature values must be in the expected range and sign;
     comeback_mode_flag is exactly 0 or 1; score_deficit_abs is non-negative;
     pace_deficit_interaction >= 0.

Additional tests:
  * Live snapshot path with comeback in Q3 → comeback_mode_flag=1.0.
  * Live snapshot with small deficit (<8 pts) → comeback_mode_flag=0.0.
  * No live + no game_id → None.
  * Parquet path (mocked midquarter) produces correct flag and pace interaction.
  * FT trips lookup from pbp_microstructure mock.
  * hypothesis() returns a well-formed Hypothesis object.
  * feature_names() matches emits.
  * validate_output() accepts valid dict, rejects garbage.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pandas as pd
import pytest

from src.loop.signal import AsOfContext, Hypothesis, Verdict
from src.loop.store import PointInTimeStore


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_signal(store=None):
    """Import and instantiate ComebackPaceSignal."""
    from signals.comeback_pace import ComebackPaceSignal
    return ComebackPaceSignal(store=store)


def _ctx(
    *,
    decision_time: _dt.datetime,
    game_id: Optional[str] = None,
    team: Optional[str] = None,
    opp: Optional[str] = None,
    snapshot: Optional[str] = None,
    live: Optional[Dict[str, Any]] = None,
) -> AsOfContext:
    return AsOfContext(
        decision_time=decision_time,
        game_id=game_id,
        team=team,
        opp=opp,
        snapshot=snapshot,
        scope="live",
        live=live,
    )


def _live_snap(
    home_score: float,
    away_score: float,
    period: int = 3,
    clock: str = "5:00",
    home_team: str = "LAL",
    away_team: str = "BOS",
) -> Dict[str, Any]:
    """Build a minimal live snapshot dict."""
    return {
        "home_team": home_team,
        "away_team": away_team,
        "period": period,
        "clock": clock,
        "home_score": home_score,
        "away_score": away_score,
        "players": [],
    }


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertions
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must not read atlas records stamped after decision_time."""

    def test_future_atlas_record_not_visible(self, tmp_path: Path) -> None:
        """A team_pace record written with as_of=FUTURE must not affect build().

        Strategy: write a future-dated team_pace record with a wildly wrong
        pace (999.0).  Build the signal with decision_time=TODAY (before that
        record).  The signal should use the league-average fallback (100.5)
        in the interaction term, NOT the future 999.0 value.

        We confirm by checking that pace_deficit_interaction is plausible for
        a comeback situation (< 200 poss/48, certainly not ~999).
        """
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        today = _dt.datetime(2025, 3, 1, 21, 0, 0)
        future_iso = "2025-03-10"  # 9 days in the future

        # Write a pathologically large future pace that would betray a leak.
        store.write_atlas(
            "team", "LAL", "team_pace", future_iso,
            {"pace": 999.0, "value": 999.0},
            {"source": "test", "n": 100, "confidence": "high"},
        )

        signal = _make_signal(store=store)
        # Build in Q4 with a large deficit so comeback_mode_flag=1.
        snap = _live_snap(
            home_score=80.0, away_score=95.0,   # home trailing by 15
            period=4, clock="4:00",
        )
        ctx = _ctx(decision_time=today, live=snap, team="LAL", opp="BOS")
        result = signal.build(ctx)

        assert result is not None, "Should compute a result for a valid live snapshot"
        interaction = result["pace_deficit_interaction"]
        # comeback_mode_flag=1.0; pace from live score (~pts-based proxy) should be
        # ~100 range.  If the future 999.0 leaked, interaction would be >> 200.
        assert interaction < 300.0, (
            f"pace_deficit_interaction={interaction:.1f} is suspiciously large; "
            f"future atlas record (pace=999) may have leaked"
        )

    def test_past_atlas_record_is_usable(self, tmp_path: Path) -> None:
        """A team_pace record stamped BEFORE decision_time IS read (not a false-pos)."""
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        yesterday = _dt.datetime(2025, 2, 28, 12, 0, 0)
        today = _dt.datetime(2025, 3, 1, 21, 0, 0)

        store.write_atlas(
            "team", "LAL", "team_pace", yesterday.date().isoformat(),
            {"pace": 108.0, "value": 108.0},
            {"source": "test", "n": 40, "confidence": "high"},
        )

        signal = _make_signal(store=store)
        # Call _team_pace_prior directly to verify the past record is read.
        prior = signal._team_pace_prior("LAL", "BOS", today)
        # Should blend 108.0 (LAL) + 100.5 (BOS fallback) = 104.25
        assert 100.0 < prior < 110.0, (
            f"Expected prior in [100, 110]; got {prior:.2f}. "
            "Past atlas record may not have been read."
        )

    def test_no_future_bleed_on_build_returns_none_or_sane(
        self, tmp_path: Path
    ) -> None:
        """Without a live snapshot or game_id the signal returns None safely."""
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        future_iso = "2030-01-01"
        store.write_atlas(
            "team", "GSW", "team_pace", future_iso,
            {"pace": 999.0},
            {"source": "test", "n": 10, "confidence": "high"},
        )
        signal = _make_signal(store=store)
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 3, 1, 21, 0),
            live=None, game_id=None,
        )
        result = signal.build(ctx)
        assert result is None, "No live + no game_id must return None"


# ---------------------------------------------------------------------------
# 2. VALUE-SANITY assertions
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Sub-features must be in expected ranges and carry correct signs/flags."""

    def test_comeback_mode_active_q4_large_deficit(self) -> None:
        """Trailing by 15 in Q4 → comeback_mode_flag=1.0, deficit_abs=15."""
        signal = _make_signal()
        snap = _live_snap(
            home_score=80.0, away_score=95.0, period=4, clock="3:00"
        )
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 3, 15, 21, 30),
            live=snap,
        )
        result = signal.build(ctx)

        assert result is not None, "Expected dict for valid Q4 comeback snapshot"
        assert isinstance(result, dict)
        assert result["score_deficit_abs"] == pytest.approx(15.0, abs=0.1)
        assert result["comeback_mode_flag"] == pytest.approx(1.0, abs=0.01)
        assert result["pace_deficit_interaction"] > 0.0, (
            "Interaction must be positive when comeback_mode_flag=1"
        )

    def test_small_deficit_q3_no_comeback_flag(self) -> None:
        """Trailing by 5 in Q3 → comeback_mode_flag=0.0 (below threshold)."""
        signal = _make_signal()
        snap = _live_snap(
            home_score=55.0, away_score=60.0, period=3, clock="6:00"
        )
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 3, 15, 21, 0),
            live=snap,
        )
        result = signal.build(ctx)

        assert result is not None
        assert result["comeback_mode_flag"] == pytest.approx(0.0, abs=0.01), (
            f"Deficit=5 < threshold=8 → flag must be 0; got {result['comeback_mode_flag']}"
        )
        assert result["pace_deficit_interaction"] == pytest.approx(0.0, abs=0.01), (
            "Interaction must be 0 when comeback_mode_flag=0"
        )

    def test_q2_large_deficit_no_comeback_flag(self) -> None:
        """Even a huge deficit in Q2 does not trigger comeback_mode (period < 3)."""
        signal = _make_signal()
        snap = _live_snap(
            home_score=30.0, away_score=55.0, period=2, clock="2:00"
        )
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 3, 15, 20, 45),
            live=snap,
        )
        result = signal.build(ctx)

        assert result is not None
        assert result["comeback_mode_flag"] == pytest.approx(0.0, abs=0.01), (
            "Period=2 → comeback_mode_flag must be 0 regardless of deficit"
        )

    def test_score_deficit_abs_is_non_negative(self) -> None:
        """score_deficit_abs must be >= 0 regardless of which team leads."""
        signal = _make_signal()
        # Home leading by 20 in Q4.
        snap = _live_snap(
            home_score=100.0, away_score=80.0, period=4, clock="2:00"
        )
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 3, 15, 22, 0),
            live=snap,
        )
        result = signal.build(ctx)
        assert result is not None
        assert result["score_deficit_abs"] >= 0.0, (
            f"score_deficit_abs must be non-negative; got {result['score_deficit_abs']}"
        )
        assert result["score_deficit_abs"] == pytest.approx(20.0, abs=0.1)

    def test_no_live_no_game_id_returns_none(self) -> None:
        """Without live snapshot or game_id the signal must return None."""
        signal = _make_signal()
        ctx = _ctx(decision_time=_dt.datetime(2025, 1, 10, 18, 0))
        assert signal.build(ctx) is None

    def test_parquet_path_mocked_comeback(self) -> None:
        """Parquet path: mocked midquarter row triggers comeback flag correctly."""
        from signals.comeback_pace import _COMEBACK_THRESHOLD

        signal = _make_signal()
        game_id = "0022300999"
        game_date = _dt.datetime(2025, 1, 5, 0, 0)
        decision_time = _dt.datetime(2025, 1, 6, 18, 0)

        mq_df = pd.DataFrame([{
            "game_id": game_id,
            "game_date": pd.Timestamp(game_date),
            "season": "2024-25",
            "home_team_id": "1610612747",
            "score_margin": 12.0,          # home leading by 12 → away trailing
            "total_pts": 180.0,
            "pace_so_far": 105.0,
            "pregame_win_prob": 0.55,
            "last_q_margin": 10.0,
            "q4_run_so_far": 8.0,
            "q4_pts_so_far_home": 15.0,
            "q4_pts_so_far_away": 7.0,
            "q4_lead_changes_so_far": 0.0,
            "q4_to_so_far_home": 1.0,
            "q4_to_so_far_away": 2.0,
            "home_team_won": 1,
        }])

        with patch("signals.comeback_pace._load_midquarter", return_value=mq_df), \
             patch("signals.comeback_pace._load_pbp_micro", return_value=None):
            ctx = _ctx(
                decision_time=decision_time,
                game_id=game_id,
                snapshot="endQ4",
            )
            result = signal.build(ctx)

        assert result is not None, "Mocked parquet path should produce a result"
        # deficit=12 >= 8 AND period=4 → comeback_mode_flag=1.0
        assert result["comeback_mode_flag"] == pytest.approx(1.0, abs=0.01)
        assert result["score_deficit_abs"] == pytest.approx(12.0, abs=0.1)
        # interaction = 1.0 × 105.0 = 105.0
        assert result["pace_deficit_interaction"] == pytest.approx(105.0, abs=1.0)

    def test_trailing_ft_trips_from_pbp_micro(self) -> None:
        """_trailing_ft_trips returns away team's FT trips when home is leading."""
        signal = _make_signal()
        micro_df = pd.DataFrame([{
            "game_id": "TESTGAME",
            "period": 3,
            "home_ft_trips_last_quarter": 4.0,
            "away_ft_trips_last_quarter": 7.0,
            "home_run_last_240s": 6.0,
            "away_run_last_240s": 9.0,
        }])
        with patch("signals.comeback_pace._load_pbp_micro", return_value=micro_df):
            # home_is_trailing=False → reading away col is wrong; home leading → away trailing
            # wait: home_is_trailing=True means home is behind
            # here we test that when home is trailing, we return HOME FT trips
            ft_home_trailing = signal._trailing_ft_trips(
                "TESTGAME", period=4, home_is_trailing=True
            )
            ft_away_trailing = signal._trailing_ft_trips(
                "TESTGAME", period=4, home_is_trailing=False
            )

        assert ft_home_trailing == pytest.approx(4.0, abs=0.01), (
            "Home trailing → home_ft_trips_last_quarter expected"
        )
        assert ft_away_trailing == pytest.approx(7.0, abs=0.01), (
            "Away trailing → away_ft_trips_last_quarter expected"
        )

    def test_no_game_id_ft_trips_zero(self) -> None:
        """_trailing_ft_trips returns 0.0 when game_id is None."""
        signal = _make_signal()
        assert signal._trailing_ft_trips(None, 3, True) == 0.0


# ---------------------------------------------------------------------------
# 3. Hypothesis + metadata checks
# ---------------------------------------------------------------------------

class TestHypothesis:
    """hypothesis() and feature metadata must be consistent with class attrs."""

    def test_hypothesis_fields(self) -> None:
        signal = _make_signal()
        h = signal.hypothesis()

        assert isinstance(h, Hypothesis), f"Expected Hypothesis, got {type(h)}"
        assert h.name == "comeback_pace"
        assert h.target == "total"
        assert h.scope == "live"
        assert h.source == "seed"
        assert "team_pace" in h.atlas_fields
        assert len(h.statement) > 30, "Statement must be non-trivial"
        assert len(h.rationale) > 30, "Rationale must be non-trivial"

    def test_feature_names(self) -> None:
        signal = _make_signal()
        names = signal.feature_names()
        expected = [
            "comeback_pace__score_deficit_abs",
            "comeback_pace__comeback_mode_flag",
            "comeback_pace__trailing_ft_trips_rate",
            "comeback_pace__pace_deficit_interaction",
        ]
        assert names == expected, f"feature_names() mismatch: {names}"

    def test_class_attributes(self) -> None:
        from signals.comeback_pace import ComebackPaceSignal
        assert ComebackPaceSignal.name == "comeback_pace"
        assert ComebackPaceSignal.target == "total"
        assert ComebackPaceSignal.scope == "live"
        assert "team_pace" in ComebackPaceSignal.reads_atlas
        assert len(ComebackPaceSignal.emits) == 4

    def test_validate_output_accepts_valid_dict(self) -> None:
        signal = _make_signal()
        valid = {
            "score_deficit_abs": 12.0,
            "comeback_mode_flag": 1.0,
            "trailing_ft_trips_rate": 3.5,
            "pace_deficit_interaction": 105.0,
        }
        assert signal.validate_output(valid) is True

    def test_validate_output_accepts_none(self) -> None:
        signal = _make_signal()
        assert signal.validate_output(None) is True

    def test_validate_output_rejects_non_numeric(self) -> None:
        signal = _make_signal()
        bad = {
            "score_deficit_abs": "big",
            "comeback_mode_flag": 1.0,
            "trailing_ft_trips_rate": 3.0,
            "pace_deficit_interaction": 100.0,
        }
        assert signal.validate_output(bad) is False

    def test_period_from_snapshot_mapping(self) -> None:
        from signals.comeback_pace import ComebackPaceSignal
        assert ComebackPaceSignal._period_from_snapshot("endQ1") == 1
        assert ComebackPaceSignal._period_from_snapshot("endQ2") == 2
        assert ComebackPaceSignal._period_from_snapshot("endQ3") == 3
        assert ComebackPaceSignal._period_from_snapshot("endQ4") == 4
        assert ComebackPaceSignal._period_from_snapshot(None) is None
        assert ComebackPaceSignal._period_from_snapshot("garbage") is None
