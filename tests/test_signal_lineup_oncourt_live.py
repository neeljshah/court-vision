"""Tests for signals/lineup_oncourt_live.py.

Covers:
  1. Leak-safety: build() must NEVER call datetime.utcnow() or read any artifact
     stamped after ctx.decision_time.
  2. Value-sanity: returned sub-features are numeric and within plausible NBA ranges.
  3. None-on-missing: build() returns None when ctx.live is absent or has no
     matching players.
  4. dict-signal contract: validate_output() accepts the returned dict.
  5. hypothesis() returns a well-formed Hypothesis targeting winprob.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on sys.path so signals/ is importable
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.loop.signal import AsOfContext, Verdict
from src.loop.store import PointInTimeStore, entity_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_snap(team: str = "CHI", n_players: int = 5, period: int = 3,
               clock: str = "5:30") -> dict:
    """Minimal live snapshot for ``team`` with ``n_players`` active players."""
    players = []
    for i in range(n_players):
        players.append({
            "player_id": 2000000 + i,
            "name": f"Player {i}",
            "team": team,
            "is_starter": True,
            "min": float(20 + i),  # non-zero → inferred on court
            "pts": 5,
            "reb": 2,
            "ast": 1,
        })
    # Add bench / opposing team players that should NOT be picked
    players.append({"player_id": 9999999, "name": "Bench Player", "team": "ORL",
                    "is_starter": False, "min": 0.0, "pts": 0})
    return {
        "game_id": "0022400123",
        "captured_at": "2026-01-15T21:30:00Z",
        "game_status": "LIVE",
        "period": period,
        "clock": clock,
        "home_team": "CHI",
        "away_team": "ORL",
        "home_score": 80,
        "away_score": 75,
        "players": players,
    }


def _make_ctx(snap: Optional[dict] = None,
              decision_time: Optional[_dt.datetime] = None,
              team: str = "CHI",
              store: Optional[PointInTimeStore] = None) -> AsOfContext:
    """Construct a minimal live AsOfContext."""
    dt = decision_time or _dt.datetime(2026, 1, 15, 21, 30, 0)
    return AsOfContext(
        decision_time=dt,
        team=team,
        opp="ORL",
        game_id="0022400123",
        game_date="2026-01-15",
        season="2024-25",
        is_home=True,
        scope="live",
        snapshot="endQ3",
        live=snap,
    )


def _make_signal(store: Optional[PointInTimeStore] = None,
                 lineup_rows: Optional[list] = None):
    """Instantiate the signal with an optional mock store and lineup parquet."""
    import pandas as pd
    from signals.lineup_oncourt_live import LineupOncourtLive, _load_lineup_df
    import signals.lineup_oncourt_live as mod

    # Build a synthetic lineup_df with matching player_ids 2000000..2000004
    if lineup_rows is None:
        lineup_rows = [
            {"player_id": 2000000 + i, "season": "2024-25",
             "lineup_top3_net_rating": 4.5 + i * 0.5,
             "lineup_top1_min_share": 0.30 + i * 0.01,
             "lineup_avg_pace_on": 101.0 + i}
            for i in range(5)
        ]
    synthetic_df = pd.DataFrame(lineup_rows)
    # Patch the module-level _lineup_df so we don't need the real parquet on disk
    mod._lineup_df = synthetic_df

    sig = LineupOncourtLive(store=store)
    return sig


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must not read anything with as_of > ctx.decision_time."""

    def test_store_read_respects_as_of_bound(self, tmp_path):
        """If the store has a record stamped AFTER decision_time, it must NOT be seen."""
        store = PointInTimeStore(store_dir=tmp_path, autoload=False)
        # Write a lineup_splits record stamped well AFTER the decision time
        future_as_of = "2099-12-31"
        store.write_atlas(
            "player", 2000000, "lineup_splits", future_as_of,
            {"lineup_top3_net_rating": 999.0, "lineup_avg_pace_on": 999.0,
             "lineup_top1_min_share": 0.99},
            {"source": "test", "n": 100, "confidence": "high"},
        )
        snap = _make_snap()
        ctx = _make_ctx(snap=snap, store=store)
        sig = _make_signal(store=store)

        result = sig.build(ctx)

        # The signal should NOT incorporate the future record (net_rating_on != 999)
        assert result is not None
        assert isinstance(result, dict)
        # net_rating_on comes from synthetic parquet (4.5..6.5), NOT 999
        assert result["net_rating_on"] < 100.0, (
            "Leak: future atlas record contaminated the build output"
        )

    def test_no_utcnow_calls_during_build(self):
        """build() must not call datetime.utcnow() internally (temporal leak)."""
        snap = _make_snap()
        ctx = _make_ctx(snap=snap)
        sig = _make_signal()

        with patch("datetime.datetime") as mock_dt:
            mock_dt.utcnow.side_effect = AssertionError(
                "Signal called datetime.utcnow() — temporal leak"
            )
            mock_dt.side_effect = lambda *a, **kw: _dt.datetime(*a, **kw)
            # Should not raise AssertionError
            try:
                result = sig.build(ctx)
            except AssertionError as exc:
                pytest.fail(str(exc))


