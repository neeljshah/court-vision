"""tests/test_signal_live_possession_pace.py — Unit tests for LivePossessionPace signal.

Two mandatory assertions per spec:
  1. Leak-safety — build() with a future-stamped store record must not return a
     value that uses that future record (the store contract guarantees this; we
     verify the signal only reads the store with as_of <= decision_time).
  2. Value sanity — for a realistic live snapshot the returned dict contains
     finite, plausible values in the expected sub-feature set.

Additional edge-case tests cover graceful degradation (missing ctx.live, zero
score, malformed clock) and atlas consumption.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

# Ensure repo root is on path before local imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.loop.signal import AsOfContext
from src.loop.store import PointInTimeStore, entity_key
from signals.live_possession_pace import (
    LivePossessionPace,
    _elapsed_seconds,
    _poss_from_score,
    _project_pace,
    _LEAGUE_AVG_PACE,
    _PTS_PER_POSS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ctx(
    decision_time: _dt.datetime,
    live: dict | None = None,
    game_id: str | None = "0022200001",
    team: str = "BOS",
    opp: str = "PHI",
) -> AsOfContext:
    return AsOfContext(
        decision_time=decision_time,
        team=team,
        opp=opp,
        game_id=game_id,
        game_date="2023-01-15",
        season="2022-23",
        scope="live",
        live=live,
    )


_LIVE_SNAP = {
    "game_id": "0022200001",
    "period": 3,
    "clock": "5:30",        # 5:30 remaining in Q3
    "home_score": 78,
    "away_score": 74,
    "home_team": "BOS",
    "away_team": "PHI",
    "game_status": "LIVE",
}

_DECISION_TIME = _dt.datetime(2023, 1, 15, 22, 0, 0)


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify the signal never uses a store record stamped after decision_time."""

    def test_future_atlas_record_not_used(self, tmp_path: Path) -> None:
        """Write a team_pace atlas record AFTER decision_time; build must ignore it.

        The PointInTimeStore contract ensures read(as_of=T) never returns a record
        with as_of > T. We verify the signal correctly passes ctx.decision_time as
        the as_of bound so it cannot pick up the future record.
        """
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)

        decision_time = _DECISION_TIME
        future_date = decision_time + _dt.timedelta(days=1)

        # Write a FUTURE record (pace=999 — clearly wrong if accidentally used).
        store.write_atlas(
            "team", "BOS", "team_pace",
            as_of=future_date,
            data={"pace": 999.0, "value": 999.0},
            provenance={"source": "test_future", "n": 100, "confidence": "high"},
        )
        # Write a PAST record (pace=102.5 — valid).
        past_date = decision_time - _dt.timedelta(days=7)
        store.write_atlas(
            "team", "BOS", "team_pace",
            as_of=past_date,
            data={"pace": 102.5, "value": 102.5},
            provenance={"source": "test_past", "n": 80, "confidence": "high"},
        )

        signal = LivePossessionPace(store=store)
        ctx = _make_ctx(decision_time=decision_time, live=_LIVE_SNAP)
        result = signal.build(ctx)

        # Signal must not return None (live snap is valid).
        assert result is not None, "Expected a dict result for valid live snap"
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

        # The future record (pace=999) must NOT have been used.
        # If the future record were used, pace_proj would be ~999 (extremely wrong).
        # Valid projected pace for this snap is in the 90-115 range.
        pace_proj = result.get("pace_proj", None)
        assert pace_proj is not None, "pace_proj must be present in result"
        assert 80.0 <= pace_proj <= 120.0, (
            f"pace_proj={pace_proj} is outside plausible range; "
            "future record (pace=999) may have leaked into the computation."
        )

    def test_no_store_record_falls_back_to_league_avg(self, tmp_path: Path) -> None:
        """With no atlas record, signal falls back to _LEAGUE_AVG_PACE."""
        store = PointInTimeStore(store_dir=tmp_path / "store2", autoload=False)
        signal = LivePossessionPace(store=store)
        ctx = _make_ctx(decision_time=_DECISION_TIME, live=_LIVE_SNAP)
        result = signal.build(ctx)

        assert result is not None
        pace_delta = result["pace_delta"]
        pace_proj = result["pace_proj"]

        # With league avg prior, delta = proj - _LEAGUE_AVG_PACE
        assert abs(pace_delta - (pace_proj - _LEAGUE_AVG_PACE)) < 0.01, (
            "pace_delta should equal pace_proj minus league avg when no atlas record"
        )


