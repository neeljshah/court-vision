"""Per-file tests for proof_mlb/curve_oos.py (run THIS file only; never full pytest)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.proof_mlb import curve_oos as M


def test_parse_innings():
    assert M._parse_innings("0,1,0,0,1,3,3,1,x") == [0, 1, 0, 0, 1, 3, 3, 1]
    assert M._parse_innings("2,0,2") == [2, 0, 2]
    assert M._parse_innings(None) is None
    assert M._parse_innings("a,b") is None


def test_rmse_bias():
    rmse, bias = M._rmse_bias(np.array([2.0, 4.0]), np.array([1.0, 1.0]))
    assert abs(bias - 2.0) < 1e-9
    assert abs(rmse - np.sqrt((1 + 9) / 2)) < 1e-9


def test_curve_remaining_frac_endpoints():
    shares = tuple([1.0 / 9] * 9)
    assert abs(M.curve_remaining_frac(shares, 0) - 1.0) < 1e-9
    assert abs(M.curve_remaining_frac(shares, 9) - 0.0) < 1e-9
    # uniform curve == flat baseline at every integer node
    for n in range(10):
        assert abs(M.curve_remaining_frac(shares, n) - M.flat_remaining_frac(n)) < 1e-9


def test_curve_remaining_frac_front_loaded():
    # front-loaded shares -> after a few innings, LESS remains than flat predicts
    shares = tuple([0.3, 0.2, 0.15, 0.1, 0.08, 0.07, 0.05, 0.03, 0.02])
    assert M.curve_remaining_frac(shares, 5) < M.flat_remaining_frac(5)


def test_fit_inning_shares_sums_to_one():
    df = pd.DataFrame({
        "home_innings": ["1,0,0,0,0,0,0,0,x", "0,0,0,0,0,0,0,0,1"],
        "away_innings": ["0,0,0,0,0,0,0,0,0", "0,0,0,0,0,0,0,0,0"],
    })
    shares = M.fit_inning_shares(df)
    assert abs(sum(shares) - 1.0) < 1e-9
    # one run in inning 1 + one run in inning 9, total 2 -> each share 0.5
    assert abs(shares[0] - 0.5) < 1e-9
    assert abs(shares[8] - 0.5) < 1e-9


def test_eval_leakfree_and_shape():
    # synthetic val game: home 9 runs front-loaded, away 0 -> final total 9
    df = pd.DataFrame({
        "home_innings": ["3,2,1,1,0,1,1,0,x"] * 3,
        "away_innings": ["0,0,0,0,0,0,0,0,0"] * 3,
    })
    shares = tuple([1.0 / 9] * 9)
    res = M._eval(df, shares, limit=None)
    assert res is not None
    assert res["n_checkpoints"] == 9          # 3 games x 3 checkpoints
    # with a uniform curve, curve and flat predictions must be identical
    assert abs(res["bias_abs_cut"]) < 1e-9
    assert abs(res["rmse_cut"]) < 1e-9


def test_run_holds_oos_on_real_corpus():
    r = M.run()
    assert r["status"] == "ok"
    # the curve must not be WORSE than flat on RMSE, and must cut |bias|
    assert r["rmse_cut"] >= -0.01
    assert r["bias_abs_cut"] > 0.0
    assert r["verdict"] in ("holds_oos", "in_sample_only")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL PASS")
