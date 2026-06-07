"""Tests for signals/garbage_time_filter.py.

Checks:
  1. Leak-safety: the signal must never return a ground-truth gt_frac whose
     build_date is AFTER the requested decision_time.
  2. Value-sanity: emitted values must be in [0, 1] or None.
  3. Live snapshot path: a blowout Q4 snapshot returns a high value.
  4. Neutral return: when no data is present the signal returns None.
  5. Hypothesis contract: name/target/scope are correct strings.
"""
from __future__ import annotations

import datetime as _dt
import sys
import os
import tempfile
import types

import pandas as pd
import pytest

# Ensure repo root is on sys.path so imports resolve
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

os.environ.setdefault("NBA_OFFLINE", "1")

from src.loop.signal import AsOfContext, TARGETS, SCOPES
from signals.garbage_time_filter import (
    GarbageTimeFilter,
    _load_gt_per_game,
    _spread_to_blowout_prob,
    _live_gt_fraction,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def signal() -> GarbageTimeFilter:
    """An unbound signal (no store)."""
    return GarbageTimeFilter(store=None)


def _make_ctx(
    decision_time: _dt.datetime,
    *,
    game_id: str = "0022400001",
    game_date: str = "2024-10-22",
    team: str = "BOS",
    season: str = "2024-25",
    scope: str = "pregame",
    live: dict | None = None,
) -> AsOfContext:
    return AsOfContext(
        decision_time=decision_time,
        player_id=1627759,
        team=team,
        opp="NYK",
        game_id=game_id,
        game_date=game_date,
        season=season,
        scope=scope,
        live=live,
    )


# --------------------------------------------------------------------------- #
# 1. Leak-safety assertion                                                      #
# --------------------------------------------------------------------------- #

def test_leak_safety_no_future_label(monkeypatch, signal):
    """Signal must NOT return a gt_frac whose build_date > decision_time.

    We inject a mock gt_per_game DataFrame where every row has
    build_date='2099-01-01' (far future).  The signal must return None
    (cannot use a future label), not the injected gt_frac.
    """
    future_gt = pd.DataFrame([
        {"game_id": "0022400001", "gt_frac": 0.5, "build_date": "2099-01-01"},
    ])
    monkeypatch.setattr(
        "signals.garbage_time_filter._gt_cache", future_gt
    )
    # Also patch spreads and season_games to be empty so pregame path also fails
    monkeypatch.setattr(
        "signals.garbage_time_filter._spreads_cache",
        pd.DataFrame(columns=["game_date", "home_team", "away_team", "home_spread"]),
    )
    monkeypatch.setitem(
        __import__("signals.garbage_time_filter", fromlist=["_season_games_cache"])
        .__dict__["_season_games_cache"],
        "2024-25",
        {},
    )

    # Decision time is 2024-10-22 — before the future build_date
    ctx = _make_ctx(_dt.datetime(2024, 10, 22, 10, 0, 0))
    result = signal.build(ctx)
    # Must NOT return the injected 0.5 (that label is from the future)
    assert result is None or result != 0.5, (
        "Leak-safety violated: signal returned a future-stamped label."
    )


# --------------------------------------------------------------------------- #
# 2. Value-sanity assertion                                                     #
# --------------------------------------------------------------------------- #

def test_value_sanity_range(monkeypatch, signal):
    """All non-None values must be in [0, 1]."""
    # Inject a valid past gt row
    past_gt = pd.DataFrame([
        {"game_id": "0022400001", "gt_frac": 0.12, "build_date": "2024-10-22"},
    ])
    monkeypatch.setattr("signals.garbage_time_filter._gt_cache", past_gt)

    ctx = _make_ctx(_dt.datetime(2024, 10, 23, 10, 0, 0))  # day after build_date
    result = signal.build(ctx)
    assert result is not None, "Expected a numeric result from past gt row."
    assert 0.0 <= result <= 1.0, f"Value {result!r} out of [0, 1]."
    assert signal.validate_output(result), "validate_output must pass for this value."


def test_value_sanity_none_is_valid(signal):
    """None return (no data) is a valid sentinel — validate_output must accept it."""
    assert signal.validate_output(None), "validate_output must accept None."


def test_blowout_prob_spread_range():
    """_spread_to_blowout_prob must return values in [0, 1]."""
    for spread in [0.0, 5.0, 8.0, 12.0, 20.0, 30.0]:
        p = _spread_to_blowout_prob(spread)
        assert 0.0 <= p <= 1.0, f"spread={spread} → prob={p} out of range."


def test_blowout_prob_monotone():
    """Larger spread → higher blowout probability."""
    probs = [_spread_to_blowout_prob(s) for s in [0, 4, 8, 14, 20]]
    for i in range(len(probs) - 1):
        assert probs[i] <= probs[i + 1], (
            f"Non-monotone at index {i}: {probs[i]:.3f} > {probs[i+1]:.3f}"
        )


# --------------------------------------------------------------------------- #
# 3. Live snapshot path                                                          #
# --------------------------------------------------------------------------- #

def test_live_blowout_q4_returns_high(signal):
    """A large Q4 blowout should return a value > 0.3."""
    live_snap = {
        "period": 4,
        "clock": "2:30",     # ~2.5 min left — within the 5-min window
        "home_score": 120,
        "away_score": 95,    # margin = 25 → deep garbage time
    }
    ctx = _make_ctx(
        _dt.datetime(2024, 10, 23, 22, 0, 0),
        scope="live",
        live=live_snap,
    )
    result = signal.build(ctx)
    assert result is not None, "Live blowout should produce a value."
    assert result > 0.3, f"Expected high value for 25-pt Q4 blowout, got {result!r}."


def test_live_close_q4_returns_zero(signal):
    """A close Q4 game should return 0.0 (not garbage time)."""
    live_snap = {
        "period": 4,
        "clock": "3:00",
        "home_score": 108,
        "away_score": 106,   # 2-pt margin
    }
    ctx = _make_ctx(
        _dt.datetime(2024, 10, 23, 22, 0, 0),
        scope="live",
        live=live_snap,
    )
    result = signal.build(ctx)
    assert result == 0.0, f"Close Q4 should return 0.0, got {result!r}."


def test_live_early_quarter_returns_zero(signal):
    """A blowout in Q1 should return 0.0 (only Q4 counts)."""
    live_snap = {
        "period": 1,
        "clock": "8:00",
        "home_score": 20,
        "away_score": 0,
    }
    ctx = _make_ctx(
        _dt.datetime(2024, 10, 23, 21, 0, 0),
        scope="live",
        live=live_snap,
    )
    result = signal.build(ctx)
    assert result == 0.0, "Non-Q4 period should return 0.0 regardless of margin."


# --------------------------------------------------------------------------- #
# 4. No-data → None                                                             #
# --------------------------------------------------------------------------- #

def test_no_data_returns_none(monkeypatch, signal):
    """When all data paths fail the signal must return None (neutral)."""
    empty_gt = pd.DataFrame(columns=["game_id", "gt_frac", "build_date"])
    empty_sp = pd.DataFrame(columns=["game_date", "home_team", "away_team", "home_spread"])
    monkeypatch.setattr("signals.garbage_time_filter._gt_cache", empty_gt)
    monkeypatch.setattr("signals.garbage_time_filter._spreads_cache", empty_sp)

    ctx = _make_ctx(
        _dt.datetime(2024, 10, 23, 10, 0, 0),
        game_id="NONEXISTENT",
        game_date="1900-01-01",
        team="XYZ",
    )
    result = signal.build(ctx)
    assert result is None, f"Expected None for no-data case, got {result!r}."


# --------------------------------------------------------------------------- #
# 5. Hypothesis contract                                                        #
# --------------------------------------------------------------------------- #

def test_hypothesis_contract(signal):
    """Hypothesis attributes must satisfy the Signal contract."""
    h = signal.hypothesis()
    assert h.name == "garbage_time_filter"
    assert h.target in TARGETS, f"target '{h.target}' not in TARGETS."
    assert h.scope in SCOPES, f"scope '{h.scope}' not in SCOPES."
    assert len(h.statement) > 10, "Statement too short."
    assert "game_context" in h.atlas_fields


def test_signal_class_attrs(signal):
    """Class-level attrs must be consistent."""
    assert signal.name == "garbage_time_filter"
    assert signal.target == "pts"
    assert signal.scope == "both"
    assert signal.feature_names() == ["garbage_time_filter"]
