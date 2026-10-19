"""S688 construct tests: game-level DM/HLN, CORP reliability, bias-corrected Brier.

Run alone: python3 -m pytest scripts/platformkit/eval_gate/test_paired_tests.py -q -s
Oracles are hand-derived closed forms, scipy.stats and sklearn -- never the module
under test. Seeded simulations print their shares (spec AMENDMENT 1, A1.7 / A1.9).
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats
from sklearn.isotonic import IsotonicRegression

from scripts.platformkit.calib_decomp import decompose
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.paired_tests import (
    compare_to_bootstrap, dm_hln, game_bootstrap_ci, game_level_dm)
from scripts.platformkit.eval_gate.reliability_corp import brier_decomposition, corp, pav

REPO = Path(__file__).resolve().parents[3]


# C1: textbook closed forms on x = [1..6]
def test_c1_textbook_literals():
    x = [1, 2, 3, 4, 5, 6]
    r1 = dm_hln(x, h=1)
    assert r1["hln"] == pytest.approx(math.sqrt(21), abs=1e-9)
    assert r1["dm"] == pytest.approx(3.5 / math.sqrt((17.5 / 6) / 6), abs=1e-9)
    r2 = dm_hln(x, h=2)
    assert r2["dm"] == pytest.approx(21 / math.sqrt(35), abs=1e-9)
    assert r2["hln"] == pytest.approx(math.sqrt(7), abs=1e-9)
    assert r2["df"] == 5 and r2["status"] == "OK"
    assert r2["p_value"] == pytest.approx(2 * stats.t.sf(math.sqrt(7), 5), abs=1e-12)


# C2: h=1 equals scipy's one-sample t on game means built here with numpy; sign
def test_c2_matches_scipy_t_and_sign():
    rng = np.random.default_rng(2)
    gids = np.repeat(np.arange(9), rng.integers(3, 30, size=9))
    ref = rng.uniform(0.15, 0.30, size=len(gids))
    cand = ref - 0.02 + rng.normal(0, 0.03, size=len(gids))  # candidate lower loss
    res = game_level_dm(ref, cand, list(gids))
    dbar = np.array([(ref - cand)[gids == g].mean() for g in range(9)])
    t = stats.ttest_1samp(dbar, 0.0)
    assert res["hln"] == pytest.approx(float(t.statistic), abs=1e-10)
    assert res["p_value"] == pytest.approx(float(t.pvalue), abs=1e-10)
    assert res["mean"] > 0 and res["mean"] == pytest.approx(dbar.mean(), abs=1e-12)
    assert res["n_games"] == 9 and res["n_rows"] == len(gids)
    assert "game-weighted" in res["estimand"]
    lo, hi = res["ci95"]
    se = dbar.std(ddof=1) / 3.0
    assert lo == pytest.approx(dbar.mean() - stats.t.ppf(0.975, 8) * se, abs=1e-10)
    assert hi == pytest.approx(dbar.mean() + stats.t.ppf(0.975, 8) * se, abs=1e-10)


def _null_draw(rng, g, dgp):
    """premise2.py generator (spec A1.7)."""
    if dgp == "equal":
        sizes = rng.integers(20, 201, size=g)
        sds = np.ones(g)
    else:
        big = rng.random(g) < 0.2
        sizes = np.where(big, 400, 20)
        sds = np.where(big, 3.0, 0.5)
    ids, d = [], []
    for k in range(g):
        u = rng.normal(0, sds[k])
        d.append(u + rng.normal(0, 0.5, size=sizes[k]))
        ids.extend([k] * int(sizes[k]))
    return np.concatenate(d), ids


def _null_share(dgp, g, draws=2000, seed=20260930):
    rng = np.random.default_rng(seed)
    ours = old = used = 0
    for _ in range(draws):
        d, ids = _null_draw(rng, g, dgp)
        if len(set(ids)) < 2:
            continue
        used += 1
        ours += game_level_dm(d, np.zeros(len(d)), ids)["p_value"] < 0.05
        old += diebold_mariano(d, ids).p_value < 0.05
    return ours / used, old / used, used


# C3: equal-size clustered null, G = 15
def test_c3_null_size_equal():
    share, old, used = _null_share("equal", 15)
    print(f"\nC3 equal G=15 seed 20260930 draws {used}: game-level {share:.4f} "
          f"dm_test {old:.4f}")
    assert 0.035 <= share <= 0.065


# C4: size-correlated clustered null, G = 15 (one-sided bar; conservative by design)
def test_c4_null_size_size_correlated():
    share, old, used = _null_share("size_corr", 15)
    print(f"\nC4 size-correlated G=15 seed 20260930 draws {used}: game-level "
          f"{share:.4f} dm_test {old:.4f}")
    assert share <= 0.065


# C5: PAV == sklearn, pinned tie fixture where y rises inside the tie
def test_c5_pav_ties_and_sklearn():
    p = [0.2, 0.3, 0.3, 0.3, 0.6]
    y = [0, 0, 1, 1, 1]
    fit = pav(p, y)
    assert np.allclose(fit, [0, 2 / 3, 2 / 3, 2 / 3, 1], atol=1e-12)
    rng = np.random.default_rng(5)
    for _ in range(50):
        pp = np.round(rng.uniform(0, 1, 120), 1)  # many ties
        yy = (rng.random(120) < pp).astype(float)
        ref = IsotonicRegression(y_min=0.0, y_max=1.0).fit_transform(pp, yy)
        assert np.max(np.abs(pav(pp, yy) - ref)) < 1e-12


# C6: CORP literals, exact calibration, constant forecast, signs, mean(PAV)
def test_c6_corp_literals_and_properties():
    r = corp([0.2, 0.3, 0.3, 0.3, 0.6], [0, 0, 1, 1, 1])
    # pav = [0, 2/3, 2/3, 2/3, 1]; squared errors against y = [0, 0, 1, 1, 1]
    bs = (0.04 + 0.09 + 0.49 + 0.49 + 0.16) / 5
    bs_pav = (0 + 4 / 9 + 1 / 9 + 1 / 9 + 0) / 5
    unc = 0.6 * 0.4
    assert r["MCB"] == pytest.approx(bs - bs_pav, abs=1e-12)
    assert r["DSC"] == pytest.approx(unc - bs_pav, abs=1e-12)
    assert r["UNC"] == pytest.approx(unc, abs=1e-12)
    assert abs(r["identity_residual"]) < 1e-12
    assert r["diagram"][1] == pytest.approx([0.3, 2 / 3], abs=1e-12)
    cal = corp([0.25] * 4 + [0.75] * 4, [1, 0, 0, 0, 1, 1, 1, 0])
    assert abs(cal["MCB"]) < 1e-12
    const = corp([0.4] * 10, [1, 0, 1, 0, 0, 1, 1, 0, 0, 1])
    assert abs(const["DSC"]) < 1e-12
    rng = np.random.default_rng(6)
    for _ in range(200):
        p = rng.uniform(0, 1, 60)
        y = (rng.random(60) < rng.uniform(0, 1)).astype(float)
        c = corp(p, y)
        assert c["MCB"] >= -1e-12 and c["DSC"] >= -1e-12
        assert np.mean(pav(p, y)) == pytest.approx(y.mean(), abs=1e-12)


def _two_bin_fixture():
    # bin [0.1,0.2): 3 rows p .1/.1/.15 y 1,0,0 ; bin [0.7,0.8): 2 rows y 1,1 ;
    # bin [0.9,1.0]: 1 row y 0 (n_k = 1 -> no correction); plus 24 rows at .5 to reach 30
    p = [0.1, 0.1, 0.15, 0.72, 0.75, 0.95] + [0.5] * 24
    y = [1, 0, 0, 1, 1, 0] + [1, 0] * 12
    return p, y


# C7: Ferro-Fricker literals, identity, existing-code naive REL, simulated bias
def test_c7_bias_corrected_literals():
    p, y = _two_bin_fixture()
    out = brier_decomposition(p, y, bins=10)
    n, o = 30, 15 / 30
    c = (3 * (1 / 3) * (2 / 3) / 2 + 2 * 1.0 * 0.0 / 1 + 24 * 0.5 * 0.5 / 23) / n
    nv = decompose(p, y, bins=10)
    bc = out["bias_corrected"]
    assert out["naive"]["REL"] == nv["reliability"]
    assert bc["correction"] == pytest.approx(c, abs=1e-12)
    assert bc["REL"] == pytest.approx(nv["reliability"] - c, abs=1e-12)
    assert bc["RES"] == pytest.approx(nv["resolution"] - c + o * (1 - o) / (n - 1), abs=1e-12)
    assert bc["UNC"] == pytest.approx(n * o * (1 - o) / (n - 1), abs=1e-12)
    assert bc["bins_uncorrected"] == 1
    lhs = bc["REL"] - bc["RES"] + bc["UNC"]
    assert lhs == pytest.approx(nv["reliability"] - nv["resolution"] + nv["uncertainty"],
                                abs=1e-12)


def test_c7_simulated_calibrated_bias():
    rng = np.random.default_rng(6881)
    naive, corrected = [], []
    for _ in range(2000):
        p = rng.uniform(0, 1, 300)
        y = (rng.random(300) < p).astype(float)
        out = brier_decomposition(p, y, bins=10)
        naive.append(out["naive"]["REL"])
        corrected.append(out["bias_corrected"]["REL"])
    print(f"\nC7 seed 6881: naive REL mean {np.mean(naive):.6f} "
          f"bias-corrected {np.mean(corrected):.6f}")
    assert abs(np.mean(corrected)) < 0.0010 and np.mean(naive) > 0.004


# C8: bootstrap comparison both ways
def test_c8_bootstrap_compare():
    rng = np.random.default_rng(8)
    dbar = rng.normal(0.02, 0.02, size=40)
    res = dm_hln(dbar)
    boot = game_bootstrap_ci(dbar, draws=2000, seed=688)
    cmp_ = compare_to_bootstrap(res, boot)
    w_h = res["ci95"][1] - res["ci95"][0]
    w_b = boot["ci95"][1] - boot["ci95"][0]
    assert cmp_["width_gap_pct"] == pytest.approx(abs(w_b - w_h) / w_h * 100, abs=1e-9)
    assert cmp_["flag"] == "WITHIN_25PCT" and cmp_["sign_agree"] is True
    idx = np.random.default_rng(688).integers(0, 40, size=(2000, 40))
    lo, hi = np.quantile(dbar[idx].mean(axis=1), [0.025, 0.975])
    assert boot["ci95"] == pytest.approx([lo, hi], abs=1e-15)
    fake = {"status": "OK", "ci95": [res["ci95"][0], res["ci95"][0] + 0.5 * w_h]}
    far = compare_to_bootstrap(res, fake)
    assert far["flag"] == "WIDTH_GAP_OVER_25PCT" and far["width_gap_pct"] == pytest.approx(50.0)
    neg = compare_to_bootstrap(res, {"status": "OK", "ci95": [-0.3, -0.1]})
    assert cmp_["sign_hln"] == 1 and neg["sign_boot"] == -1 and neg["sign_agree"] is False
    mid = compare_to_bootstrap(res, {"status": "OK", "ci95": [-0.01, 0.03]})
    assert mid["sign_boot"] == 0 and mid["sign_agree"] is False


# C9: degenerate and invalid inputs
def test_c9_degenerate_inputs():
    assert dm_hln([])["status"] == "INSUFFICIENT"
    assert dm_hln([0.3])["status"] == "INSUFFICIENT"
    assert dm_hln([0.1, 0.2], h=2)["status"] == "INSUFFICIENT"
    assert dm_hln([0.1, 0.2, 0.3], h=3)["status"] == "INSUFFICIENT"
    assert dm_hln([0.1, 0.2, 0.3], h=5)["status"] == "INSUFFICIENT"  # factor > 0 here
    assert dm_hln([0.2] * 7)["status"] == "NONPOSITIVE_VARIANCE"
    assert dm_hln([0.3] * 7 + [0.30000000000000004])["status"] == "NONPOSITIVE_VARIANCE"
    assert dm_hln([1, -1, 1, -1, 1, -1], h=2)["status"] == "NONPOSITIVE_VARIANCE"
    z = dm_hln([-1.0, 1.0, -2.0, 2.0])
    assert z["status"] == "OK" and z["hln"] == 0.0 and z["ci95"][0] < 0 < z["ci95"][1]
    for bad_h in (0, -1, 1.0, True):
        with pytest.raises(ValueError):
            dm_hln([1, 2, 3], h=bad_h)
    for bad in ([1, float("nan")], [1, float("inf")]):
        with pytest.raises(ValueError):
            dm_hln(bad)
    with pytest.raises(ValueError):
        game_level_dm([0.1, 0.2], [0.1], ["a", "b"])
    one = game_level_dm([0.2, 0.3, 0.1], [0.1, 0.1, 0.1], ["g", "g", "g"])
    assert one["status"] == "INSUFFICIENT" and one["n_games"] == 1
    flat = corp([0.3, 0.6, 0.9], [1, 1, 1])
    assert flat["UNC"] == 0.0 and abs(flat["identity_residual"]) < 1e-12
    small = brier_decomposition([0.2, 0.8], [0, 1])
    assert small["status"] == "INSUFFICIENT_DATA" and small["bias_corrected"] is None
    with pytest.raises(ValueError):
        corp([1.2, 0.5], [1, 0])
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            corp([bad, 0.5], [1, 0])
    with pytest.raises(ValueError):
        corp([0.2, 0.5], [2, 0])
    assert compare_to_bootstrap(dm_hln([1.0]), {"status": "OK", "ci95": [0, 1]})["status"] \
        == "INSUFFICIENT"


# C10: CLI in a fresh process, strict JSON
def test_c10_cli_fresh_process(tmp_path):
    rng = np.random.default_rng(10)
    rows = ["game_id,loss_ref,loss_cand"]
    for g in range(12):
        for _ in range(int(rng.integers(5, 40))):
            a = rng.uniform(0.1, 0.4)
            rows.append(f"G{g},{a:.6f},{a - 0.01 + rng.normal(0, 0.02):.6f}")
    (tmp_path / "rows.csv").write_text("\n".join(rows) + "\n", encoding="ascii")
    py = ["p,y"] + [f"{p:.4f},{int(rng.random() < p)}" for p in rng.uniform(0, 1, 200)]
    (tmp_path / "py.csv").write_text("\n".join(py) + "\n", encoding="ascii")
    cmd = [sys.executable, "-m", "scripts.platformkit.eval_gate.paired_tests",
           "--csv", str(tmp_path / "rows.csv"), "--reliability-csv", str(tmp_path / "py.csv")]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=True)
    assert proc.stdout.isascii()

    def _raise(tok):
        raise ValueError(tok)
    rep = json.loads(proc.stdout, parse_constant=_raise)
    for key in ("row", "report_only", "estimand", "dm_hln", "bootstrap", "compare"):
        assert key in rep
    assert rep["row"] == "S688" and rep["report_only"] is True
    assert rep["dm_hln"]["n_games"] == 12 and rep["dm_hln"]["status"] == "OK"
    assert rep["corp"]["status"] == "OK" and rep["brier_decomposition"]["status"] == "OK"
    assert rep["compare"]["flag"] in ("WITHIN_25PCT", "WIDTH_GAP_OVER_25PCT")
    games = np.array(rep["dm_hln"]["game_means"])  # bootstrap resamples GAMES
    assert rep["bootstrap"]["ci95"] == pytest.approx(
        game_bootstrap_ci(games, draws=2000, seed=688)["ci95"], abs=1e-12)
