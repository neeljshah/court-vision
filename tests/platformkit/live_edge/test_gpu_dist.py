"""Per-file test for gpu_dist.py -- small synthetic fit/predict + torch-cuda
fallback path, on real hardware (RTX 4060 confirmed in the STATE.md premise
check; skip with a printed reason if this box lacks a usable GPU)."""
import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.live_edge.tail_calib import gpu_dist as gd
from scripts.platformkit.live_edge.tail_calib import calib as tc
from scripts.platformkit.live_edge.tail_calib import calib_v2 as tc2


def _has_lgbm_gpu() -> bool:
    try:
        import lightgbm as lgb
        lgb.LGBMRegressor(device="gpu", n_estimators=2, verbosity=-1).fit(
            np.random.rand(20, 1), np.random.rand(20))
        return True
    except Exception:
        return False


def _synthetic_discovery(n_entities=6, n_games=40, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_entities):
        mean = 10 + e * 3
        vals = rng.normal(mean, 4.0, n_games)
        for v in vals:
            rows.append({"player_id": e, "pts": max(v, 0.0)})
    return pd.DataFrame(rows)


@pytest.mark.skipif(not _has_lgbm_gpu(), reason="LightGBM GPU build unavailable on this box")
def test_fit_predict_monotonic_and_gpu_device():
    disc = _synthetic_discovery()
    fit = gd.fit_gpu_quantiles(disc, "player_id", "pts", min_n=5)
    assert fit["device"] == "lightgbm-gpu"
    quantiles = gd.predict_entity_quantiles(fit)
    assert set(quantiles.keys()) == set(range(6))
    for e, m in quantiles.items():
        vals = [m["quantiles"][str(q)] for q in gd.QUANTILES]
        assert vals == sorted(vals)  # monotonic non-crossing


@pytest.mark.skipif(not _has_lgbm_gpu(), reason="LightGBM GPU build unavailable on this box")
def test_plugs_into_calib_ppf_cdf_and_crps():
    """The whole point of gpu_dist: its output dict must be a drop-in for
    calib.py/calib_v2.py's ppf/cdf/CRPS -- verify that end to end."""
    disc = _synthetic_discovery()
    fit = gd.fit_gpu_quantiles(disc, "player_id", "pts", min_n=5)
    quantiles = gd.predict_entity_quantiles(fit)
    m = quantiles[0]
    ppf_mid = tc2.tail_aware_v2_ppf(0.5, m["quantiles"])
    cdf_mid = tc2.tail_aware_v2_cdf(ppf_mid, m["quantiles"])
    assert 0.0 <= cdf_mid <= 1.0
    crps = tc.crps_approx(lambda q: tc2.tail_aware_v2_ppf(q, m["quantiles"]), 10.0)
    assert np.isfinite(crps) and crps >= 0.0
    # tails extrapolate smoothly (no flat clip): a value far beyond the max
    # anchor must map to a CDF strictly less than 1 (open-ended, not pinned).
    far_beyond = max(m["quantiles"].values()) + 50.0
    assert tc2.tail_aware_v2_cdf(far_beyond, m["quantiles"]) < 1.0


def test_torch_cuda_fallback_path_runs():
    """Directly exercises the torch-cuda quantile-embedding fallback (not
    reachable via the LightGBM-GPU happy path on this box) -- skip loudly if
    this machine has no CUDA device at all (GPU requirement, not a soft skip)."""
    import torch
    if not torch.cuda.is_available():
        pytest.skip("torch.cuda unavailable on this box -- GPU requirement cannot be met here")
    rng = np.random.default_rng(1)
    y = rng.normal(20.0, 5.0, 200)
    codes = rng.integers(0, 3, 200)
    model = gd._train_torch_quantiles(codes, y)
    preds = model.predict(np.array([0, 1, 2]))
    assert preds.shape == (3, len(gd.QUANTILES))