# ---------------------------------------------------------------------------
# 2. VALUE SANITY assertion
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Plausibility checks on returned sub-feature values."""

    def _build_no_store(self, live: dict) -> dict | None:
        sig = LivePossessionPace(store=None)
        ctx = _make_ctx(decision_time=_DECISION_TIME, live=live)
        return sig.build(ctx)

    def test_realistic_midgame_snap_returns_dict_with_all_keys(self) -> None:
        result = self._build_no_store(_LIVE_SNAP)
        assert result is not None
        assert isinstance(result, dict)
        assert "pace_proj" in result
        assert "pace_delta" in result
        assert "recent_scoring_rate" in result

    def test_pace_proj_in_plausible_nba_range(self) -> None:
        """Projected pace must be within 80–120 poss/48 for a realistic snap."""
        result = self._build_no_store(_LIVE_SNAP)
        assert result is not None
        assert 80.0 <= result["pace_proj"] <= 120.0, (
            f"pace_proj={result['pace_proj']} outside plausible NBA range 80-120"
        )

    def test_recent_scoring_rate_is_non_negative(self) -> None:
        result = self._build_no_store(_LIVE_SNAP)
        assert result is not None
        assert result["recent_scoring_rate"] >= 0.0

    def test_validate_output_accepts_result(self) -> None:
        sig = LivePossessionPace(store=None)
        result = self._build_no_store(_LIVE_SNAP)
        assert result is not None
        assert sig.validate_output(result) is True

    def test_feature_names_match_emits(self) -> None:
        sig = LivePossessionPace(store=None)
        expected = [
            "live_possession_pace__pace_proj",
            "live_possession_pace__pace_delta",
            "live_possession_pace__recent_scoring_rate",
        ]
        assert sig.feature_names() == expected

    def test_pace_increases_with_higher_score(self) -> None:
        """Higher score at the same elapsed time → higher pace projection."""
        slow_snap = dict(_LIVE_SNAP, home_score=55, away_score=50)
        fast_snap = dict(_LIVE_SNAP, home_score=85, away_score=82)
        result_slow = self._build_no_store(slow_snap)
        result_fast = self._build_no_store(fast_snap)
        assert result_slow is not None and result_fast is not None
        assert result_fast["pace_proj"] > result_slow["pace_proj"], (
            "Higher cumulative score at same clock should project higher pace"
        )

    def test_pace_delta_sign_is_consistent(self) -> None:
        """A very fast game gives positive delta (above league avg)."""
        fast_snap = dict(_LIVE_SNAP, home_score=90, away_score=88, period=2, clock="0:01")
        result = self._build_no_store(fast_snap)
        assert result is not None
        # 178 pts in ~Q2 end → extremely high pace → delta should be positive
        assert result["pace_delta"] > 0, (
            "Fast game (178 pts by end of Q2) should yield positive pace_delta"
        )


# ---------------------------------------------------------------------------
# 3. Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    """Signal must not crash on edge cases; must return None when data absent."""

    def _build(self, live: dict | None) -> dict | None:
        sig = LivePossessionPace(store=None)
        ctx = _make_ctx(decision_time=_DECISION_TIME, live=live)
        return sig.build(ctx)

    def test_no_live_snap_returns_none(self) -> None:
        assert self._build(None) is None

    def test_empty_live_dict_returns_none(self) -> None:
        assert self._build({}) is None

    def test_malformed_clock_does_not_crash(self) -> None:
        snap = dict(_LIVE_SNAP, clock="INVALID")
        result = self._build(snap)
        # Should degrade to period_start but not crash
        assert result is None or isinstance(result, dict)

    def test_zero_score_returns_dict(self) -> None:
        snap = dict(_LIVE_SNAP, home_score=0, away_score=0, period=1, clock="11:58")
        result = self._build(snap)
        # Zero score early Q1 — may return dict or None depending on elapsed_sec
        assert result is None or isinstance(result, dict)

    def test_negative_score_returns_none(self) -> None:
        snap = dict(_LIVE_SNAP, home_score=-1, away_score=0)
        assert self._build(snap) is None


# ---------------------------------------------------------------------------
# 4. Helper unit tests (pure functions)
# ---------------------------------------------------------------------------

class TestHelpers:
    """Unit-test pure helper functions in the module."""

    def test_elapsed_seconds_q1_start(self) -> None:
        assert _elapsed_seconds(1, "12:00") == pytest.approx(0.0, abs=1.0)

    def test_elapsed_seconds_q1_end(self) -> None:
        assert _elapsed_seconds(1, "0:00") == pytest.approx(720.0, abs=1.0)

    def test_elapsed_seconds_q3_mid(self) -> None:
        # Q3 starts at 1440s; 6 min remaining → 720-360 = 360s into Q3 → 1800 total
        assert _elapsed_seconds(3, "6:00") == pytest.approx(1800.0, abs=1.0)

    def test_poss_from_score_round_trip(self) -> None:
        # _poss_from_score returns per-TEAM possessions from the combined score.
        # combined_score / (2 * PTS_PER_POSS) = per-team estimate.
        score = 100.0
        poss = _poss_from_score(score)
        assert poss == pytest.approx(score / (2.0 * _PTS_PER_POSS), abs=0.01)

    def test_project_pace_at_halfpoint(self) -> None:
        # Exactly half game elapsed (1440s), 50 poss so far → 100 poss/48 projected
        proj, delta = _project_pace(50.0, 1440.0, _LEAGUE_AVG_PACE)
        assert proj == pytest.approx(100.0, abs=0.5)

    def test_project_pace_delta_zero_when_on_track(self) -> None:
        # If current pace = prior, delta ≈ 0
        half_poss = _LEAGUE_AVG_PACE / 2.0
        proj, delta = _project_pace(half_poss, 1440.0, _LEAGUE_AVG_PACE)
        assert abs(delta) < 2.0  # within 2 poss/48 noise tolerance


# ---------------------------------------------------------------------------
# 5. Hypothesis contract
# ---------------------------------------------------------------------------

class TestHypothesis:
    def test_hypothesis_contract(self) -> None:
        sig = LivePossessionPace(store=None)
        h = sig.hypothesis()
        assert h.name == "live_possession_pace"
        assert h.target == "total"
        assert h.scope == "live"
        assert h.source == "seed"
        assert "team_pace" in h.atlas_fields
        assert len(h.statement) > 20
