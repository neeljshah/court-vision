"""Per-file test for the S87 tick-informativeness pass. Run from the repo root:

    python -m pytest scripts/platformkit/eval_gate/test_tick_informative.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate.tick_informative import _ARTIFACTS, _CACHE, flag_ticks, requote


def _frame() -> pd.DataFrame:
    # g1: t0 new, t1 fully held, t2 market moves, t2 duplicate ts, t3 model-only moves.
    return pd.DataFrame(
        {
            "game": ["g1", "g1", "g1", "g1", "g1", "g2", "g2"],
            "timestamp": ["t0", "t1", "t2", "t2", "t3", "t0", "t1"],
            "market": [0.50, 0.50, 0.60, 0.60, 0.60, 0.40, 0.40],
            "model": [0.50, 0.50, 0.50, 0.50, 0.55, 0.40, 0.41],
            "loss_differential": [0.01, 0.00, -0.02, -0.02, 0.03, 0.02, -0.01],
        }
    )


def test_flags_and_counts():
    flagged, summary = flag_ticks(_frame(), loss_col="loss_differential")
    assert list(flagged["is_dup"]) == [False, False, False, True, False, False, False]
    assert list(flagged["is_held_market"]) == [False, True, False, True, True, False, True]
    assert list(flagged["is_held_model"]) == [False, True, True, True, False, False, False]
    # informative = not a duplicate AND (market moved OR model moved)
    assert list(flagged["is_informative"]) == [True, False, True, False, True, True, True]
    assert summary["n"] == 7 and summary["n_dup"] == 1
    assert summary["n_held_market"] == 4 and summary["n_held_model"] == 3
    assert summary["n_held_both"] == 2 and summary["n_informative"] == 5
    assert summary["n_games"] == 2


def test_first_tick_of_a_game_is_never_held():
    flagged, _ = flag_ticks(_frame())
    firsts = flagged.groupby("game", sort=False).head(1)
    assert not firsts["is_held_market"].any() and not firsts["is_held_model"].any()
    assert firsts["is_informative"].all()


def test_pure_and_reuses_the_icc_helper():
    frame = _frame()
    before = frame.copy()
    _, summary = flag_ticks(frame, loss_col="loss_differential")
    pd.testing.assert_frame_equal(frame, before)          # input untouched
    assert summary["n_eff_icc"] is not None and 0 < summary["n_eff_icc"] <= summary["n_informative"]
    assert flag_ticks(frame)[1]["n_eff_icc"] is None       # no loss column -> no invented ESS


def test_missing_column_raises():
    with pytest.raises(ValueError, match="missing required columns"):
        flag_ticks(_frame().drop(columns=["market"]))


@pytest.mark.parametrize("name", sorted(_ARTIFACTS))
def test_requote_reproduces_the_published_ci(name):
    spec = _ARTIFACTS[name]
    if not (_CACHE / spec["csv"]).exists() or not (_CACHE / spec["json"]).exists():
        pytest.skip("local-only archived artifact absent: %s" % spec["csv"])
    row = requote(name)
    # Q9: the published CI must come back out of the archived series before the
    # informative-subset CI beside it may be read at all.
    assert row["published_ci_reproduced_from_series"] is True
    assert row["after_informative"]["n"] == row["tick_flags"]["n_informative"]
    assert row["after_informative"]["n"] <= row["before_all_rows"]["n"]
