"""S48 tests for the additive tennis ``event_uid`` key.

Calibration infrastructure only -- no dollar, ROI, profit or edge claim here.
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.event_uid import (
    EVENT_UID, ODDS_PARQUET, SPINE_PARQUETS,
    add_odds_event_uid, add_spine_event_uid,
)

# The real collision the S03 lane named: one id, two different real matches.
_BRISBANE_AO_ID = "20150104-atp-2015-339-105449-105453-20"

_ODDS_COLUMNS_BEFORE_S48 = [
    "event_id", "date_td", "tour", "tournament_td", "round_td", "comment",
    "b365w", "b365l", "psw", "psl", "maxw", "maxl", "avgw", "avgl",
    "b365_p1", "b365_p2", "ps_p1", "ps_p2",
]


def _collision_fixture() -> pd.DataFrame:
    """The Brisbane / Australian Open pair, verbatim from odds.parquet."""
    return pd.DataFrame({
        "event_id": [_BRISBANE_AO_ID, _BRISBANE_AO_ID],
        "date_td": [pd.Timestamp("2015-01-07").date(), pd.Timestamp("2015-01-24").date()],
        "tour": ["atp", "atp"],
        "tournament_td": ["Brisbane International", "Australian Open"],
        "round_td": ["2nd Round", "3rd Round"],
        "ps_p1": [1.53, 2.10],
        "ps_p2": [2.67, 1.75],
    })


def test_brisbane_and_australian_open_get_different_event_uid():
    out = add_odds_event_uid(_collision_fixture())
    assert out[EVENT_UID].nunique() == 2
    # The row closest to the tourney start date encoded in the id keeps the id.
    assert out.loc[0, EVENT_UID] == _BRISBANE_AO_ID
    assert out.loc[1, EVENT_UID] == f"{_BRISBANE_AO_ID}@20150124-australianopen"


def test_odds_derivation_is_additive_on_a_fixture():
    before = _collision_fixture()
    after = add_odds_event_uid(before)
    assert list(after.columns) == [*before.columns, EVENT_UID]
    for column in before.columns:
        assert after[column].equals(before[column])


def test_row_order_and_uid_are_independent_of_input_order():
    shuffled = _collision_fixture().iloc[::-1].reset_index(drop=True)
    out = add_odds_event_uid(shuffled)
    assert out.loc[1, EVENT_UID] == _BRISBANE_AO_ID          # the Brisbane row
    assert out.loc[0, EVENT_UID].endswith("@20150124-australianopen")


def test_spine_derivation_refuses_a_colliding_event_id():
    with pytest.raises(ValueError, match="not unique"):
        add_spine_event_uid(pd.DataFrame({"event_id": ["a", "a"]}))


@pytest.mark.skipif(not ODDS_PARQUET.exists(), reason="local odds.parquet absent")
def test_real_odds_parquet_has_zero_duplicate_event_uid():
    odds = pd.read_parquet(ODDS_PARQUET)
    assert list(odds.columns) == [*_ODDS_COLUMNS_BEFORE_S48, EVENT_UID]
    assert len(odds) == 33952
    assert odds["event_id"].nunique() == 33859          # 93 ids name two matches
    assert odds[EVENT_UID].nunique() == len(odds)       # the collision is gone
    pair = odds.loc[odds["event_id"] == _BRISBANE_AO_ID, EVENT_UID]
    assert pair.nunique() == 2


@pytest.mark.skipif(not all(p.exists() for p in SPINE_PARQUETS),
                    reason="local spine parquets absent")
def test_real_spines_carry_event_uid_equal_to_event_id():
    for path, rows in zip(SPINE_PARQUETS, (30616, 11270)):
        spine = pd.read_parquet(path)
        assert len(spine) == rows
        assert list(spine.columns)[-1] == EVENT_UID
        assert spine[EVENT_UID].equals(spine["event_id"].astype(str))
        assert spine[EVENT_UID].nunique() == rows
