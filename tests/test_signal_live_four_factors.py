"""Tests for signals/live_four_factors.py.

Assertions
----------
1. Leak-safety: build() never returns a value whose source row has a game_date
   AFTER ctx.decision_time (future-row guard).
2. Value sanity: when a known valid row is fed, all 8 sub-features are finite
   floats in plausible basketball ranges.
3. Missing context returns None (no crash on missing game_id / snapshot / is_home).
4. Dict keys match Signal.emits exactly.
5. hypothesis() returns a Hypothesis with correct name/target/scope.
"""
from __future__ import annotations

import datetime as _dt
import math
import sys
import os

# Ensure repo root is on sys.path when running from any directory.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

os.environ.setdefault("NBA_OFFLINE", "1")

import pandas as pd
import pytest

from src.loop.signal import AsOfContext, Hypothesis
from signals.live_four_factors import LiveFourFactors, _load_qbox, _VALID_SNAPSHOTS


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    *,
    game_id: str,
    snapshot: str,
    is_home: bool,
    decision_time: _dt.datetime,
    team: str = "HOM",
    opp: str = "AWY",
) -> AsOfContext:
    return AsOfContext(
        decision_time=decision_time,
        game_id=game_id,
        snapshot=snapshot,
        is_home=is_home,
        team=team,
        opp=opp,
        scope="live",
    )


def _load_one_valid_game() -> tuple:
    """Return (game_id, snapshot, game_date) from the first row of the parquet."""
    qbox = _load_qbox()
    row = qbox.dropna(subset=["game_date"]).iloc[0]
    return str(row["game_id"]), str(row["snapshot"]), pd.Timestamp(row["game_date"])


# ---------------------------------------------------------------------------
# Test 1: Leak-safety — decision_time BEFORE the game_date → must return None
# ---------------------------------------------------------------------------

def test_leak_safety_future_game_returns_none():
    """A decision_time strictly before the game's date must return None.

    This verifies that the parquet filter ``game_date <= decision_date`` is
    enforced and no future-row leaks through.
    """
    signal = LiveFourFactors()
    game_id, snapshot, game_date = _load_one_valid_game()

    # Set decision_time to 1 day BEFORE the game — this game must be invisible.
    decision_before = _dt.datetime.combine(
        (game_date - pd.Timedelta(days=1)).date(),
        _dt.time(23, 59, 59),
        tzinfo=_dt.timezone.utc,
    )
    ctx = _make_ctx(
        game_id=game_id,
        snapshot=snapshot,
        is_home=True,
        decision_time=decision_before,
    )
    result = signal.build(ctx)
    assert result is None, (
        f"Leak detected: build() returned {result!r} for a game dated "
        f"{game_date.date()} when decision_time is {decision_before.date()}"
    )


# ---------------------------------------------------------------------------
# Test 2: Value sanity — valid context produces 8 finite floats in range
# ---------------------------------------------------------------------------

def test_value_sanity_valid_context():
    """With a known-good (game_id, snapshot, is_home), all 8 sub-features are
    finite floats within plausible basketball four-factor ranges.
    """
    signal = LiveFourFactors()
    game_id, snapshot, game_date = _load_one_valid_game()

    # decision_time ON the game date (same day, end-of-day)
    decision_on = _dt.datetime.combine(
        game_date.date(),
        _dt.time(23, 59, 59),
        tzinfo=_dt.timezone.utc,
    )
    ctx = _make_ctx(
        game_id=game_id,
        snapshot=snapshot,
        is_home=True,
        decision_time=decision_on,
    )
    result = signal.build(ctx)
    assert result is not None, (
        f"Expected a dict but got None for game_id={game_id} "
        f"snapshot={snapshot} on decision_date={game_date.date()}"
    )
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    # All 8 expected keys must be present.
    expected_keys = set(signal.emits)
    assert set(result.keys()) == expected_keys, (
        f"Key mismatch: got {set(result.keys())}, expected {expected_keys}"
    )

    # Every value must be a finite float in a plausible range.
    for key, val in result.items():
        assert isinstance(val, float), f"{key}: expected float, got {type(val)}"
        assert math.isfinite(val), f"{key}: non-finite value {val}"

    # Cumulative eFG% must be in [0.0, 1.0]
    efg = result["efg_cum"]
    assert 0.0 <= efg <= 1.0, f"efg_cum={efg} out of range"

    # TOV per possession is typically 0.05 – 0.30
    tov = result["tov_poss_cum"]
    assert 0.0 <= tov <= 0.60, f"tov_poss_cum={tov} out of range"

    # OREB% typically 0 – 0.65
    oreb = result["oreb_pct_cum"]
    assert 0.0 <= oreb <= 1.0, f"oreb_pct_cum={oreb} out of range"

    # FT rate (FTA/FGA) typically 0 – 1.0 (rarely above 0.6 in a game)
    ftr = result["ft_rate_cum"]
    assert 0.0 <= ftr <= 2.0, f"ft_rate_cum={ftr} out of range"


