"""tests/test_signal_foul_out_hazard.py — Unit tests for FoulOutHazard signal.

Covers:
  1. Leak-safety: build() must NEVER read data stamped after ctx.decision_time.
  2. Value-sanity: hazard in [0,1], fouls_remaining in [0,6], pf_rate_l5 >= 0.
  3. Edge cases: None when live=None, None when player not in snapshot.
  4. Monotonicity: hazard increases as foul count grows (same clock).
  5. hypothesis() returns correct target/scope/name.
  6. feature_names() matches emits.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from signals.foul_out_hazard import (
    FoulOutHazard,
    PF_LIMIT,
    _elapsed_minutes,
    _foul_hazard_score,
)
from src.loop.signal import AsOfContext, Hypothesis, Verdict
from src.loop.store import PointInTimeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_live_snap(
    player_id: int,
    pf: int,
    period: int = 3,
    clock: str = "6:00",
    game_id: str = "0022400001",
    home_team: str = "LAL",
    team: str = "LAL",
) -> Dict[str, Any]:
    """Build a minimal live snapshot dict matching the spec_data.md §6 schema."""
    return {
        "game_id": game_id,
        "period": period,
        "clock": clock,
        "home_score": 55,
        "away_score": 52,
        "home_team": home_team,
        "away_team": "GSW",
        "game_status": "LIVE",
        "captured_at": "2026-05-30T22:30:00Z",
        "players": [
            {
                "player_id": player_id,
                "name": "Test Player",
                "team": team,
                "min": "18:00",
                "pts": 12,
                "reb": 4,
                "ast": 2,
                "fg3m": 1,
                "stl": 1,
                "blk": 0,
                "tov": 1,
                "pf": pf,
                "is_starter": True,
            }
        ],
    }


def _make_ctx(
    player_id: int,
    pf: int = 2,
    period: int = 3,
    clock: str = "6:00",
    decision_time: Optional[_dt.datetime] = None,
    store: Optional[PointInTimeStore] = None,
    game_date: str = "2026-05-30",
) -> AsOfContext:
    """Build an AsOfContext with a live snapshot."""
    if decision_time is None:
        decision_time = _dt.datetime(2026, 5, 30, 22, 30, 0)
    snap = _make_live_snap(player_id=player_id, pf=pf, period=period, clock=clock)
    return AsOfContext(
        decision_time=decision_time,
        player_id=player_id,
        team="LAL",
        opp="GSW",
        game_id="0022400001",
        game_date=game_date,
        season="2025-26",
        is_home=True,
        scope="live",
        snapshot=f"endQ{period}",
        live=snap,
        extra={},
    )


# ---------------------------------------------------------------------------
# Test: leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """The signal must NEVER return data from after ctx.decision_time."""

    def test_store_read_does_not_cross_decision_time(self, tmp_path: Path) -> None:
        """Write a future foul_propensity record; build() must NOT see it.

        Strategy: write a record stamped tomorrow into the store; confirm that
        the signal's read_atlas call with as_of=today cannot see it.
        """
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)

        player_id = 1234567
        today = _dt.datetime(2026, 5, 30, 20, 0, 0)
        tomorrow_iso = "2026-05-31"

        # Write a FUTURE foul_propensity atlas record (pf_per_36_l5 = 99.0)
        store.write_atlas(
            "player", player_id, "foul_propensity", tomorrow_iso,
            {"pf_per_36_l5": 99.0, "foul_trouble_rate_l10": 0.5, "n_games": 50},
            provenance={"source": "test", "n": 50, "confidence": "high",
                        "as_of": tomorrow_iso},
        )

        signal = FoulOutHazard(store=store)
        ctx = _make_ctx(player_id=player_id, pf=2, decision_time=today)

        result = signal.build(ctx)

        # The signal must produce a result (live snap is present)
        assert result is not None, "Signal should compute a result when live snap present"
        # pf_rate_l5 must NOT be 99.0 (the future-stamped value)
        assert result["pf_rate_l5"] != 99.0, (
            "Leak detected: signal read a foul_propensity record stamped AFTER "
            "ctx.decision_time. Leak-safety contract violated."
        )

    def test_read_atlas_cutoff_is_decision_time(self, tmp_path: Path) -> None:
        """Write a PAST record; it SHOULD be visible (correct behavior)."""
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)

        player_id = 9876543
        yesterday_iso = "2026-05-29"
        today = _dt.datetime(2026, 5, 30, 20, 0, 0)

        # Write a PAST record (should be visible)
        store.write_atlas(
            "player", player_id, "foul_propensity", yesterday_iso,
            {"pf_per_36_l5": 4.2, "foul_trouble_rate_l10": 0.3, "n_games": 15},
            provenance={"source": "test", "n": 15, "confidence": "med",
                        "as_of": yesterday_iso},
        )

        signal = FoulOutHazard(store=store)
        ctx = _make_ctx(player_id=player_id, pf=1, decision_time=today)

        result = signal.build(ctx)

        assert result is not None
        # Should pick up the past record's pf_per_36_l5 = 4.2
        assert abs(result["pf_rate_l5"] - 4.2) < 1e-6, (
            f"Expected pf_rate_l5=4.2 from past atlas record, got {result['pf_rate_l5']}"
        )


# ---------------------------------------------------------------------------
# Test: value-sanity assertions
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Output values must be in the expected basketball-plausible ranges."""

    def test_hazard_in_unit_interval(self) -> None:
        signal = FoulOutHazard()
        for pf in range(0, 7):
            for period in (1, 2, 3, 4):
                ctx = _make_ctx(player_id=1, pf=pf, period=period, clock="6:00")
                result = signal.build(ctx)
                assert result is not None
                assert 0.0 <= result["hazard"] <= 1.0, (
                    f"hazard={result['hazard']} out of [0,1] for pf={pf} period={period}"
                )

    def test_fouls_remaining_non_negative(self) -> None:
        signal = FoulOutHazard()
        for pf in (0, 3, 5, 6, 7):   # 7 is over limit (edge case)
            ctx = _make_ctx(player_id=1, pf=pf)
            result = signal.build(ctx)
            if result is not None:
                assert result["fouls_remaining"] >= 0.0, (
                    f"fouls_remaining={result['fouls_remaining']} is negative (pf={pf})"
                )

    def test_fouls_remaining_at_limit(self) -> None:
        signal = FoulOutHazard()
        ctx = _make_ctx(player_id=1, pf=PF_LIMIT)  # exactly fouled out
        result = signal.build(ctx)
        assert result is not None
        assert result["fouls_remaining"] == 0.0

    def test_pf_rate_l5_non_negative(self) -> None:
        signal = FoulOutHazard()
        ctx = _make_ctx(player_id=99999, pf=2)   # unknown player → fallback 0.0
        result = signal.build(ctx)
        if result is not None:
            assert result["pf_rate_l5"] >= 0.0

    def test_no_foul_low_hazard(self) -> None:
        """A player with 0 fouls in Q1 should have a near-zero hazard."""
        signal = FoulOutHazard()
        ctx = _make_ctx(player_id=1, pf=0, period=1, clock="10:00")
        result = signal.build(ctx)
        assert result is not None
        assert result["hazard"] < 0.15, (
            f"Expected near-zero hazard for 0 fouls in Q1, got {result['hazard']:.4f}"
        )

    def test_high_foul_high_hazard(self) -> None:
        """5 fouls in Q3 mid-period should yield a meaningful hazard."""
        signal = FoulOutHazard()
        ctx = _make_ctx(player_id=1, pf=5, period=3, clock="6:00")
        result = signal.build(ctx)
        assert result is not None
        assert result["hazard"] > 0.1, (
            f"Expected elevated hazard for 5 fouls in Q3, got {result['hazard']:.4f}"
        )


