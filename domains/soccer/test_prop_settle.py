"""Per-file test for domains.soccer.prop_settle (network-free, canned df).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_prop_settle.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.prop_settle import realized_stat, settle_prop


def _canned_df():
    # One player, one match. Cards = yellowCards + redCards = 1 + 1 = 2.
    return pd.DataFrame(
        [
            {
                "event_id": "E1",
                "player_id": "P1",
                "totalShots": 3.0,
                "shotsOnTarget": 1.0,
                "yellowCards": 1.0,
                "redCards": 1.0,
                "goalAssists": 0.0,
            }
        ]
    )


def test_over_win_and_loss():
    assert settle_prop(3.0, 2.5, "over")["result"] == "win"
    assert settle_prop(2.0, 2.5, "over")["result"] == "loss"


def test_under_win_and_loss():
    assert settle_prop(1.0, 2.5, "under")["result"] == "win"
    assert settle_prop(4.0, 2.5, "under")["result"] == "loss"


def test_integer_line_push():
    assert settle_prop(2.0, 2.0, "over")["result"] == "push"
    assert settle_prop(2.0, 2.0, "under")["result"] == "push"


def test_half_line_never_pushes():
    # No realized==line possible on a .5 line; both sides resolve to win/loss.
    assert settle_prop(2.0, 1.5, "over")["result"] == "win"
    assert settle_prop(1.0, 1.5, "over")["result"] == "loss"


def test_missing_is_pending():
    assert settle_prop(None, 1.5, "over")["result"] == "pending"


def test_realized_stat_sums_multi_column_cards():
    df = _canned_df()
    assert realized_stat(df, "P1", "E1", "Cards") == 2.0
    assert realized_stat(df, "P1", "E1", "Shots") == 3.0


def test_realized_stat_missing_returns_none():
    df = _canned_df()
    assert realized_stat(df, "NOPE", "E1", "Shots") is None
    assert realized_stat(df, "P1", "NOPE", "Shots") is None
    assert realized_stat(df, "P1", "E1", "BogusStat") is None


def test_realized_stat_nan_column_is_missing_not_zero():
    # HONESTY: a row that EXISTS but whose mapped stat column is NaN (DNP / not
    # scraped) must be treated as MISSING (None), NOT fabricated as a realized 0.
    df = pd.DataFrame(
        [{"event_id": "E1", "player_id": "P1", "totalShots": float("nan")}]
    )
    assert realized_stat(df, "P1", "E1", "Shots") is None


def test_realized_stat_genuine_zero_grades_as_zero():
    # A genuinely-recorded 0 (player played, took 0 shots) is a REAL 0, not None.
    df = pd.DataFrame(
        [{"event_id": "E1", "player_id": "P1", "totalShots": 0.0}]
    )
    assert realized_stat(df, "P1", "E1", "Shots") == 0.0


def test_realized_stat_all_nan_multicol_is_missing():
    # Cards = yellowCards + redCards; if BOTH are NaN -> missing (None).
    df = pd.DataFrame(
        [{"event_id": "E1", "player_id": "P1",
          "yellowCards": float("nan"), "redCards": float("nan")}]
    )
    assert realized_stat(df, "P1", "E1", "Cards") is None
    # But if ONE column has a real value, that real value is the realized count.
    df2 = pd.DataFrame(
        [{"event_id": "E1", "player_id": "P1",
          "yellowCards": 1.0, "redCards": float("nan")}]
    )
    assert realized_stat(df2, "P1", "E1", "Cards") == 1.0