# ---------------------------------------------------------------------------
# Test 3: Missing context → None (not an exception)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs,desc", [
    ({"game_id": None, "snapshot": "endQ2", "is_home": True}, "game_id=None"),
    ({"game_id": "0022400001", "snapshot": None, "is_home": True}, "snapshot=None"),
    ({"game_id": "0022400001", "snapshot": "halftime", "is_home": True}, "invalid snapshot"),
    ({"game_id": "0022400001", "snapshot": "endQ2", "is_home": None}, "is_home=None"),
    ({"game_id": "FAKE999999", "snapshot": "endQ3", "is_home": False}, "unknown game_id"),
])
def test_missing_context_returns_none(kwargs, desc):
    """Missing or invalid context fields must return None, not raise."""
    signal = LiveFourFactors()
    decision_time = _dt.datetime(2025, 4, 1, 23, 59, 59, tzinfo=_dt.timezone.utc)
    ctx = AsOfContext(
        decision_time=decision_time,
        scope="live",
        **kwargs,
    )
    result = signal.build(ctx)
    assert result is None, f"[{desc}] Expected None, got {result!r}"


# ---------------------------------------------------------------------------
# Test 4: feature_names() matches emits
# ---------------------------------------------------------------------------

def test_feature_names_match_emits():
    signal = LiveFourFactors()
    expected = [f"{signal.name}__{k}" for k in signal.emits]
    assert signal.feature_names() == expected


# ---------------------------------------------------------------------------
# Test 5: hypothesis() contract
# ---------------------------------------------------------------------------

def test_hypothesis_contract():
    signal = LiveFourFactors()
    h = signal.hypothesis()
    assert isinstance(h, Hypothesis)
    assert h.name == "live_four_factors"
    assert h.target == "winprob"
    assert h.scope == "live"
    assert len(h.statement) > 20
    assert len(h.atlas_fields) >= 1


# ---------------------------------------------------------------------------
# Test 6: validate_output is consistent with build output
# ---------------------------------------------------------------------------

def test_validate_output_on_real_build():
    signal = LiveFourFactors()
    game_id, snapshot, game_date = _load_one_valid_game()
    decision_on = _dt.datetime.combine(
        game_date.date(), _dt.time(23, 59, 59), tzinfo=_dt.timezone.utc
    )
    ctx = _make_ctx(
        game_id=game_id, snapshot=snapshot, is_home=True, decision_time=decision_on
    )
    result = signal.build(ctx)
    assert signal.validate_output(result), f"validate_output failed on {result!r}"


# ---------------------------------------------------------------------------
# Test 7: home vs away sides differ (or at least don't crash)
# ---------------------------------------------------------------------------

def test_home_away_sides_are_distinct():
    signal = LiveFourFactors()
    game_id, snapshot, game_date = _load_one_valid_game()
    decision_on = _dt.datetime.combine(
        game_date.date(), _dt.time(23, 59, 59), tzinfo=_dt.timezone.utc
    )
    ctx_home = _make_ctx(game_id=game_id, snapshot=snapshot, is_home=True,
                         decision_time=decision_on, team="HOM", opp="AWY")
    ctx_away = _make_ctx(game_id=game_id, snapshot=snapshot, is_home=False,
                         decision_time=decision_on, team="AWY", opp="HOM")
    res_home = signal.build(ctx_home)
    res_away = signal.build(ctx_away)
    # Both should return dicts (not None)
    assert res_home is not None
    assert res_away is not None
    # The efg_cum values should be mirror images (home side vs away side)
    # efg_cum(home) == away's efg_diff + home's efg_cum = cross-validate
    # More simply: efg_diff home + efg_diff away = 0 (they are negatives)
    if res_home["efg_diff"] is not None and res_away["efg_diff"] is not None:
        assert abs(res_home["efg_diff"] + res_away["efg_diff"]) < 1e-9, (
            f"Home efg_diff {res_home['efg_diff']} + away {res_away['efg_diff']} "
            f"should sum to zero"
        )