# ---------------------------------------------------------------------------
# Test: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Signal must handle missing/null inputs gracefully."""

    def test_no_live_returns_none(self) -> None:
        signal = FoulOutHazard()
        ctx = AsOfContext(
            decision_time=_dt.datetime(2026, 5, 30),
            player_id=1,
            scope="live",
            live=None,
        )
        assert signal.build(ctx) is None

    def test_no_player_id_returns_none(self) -> None:
        signal = FoulOutHazard()
        snap = _make_live_snap(player_id=1, pf=2)
        ctx = AsOfContext(
            decision_time=_dt.datetime(2026, 5, 30),
            player_id=None,
            scope="live",
            live=snap,
        )
        assert signal.build(ctx) is None

    def test_player_not_in_snapshot_no_fallback_returns_none(self) -> None:
        """If player_id is not in the live snapshot and foul_state parquet is
        missing, build() should return None rather than crash."""
        with patch("signals.foul_out_hazard._load_foul_state",
                   return_value=__import__("pandas").DataFrame()):
            signal = FoulOutHazard()
            snap = _make_live_snap(player_id=999, pf=2)  # player 888 not in snap
            ctx = AsOfContext(
                decision_time=_dt.datetime(2026, 5, 30),
                player_id=888,   # absent
                scope="live",
                live=snap,
            )
            result = signal.build(ctx)
            assert result is None

    def test_validate_output_dict(self) -> None:
        signal = FoulOutHazard()
        ctx = _make_ctx(player_id=1, pf=3)
        result = signal.build(ctx)
        assert result is None or signal.validate_output(result)


