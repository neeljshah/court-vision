"""Tests for scripts/ingame/ingame_rmsebias_harness.py — the in-game RMSE+bias eval GATE.

Proves the load-bearing discipline end-to-end: (1) the gate scores RMSE+bias and NEVER gates on MAE;
(2) BASE / identity-bayes reproduce ``routed`` byte-for-byte (RMSE delta 0.0); (3) the vectorized bayes
posterior matches the per-row module within 1e-9 (parity gate); (4) on a right-skewed truth the shrink
candidate WINS MAE yet the gate reports new_rmse > base_rmse and FAILS (the MAE-vs-RMSE artifact guard).
Logic tests use tiny in-memory synthetic frames; the real-cache test is skipped if the smoke cache is absent.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "scripts", "team_system"), os.path.join(ROOT, "src"),
          os.path.join(ROOT, "scripts", "ingame")):
    sys.path.insert(0, p)

import ingame_rmsebias_harness as H  # noqa: E402
from ingame.bayes_player_update import posterior_projection  # noqa: E402
from ingame.live_state_hook import remaining_min_from  # noqa: E402

_SMOKE = os.path.join(ROOT, "data", "cache", "ingame_eval_cache_smoke.parquet")


def _df(routed, truth, cur, cur_min, stat, g_el, g_rem, margin=0.0,
        game_id="0022201014", bucket="06min(midQ1)"):
    """Build a minimal synthetic eval frame with every column the rules read."""
    n = len(routed)

    def _col(x):
        return x if isinstance(x, (list, tuple, np.ndarray)) else [x] * n
    return pd.DataFrame({
        "routed": np.asarray(routed, float), "truth": np.asarray(truth, float),
        "cur": np.asarray(cur, float), "cur_min": np.asarray(cur_min, float),
        "stat": list(_col(stat)), "game_elapsed_sec": np.asarray(_col(g_el), float),
        "game_remaining_sec": np.asarray(_col(g_rem), float),
        "score_margin": np.asarray(_col(margin), float),
        "game_id": list(_col(game_id)), "bucket": list(_col(bucket)),
    })


def test_rmse_bias_mae_basic():
    # pred=[10,12], truth=[11,11] -> err=[-1,+1]: bias 0, mae 1, rmse 1
    rmse, bias, mae = H.rmse_bias_mae([10.0, 12.0], [11.0, 11.0])
    assert abs(bias - 0.0) < 1e-12
    assert abs(mae - 1.0) < 1e-12
    assert abs(rmse - 1.0) < 1e-12
    # a biased vector: pred=[5,5,5], truth=[2,2,2] -> err 3: bias 3, mae 3, rmse 3
    rmse2, bias2, mae2 = H.rmse_bias_mae([5.0, 5.0, 5.0], [2.0, 2.0, 2.0])
    assert abs(bias2 - 3.0) < 1e-12 and abs(mae2 - 3.0) < 1e-12 and abs(rmse2 - 3.0) < 1e-12


def test_base_rule_is_identity():
    df = _df(routed=[20.0, 8.0, 5.0], truth=[30.0, 12.0, 6.0], cur=[5.0, 2.0, 1.0],
             cur_min=[10.0, 10.0, 10.0], stat=["pts", "reb", "ast"], g_el=600.0, g_rem=2280.0)
    r = H.score_rule(df, H.base_rule, "base", verbose=False)
    o = r["overall"]
    assert abs(o["new_rmse"] - o["base_rmse"]) < 1e-12  # identity: delta exactly 0
    assert abs(o["new_bias"] - o["base_bias"]) < 1e-12
    assert o["pass"] is False  # cannot beat itself (strict RMSE improvement required)


def test_bayes_identity_equals_base():
    # trust_override=None + no trust_curve json -> trust_w 0 -> posterior == routed within 1e-9
    df = _df(routed=[22.0, 9.0, 4.0, 1.5], truth=[28.0, 11.0, 7.0, 2.0],
             cur=[6.0, 3.0, 2.0, 1.0], cur_min=[12.0, 12.0, 12.0, 12.0],
             stat=["pts", "reb", "ast", "fg3m"], g_el=720.0, g_rem=2160.0)
    out = H.bayes_rule(df, trust_override=None)
    assert np.allclose(out, df["routed"].to_numpy(float), atol=1e-9)


def test_bayes_vectorized_matches_module():
    # parity gate: the fast vectorized posterior must equal the per-row module within 1e-9
    rng = np.random.default_rng(11)
    n = 50
    stats = rng.choice(H.STATS, size=n)
    routed = rng.uniform(1.0, 30.0, size=n)
    cur = rng.uniform(0.0, 15.0, size=n)
    cur_min = rng.uniform(0.0, 30.0, size=n)
    g_el = rng.uniform(120.0, 2700.0, size=n)
    g_rem = 2880.0 - g_el
    margin = rng.uniform(-20.0, 20.0, size=n)
    # mix in a playoff game id (startswith 004) to exercise the AST playoff cap
    gids = np.where(rng.random(n) < 0.5, "0042200401", "0022201014")
    df = _df(routed=routed, truth=routed, cur=cur, cur_min=cur_min, stat=list(stats),
             g_el=g_el, g_rem=g_rem, margin=margin, game_id=list(gids))

    vec = H.bayes_rule(df, trust_override=0.4)
    ref = np.empty(n)
    for i in range(n):
        rm = remaining_min_from(float(cur_min[i]), float(g_el[i]), float(g_rem[i]))
        regime = {"is_playoff": str(gids[i]).startswith("004"),
                  "margin_bucket": 0 if abs(margin[i]) <= 5 else (1 if abs(margin[i]) <= 12 else 2)}
        post, _, _ = posterior_projection(prior=float(routed[i]), current=float(cur[i]),
                                          min_so_far=float(cur_min[i]), remaining_min=rm,
                                          stat=str(stats[i]), regime=regime, trust_override=0.4)
        ref[i] = post
    assert np.allclose(vec, ref, atol=1e-9), f"max diff {np.abs(vec - ref).max():.2e}"


def test_shrink_loses_on_rmse_when_it_wins_mae():
    # Right-skewed truth: most finals near the live pace, a few big finishes pull the MEAN above the median.
    # routed = base prior = the MEAN target (RMSE-optimal). shrink pulls toward the live (lower) score ->
    # it sits near the median -> WINS MAE but the gate reports higher RMSE + negative bias -> FAIL.
    rng = np.random.default_rng(7)
    n = 4000
    truth = rng.lognormal(mean=3.0, sigma=0.6, size=n)        # right-skewed finals
    routed = np.full(n, float(truth.mean()))                  # base = mean (RMSE-optimal prior)
    cur = np.full(n, float(np.median(truth)))                 # live so-far ~ the median proxy
    df = _df(routed=routed, truth=truth, cur=cur, cur_min=np.full(n, 20.0),
             stat=["pts"] * n, g_el=2851.2, g_rem=28.8)        # remaining_frac ~ 0.01 -> shrink collapses to cur

    shrink_pred = H.shrink_rule(df)
    _, _, base_mae = H.rmse_bias_mae(routed, truth)
    _, _, shrink_mae = H.rmse_bias_mae(shrink_pred, truth)
    assert shrink_mae < base_mae, "setup invalid: shrink should win MAE (the seductive trap)"

    r = H.score_rule(df, H.shrink_rule, "shrink", verbose=False)
    o = r["overall"]
    assert o["new_rmse"] > o["base_rmse"], "shrink must LOSE on RMSE (the artifact)"
    assert o["new_bias"] < 0, "shrink-toward-current runs negatively biased on a right-skewed target"
    assert o["pass"] is False  # gate (RMSE+bias only) correctly rejects the MAE-winning shrink


def test_mae_is_reported_but_never_gates():
    # A candidate that improves MAE while worsening RMSE must STILL fail the gate (MAE is not a criterion).
    rng = np.random.default_rng(3)
    n = 2000
    truth = rng.lognormal(mean=3.0, sigma=0.6, size=n)
    routed = np.full(n, float(truth.mean()))
    cur = np.full(n, float(np.median(truth)))
    df = _df(routed=routed, truth=truth, cur=cur, cur_min=np.full(n, 20.0),
             stat=["pts"] * n, g_el=2851.2, g_rem=28.8)
    res = H.score_rule(df, H.shrink_rule, "shrink", verbose=False)["overall"]
    assert res["new_mae"] < res["base_mae"]   # MAE improves
    assert res["pass"] is False               # ... yet the gate still fails (MAE never gates)


@pytest.mark.skipif(not os.path.exists(_SMOKE), reason="smoke cache not present")
def test_real_smoke_cache_base_identity():
    df = H.load_eval_frame(_SMOKE)
    assert len(df) > 0
    r = H.score_rule(df, H.base_rule, "base(smoke)", verbose=False)
    o = r["overall"]
    assert abs(o["new_rmse"] - o["base_rmse"]) < 1e-9  # byte-identity on the real cache
    # identity-bayes (no override) also reproduces routed on the real cache
    out = H.bayes_rule(df, trust_override=None)
    assert np.allclose(out, df["routed"].to_numpy(float), atol=1e-9)
