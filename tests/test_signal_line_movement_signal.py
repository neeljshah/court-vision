"""tests/test_signal_line_movement_signal.py — unit tests for LineMovementSignal.

Tests
-----
1. Leak-safety assertion: build() must NOT return a non-None value when the
   decision_time is set *before* any line was posted (all captured_at rows
   are in the future relative to decision_time).  If it fires with a future-
   stamped line it violates the leak contract.

2. Value-sanity assertion: with a realistic two-snapshot CSV (opener then
   current with a real spread move), build() returns a dict with the expected
   keys, numerically sane ranges, and correct sign/magnitude.

3. Missing-file returns None: when no pin_mainline CSV exists for the game's
   date, build() returns None (DEFER by coverage), not an exception.

4. hypothesis() contract: the returned Hypothesis has the correct name, target,
   and scope.

5. validate_output() passes for both None and a well-formed dict.
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
import tempfile
from pathlib import Path
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Helpers to create a minimal pin_mainline CSV in a temp directory
# ---------------------------------------------------------------------------

_GAME_ID = 9999001


def _make_mainline_csv(path: Path,
                       opener_ts: str,
                       current_ts: str,
                       spread_opener: float = -3.5,
                       spread_current: float = -5.0,
                       ml_home_opener: int = -147,
                       ml_home_current: int = -165,
                       total_opener: float = 212.0,
                       total_current: float = 214.0) -> None:
    """Write a minimal two-snapshot pin_mainline CSV to ``path``."""
    rows = []
    for ts, spread, ml_home, total in [
        (opener_ts, spread_opener, ml_home_opener, total_opener),
        (current_ts, spread_current, ml_home_current, total_current),
    ]:
        # moneyline home
        rows.append({"captured_at": ts, "book": "pin", "game_id": _GAME_ID,
                     "market_type": "moneyline", "side": "home", "line": "",
                     "price": ml_home, "home_team": "Oklahoma City Thunder",
                     "away_team": "San Antonio Spurs",
                     "start_time": "2026-05-30T00:05:00Z"})
        # spread home
        rows.append({"captured_at": ts, "book": "pin", "game_id": _GAME_ID,
                     "market_type": "spread", "side": "home", "line": spread,
                     "price": -110, "home_team": "Oklahoma City Thunder",
                     "away_team": "San Antonio Spurs",
                     "start_time": "2026-05-30T00:05:00Z"})
        # total over
        rows.append({"captured_at": ts, "book": "pin", "game_id": _GAME_ID,
                     "market_type": "total", "side": "over", "line": total,
                     "price": -110, "home_team": "Oklahoma City Thunder",
                     "away_team": "San Antonio Spurs",
                     "start_time": "2026-05-30T00:05:00Z"})
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Fixture: patch the lines directory to a temp dir
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_lines_dir(tmp_path, monkeypatch):
    """Override signals.line_movement_signal._LINES_DIR to use a temp dir."""
    import signals.line_movement_signal as mod
    monkeypatch.setattr(mod, "_LINES_DIR", tmp_path)
    # Also clear the module-level cache so each test starts fresh
    mod._mainline_cache.clear()
    yield tmp_path
    mod._mainline_cache.clear()


# ---------------------------------------------------------------------------
# Test 1 — LEAK-SAFETY: decision_time BEFORE any captured_at → None
# ---------------------------------------------------------------------------

def test_leak_safety_no_future_data(tmp_lines_dir):
    """build() must return None when decision_time is before all posted lines.

    This is the canonical leak-safety assertion: if decision_time is set to
    a moment earlier than the opener captured_at, no line has been posted yet
    and the signal must return None, not a value derived from future rows.
    """
    import signals.line_movement_signal as mod
    from signals.line_movement_signal import LineMovementSignal
    from src.loop.signal import AsOfContext

    # Write a CSV whose earliest line is at 14:44 on 2026-05-30
    date_str = "2026-05-30"
    csv_path = tmp_lines_dir / f"{date_str}_pin_mainline.csv"
    _make_mainline_csv(
        csv_path,
        opener_ts="2026-05-30T14:44",
        current_ts="2026-05-30T15:30",
    )

    # Decision time is 13:00 — BEFORE any line is posted
    decision_time = _dt.datetime(2026, 5, 30, 13, 0, 0)

    ctx = AsOfContext(
        decision_time=decision_time,
        game_id=str(_GAME_ID),
        game_date=date_str,
        team="OKC",
        opp="SAS",
        is_home=True,
        scope="pregame",
    )

    signal = LineMovementSignal(store=None)
    result = signal.build(ctx)

    # The current_sub filter (captured_at <= 13:00) will be empty for all
    # markets → _extract_opener_current returns (opener, None) for spread.
    # build() returns None when spread current is None.
    assert result is None, (
        f"LEAK VIOLATION: build() returned {result!r} with decision_time before "
        "any line was posted.  Signal must not use future data."
    )


# ---------------------------------------------------------------------------
# Test 2 — VALUE SANITY: realistic two-snapshot scenario
# ---------------------------------------------------------------------------

def test_value_sanity_spread_move(tmp_lines_dir):
    """build() emits correct numeric values for a known spread/ml/total move.

    Scenario: opener spread = −3.5 (home favoured by 3.5), current = −5.0
    (home strengthened).  spread_move should be −5.0 − (−3.5) = −1.5.
    ml_prob_move should be positive (home getting shorter odds).
    total_move should be 214 − 212 = +2.0.
    line_speed should be positive.
    """
    from signals.line_movement_signal import LineMovementSignal
    from src.loop.signal import AsOfContext

    date_str = "2026-05-30"
    csv_path = tmp_lines_dir / f"{date_str}_pin_mainline.csv"
    _make_mainline_csv(
        csv_path,
        opener_ts="2026-05-30T14:44",
        current_ts="2026-05-30T15:30",
        spread_opener=-3.5,
        spread_current=-5.0,
        ml_home_opener=-147,
        ml_home_current=-170,
        total_opener=212.0,
        total_current=214.0,
    )

    # decision_time is AFTER current snapshot (15:30) → sees both rows
    decision_time = _dt.datetime(2026, 5, 30, 16, 0, 0)

    ctx = AsOfContext(
        decision_time=decision_time,
        game_id=str(_GAME_ID),
        game_date=date_str,
        team="OKC",
        opp="SAS",
        is_home=True,
        scope="pregame",
    )

    signal = LineMovementSignal(store=None)
    result = signal.build(ctx)

    assert result is not None, "build() returned None but should have emitted sub-features"
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    required_keys = {"spread_move", "ml_prob_move", "total_move", "line_speed"}
    assert required_keys.issubset(set(result.keys())), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )

    # spread_move = current − opener = −5.0 − (−3.5) = −1.5
    assert abs(result["spread_move"] - (-1.5)) < 1e-6, (
        f"spread_move wrong: expected −1.5, got {result['spread_move']}"
    )

    # ml_prob_move: home going from -147 to -170 → prob increases
    assert result["ml_prob_move"] > 0.0, (
        f"ml_prob_move should be positive (home getting shorter), got {result['ml_prob_move']}"
    )
    assert result["ml_prob_move"] < 0.20, (
        f"ml_prob_move implausibly large: {result['ml_prob_move']}"
    )

    # total_move = 214 − 212 = +2.0
    assert abs(result["total_move"] - 2.0) < 1e-6, (
        f"total_move wrong: expected 2.0, got {result['total_move']}"
    )

    # line_speed > 0 (spread moved and some time elapsed)
    assert result["line_speed"] > 0.0, f"line_speed should be > 0, got {result['line_speed']}"
    assert result["line_speed"] <= 5.0, f"line_speed capped at 5.0, got {result['line_speed']}"

    # validate_output passes
    assert signal.validate_output(result), "validate_output failed on well-formed dict"


# ---------------------------------------------------------------------------
# Test 3 — MISSING FILE returns None
# ---------------------------------------------------------------------------

def test_missing_file_returns_none(tmp_lines_dir):
    """When no pin_mainline CSV exists for the game date, build() returns None."""
    from signals.line_movement_signal import LineMovementSignal
    from src.loop.signal import AsOfContext

    ctx = AsOfContext(
        decision_time=_dt.datetime(2026, 5, 28, 12, 0, 0),
        game_id="9999999",
        game_date="2026-05-28",
        scope="pregame",
    )

    signal = LineMovementSignal(store=None)
    result = signal.build(ctx)

    assert result is None, f"Expected None for missing file, got {result!r}"


# ---------------------------------------------------------------------------
# Test 4 — hypothesis() contract
# ---------------------------------------------------------------------------

def test_hypothesis_contract():
    """hypothesis() returns a Hypothesis with correct name/target/scope."""
    from signals.line_movement_signal import LineMovementSignal
    from src.loop.signal import Hypothesis

    signal = LineMovementSignal(store=None)
    h = signal.hypothesis()

    assert isinstance(h, Hypothesis)
    assert h.name == "line_movement_signal"
    assert h.target == "winprob"
    assert h.scope == "both"
    assert h.source == "seed"
    assert "team_public_betting_bias" in h.atlas_fields


# ---------------------------------------------------------------------------
# Test 5 — validate_output covers None and well-formed dict
# ---------------------------------------------------------------------------

def test_validate_output_none_and_dict():
    """validate_output() accepts None (neutral) and a well-formed sub-feature dict."""
    from signals.line_movement_signal import LineMovementSignal

    signal = LineMovementSignal(store=None)

    # None is always valid
    assert signal.validate_output(None) is True

    # Well-formed dict
    good = {
        "spread_move": -1.5,
        "ml_prob_move": 0.03,
        "total_move": 2.0,
        "line_speed": 0.7,
    }
    assert signal.validate_output(good) is True

    # Non-numeric value fails
    bad = {"spread_move": "oops", "ml_prob_move": 0.0, "total_move": 0.0, "line_speed": 0.0}
    assert signal.validate_output(bad) is False
