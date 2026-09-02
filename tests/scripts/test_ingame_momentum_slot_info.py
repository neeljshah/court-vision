"""S69: ``_build_slot_info`` after the iterrows removal.

The row loop was 89 percent of the per-game profile and pushed the builder past
the 300 s refresh timeout. The replacement prepares the columns once and keeps
the ``Counter`` tally, so these tests pin the three semantics that a naive
vectorisation would have silently changed:

  * slot 0 / missing player_id contributes nothing;
  * a jersey of ``"12.0"`` counts as ``"12"`` and a non-numeric one is dropped;
  * a NaN ``team_abbrev`` does NOT fall back to ``team`` (NaN is truthy in
    Python, so ``row["team_abbrev"] or row["team"]`` kept the NaN), while an
    empty-string abbrev does.

Calibration/audit fixture only: no metric, no bar, no market claim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import build_ingame_momentum as im


def _slot_info(frame: pd.DataFrame):
    jersey, team, _ = im._build_slot_info(frame, None)
    return jersey, team


def test_zero_and_missing_slots_are_dropped():
    frame = pd.DataFrame({
        "player_id": [0, np.nan, 7, 7],
        "jersey_number": ["3", "4", "23", "23"],
        "team_abbrev": ["LAL", "LAL", "BOS", "BOS"],
    })
    jersey, team = _slot_info(frame)
    assert jersey == {7: "23"}
    assert team == {7: "BOS"}


def test_jersey_is_normalised_and_non_numeric_dropped():
    frame = pd.DataFrame({
        "player_id": [5, 5, 5, 9],
        "jersey_number": ["12.0", "12", "  12 ", "not-a-number"],
        "team_abbrev": ["NYK"] * 4,
    })
    jersey, _ = _slot_info(frame)
    assert jersey == {5: "12"}
    assert 9 not in jersey


def test_nan_abbrev_does_not_fall_back_but_empty_string_does():
    frame = pd.DataFrame({
        "player_id": [1, 2],
        "jersey_number": ["1", "2"],
        "team_abbrev": [np.nan, ""],
        "team": ["MIA", "MIA"],
    })
    _, team = _slot_info(frame)
    assert 1 not in team, "NaN is truthy: the row loop kept it and dropped the row"
    assert team[2] == "MIA"


def test_team_column_alone_is_used_when_abbrev_absent():
    frame = pd.DataFrame({
        "player_id": [4, 4],
        "jersey_number": ["8", "8"],
        "team": ["GSW", "GSW"],
    })
    _, team = _slot_info(frame)
    assert team == {4: "GSW"}


def test_empty_frame_is_not_an_error():
    frame = pd.DataFrame({"player_id": [], "jersey_number": [], "team_abbrev": []})
    assert _slot_info(frame) == ({}, {})
