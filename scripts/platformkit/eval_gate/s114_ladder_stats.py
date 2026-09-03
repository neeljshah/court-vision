"""S114's artifact-side statistics, split out of `s114_ingame_ensemble` for the LOC rail.

Both are PURE functions of the archived per-tick series, moved verbatim -- no number changes.
`paired` is the game-clustered DM on a paired loss differential (Q9's per-unit differential);
`pbo` is the fold-level CSCV probability of backtest overfitting over the k ladder (Bailey et
al.), distinct from `eval_gate.pbo.cscv_pbo`, which re-slices contiguous ROW blocks instead.

Calibration language only. ASCII only. Covered by the S114 per-file test:
python -m pytest tests/platformkit/ingame/test_s114_ingame_ensemble.py -q
"""
from __future__ import annotations

import itertools
import math
from typing import Dict, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.foundry.ingame_screen_nba import _dm_fast, _icc

def paired(series: pd.DataFrame, worse: str, better: str) -> dict:
    """Game-clustered DM on `loss(worse) - loss(better)`; positive means `better` won."""
    y = series["y"].to_numpy(dtype=float)
    delta = ((series[worse].to_numpy(dtype=float) - y) ** 2
             - (series[better].to_numpy(dtype=float) - y) ** 2)
    codes, uniques = pd.factorize(series["game"], sort=False)
    stat, p_raw, ci = _dm_fast(delta, codes, len(uniques))
    rho, size = _icc(delta, codes, len(uniques)), len(series) / max(1, len(uniques))
    return {"improvement": float(delta.mean()), "dm_stat": stat, "dm_p_raw": p_raw, "ci95": ci,
            "icc_game": float(rho), "n_games": int(len(uniques)), "n_eff": float(
                len(series) / max(1.0, 1.0 + (size - 1.0) * rho))}

def pbo(matrix: Dict[str, Dict[int, float]], keys: Sequence[int]) -> dict:
    """CSCV probability of backtest overfitting over k (Bailey et al.). Five folds do not
    split evenly: each 2-fold IS subset is paired with its 3-fold complement, stated here."""
    folds, logits = sorted(matrix), []
    for combo in itertools.combinations(folds, 2):
        best = max(keys, key=lambda k: float(np.mean([matrix[f][k] for f in combo])))
        held = {k: float(np.mean([matrix[f][k] for f in folds if f not in combo])) for k in keys}
        w = (sorted(keys, key=held.get).index(best) + 1) / (len(keys) + 1.0)
        logits.append(math.log(w / (1.0 - w)))
    if not logits:
        return {"pbo": None, "n_splits": 0}
    return {"pbo": float(sum(1 for v in logits if v <= 0.0) / len(logits)),
            "n_splits": len(logits), "median_logit": float(np.median(logits)),
            "is_size": 2, "oos_size": len(folds) - 2, "configs": list(keys)}

__all__ = ["paired", "pbo"]