# ---------------------------------------------------------------------------
# Test: monotonicity
# ---------------------------------------------------------------------------

class TestMonotonicity:
    """More fouls → higher hazard (same clock), fewer fouls_remaining."""

    def test_hazard_increases_with_foul_count(self) -> None:
        signal = FoulOutHazard()
        hazards = []
        for pf in range(0, PF_LIMIT):
            ctx = _make_ctx(player_id=1, pf=pf, period=3, clock="6:00")
            result = signal.build(ctx)
            assert result is not None
            hazards.append(result["hazard"])

        for i in range(1, len(hazards)):
            assert hazards[i] >= hazards[i - 1], (
                f"Hazard not monotone: hazard[pf={i}]={hazards[i]:.4f} "
                f"< hazard[pf={i-1}]={hazards[i-1]:.4f}"
            )

    def test_fouls_remaining_decreases_with_pf(self) -> None:
        signal = FoulOutHazard()
        remainders = []
        for pf in range(0, PF_LIMIT + 1):
            ctx = _make_ctx(player_id=1, pf=pf)
            result = signal.build(ctx)
            if result is not None:
                remainders.append(result["fouls_remaining"])
        for i in range(1, len(remainders)):
            assert remainders[i] <= remainders[i - 1]


# ---------------------------------------------------------------------------
# Test: hypothesis() and feature_names()
# ---------------------------------------------------------------------------

class TestMetadata:
    """Signal metadata must satisfy the contract."""

    def test_hypothesis_returns_correct_target(self) -> None:
        h = FoulOutHazard().hypothesis()
        assert isinstance(h, Hypothesis)
        assert h.target == "minutes"
        assert h.scope == "live"
        assert h.name == "foul_out_hazard"

    def test_hypothesis_expected_verdict(self) -> None:
        h = FoulOutHazard().hypothesis()
        assert h.expected_verdict in (Verdict.SHIP, Verdict.VARIANCE_ONLY,
                                       Verdict.DEFER, Verdict.REJECT,
                                       "SHIP", "VARIANCE_ONLY", "DEFER", "REJECT",
                                       None)

    def test_feature_names_match_emits(self) -> None:
        s = FoulOutHazard()
        names = s.feature_names()
        assert names == [f"foul_out_hazard__{k}" for k in s.emits]

    def test_scope_and_target_valid(self) -> None:
        from src.loop.signal import TARGETS, SCOPES
        s = FoulOutHazard()
        assert s.target in TARGETS
        assert s.scope in SCOPES


# ---------------------------------------------------------------------------
# Test: internal helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    """Smoke tests for the pure helper functions."""

    def test_elapsed_minutes_q1_start(self) -> None:
        assert abs(_elapsed_minutes(1, "12:00") - 0.0) < 0.01

    def test_elapsed_minutes_q1_end(self) -> None:
        assert abs(_elapsed_minutes(1, "0:00") - 12.0) < 0.01

    def test_elapsed_minutes_q3_midpoint(self) -> None:
        # Q1(12) + Q2(12) = 24 completed; 6 min into Q3 → 30 total
        assert abs(_elapsed_minutes(3, "6:00") - 30.0) < 0.01

    def test_foul_hazard_score_no_fouls_is_low(self) -> None:
        score = _foul_hazard_score(0, elapsed=0.0)
        assert score < 0.2

    def test_foul_hazard_score_at_limit_returns_half(self) -> None:
        # PF == limit → 0.5 (already fouled out, neutral)
        score = _foul_hazard_score(PF_LIMIT, elapsed=24.0)
        assert score == 0.5

    def test_foul_hazard_score_late_game_dampened(self) -> None:
        """Hazard at 47 minutes (end of Q4) should be low — little time left."""
        score_early = _foul_hazard_score(4, elapsed=10.0)
        score_late = _foul_hazard_score(4, elapsed=46.0)
        assert score_late < score_early, (
            "Hazard should be lower at end-of-game even for same foul count"
        )