# ---------------------------------------------------------------------------
# 2. Value-sanity assertions
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Output sub-features must lie in plausible NBA ranges."""

    def test_returns_dict_with_four_keys(self):
        sig = _make_signal()
        snap = _make_snap()
        ctx = _make_ctx(snap=snap)
        result = sig.build(ctx)

        assert isinstance(result, dict)
        assert set(result.keys()) == {
            "net_rating_on", "pace_on", "min_share_top1", "time_remaining_weight"
        }

    def test_net_rating_plausible_range(self):
        """Season net-rating is typically in [-20, +20] for real NBA lineups."""
        sig = _make_signal()
        snap = _make_snap()
        ctx = _make_ctx(snap=snap)
        result = sig.build(ctx)

        assert result is not None
        assert -30.0 <= result["net_rating_on"] <= 30.0, (
            f"net_rating_on={result['net_rating_on']} outside plausible NBA range"
        )

    def test_pace_plausible_range(self):
        """NBA team pace is typically 90–115 possessions per 48 min."""
        sig = _make_signal()
        snap = _make_snap()
        ctx = _make_ctx(snap=snap)
        result = sig.build(ctx)

        assert result is not None
        assert 80.0 <= result["pace_on"] <= 130.0, (
            f"pace_on={result['pace_on']} outside plausible NBA range"
        )

    def test_min_share_zero_to_one(self):
        sig = _make_signal()
        snap = _make_snap()
        ctx = _make_ctx(snap=snap)
        result = sig.build(ctx)

        assert result is not None
        assert 0.0 <= result["min_share_top1"] <= 1.0, (
            f"min_share_top1={result['min_share_top1']} not in [0,1]"
        )

    def test_time_remaining_weight_non_negative(self):
        sig = _make_signal()
        snap = _make_snap(period=3, clock="5:30")
        ctx = _make_ctx(snap=snap)
        result = sig.build(ctx)

        assert result is not None
        assert result["time_remaining_weight"] >= 0.0

    def test_validate_output_accepts_result(self):
        """Signal.validate_output() must accept the returned dict."""
        sig = _make_signal()
        snap = _make_snap()
        ctx = _make_ctx(snap=snap)
        result = sig.build(ctx)

        assert sig.validate_output(result), (
            "validate_output returned False — sub-features are not all numeric"
        )

    def test_feature_names_match_emits(self):
        sig = _make_signal()
        fnames = sig.feature_names()
        assert len(fnames) == len(sig.emits)
        for fn in fnames:
            assert fn.startswith("lineup_oncourt_live__")


# ---------------------------------------------------------------------------
# 3. None-on-missing / edge cases
# ---------------------------------------------------------------------------

class TestNoneOnMissing:
    """build() must return None gracefully when required context is absent."""

    def test_none_when_live_absent(self):
        sig = _make_signal()
        ctx = _make_ctx(snap=None)  # no live snapshot
        assert sig.build(ctx) is None

    def test_none_when_team_absent(self):
        sig = _make_signal()
        snap = _make_snap()
        ctx = AsOfContext(
            decision_time=_dt.datetime(2026, 1, 15, 21, 30),
            team=None,  # missing team
            scope="live",
            live=snap,
        )
        assert sig.build(ctx) is None

    def test_none_when_no_players_match_team(self):
        sig = _make_signal()
        snap = _make_snap(team="CHI")
        ctx = _make_ctx(snap=snap, team="GSW")  # team not in snapshot
        assert sig.build(ctx) is None

    def test_none_when_all_players_have_zero_minutes(self):
        """Players who have played 0 minutes are excluded from on-court inference."""
        import pandas as pd
        from signals.lineup_oncourt_live import LineupOncourtLive
        import signals.lineup_oncourt_live as mod

        zero_min_snap = {
            "game_id": "0022400999",
            "period": 2,
            "clock": "6:00",
            "home_team": "CHI",
            "away_team": "ORL",
            "home_score": 0,
            "away_score": 0,
            "players": [
                {"player_id": 2000000 + i, "team": "CHI", "is_starter": True,
                 "min": 0.0, "pts": 0}
                for i in range(5)
            ],
        }
        mod._lineup_df = pd.DataFrame([
            {"player_id": 2000000 + i, "season": "2024-25",
             "lineup_top3_net_rating": 3.0,
             "lineup_top1_min_share": 0.25,
             "lineup_avg_pace_on": 100.0}
            for i in range(5)
        ])
        sig = LineupOncourtLive()
        ctx = _make_ctx(snap=zero_min_snap)
        assert sig.build(ctx) is None


# ---------------------------------------------------------------------------
# 4. Hypothesis contract
# ---------------------------------------------------------------------------

class TestHypothesis:
    def test_hypothesis_well_formed(self):
        from signals.lineup_oncourt_live import LineupOncourtLive
        sig = LineupOncourtLive()
        hyp = sig.hypothesis()

        assert hyp.name == "lineup_oncourt_live"
        assert hyp.target == "winprob"
        assert hyp.scope == "live"
        assert isinstance(hyp.statement, str) and len(hyp.statement) > 10
        assert "lineup_splits" in hyp.atlas_fields
        assert hyp.expected_verdict == "DEFER"

    def test_signal_class_attrs(self):
        from signals.lineup_oncourt_live import LineupOncourtLive
        assert LineupOncourtLive.name == "lineup_oncourt_live"
        assert LineupOncourtLive.target == "winprob"
        assert LineupOncourtLive.scope == "live"
        assert "lineup_splits" in LineupOncourtLive.reads_atlas
        assert len(LineupOncourtLive.emits) == 4
