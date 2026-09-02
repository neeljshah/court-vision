"""Focused tests for the tennis decimal-close join (ATP/WTA, de-leaked p1/p2)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.combo.corpus_cache import load_gate_corpus
from scripts.platformkit.eval_gate.close_join import (
    JoinSpec, close_column, coverage_report, gate_corpus_states,
)

_SPEC = JoinSpec(
    "tennis", "event_id", "date", "ps_p1", "ps_p2", "b365_p1", "b365_p2",
    "p1_win", "p2_win", price_suffixes=("_p1", "_p2"),
)

# The full spines the S03 acceptance rule fixes as the per-unit denominators.
_SPINE = {"ATP": 30616, "WTA": 11270}


def test_winner_loser_columns_are_refused():
    leaky = JoinSpec("tennis", "event_id", "date", "psw", "psl", "b365w", "b365l",
                     "p1_win", "p2_win", price_suffixes=("_p1", "_p2"))
    frame = pd.DataFrame({"psw": [2.0], "psl": [2.0], "b365w": [2.0], "b365l": [2.0]})
    with pytest.raises(ValueError, match="leaky winner/loser"):
        close_column(frame, leaky)


def test_non_p1_p2_suffix_is_refused():
    odd = JoinSpec("tennis", "event_id", "date", "ps_home", "ps_p2", "b365_p1", "b365_p2",
                   "p1_win", "p2_win", price_suffixes=("_p1", "_p2"))
    with pytest.raises(ValueError, match="must end with"):
        close_column(pd.DataFrame({"ps_home": [2.0], "ps_p2": [2.0]}), odd)


def test_null_pinnacle_price_joins_through_the_b365_fallback():
    frame = pd.DataFrame({
        "ps_p1": [2.0, np.nan], "ps_p2": [2.0, np.nan],
        "b365_p1": [5.0, 2.0], "b365_p2": [5.0, 4.0],
    })
    result = close_column(frame, _SPEC)
    assert result.iloc[0] == 0.5              # ps_* wins when present
    assert result.iloc[1] == 2.0 / 3.0        # b365_* fallback carries the null row
    assert result.attrs["null_close_count"] == 0
    assert result.attrs["valid_close_count"] == 2


def test_bad_tennis_prices_are_dropped_and_counted():
    frame = pd.DataFrame({
        "ps_p1": [2.0, 1.0, np.nan], "ps_p2": [2.0, 2.0, 2.0],
        "b365_p1": [np.nan, np.nan, np.nan], "b365_p2": [np.nan, np.nan, np.nan],
    })
    result = close_column(frame, _SPEC)
    assert result.notna().sum() == 1
    assert result.attrs["bad_price_drop_count"] == 1
    assert result.attrs["null_close_count"] == 1


def test_coverage_report_keys_and_full_spine_denominators():
    report = coverage_report("tennis")
    assert report["vintage"] == "SYNTHETIC"          # S34
    assert report["by_year"] and report["by_corpus_unit"]
    assert set(report["by_corpus_unit"]) == set(_SPINE)
    assert report["unjoined"] > 0
    for unit, spine_rows in _SPINE.items():
        block = report["by_corpus_unit"][unit]
        # S35: the FULL spine is the denominator, so a 1.0 rate is impossible here.
        assert block["denominator"] == spine_rows
        assert block["joined"] < spine_rows
        assert block["join_rate"] < 1.0
        assert block["brier_devig_close"] < block["brier_p_base"]
    assert sum(b["denominator"] for b in report["by_corpus_unit"].values()) == report["denominator"]
    assert sum(b["denominator"] for b in report["by_year"].values()) == report["denominator"]


def test_event_uid_key_is_opt_in_and_removes_the_ambiguous_drop():
    """S48: the default key is untouched; ``event_uid`` retires the collision."""
    default = coverage_report("tennis")
    opt_in = coverage_report("tennis", key="event_uid")

    # Default reads exactly what the S03 landing measured.
    assert default["join_key"] == "event_id"
    assert default["ambiguous_event_id_drop_count"] == 186
    assert default["by_corpus_unit"]["ATP"]["joined"] == 25764
    assert default["by_corpus_unit"]["WTA"]["joined"] == 8002

    # Opt-in: 93 spine rows recover their own price row, none is mislabelled.
    assert opt_in["join_key"] == "event_uid"
    assert opt_in["ambiguous_event_id_drop_count"] == 0
    assert opt_in["by_corpus_unit"]["ATP"]["joined"] == 25831
    assert opt_in["by_corpus_unit"]["WTA"]["joined"] == 8028
    for unit, spine_rows in _SPINE.items():
        block = opt_in["by_corpus_unit"][unit]
        assert block["denominator"] == spine_rows      # S35 denominator unmoved
        assert block["join_rate"] < 1.0
        assert block["brier_devig_close"] < block["brier_p_base"]
    assert opt_in["denominator"] == default["denominator"] == 41886
    assert opt_in["joined"] - default["joined"] == 93


def test_states_are_monotone_in_event_date_within_each_corpus_unit():
    """S50: the tennis states pass is already chronological, ATP and WTA both.

    `gate_corpus_states` sorts globally by the spine `date`; this pins BOTH facts
    the S50 row needs -- that spine date IS the corpus `event_date` on every
    emitted state, and that the emitted order never steps backwards inside a
    corpus_unit. The gate corpus's own row order does step backwards at the
    ATP->WTA boundary (S44); the states do not, so no per-unit re-ordering was
    needed here.
    """
    states = pd.DataFrame(gate_corpus_states("tennis", "2014-01-01", "2026-12-31"))
    corpus = load_gate_corpus("tennis")[["event_id", "corpus_unit", "event_date"]].copy()
    corpus["event_id"] = corpus["event_id"].astype(str)
    merged = states.merge(corpus, left_on="game_id", right_on="event_id",
                          how="left", validate="one_to_one")

    assert len(merged) == 33685 and merged["corpus_unit"].notna().all()
    event_date = pd.to_datetime(merged["event_date"]).dt.date.astype(str)
    assert int((event_date == merged["game_date"]).sum()) == len(merged)
    assert set(merged["corpus_unit"]) == {"ATP", "WTA"}
    for unit, block in merged.groupby("corpus_unit", sort=True):
        assert block["game_date"].is_monotonic_increasing, unit
    assert (merged["vintage"] == "SYNTHETIC").all()          # S34, unmoved


def test_unknown_join_key_raises_rather_than_silently_falling_back():
    with pytest.raises(KeyError, match="event_uid_typo"):
        coverage_report("tennis", key="event_uid_typo")
