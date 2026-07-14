"""Per-file test for gpu_dist_v2.py -- the coverage-constrained GPU quantile
recalibration. Covers the new logic only (gpu_dist.py's own training path is
covered elsewhere); one small integration case confirms the real GPU fit
plugs into recalibrate_predictions without a key/shape mismatch.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.tail_calib import gpu_dist_v2 as gd2


def test_recalibrate_entity_matches_anchor_exactly():
    gpu_q = {"0.05": 0.0, "0.50": 10.0, "0.95": 20.0}
    emp_q = {"0.05": 5.0, "0.50": 15.0, "0.95": 25.0}
    out = gd2.recalibrate_entity(gpu_q, emp_q)
    assert abs(out["0.05"] - emp_q["0.05"]) < 1e-9
    assert abs(out["0.95"] - emp_q["0.95"]) < 1e-9


def test_recalibrate_entity_preserves_monotonicity():
    gpu_q = {"0.05": 1.0, "0.25": 3.0, "0.50": 4.0, "0.75": 6.0, "0.95": 9.0}
    emp_q = {"0.05": 2.0, "0.25": 4.0, "0.50": 8.0, "0.75": 12.0, "0.95": 20.0}
    out = gd2.recalibrate_entity(gpu_q, emp_q)
    vals = [out[k] for k in ("0.05", "0.25", "0.50", "0.75", "0.95")]
    assert vals == sorted(vals)


def test_recalibrate_entity_degenerate_falls_back_to_empirical():
    gpu_q = {"0.05": 5.0, "0.95": 5.0}  # flat GPU quantiles -- zero span
    emp_q = {"0.05": 2.0, "0.95": 8.0}
    out = gd2.recalibrate_entity(gpu_q, emp_q)
    assert out == emp_q


def test_recalibrate_predictions_skips_insufficient_and_missing():
    fit_gpu = {"a": {"quantiles": {"0.05": 0.0, "0.95": 10.0}},
               "b": {"quantiles": {"0.05": 0.0, "0.95": 10.0}}}
    fit_emp = {"a": {"insufficient": False, "quantiles": {"0.05": 1.0, "0.95": 11.0}},
               "b": {"insufficient": True}}
    out = gd2.recalibrate_predictions(fit_gpu, fit_emp)
    assert set(out) == {"a"}
    assert out["a"]["insufficient"] is False
    assert "mean" in out["a"] and "std" in out["a"]


def test_fit_gpu_v2_integration_shape():
    """Tiny synthetic discovery set through the real GPU fit -- catches any
    key/shape mismatch between gpu_dist's output and calib's fit_predictors
    output before it hits the full 3-corpora suite."""
    rng = np.random.default_rng(0)
    rows = []
    for entity in ("p1", "p2"):
        for v in rng.normal(20, 5, size=15):
            rows.append({"player_id": entity, "pts": max(float(v), 0.0)})
    disc = pd.DataFrame(rows)
    fit = gd2.fit_gpu_v2(disc, "player_id", "pts")
    assert fit["device"] in ("lightgbm-gpu", "torch-cuda")
    assert set(fit["quantiles"]) <= {"p1", "p2"}
    for m in fit["quantiles"].values():
        qs = sorted(float(k) for k in m["quantiles"])
        vals = [m["quantiles"][str(q)] for q in qs]
        assert vals == sorted(vals)
