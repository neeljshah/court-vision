"""Per-file test for domains.soccer.player_minutes (network-free).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_player_minutes.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.player_minutes import expected_minutes


def _row(pid, date, starter, minutes):
    return {
        "player_id": pid,
        "date": date,
        "starter": starter,
        "minutes": minutes,
    }


def _df():
    return pd.DataFrame([
        # Pure starter.
        _row("START", "2026-06-01", True, 90),
        _row("START", "2026-06-05", True, 88),
        # Pure sub (always came on, ~20 min).
        _row("SUB", "2026-06-01", False, 18),
        _row("SUB", "2026-06-05", False, 22),
        # Mixed: started once, subbed once.
        _row("MIX", "2026-06-01", True, 90),
        _row("MIX", "2026-06-05", False, 30),
    ])


def test_pure_starter_high_minutes():
    em = expected_minutes(_df(), "START", "2026-06-10")
    assert em["status"] == "ok"
    assert em["start_prob"] == 1.0
    assert em["e_minutes"] >= 85.0


def test_pure_sub_low_minutes():
    em = expected_minutes(_df(), "SUB", "2026-06-10")
    assert em["status"] == "ok"
    assert em["start_prob"] == 0.0
    # avg sub minutes = (18+22)/2 = 20.
    assert abs(em["e_minutes"] - 20.0) < 1e-9


def test_mixed_between_sub_and_starter():
    em = expected_minutes(_df(), "MIX", "2026-06-10")
    assert em["status"] == "ok"
    assert abs(em["start_prob"] - 0.5) < 1e-9
    # 0.5*85 + 0.5*30 = 57.5.
    assert abs(em["e_minutes"] - 57.5) < 1e-9


def test_no_history_unknown():
    em = expected_minutes(_df(), "GHOST", "2026-06-10")
    assert em["status"] == "unknown"
    assert em["e_minutes"] is None


def test_leak_free_future_excluded():
    df = _df()
    before = expected_minutes(df, "SUB", "2026-06-10")
    # Add future + on-date rows where SUB suddenly always starts; must be ignored.
    leak = pd.DataFrame([
        _row("SUB", "2026-06-10", True, 90),
        _row("SUB", "2026-07-01", True, 90),
    ])
    after = expected_minutes(pd.concat([df, leak], ignore_index=True), "SUB", "2026-06-10")
    assert before == after
