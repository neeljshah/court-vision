"""S79: the family-combination screen -- k=1 IS the single-feature screen, a planted joint signal
is detectable, and a duplicated column is deduped. Construct corpus; no real data, no results DB,
no ledger, no verdict partition is opened here.

Run: python -m pytest tests/platformkit/foundry/test_family_combo_screen.py -q
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.walkforward import walk_forward
from scripts.platformkit.foundry import family_combo_screen as fcs
from scripts.platformkit.foundry.screen_predictor import RealScreenPredictor

TEAMS = tuple("T%02d" % i for i in range(12))


def _corpus(rows: int = 300, seed: int = 11) -> list:
    """States whose outcome needs BOTH planted as-of features; neither alone carries the pair."""
    rng, base, states = random.Random(seed), date(2025, 1, 6), []
    for index in range(rows):
        day = base + timedelta(days=(index // 6) * 7 + (index % 6))
        close = 0.35 + 0.3 * rng.random()
        a, b = rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)
        eta = math.log(close / (1 - close)) + 1.2 * a + 1.2 * b
        avail = "%sT00:00:00" % day.isoformat()
        states.append({"game_id": "g%04d" % index, "state_ts": "%sT12:00:00" % day.isoformat(),
                       "game_date": day.isoformat(), "sport": "nba",
                       "home": TEAMS[index % 12], "away": TEAMS[(index + 5) % 12],
                       "features": {"p_ref": close, "a_asof": a, "b_asof": b},
                       "feature_avail": {"p_ref": avail, "a_asof": avail, "b_asof": avail},
                       "devig_close_prob": close, "outcome":
                           int(rng.random() < 1.0 / (1.0 + math.exp(-eta)))})
    return states


def test_k1_combo_predictor_is_the_single_feature_screen() -> None:
    """The whole comparison rests on this: the k=1 arm must be the S58c screen, not a re-derivation."""
    states = _corpus()
    combo = walk_forward(list(states), fcs.ComboPredictor(["a_asof"])).records
    single = walk_forward(list(states), RealScreenPredictor("a_asof")).records
    # 1e-12, not exact equality: the k-vector dot product reassociates the same sum (~1e-17).
    assert np.allclose([r["p_model"] for r in combo], [r["p_model"] for r in single], atol=1e-12)


def test_a_planted_joint_signal_is_detectable() -> None:
    """A null combo result must be a MEASUREMENT, not a screen that could never find anything."""
    states = _corpus()
    pair = fcs.score(states, ["a_asof", "b_asof"], "nba")
    one = fcs.score(states, ["a_asof"], "nba")
    assert pair["improvement"] > one["improvement"] > 0.0
    assert pair["n_events"] == pair["n_unique_events"] == len(states)
    assert len(pair["series"]) == len(states)                     # Q9: the differential is archived
    assert pair["ci95"][0] <= pair["dm_stat"] * 0.0 + pair["ci95"][1]


def test_bind_features_dedupes_an_identical_column() -> None:
    """`p_base` and `p_home_elo` are one column under two names; a k=5 of copies is a k=1."""
    class _Pick:
        def __init__(self, name, values):
            self.hash, self.values = name, values
            self.hypothesis = type("H", (), {"feature": name, "transform": "raw", "params": ()})()

    class _Binder:
        rows = 10
        states = [{"game_date": "2025-01-0%d" % (i + 1), "devig_close_prob": 0.5, "game_id": "g%d" % i}
                  for i in range(6)]

        def feature_values(self, hypothesis):
            return pd.Series(dict(_VALUES)[hypothesis.feature])

    _VALUES = [("x", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]), ("x_copy", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
               ("z", [6.0, 5.0, 4.0, 3.0, 2.0, 1.0])]
    picks = [_Pick(name, values) for name, values in _VALUES]
    built, names, used = fcs.bind_features(_Binder(), picks)
    assert names == ["x__raw__none", "z__raw__none"] and len(used) == 2
    assert len(built) == 6 and np.isfinite(built[0]["features"]["x__raw__none"])
