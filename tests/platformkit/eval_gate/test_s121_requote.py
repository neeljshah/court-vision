"""S121 re-quote: which archived ticks survive the tick-clean partition, and the paired-loss
arithmetic the re-quote uses. Archive-free -- every fixture is built here.

Run: python -m pytest tests/platformkit/eval_gate/test_s121_requote.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.eval_gate import s121_requote as R

_SUM = "home_score=1 away_score=0 inning={i}"


def _series(spec) -> pd.DataFrame:
    """One archived row per (feature, tick): the columns the S82/S117 series files carry."""
    rows = []
    for feature in ("f1", "f2"):
        for tick, (game, ts, y, p_null, p_cand) in enumerate(spec):
            rows.append({"feature": feature, "tick_index": tick, "game": game, "timestamp": ts,
                         "y": y, "p_e4": 0.5, "p_null": p_null, "p_candidate": p_cand,
                         "market": 0.5, "x": 0.0})
    return pd.DataFrame(rows)


_SPEC = [("A", "2026-07-05T20:00:00Z", 1.0, 0.4, 0.6), ("A", "2026-07-05T22:00:00Z", 1.0, 0.4, 0.6),
         ("A", "2026-07-06T20:00:00Z", 0.0, 0.6, 0.4), ("B", "2026-07-06T19:00:00Z", 0.0, 0.6, 0.4)]


def test_single_block_archive_drops_nothing_and_says_so():
    """S117's archives all sit in one ISO week; a one-block partition is reported, not forced."""
    one_week = [(g, t, y, n, c) for g, t, y, n, c in _SPEC if t[:10] == "2026-07-06"]
    clean = R.clean_tick_ids(_series(one_week))
    assert clean["single_block"] is True and clean["n_dropped"] == 0
    assert clean["keep"] == {0, 1}


def test_tick_week_drops_the_ticks_dated_in_the_verdict_week():
    clean = R.clean_tick_ids(_series(_SPEC))
    assert clean["single_block"] is False
    assert clean["tick_weeks"] == ["2026-W27", "2026-W28"]
    assert clean["screen_weeks"] == ["2026-W27"]      # only the first block is the screen side
    assert clean["keep"] == {0, 1} and clean["n_dropped"] == 2
    assert clean["real_game_purged"] is False


def test_a_real_game_running_past_midnight_is_kept_whole():
    """Ticker A's third tick is the SAME real game (inning still rising), so the S106 purge
    keeps it on the screen side rather than cutting the game in half."""
    spec = [("A", "2026-07-05T23:00:00Z", 1.0, 0.4, 0.6), ("A", "2026-07-06T01:00:00Z", 1.0, 0.4, 0.6),
            ("B", "2026-07-06T19:00:00Z", 0.0, 0.6, 0.4), ("B", "2026-07-06T21:00:00Z", 0.0, 0.6, 0.4)]
    innings = [1, 8, 1, 6]
    clean = R.clean_tick_ids(_series(spec), state_summary=[_SUM.format(i=i) for i in innings])
    assert clean["keep"] == {0, 1} and clean["real_game_purged"] is True
    assert clean["kept_outside_screen_week"] == 1      # the 01:00 tick, kept with its own game


def test_score_series_reproduces_the_paired_loss_arithmetic():
    rows = R.score_series(_series(_SPEC))
    assert [r["feature"] for r in rows] == ["f1", "f2"]
    for row in rows:
        assert row["n_ticks"] == 4 and row["n_games"] == 2
        # every tick: null loss 0.36, candidate loss 0.16 -> improvement 0.20, well under no bar
        assert abs(row["improvement_vs_null"] - 0.20) < 1e-12
        assert row["bar"] == R.BAR and row["by_game"]["n_clusters"] == 2
