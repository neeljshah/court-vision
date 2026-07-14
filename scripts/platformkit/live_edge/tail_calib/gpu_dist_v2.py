"""scripts.platformkit.live_edge.tail_calib.gpu_dist_v2 -- GPU-DIST v2: the
coverage-constrained variant. v1 (gpu_dist.py, run f37e8e51 -> GPU_DIST_REPORT.
md) was MIXED: GPU quantile regression genuinely smooths the noisy per-entity
empirical quantile vector (better CRPS + PIT-KS on both corpora) but
regularization SHRINKS every entity's predicted quantiles toward the pooled
population level -- narrowing central 50/80/90% coverage below nominal on NBA
(mean abs error 0.0195 -> 0.0624) instead of fixing it.

v2 fix (rails option b -- post-hoc affine rescale): keep gpu_dist.py's trained
quantile model UNCHANGED (imported, never retrained/re-implemented here). Per
entity, affine-transform its smoothed GPU quantile vector so it matches that
SAME entity's own empirical band width/center at q=0.05/0.95 -- the widest
central level the gate checks (nominal 90%) and an exact point on tails.
QUANTILES's 13-pt grid. This pins the widest checked coverage level BY
CONSTRUCTION; the GPU model's interior body-shape smoothing rides along
unchanged (only re-centered/re-scaled, relative spacing untouched), so 50/80%
should track closely too. Degenerate band (empirical or GPU span ~0): fall
back to the empirical quantile vector verbatim -- never risk widening a
collapsed entity into GPU noise.

INVARIANTS: <=300 LOC. ASCII stdout. Never writes data/registry/. No $/edge
claims -- calibration language only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.tail_calib import calib as tc
from scripts.platformkit.live_edge.tail_calib import gpu_dist as gd

ANCHOR_LO, ANCHOR_HI = "0.05", "0.95"  # widest coverage level the gate checks (90%), exact grid pts


def recalibrate_entity(gpu_q: dict, emp_q: dict) -> dict:
    """Affine-map one entity's GPU quantile dict onto its own empirical
    90%-band width/center. Both dicts key on str(tails.QUANTILES) -- same
    convention gpu_dist.predict_entity_quantiles and tails.compute_tail_metrics
    already use, so no re-keying is needed."""
    gpu_lo, gpu_hi = gpu_q[ANCHOR_LO], gpu_q[ANCHOR_HI]
    emp_lo, emp_hi = emp_q[ANCHOR_LO], emp_q[ANCHOR_HI]
    gpu_span, emp_span = gpu_hi - gpu_lo, emp_hi - emp_lo
    if gpu_span <= 1e-9 or emp_span <= 1e-9:
        return dict(emp_q)  # degenerate -- empirical fallback, never widen noise
    scale = emp_span / gpu_span
    center_gpu, center_emp = 0.5 * (gpu_lo + gpu_hi), 0.5 * (emp_lo + emp_hi)
    return {q: center_emp + (v - center_gpu) * scale for q, v in gpu_q.items()}


def recalibrate_predictions(fit_gpu: dict[object, dict], fit_emp: dict[object, dict]) -> dict[object, dict]:
    """Coverage-constrained GPU predictor: SAME {insufficient, mean, std,
    quantiles} shape as gpu_dist.predict_entity_quantiles / tails.
    compute_tail_metrics, so it plugs into calib.py/calib_v2.py/promote_gate.py
    unmodified. Only entities present (and sufficient) in BOTH fits are
    recalibrated -- mirrors the existing intersection gating in
    run_gpu_dist.py's evaluate_3way/gate_gpu_vs_incumbent."""
    out = {}
    for e, gm in fit_gpu.items():
        em = fit_emp.get(e)
        if em is None or em.get("insufficient"):
            continue
        qdict = recalibrate_entity(gm["quantiles"], em["quantiles"])
        vals = np.array(list(qdict.values()), dtype=float)
        out[e] = {"insufficient": False, "mean": float(vals.mean()),
                   "std": float(vals.std(ddof=1)), "quantiles": qdict}
    return out


def fit_gpu_v2(discovery: pd.DataFrame, entity_col: str, stat_col: str) -> dict:
    """One call = the whole v2 predictor: trains gpu_dist's model UNCHANGED,
    fits the empirical incumbent (calib.py's own machinery, same discovery
    rows), then affine-recalibrates each entity. Returns {device, fit_seconds,
    quantiles: {entity: {...}}} -- device/fit_seconds forwarded from the
    underlying GPU fit so the report can print the real device string."""
    gpu_fit = gd.fit_gpu_quantiles(discovery, entity_col, stat_col)
    fit_gpu = gd.predict_entity_quantiles(gpu_fit)
    fit_emp = tc.fit_predictors(discovery, entity_col, stat_col)
    quantiles = recalibrate_predictions(fit_gpu, fit_emp)
    print(f"[gpu_dist_v2] recalibrated {len(quantiles)}/{len(fit_gpu)} GPU entities "
          f"to empirical q={ANCHOR_LO}/{ANCHOR_HI} band (device={gpu_fit['device']})")
    return {"device": gpu_fit["device"], "fit_seconds": gpu_fit["fit_seconds"], "quantiles": quantiles}
