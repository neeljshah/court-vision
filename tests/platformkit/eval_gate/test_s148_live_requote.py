"""S148 -- the live rule on a synthetic frame, and one published CI reproduced."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s148_live_requote as s148


def test_live_mask_on_three_synthetic_games():
    """g1 regulation, g2 overtime, g3 a quarter-end buzzer in P1-P3.

    Dead is period >= 4 AND game_clock_s == 0 -- so a P2 buzzer stays live, the
    P4 and OT zeros go, and a missing clock cannot be confirmed dead.
    """
    frame = pd.DataFrame({
        "game_id": ["g1", "g1", "g1", "g2", "g2", "g2", "g3", "g3", "g3"],
        "period":  [1, 4, 4, 4, 5, 5, 2, 3, 4],
        "game_clock_s": [720.0, 12.0, 0.0, 0.0, 300.0, 0.0, 0.0, 0.0, None],
    })
    mask = s148.live_mask(frame)
    assert list(mask) == [True, True, False, False, True, False, True, True, True]
    assert int((~mask).sum()) == 3
    # every game keeps at least one live tick
    assert frame[mask]["game_id"].nunique() == 3


def test_verdict_reading_is_the_same_function_on_both_row_sets():
    ahead = {"dm_ci95": [0.005, 0.009], "mean_loss_differential": 0.007}
    below = {"dm_ci95": [0.0001, 0.0009], "mean_loss_differential": 0.0005}
    assert s148.verdict(ahead) == "AHEAD"
    assert s148.verdict(below) == "POSITIVE-BELOW-BAR"
    assert s148.verdict({"dm_ci95": [-0.009, -0.005], "mean_loss_differential": -0.007}) == "NEGATIVE"
    assert s148.verdict({"dm_ci95": [-0.009, 0.005], "mean_loss_differential": -0.002}) == "NULL"


_S86 = s148._SPECS["S86"]


@pytest.mark.skipif(
    not ((s148._CACHE / _S86["csv"]).exists() and (s148._CACHE / _S86["json"]).exists()),
    reason="local-only archives under data/cache/eval_gate are absent")
def test_s86_pooled_ci_reproduces_from_its_archive_to_1e_9():
    row = s148.requote(_S86, s148.live_index())
    assert row["a2"]["reproduced"], row["a2"]
    assert row["a2"]["max_abs_delta"] < 1e-9, row["a2"]
    # the live re-quote is a strict subset of the same rows, never a refit
    assert row["live"]["n"] < row["all"]["n"]
    assert row["live"]["n"] + row["n_excluded_dead"] == row["all"]["n"]
