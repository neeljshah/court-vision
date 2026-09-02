"""Synthetic checks for the Hedge trial wiring (no real corpus, no ledger write)."""
from __future__ import annotations

import pytest

from scripts.platformkit import hedge_trial_arms as A
from scripts.platformkit import hedge_trial_runner as R
from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.walkforward import assert_vintage
from scripts.platformkit.ingame import hedge_combiner as hc


def _ticks(n_dates: int = 6, games: int = 4, per_game: int = 3):
    ticks = []
    for d in range(n_dates):
        for g in range(games):
            gid, y = "KXMLBGAME-26JUL%02d1310AAA%s" % (d + 1, "BBB" if g % 2 else "CCC"), float((d + g) % 2)
            for k in range(per_game):
                ticks.append({"game": gid + str(g), "timestamp": "2026-07-%02dT2%d:00:0%dZ" % (d + 1, g, k),
                              "outcome": y, "model_prob": 0.6 if y else 0.4, "market_prob": 0.5,
                              "in_window": k > 0, "_row_id": len(ticks),
                              "state_summary": "inning=%d" % (3 * k + 1)})
    good = [float(t["outcome"]) * 0.8 + 0.1 for t in ticks]
    bad = [0.9 - float(t["outcome"]) * 0.8 for t in ticks]
    return ticks, {"raw_model": [t["model_prob"] for t in ticks], "good": good, "bad": bad}


def test_hedge_series_reproduces_evaluate_brier():
    ticks, arms = _ticks()
    report = hc.evaluate(ticks, arms, t_rounds=24, bootstrap_iterations=2)
    hedge = A.hedge_series(ticks, arms, 24)
    frame = R._losses(ticks, hedge, R._paired_index(ticks, hedge))
    assert frame["loss_hedge"].mean() == pytest.approx(report["slices"]["all_ticks"]["metrics"]["hedge_brier"], abs=1e-12)
    assert all(v is None for v in hedge[:12])          # first date is burn-in, never scored


def test_e2_regime_series_absent_outside_window():
    ticks, _ = _ticks()
    series = A.e2_regime_series(ticks)
    scored = [i for i, t in enumerate(ticks) if t["in_window"] and str(t["timestamp"])[:10] > "2026-07-01"]
    assert all(series[i] is not None for i in scored)
    assert all(series[i] is None for i, t in enumerate(ticks) if not t["in_window"])


def test_game_states_pass_vintage_and_cpcv_runs():
    ticks, arms = _ticks(n_dates=8)
    states = A.game_states(ticks, arms)
    for s in states:
        assert_vintage(s)
        assert s["home"] != s["away"] and len(s["home"]) == 3
    records = cpcv_evaluate(states, A.hedge_predictor(tuple(arms), 24), n_groups=4, n_test_groups=1)
    assert records and all(0.0 <= r["p_model"] <= 1.0 for r in records)


def test_verdict_rule_is_the_preregistered_bar():
    base = {"improvement_vs_raw": 0.004, "dm_ci95_improvement": [0.001, 0.007], "deflated_p": 0.01}
    assert R.verdict_of(base) == "AHEAD"
    assert R.verdict_of({**base, "improvement_vs_raw": 0.0039}) == "BEHIND"
    assert R.verdict_of({**base, "dm_ci95_improvement": [-0.001, 0.009]}) == "BEHIND"
    assert R.verdict_of({**base, "deflated_p": 0.05}) == "BEHIND"
    assert R.BAR == 0.004 and R.LOCK == pytest.approx(-0.0343, abs=1e-4)


def test_pbo_and_slices_on_synthetic():
    ticks, arms = _ticks(n_dates=10, games=6)
    block = R.pbo_block(ticks, arms, "mlb")
    assert 0.0 <= block["pbo"] <= 1.0 and set(block["configs"]) >= {"uniform", "hedge_T371", "good"}
    hedge = A.hedge_series(ticks, arms, 371)
    slices = R.regime_slices(R._losses(ticks, hedge, R._paired_index(ticks, hedge)))
    assert {"all_ticks", "in_window_ticks", "inning=early_1_3", "month=07"} <= set(slices)


def test_candidate_mode_single_arm_is_the_arm_and_e4_runs():
    ticks, arms = _ticks(n_dates=8)
    for t in ticks:                                   # give E4 a parseable score state
        t["state_summary"] = "home_score=%d.0 away_score=0.0 inning=3" % (2 if t["outcome"] else 0)
    features = A.score_diff_features(ticks)
    assert features["score_diff"].tolist()[:2] == [0.0, 0.0] or features["score_diff"].notna().all()
    only = A.arm_series(ticks, features, "mlb", only=("raw_model", "e4_blend"))
    assert set(only) == {"raw_model", "e4_blend"}
    guard = A.e4_blend_series(ticks, features, column="arm_a_prob")
    first_date = sum(str(t["timestamp"])[:10] == "2026-07-01" for t in ticks)
    assert all(v is None for v in only["e4_blend"][:first_date]) and any(v is not None for v in guard)
    single = A.hedge_series(ticks, {"good": arms["good"]}, 371)
    assert all(single[i] == arms["good"][i] for i in range(len(ticks)) if single[i] is not None)
    assert sum(v is not None for v in single) == len(ticks) - 12   # burn-in only
    block = R.pbo_block(ticks, R.e4_configs(ticks, features, only), "mlb", mixtures=False)
    assert "uniform" not in block["configs"] and set(block["configs"]) >= {"e4_guard_only", "e4_blend", "raw_model"}
    assert set(R.E4_VARIANTS) <= set(block["configs"])


def _uncached_hedge(arm_names, t_rounds):
    """Reference predictor: refits Hedge from scratch on every call (no cache)."""
    def predict(train, test, _select_inside):
        state = hc.initial_state(arm_names, t_rounds)
        for s in train:
            state = hc.fold_settlement(state, s["game_id"], s["features"]["arm_ticks"], s["outcome"])
        p = hc.predict(state, test["features"]["checkpoint"])
        return float(p if p is not None else test["features"]["checkpoint"]["raw_model"])
    return predict


def test_hedge_predictor_cache_is_keyed_on_train_content_not_address():
    """RT-2: `key = id(train)` served one CPCV split's Hedge state to another
    (CPython reuses the freed list address), so weights fit on a different
    split's games -- possibly including the current test block -- priced the
    test rows. The cached predictor must agree with an uncached refit on EVERY
    row of a multi-split path."""
    ticks, arms = _ticks(n_dates=16)              # 16 dates x 4 games = 64 games
    states = A.game_states(ticks, arms)
    names = tuple(arms)
    cached = cpcv_evaluate(states, A.hedge_predictor(names, 371), n_groups=8, n_test_groups=2)
    fresh = cpcv_evaluate(states, _uncached_hedge(names, 371), n_groups=8, n_test_groups=2)
    assert len({r["split_id"] for r in cached}) >= 20   # enough splits to reuse addresses
    assert [r["p_model"] for r in cached] == [r["p_model"] for r in fresh]
