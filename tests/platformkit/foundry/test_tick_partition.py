"""S121: the tick-grain screen/verdict partition -- a ticker spanning two ISO weeks, the
default's byte-identical reproduction of the ticker rule, and tick-level disjointness.

Run: python -m pytest tests/platformkit/foundry/test_tick_partition.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.foundry import tick_partition as T
from scripts.platformkit.foundry.ingame_screen import partition

_SUM = "home_score={h} away_score={a} inning={i}"


def _rows() -> tuple:
    """Two tickers. STRADDLE first-ticks 2026-07-05 (W27) and parks a SECOND real game on
    07-06 (W28, inning back to 1); CLEAN lives entirely inside 07-06."""
    spec = [("STRADDLE", "2026-07-05T20:00:00Z", 1, 0, 0),
            ("STRADDLE", "2026-07-05T22:00:00Z", 7, 2, 1),
            ("STRADDLE", "2026-07-06T20:00:00Z", 1, 0, 0),
            ("STRADDLE", "2026-07-06T23:00:00Z", 8, 3, 4),
            ("CLEAN", "2026-07-06T19:00:00Z", 1, 0, 0),
            ("CLEAN", "2026-07-06T21:00:00Z", 5, 1, 1)]
    rows = pd.DataFrame({"row_id": list(range(len(spec))),
                         "game": [s[0] for s in spec], "ts": [s[1] for s in spec],
                         "game_date": [min(x[1][:10] for x in spec if x[0] == s[0]) for s in spec]})
    summaries = [_SUM.format(i=s[2], h=s[3], a=s[4]) for s in spec]
    return rows, summaries


def test_ticker_week_default_keeps_every_tick_of_a_straddling_ticker():
    rows, summaries = _rows()
    part = partition(rows)
    side, meta = T.screen_side(rows, part, state_summary=summaries)
    assert meta["mode"] == "ticker_week" and meta["real_game_purged"] is False
    # STRADDLE's game-first date is in W27 -> the whole ticker, W28 ticks included, is screened.
    assert sorted(side["row_id"]) == [0, 1, 2, 3]
    assert set(side["ts"].str[:10]) == {"2026-07-05", "2026-07-06"}


def test_tick_week_drops_the_ticks_dated_in_the_verdict_week():
    rows, summaries = _rows()
    part = partition(rows)
    side, meta = T.screen_side(rows, part, mode="tick_week", state_summary=summaries)
    assert meta["mode"] == "tick_week" and meta["real_game_purged"] is True
    assert sorted(side["row_id"]) == [0, 1]                 # the W28 half of STRADDLE is gone
    assert meta["n_screen_ticks"] == 2 and meta["n_verdict_ticks"] == 4
    assert meta["n_dropped_vs_ticker_week"] == 2


def test_the_two_tick_sides_are_disjoint_and_exhaustive():
    rows, summaries = _rows()
    tick = T.tick_partition(rows, state_summary=summaries)
    assert not (tick.screen_ids & tick.verdict_ids)
    assert tick.screen_ids | tick.verdict_ids == {str(i) for i in rows["row_id"]}


def test_a_real_game_is_never_split_across_the_boundary():
    """A single real game running past midnight into the next ISO week stays whole: every one
    of its ticks is blocked by the real game's FIRST tick, so no cluster sits on both sides."""
    spec = [("LATE", "2026-07-05T23:00:00Z", 1), ("LATE", "2026-07-06T01:30:00Z", 8),
            ("OTHER", "2026-07-06T19:00:00Z", 1), ("OTHER", "2026-07-06T21:00:00Z", 6)]
    rows = pd.DataFrame({"row_id": list(range(4)), "game": [s[0] for s in spec],
                         "ts": [s[1] for s in spec],
                         "game_date": ["2026-07-05", "2026-07-05", "2026-07-06", "2026-07-06"]})
    summaries = [_SUM.format(i=s[2], h=1, a=0) for s in spec]
    side, meta = T.screen_side(rows, partition(rows), mode="tick_week", state_summary=summaries)
    assert sorted(side["row_id"]) == [0, 1]      # the 01:30 tick follows its own real game
    assert meta["n_screen_ticks"] == 2


def test_env_var_selects_the_mode_and_an_unknown_mode_is_refused(monkeypatch):
    assert T.partition_mode() == "ticker_week"
    monkeypatch.setenv(T.ENV_VAR, "tick_week")
    assert T.partition_mode() == "tick_week"
    assert T.partition_mode("ticker_week") == "ticker_week"     # the argument still wins
    with pytest.raises(ValueError):
        T.partition_mode("by_month")
