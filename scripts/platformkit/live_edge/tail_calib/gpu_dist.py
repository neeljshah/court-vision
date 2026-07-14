"""scripts.platformkit.live_edge.tail_calib.gpu_dist -- GPU-DIST: a GPU-trained
conditional quantile-regression predictive distribution, aimed at the ONE
residual ceiling left after TAIL-CALIB-v2 (4227a526): width is fixed by the
empirical-quantile predictor, but its PIT body-shape still regresses vs Normal
(v2's parametric tail proved that's NOT a clip artifact -- it's a real
finite-sample noisy-quantile miscalibration).

Same feature as the incumbent uses: entity identity only (tails.py's
compute_tail_metrics conditions purely on entity_col groupby; no other
covariate is fit anywhere in tail_calib). This isolates the test to "does a
regularized, GPU-trained quantile MODEL smooth the noisy per-entity empirical
quantiles better than raw sample quantiles" -- not "do new features help".

Per quantile in the SHARED grid (calib.QUANTILES, 13 points), one LightGBM
quantile regressor (device='gpu', objective='quantile') is trained on
(entity_id -> stat). Predicted quantiles are sorted per entity (Chernozhukov
rearrangement) for a monotonic, non-crossing grid -- then handed to
calib_v2's parametric-tail ppf/cdf (imported, never re-implemented) for a
smooth, non-flat CDF/PPF, exactly like the v1/v2 predictors' "quantiles"
dict shape -- so this predictor plugs into calib.py/calib_v2.py/promote_gate.py's
existing crps_approx/pit_uniformity/entity_diffs machinery unmodified.

GPU REQUIRED: primary path is LightGBM device='gpu' (OpenCL, confirmed
working on this box's RTX 4060 -- device='cuda' fails, tree learner not
compiled with CUDA). If that raises, falls back to a torch-cuda quantile
embedding trained with pinball loss (torch.cuda confirmed True) -- NEVER
silently to CPU; a CPU fallback is reported loudly as a GPU-requirement FAIL.

INVARIANTS: <=300 LOC. ASCII stdout. Never writes data/registry/. No $/edge
claims -- calibration language only.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.tail_calib import calib as tc

QUANTILES = tc.QUANTILES  # shared 13-pt grid -- same instrument as v1/v2
N_ESTIMATORS = 200
NUM_LEAVES = 15
MIN_CHILD_SAMPLES = 20


def _train_lgbm_quantiles(X: pd.DataFrame, y: np.ndarray) -> dict:
    import lightgbm as lgb
    models = {}
    for q in QUANTILES:
        m = lgb.LGBMRegressor(objective="quantile", alpha=q, device="gpu",
                               n_estimators=N_ESTIMATORS, num_leaves=NUM_LEAVES,
                               min_child_samples=MIN_CHILD_SAMPLES, verbosity=-1)
        m.fit(X, y)
        models[q] = m
    return models


def _predict_lgbm_quantiles(models: dict, X_pred: pd.DataFrame) -> np.ndarray:
    cols = [models[q].predict(X_pred) for q in QUANTILES]
    return np.stack(cols, axis=1)  # (n_rows, n_quantiles)


class _QuantileEmbed:
    """torch-cuda fallback: one learned quantile vector per entity, fit by
    pinball-loss gradient descent (the torch analog of per-entity quantile
    regression when LightGBM's GPU build is unusable). ponytail: a plain
    embedding table is the whole model -- entity IS the only feature, so
    there is nothing for a deeper net to condition on beyond it."""

    def __init__(self, n_entities: int, n_quantiles: int, torch_mod):
        self.torch = torch_mod
        nn = torch_mod.nn
        self.device = torch_mod.device("cuda")
        self.emb = nn.Embedding(n_entities, n_quantiles).to(self.device)

    def fit(self, codes: np.ndarray, y: np.ndarray, quantiles: list[float],
            epochs: int = 300, lr: float = 0.5):
        torch = self.torch
        idx = torch.tensor(codes, dtype=torch.long, device=self.device)
        yt = torch.tensor(y, dtype=torch.float32, device=self.device)
        qs = torch.tensor(quantiles, dtype=torch.float32, device=self.device)
        # init each entity's row at the GLOBAL empirical quantiles -- gives
        # the optimizer a sane starting point instead of random noise.
        with torch.no_grad():
            init = torch.tensor(np.quantile(y, quantiles), dtype=torch.float32, device=self.device)
            self.emb.weight.copy_(init.unsqueeze(0).expand(self.emb.weight.shape[0], -1))
        opt = torch.optim.Adam(self.emb.parameters(), lr=lr)
        for _ in range(epochs):
            opt.zero_grad()
            pred = self.emb(idx)
            diff = yt.unsqueeze(1) - pred
            loss = torch.maximum(qs * diff, (qs - 1) * diff).mean()
            loss.backward()
            opt.step()
        return self

    def predict(self, codes: np.ndarray) -> np.ndarray:
        torch = self.torch
        idx = torch.tensor(codes, dtype=torch.long, device=self.device)
        with torch.no_grad():
            return self.emb(idx).cpu().numpy()


def _train_torch_quantiles(codes: np.ndarray, y: np.ndarray) -> _QuantileEmbed:
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU REQUIREMENT FAIL: neither LightGBM GPU nor "
                            "torch.cuda are usable -- refusing a silent CPU fallback.")
    model = _QuantileEmbed(int(codes.max()) + 1, len(QUANTILES), torch)
    model.fit(codes, y, QUANTILES)
    return model


def fit_gpu_quantiles(discovery: pd.DataFrame, entity_col: str, stat_col: str,
                       min_n: int | None = None) -> dict:
    """Fit the GPU conditional quantile model on discovery rows. Returns a
    dict {device, categories, models|torch_model} consumable by
    predict_entity_quantiles. Entity population mirrors tails.MIN_N exactly
    (same population every predictor is scored on)."""
    min_n = tl.MIN_N if min_n is None else min_n
    counts = discovery.groupby(entity_col, observed=True)[stat_col].count()
    valid = counts[counts >= min_n].index
    train_df = discovery[discovery[entity_col].isin(valid)].copy()
    train_df["_entity"] = train_df[entity_col].astype("category")
    categories = list(train_df["_entity"].cat.categories)
    y = train_df[stat_col].to_numpy(dtype=float)

    t0 = time.perf_counter()
    try:
        X = train_df[["_entity"]]
        models = _train_lgbm_quantiles(X, y)
        device, payload = "lightgbm-gpu", {"models": models}
    except Exception as exc:  # noqa: BLE001 -- must fall back, not crash the lane
        print(f"[gpu_dist] LightGBM GPU path FAILED ({exc!r}) -- "
              f"falling back to torch-cuda quantile embedding")
        codes = train_df["_entity"].cat.codes.to_numpy()
        torch_model = _train_torch_quantiles(codes, y)
        device, payload = "torch-cuda", {"torch_model": torch_model}
    fit_seconds = time.perf_counter() - t0
    print(f"[gpu_dist] fit device={device} entities={len(categories)} "
          f"rows={len(train_df)} seconds={fit_seconds:.2f}")
    return {"device": device, "categories": categories, "fit_seconds": fit_seconds, **payload}


def predict_entity_quantiles(fit: dict) -> dict[object, dict]:
    """Per-entity monotonic quantile dict, SAME shape as
    tails.compute_tail_metrics()[e]['quantiles'] -- so calib.py's
    tail_aware_ppf / calib_v2.py's tail_aware_v2_ppf / calib.crps_approx work
    on this predictor completely unmodified (fair, zero-reimplementation
    comparison)."""
    categories = fit["categories"]
    n = len(categories)
    if fit["device"] == "lightgbm-gpu":
        X_pred = pd.DataFrame({"_entity": pd.Categorical(categories, categories=categories)})
        raw = _predict_lgbm_quantiles(fit["models"], X_pred)
    else:
        raw = fit["torch_model"].predict(np.arange(n))
    raw_sorted = np.sort(raw, axis=1)  # Chernozhukov rearrangement -- monotonic, non-crossing

    out = {}
    for i, e in enumerate(categories):
        qdict = {str(q): float(v) for q, v in zip(QUANTILES, raw_sorted[i])}
        out[e] = {
            "insufficient": False,
            "mean": float(np.mean(raw_sorted[i])),
            "std": float(np.std(raw_sorted[i], ddof=1)),
            "quantiles": qdict,
        }
    return out
