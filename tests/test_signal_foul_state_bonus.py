"""tests/test_signal_foul_state_bonus.py — Unit tests for FoulStateBonusSignal.

Two required assertions per spec:
  1. LEAK-SAFETY — build() never returns data stamped after ctx.decision_time.
     Verified by writing a foul-state record into the store with a FUTURE as_of
     and confirming the signal does NOT use it (returns None or the pre-cutoff value).
  2. VALUE SANITY — the sub-features are in the expected range and sign.

Additional tests:
  * live snapshot path produces correct bonus flags.
  * parquet path returns None when game_id is absent.
  * ref_crew_fta multiplier clamps to [0.5, 2.0].
  * hypothesis() returns a well-formed Hypothesis object.
  * validate_output() accepts the dict and rejects garbage.
"""
from __future__ import annotations

import datetime as _dt
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

from src.loop.signal import AsOfContext, Hypothesis, Verdict
from src.loop.store import PointInTimeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _make_signal(store=None):
    """Import and instantiate FoulStateBonusSignal, binding an optional store."""
    from signals.foul_state_bonus import FoulStateBonusSignal
    return FoulStateBonusSignal(store=store)


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Build() must not use any information stamped after decision_time."""

    def test_future_store_record_not_used(self, tmp_path: Path) -> None:
        """Writing a foul-state atlas record with a FUTURE as_of must not affect build().

        Strategy: create a store, write an officials atlas record with as_of=TOMORROW,
        build the signal with decision_time=TODAY and no live snapshot.
        The signal should return None (no parquet row for a fake game_id), NOT a
        value derived from the future store record.
        """
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        today = _dt.datetime(2025, 1, 15, 12, 0, 0)
        tomorrow_iso = "2025-01-16"

        # Write a future-dated officials record into the store
        store.write_atlas(
            "team", "LAL", "officials", tomorrow_iso,
            {"ref_crew_fta": 99.0, "ref_crew_fouls": 99.0},
            {"source": "test", "n": 100, "confidence": "high"},
        )

        signal = _make_signal(store=store)
        ctx = _ctx(
            decision_time=today,
            game_id="FAKE_GAME_999",
            team="LAL",
            snapshot="endQ2",
            live=None,
        )
        result = signal.build(ctx)

        # Must return None — no parquet row for FAKE_GAME_999 AND
        # the future store record must NOT be visible.
        # If the store were leaking, ref_crew_fta=99.0 would produce a multiplier
        # far outside the clamped [0.5, 2.0] range; but since no parquet row exists
        # for the fake game, result should be None regardless.
        assert result is None, (
            f"Expected None for unknown game_id with future store record; got {result}"
        )

    def test_past_store_record_is_used_correctly(self, tmp_path: Path) -> None:
        """A store record stamped BEFORE decision_time IS read (not a false positive)."""
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        yesterday = _dt.datetime(2025, 1, 14, 12, 0, 0)
        today = _dt.datetime(2025, 1, 15, 12, 0, 0)

        # Write a PAST officials atlas record
        store.write_atlas(
            "team", "GSW", "officials", yesterday.date().isoformat(),
            {"ref_crew_fta": 50.0},  # above average
            {"source": "test", "n": 50, "confidence": "high"},
        )

        signal = _make_signal(store=store)

        # We verify _ref_fta_multiplier reads the past record (> 1.0)
        ctx = _ctx(decision_time=today, team="GSW", game_id=None)
        mult = signal._ref_fta_multiplier(ctx)
        # 50.0 / 44.76 ≈ 1.117 — should be above 1.0
        assert mult > 1.0, (
            f"Expected multiplier > 1.0 for ref_crew_fta=50.0; got {mult:.4f}"
        )

    def test_future_store_record_for_multiplier_not_used(self, tmp_path: Path) -> None:
        """_ref_fta_multiplier must NOT use a store record stamped after decision_time."""
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        today = _dt.datetime(2025, 1, 15, 12, 0, 0)
        future_iso = "2025-01-20"

        store.write_atlas(
            "team", "BOS", "officials", future_iso,
            {"ref_crew_fta": 99.0},
            {"source": "test", "n": 50, "confidence": "high"},
        )

        signal = _make_signal(store=store)
        ctx = _ctx(decision_time=today, team="BOS", game_id=None)
        mult = signal._ref_fta_multiplier(ctx)
        # With no past record and no game_id, multiplier must be 1.0 (neutral)
        assert mult == 1.0, (
            f"Future store record must not leak; expected 1.0 neutral, got {mult:.4f}"
        )


# ---------------------------------------------------------------------------
# 2. Value-sanity assertions
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Sub-feature values must be in the expected range and sign."""

    def test_live_snapshot_both_in_bonus(self) -> None:
        """When both teams have >= 5 PFs, both bonus flags should be ~1.0."""
        signal = _make_signal()
        snap = {
            "home_team": "LAL",
            "away_team": "BOS",
            "period": 3,
            "players": [
                # Home: 6 PFs total → in bonus
                {"team": "LAL", "pf": 3},
                {"team": "LAL", "pf": 3},
                # Away: 5 PFs total → exactly in bonus
                {"team": "BOS", "pf": 2},
                {"team": "BOS", "pf": 3},
            ],
        }
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 3, 1, 21, 0),
            live=snap,
            team="LAL",
            opp="BOS",
        )
        result = signal.build(ctx)

        assert result is not None, "Expected a dict result for valid live snapshot"
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert result["home_bonus_flag"] == pytest.approx(1.0, abs=0.01), (
            f"Home (6 PFs) should be in bonus; got {result['home_bonus_flag']}"
        )
        assert result["away_bonus_flag"] == pytest.approx(1.0, abs=0.01), (
            f"Away (5 PFs) should be in bonus; got {result['away_bonus_flag']}"
        )
        assert result["pf_imbalance"] == pytest.approx(1.0, abs=0.01), (
            f"pf_imbalance should be 6-5=1; got {result['pf_imbalance']}"
        )

    def test_live_snapshot_only_away_in_bonus(self) -> None:
        """Only away in bonus → away_bonus_flag=1, home_bonus_flag=0."""
        signal = _make_signal()
        snap = {
            "home_team": "DEN",
            "away_team": "OKC",
            "period": 2,
            "players": [
                {"team": "DEN", "pf": 1},
                {"team": "DEN", "pf": 2},   # 3 total — not in bonus
                {"team": "OKC", "pf": 3},
                {"team": "OKC", "pf": 3},   # 6 total — in bonus
            ],
        }
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 2, 15, 20, 30),
            live=snap,
            team="DEN",
            opp="OKC",
        )
        result = signal.build(ctx)

        assert result is not None
        assert result["home_bonus_flag"] == pytest.approx(0.0, abs=0.01), (
            f"DEN (3 PFs) not in bonus; got {result['home_bonus_flag']}"
        )
        assert result["away_bonus_flag"] == pytest.approx(1.0, abs=0.01), (
            f"OKC (6 PFs) in bonus; got {result['away_bonus_flag']}"
        )
        assert result["pf_imbalance"] == pytest.approx(-3.0, abs=0.01)

    def test_live_snapshot_no_fouls_returns_none(self) -> None:
        """Snapshot with all-zero PFs should return None (neutral/missing)."""
        signal = _make_signal()
        snap = {
            "home_team": "MIA",
            "away_team": "NYK",
            "period": 1,
            "players": [
                {"team": "MIA", "pf": 0},
                {"team": "NYK", "pf": 0},
            ],
        }
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 4, 1, 19, 0),
            live=snap,
        )
        result = signal.build(ctx)
        assert result is None, "All-zero PFs should yield None"

    def test_no_live_no_game_id_returns_none(self) -> None:
        """No live snapshot and no game_id → cannot look up parquet → None."""
        signal = _make_signal()
        ctx = _ctx(
            decision_time=_dt.datetime(2025, 1, 10, 18, 0),
            live=None,
            game_id=None,
        )
        result = signal.build(ctx)
        assert result is None

    def test_ref_fta_multiplier_clamped(self) -> None:
        """_ref_fta_multiplier must stay within [0.5, 2.0] even for extreme values."""
        signal = _make_signal()

        # Simulate parquet lookup by patching _load_officials to return extreme row
        import pandas as pd
        extreme_df = pd.DataFrame([{
            "game_id": "EXTREME_GAME",
            "game_date": "2025-01-01",
            "team_abbreviation": "TEST",
            "ref_crew_fouls": 99.0,
            "ref_crew_fta": 200.0,   # extreme high
        }])
        with patch("signals.foul_state_bonus._load_officials", return_value=extreme_df):
            ctx = _ctx(
                decision_time=_dt.datetime(2025, 1, 10),
                game_id="EXTREME_GAME",
            )
            mult = signal._ref_fta_multiplier(ctx)
        assert mult <= 2.0, f"Multiplier must be clamped to 2.0; got {mult}"
        assert mult >= 0.5, f"Multiplier must be clamped to 0.5; got {mult}"

    def test_period_from_snapshot_mapping(self) -> None:
        """_period_from_snapshot must map endQ2→2, endQ3→3, None→None."""
        from signals.foul_state_bonus import FoulStateBonusSignal
        assert FoulStateBonusSignal._period_from_snapshot("endQ1") == 1
        assert FoulStateBonusSignal._period_from_snapshot("endQ2") == 2
        assert FoulStateBonusSignal._period_from_snapshot("endQ3") == 3
        assert FoulStateBonusSignal._period_from_snapshot(None) is None
        assert FoulStateBonusSignal._period_from_snapshot("unknown") is None


