import numpy as np
import pandas as pd

from domains.soccer.chain_engine.shot_model import ShotModel
from domains.soccer.chain_engine.match_sim import (
    PossessionRate, simulate_match, simulate_match_ensemble,
)


def _fit_models():
    rows = []
    for tb in range(6):
        for team, ih in (("H", True), ("A", False)):
            for i in range(30):
                rows.append({"match_id": 1, "team": team, "is_home": ih,
                             "time_bucket": tb, "score_bucket": 1,
                             "had_shot": 1 if i % 5 == 0 else 0,
                             "xg": 0.15 if i % 5 == 0 else float("nan"), "goal": False})
    df = pd.DataFrame(rows)
    return ShotModel.fit(df), PossessionRate.fit(df)


def test_possession_rate_positive_for_seen_slots():
    _, rate = _fit_models()
    assert rate.mean(0, True) > 0
    assert rate.mean(2, False) > 0


def test_simulate_match_terminates_with_nonneg_goals():
    shot_model, rate = _fit_models()
    rng = np.random.default_rng(0)
    hg, ag = simulate_match("H", "A", shot_model, rate, rng)
    assert hg >= 0 and ag >= 0


def test_simulate_match_ensemble_shapes():
    shot_model, rate = _fit_models()
    hg, ag = simulate_match_ensemble("H", "A", shot_model, rate, n=200, seed=3)
    assert len(hg) == 200 and len(ag) == 200
    assert (hg >= 0).all() and (ag >= 0).all()
