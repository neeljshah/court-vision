"""Per-file tests for the OFFLINE in-game PROOF (Milestone-6, honesty-critical).

On a SMALL synthetic two-window fixture (NO corpus, NO network) we prove the
fitter is honest:
  * it runs and emits a Verdict object of the right SHAPE (verdict / metrics /
    seasons / caveats) with the required metric keys;
  * point markets are graded with RMSE + BIAS (NOT MAE) -- the verdict carries
    rmse_base/rmse_blend/bias and NO mae_* key;
  * a deliberately-leaky pregame prior (p0 == outcome) is REJECTED;
  * the freshness invariant (variance SHRINKS Q1->Q3) is enforced;
  * the verdict label is one of AHEAD / MATCHES_CLOSE / BEHIND and is honest.

Run (per-file ONLY -- a full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest tests/platformkit/test_fit_w_surface.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.ingame.fit_w_surface import (
    Verdict,
    assert_variance_shrink,
    evaluate,
    reject_leaky_prior,
    states_from_linescores,
    _bias,
    _rmse,
)

_QFRAC = {1: 0.25, 2: 0.5, 3: 0.75}


def _make_window(seed: int, n_games: int = 120) -> list:
    """Synthetic leak-free as-of states: realized margin trends toward the outcome
    and its residual variance shrinks Q1->Q3 (the freshness lever). p0 is a fixed
    base-rate prior (no leak)."""
    rng = np.random.default_rng(seed)
    p0 = 0.55
    states = []
    for g in range(n_games):
        strength = rng.standard_normal()
        margin_final = float(8.0 * strength + 6.0 * rng.standard_normal())
        y = int(margin_final > 0)
        for q in (1, 2, 3):
            frac = _QFRAC[q]
            noise = (1.0 - frac) * 12.0
            diff = frac * margin_final + noise * rng.standard_normal()
            slope = 0.06 + 0.10 * frac
            states.append({
                "game_id": seed * 10000 + g, "period": q,
                "seconds_remaining": 2880.0 * (1.0 - frac),
                "score_diff": float(diff), "p0": p0,
                "p_live": float(1.0 / (1.0 + np.exp(-slope * diff))),
                "outcome": y, "margin_final": margin_final,
            })
    return states


def test_rmse_bias_helpers_not_mae():
    pred = [1.0, 2.0, 3.0]
    act = [1.0, 2.0, 5.0]
    assert abs(_rmse(pred, act) - (4.0 / 3.0) ** 0.5) < 1e-9
    assert abs(_bias(pred, act) - (-2.0 / 3.0)) < 1e-9   # signed, not absolute


def test_evaluate_shape_and_metric_keys():
    fit = _make_window(seed=1)
    ev = _make_window(seed=2)
    v = evaluate(fit, ev, seasons={"train": "A", "eval": "B"}, caveats=["x"])
    assert isinstance(v, Verdict)
    d = v.to_dict()
    assert set(d) == {"verdict", "baseline", "vs_close", "metrics", "seasons", "caveats"}
    assert d["verdict"] in {"CALIBRATION_GAIN_VS_BASERATE", "MATCHES_BASERATE", "WORSE_THAN_BASERATE"}
    # the artifact must NEVER imply a market edge: close comparison is unproven
    assert d["baseline"] == "pregame_base_rate_prior"
    assert "UNPROVEN" in d["vs_close"]
    for k in ("rmse_base", "rmse_blend", "bias", "brier_base", "brier_blend",
              "dm_stat", "dm_p", "n"):
        assert k in d["metrics"], k
    # graded on RMSE + BIAS, never MAE
    assert not any("mae" in k.lower() for k in d["metrics"]), d["metrics"]
    assert d["caveats"] == ["x"]
    assert d["seasons"]["train"] == "A"


def test_blend_beats_or_matches_base_oos():
    """On a fixture where realized state truly carries info, the blend should NOT
    regress vs the base-rate prior (gain or match -- never worse)."""
    v = evaluate(_make_window(seed=11), _make_window(seed=12))
    assert v.verdict in {"CALIBRATION_GAIN_VS_BASERATE", "MATCHES_BASERATE"}
    m = v.metrics
    assert m["rmse_blend"] <= m["rmse_base"] + 1e-9     # point head not worse
    assert m["brier_blend"] <= m["brier_base"] + 1e-9   # win-prob not worse
    assert abs(m["bias"]) < 2.0                          # roughly unbiased


def test_leaky_prior_rejected():
    leaky = [{"game_id": 1, "period": 3, "seconds_remaining": 720.0,
              "score_diff": 5.0, "p0": 1.0, "p_live": 0.9,
              "outcome": 1, "margin_final": 5.0}]
    with pytest.raises(AssertionError):
        reject_leaky_prior(leaky)
    with pytest.raises(AssertionError):
        evaluate(leaky, leaky)


def test_variance_shrink_enforced():
    # monotone-shrinking fixture passes
    shrink = assert_variance_shrink(_make_window(seed=5))
    assert shrink[1] >= shrink[2] >= shrink[3]
    # a fixture whose variance GROWS late must raise
    bad = []
    rng = np.random.default_rng(0)
    for g in range(40):
        for q in (1, 2, 3):
            spread = q * 10.0           # variance grows with period -> illegal
            bad.append({"game_id": g, "period": q, "seconds_remaining": 0.0,
                        "score_diff": 0.0, "p0": 0.5, "p_live": 0.5,
                        "outcome": 1,
                        "margin_final": float(spread * rng.standard_normal())})
    with pytest.raises(AssertionError):
        assert_variance_shrink(bad)


def test_states_from_linescores_leak_free():
    import pandas as pd
    df = pd.DataFrame([{
        "event_id": 7, "home_abbr": "AAA", "away_abbr": "BBB",
        "home_q1": 30, "home_q2": 25, "home_q3": 20, "home_q4": 25,
        "away_q1": 20, "away_q2": 20, "away_q3": 30, "away_q4": 20,
        "date": pd.Timestamp("2025-11-01"),
    }])
    states = states_from_linescores(df, p0=0.55)
    assert len(states) == 3                       # Q1, Q2, Q3 only (no Q4 leak)
    assert states[0]["score_diff"] == 10.0        # 30-20 after Q1
    assert states[1]["score_diff"] == 15.0        # 55-40 after Q2
    assert states[2]["score_diff"] == 5.0         # 75-70 after Q3
    assert all(s["outcome"] == 1 for s in states)  # home 100 > away 90
    assert all(s["margin_final"] == 10.0 for s in states)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} fit_w_surface tests passed.")
