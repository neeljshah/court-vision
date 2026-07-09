"""Per-file tests for pitch_engine.validate -- pure helpers (no parquet read)."""
import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.validate import _logloss, _lineups


def test_logloss_perfect_and_uniform():
    assert _logloss(np.ones(5)) == 0.0                      # perfect
    ll = _logloss(np.full(4, 0.25))
    assert abs(ll - np.log(4)) < 1e-9                       # uniform over 4


def test_lineups_order_and_starters():
    gpa = pd.DataFrame({
        "inning_topbot": ["Top", "Top", "Top", "Bot", "Bot"],
        "batter": [11, 12, 11, 21, 22],
        "pitcher": [90, 90, 90, 80, 80],
        "stand": ["R", "L", "R", "R", "L"],
        "p_throws": ["R", "R", "R", "L", "L"],
    })
    ab, hb, hp, ap, stand, throw = _lineups(gpa)
    assert ab == [11, 12]           # away batters, first-appearance order, deduped
    assert hb == [21, 22]
    assert hp == 90 and ap == 80    # home pitcher fields in Top; away in Bot
    assert throw[90] == "R" and stand[22] == "L"
