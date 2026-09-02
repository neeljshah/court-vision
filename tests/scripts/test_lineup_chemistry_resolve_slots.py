"""S69: ``resolve_slots`` after the iterrows removal.

The tally that feeds slot resolution was a per-frame-row pandas Series loop over
every game's full tracking table. These tests pin the four semantics a naive
vectorisation would have changed:

  * slot 0 / NaN player_id contributes nothing;
  * a jersey of ``"12.0"`` counts as ``"12"``, a non-numeric one is dropped;
  * a tracking ``player_name`` containing ``"?"`` (an unresolved slot label) is
    dropped, as are ``"nan"``, ``""`` and ``"None"``;
  * the jersey channel wins over the tracking-name channel.

Calibration/audit fixture only: no metric, no bar, no market claim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import build_lineup_chemistry as lc


def _frame(rows):
    return pd.DataFrame(rows, columns=["player_id", "jersey_number", "player_name"])


def test_zero_and_nan_slots_contribute_nothing():
    df = _frame([[0, "23", "Real Player"], [np.nan, "23", "Real Player"]])
    assert lc.resolve_slots(df, {}, {"real player": 7}, {}) == {}


def test_jersey_channel_normalises_and_wins():
    df = _frame([[1, "12.0", "Wrong Name"], [1, "12", "Wrong Name"]])
    out = lc.resolve_slots(df, {"12": "Right Name"}, {"right name": 99}, {})
    assert out == {1: (99, "Right Name")}


def test_non_numeric_jersey_falls_through_to_the_name_channel():
    df = _frame([[2, "not-a-number", "Named Player"]])
    out = lc.resolve_slots(df, {"12": "Right Name"}, {"named player": 55}, {})
    assert out == {2: (55, "Named Player")}


def test_placeholder_names_are_dropped():
    for bad in ("#?", "Player ?", "nan", "None", ""):
        df = _frame([[3, "", bad]])
        assert lc.resolve_slots(df, {}, {lc._norm(bad): 1}, {}) == {}, bad


def test_unresolvable_slot_is_omitted_not_invented():
    df = _frame([[4, "77", "Unknown Person"]])
    assert lc.resolve_slots(df, {}, {}, {}) == {}
