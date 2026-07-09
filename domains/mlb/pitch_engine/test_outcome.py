"""Per-file tests for pitch_engine.outcome -- tiers + outcome table backoff."""
import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel, N_OUT


def _pa_frame():
    # three batters: a masher (all HR), a scrub (all K), a middle (all 1B)
    rows = []
    for b, evt in [(1, "HR"), (2, "K"), (3, "1B")]:
        for _ in range(60):
            rows.append({"batter": b, "pclass": "FB", "pa_evt": evt})
    return pd.DataFrame(rows)


def test_tiers_order():
    t = BatterTiers.fit(_pa_frame())
    # masher tier > scrub tier
    assert t.tier(1, 0) == 2
    assert t.tier(2, 0) == 0
    # unknown batter -> league tier 1
    assert t.tier(999, 0) == 1


def test_outcome_probs_normalized_and_backoff():
    t = BatterTiers.fit(_pa_frame())
    # pitch frame: FB in-zone count 0-0, mostly called strikes
    n = 200
    pf = pd.DataFrame({
        "pclass": ["FB"] * n, "zbucket": ["IZ"] * n, "cidx": [0] * n,
        "batter": [1] * n,
        "outcome": ["called_strike"] * 150 + ["ball"] * 50,
    })
    m = OutcomeModel.fit(pf, t)
    p = m.outcome_probs(0, 0, 0, t.tier(1, 0))
    assert abs(p.sum() - 1.0) < 1e-9
    assert len(p) == N_OUT
    # called_strike is index 1 in OUTCOMES
    assert p.argmax() == 1
    # backoff to global for an unseen (class,zone,count,tier) cell -> still normalized
    p2 = m.outcome_probs(2, 1, 11, 2)
    assert abs(p2.sum() - 1.0) < 1e-9