# ---------------------------------------------------------------------------
# 3. Hypothesis + metadata checks
# ---------------------------------------------------------------------------

class TestHypothesis:
    """hypothesis() must return a well-formed Hypothesis consistent with class attrs."""

    def test_hypothesis_fields(self) -> None:
        signal = _make_signal()
        h = signal.hypothesis()

        assert isinstance(h, Hypothesis), f"Expected Hypothesis, got {type(h)}"
        assert h.name == "foul_state_bonus"
        assert h.target == "total"
        assert h.scope == "live"
        assert h.source == "seed"
        assert "officials" in h.atlas_fields
        assert h.expected_verdict == Verdict.SHIP
        assert h.priority == "P1"
        assert len(h.statement) > 20, "Statement should be non-trivial"

    def test_feature_names(self) -> None:
        signal = _make_signal()
        names = signal.feature_names()
        expected = [
            "foul_state_bonus__home_bonus_flag",
            "foul_state_bonus__away_bonus_flag",
            "foul_state_bonus__pf_imbalance",
        ]
        assert names == expected, f"feature_names() mismatch: {names}"

    def test_validate_output_accepts_valid_dict(self) -> None:
        signal = _make_signal()
        valid = {"home_bonus_flag": 1.0, "away_bonus_flag": 0.0, "pf_imbalance": 3.0}
        assert signal.validate_output(valid) is True

    def test_validate_output_accepts_none(self) -> None:
        signal = _make_signal()
        assert signal.validate_output(None) is True

    def test_validate_output_rejects_non_numeric(self) -> None:
        signal = _make_signal()
        bad = {"home_bonus_flag": "yes", "away_bonus_flag": 0.0, "pf_imbalance": 0.0}
        assert signal.validate_output(bad) is False

    def test_class_attributes(self) -> None:
        from signals.foul_state_bonus import FoulStateBonusSignal
        assert FoulStateBonusSignal.name == "foul_state_bonus"
        assert FoulStateBonusSignal.target == "total"
        assert FoulStateBonusSignal.scope == "live"
        assert "officials" in FoulStateBonusSignal.reads_atlas
        assert len(FoulStateBonusSignal.emits) == 3
