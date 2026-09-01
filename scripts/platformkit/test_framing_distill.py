"""Synthetic-data tests for framing_distill (prereg harness).

Pre-registered machinery checks:
  1. a planted framing-relevant signal in the command_* candidate columns
     must be recovered (verdict PASS, both directions, p < eps), and the
     identity-only control must lose to the baseline (no CONTROL_FAIL);
  2. a pure-noise candidate must NOT reject the null (verdict REJECT);
  3. an identity-confounded dataset (location relation flipped between
     corpora, so only catcher identity transfers) must trigger CONTROL_FAIL;
  4. the NOT_TESTABLE readiness path reports missing columns exactly.
"""
import numpy as np
import pandas as pd

from scripts.platformkit import framing_distill as fd

N_ROWS = 12000
N_CATCH = 40
N_PITCH = 80


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _one_corpus(rng, c_eff, p_eff, cand_mode, signal=0.8, year=2023,
                flip=False):
    n = N_ROWS
    catcher = rng.integers(0, N_CATCH, n)
    pitcher = rng.integers(0, N_PITCH, n)
    plate_x = rng.normal(0.0, 0.9, n)
    plate_z = rng.normal(2.5, 0.7, n)
    sz_top = np.full(n, 3.4)
    sz_bot = np.full(n, 1.6)
    balls = rng.integers(0, 4, n)
    strikes = rng.integers(0, 3, n)
    stand = np.where(rng.random(n) < 0.5, "R", "L")
    p_throws = np.where(rng.random(n) < 0.5, "R", "L")
    dist = np.sqrt((plate_x / 0.83) ** 2 + ((plate_z - 2.5) / 0.9) ** 2)
    core = 2.0 - 2.4 * dist
    if flip:  # location relation inverted: only identity transfers OOS
        core = -core
    latent = (core + c_eff[catcher] + p_eff[pitcher]
              + 0.15 * (strikes - balls))
    if cand_mode == "signal":
        u = rng.normal(0.0, 1.0, n)
        latent = latent + signal * u
        cand1 = u + 0.3 * rng.normal(0.0, 1.0, n)
        cand2 = 0.6 * u + rng.normal(0.0, 1.0, n)
    else:  # pure noise, independent of the outcome
        cand1 = rng.normal(0.0, 1.0, n)
        cand2 = rng.normal(0.0, 1.0, n)
    y = (rng.random(n) < _sigmoid(latent)).astype(float)
    game_date = (pd.Timestamp("%d-04-01" % year)
                 + pd.to_timedelta(rng.integers(0, 180, n), unit="D"))
    return pd.DataFrame({
        "fielder_2": catcher, "pitcher": pitcher, "stand": stand,
        "p_throws": p_throws, "balls": balls, "strikes": strikes,
        "plate_x": plate_x, "plate_z": plate_z,
        "sz_top": sz_top, "sz_bot": sz_bot,
        "command_target_dev_x_ft": cand1,
        "command_target_height_ft": cand2,
        "game_date": game_date,
        "y": y,
    })


def _synth_pair(seed, cand_mode):
    rng = np.random.default_rng(seed)
    c_eff = rng.normal(0.0, 0.35, N_CATCH)
    p_eff = rng.normal(0.0, 0.20, N_PITCH)
    a = _one_corpus(rng, c_eff, p_eff, cand_mode, year=2023)
    b = _one_corpus(rng, c_eff, p_eff, cand_mode, year=2024)
    return a, b


def test_planted_effect_recovered():
    a, b = _synth_pair(7, "signal")
    res = fd.run_prereg(a, b, np.random.default_rng(11))
    assert res["verdict"] == "PASS"
    assert res["control_ok"]
    for r in res["directions"]:
        assert r["cand_brier"] < r["base_brier"]
        assert r["p_catcher_cluster"] < fd.EPS
        assert r["baseline_skillful"]
        assert r["control_loses"]
        assert r["control_brier"] > r["base_brier"]
    # game_date declared tension: only 2023->2024 uses strictly earlier pitches
    assert res["directions"][0]["effects_use_only_earlier"]
    assert not res["directions"][1]["effects_use_only_earlier"]
    assert len(res["planted_null"]) == 2 * fd.N_NULL_SEEDS
    assert not all(fd.direction_pass(r) for r in res["planted_null"])


def test_identity_confounded_triggers_control_fail():
    rng = np.random.default_rng(23)
    c_eff = rng.normal(0.0, 0.7, N_CATCH)
    p_eff = rng.normal(0.0, 0.10, N_PITCH)
    a = _one_corpus(rng, c_eff, p_eff, "signal", year=2023, flip=False)
    b = _one_corpus(rng, c_eff, p_eff, "signal", year=2024, flip=True)
    res = fd.run_prereg(a, b, np.random.default_rng(29))
    assert res["verdict"] == "CONTROL_FAIL"
    assert not res["control_ok"]
    assert any(not r["control_loses"] for r in res["directions"])


def test_null_not_rejected():
    a, b = _synth_pair(13, "noise")
    res = fd.run_prereg(a, b, np.random.default_rng(17))
    assert res["verdict"] == "REJECT"
    assert not all(fd.direction_pass(r) for r in res["directions"])


def test_readiness_reports_missing(tmp_path):
    miss = fd.readiness(root=str(tmp_path))
    assert set(miss) == {2023, 2024}
    for year in miss:
        assert miss[year] and "file absent" in miss[year][0]
