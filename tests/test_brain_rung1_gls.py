"""P2.2 — control_brain Rung-1 GLS redundancy weights (gated CV_BRAIN_GLS).

Proves: (1) the redundancy formula down-weights a correlated cluster and up-weights a decorrelated
engine; (2) with the flag OFF the brain stays equal-weight (byte-identical); (3) with the flag ON +
a decorrelation artifact present, engine_weights routes through Rung 1. No skill claim — redundancy
guard only (D03 §4.4).
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import brain.control_brain as cb  # noqa: E402


def _preds(n):
    return [{"engine": f"e{i}", "margin_home": float(i), "margin_sd": 5.0,
             "win_prob_home": 0.5, "total": 220.0, "home_pts": 110.0, "away_pts": 110.0,
             "n_models": 1, "n_signals": 0, "notes": ""} for i in range(n)]


# corr: e0,e1,e2 a tight net-rating cluster (r=0.95); e3 decorrelated (r=0)
_CORR = [[1.0, 0.95, 0.95, 0.0],
         [0.95, 1.0, 0.95, 0.0],
         [0.95, 0.95, 1.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]]


def test_gls_formula_downweights_cluster():
    w = cb.gls_redundancy_weights(np.asarray(_CORR, dtype=float))
    assert w.shape == (4,)
    assert abs(float(w.sum()) - 1.0) < 1e-9
    assert (w >= 0).all()
    # the decorrelated engine e3 must outweigh any single clustered engine
    assert w[3] > w[0] and w[3] > w[1] and w[3] > w[2]


def test_default_is_equal_weight_byte_identical():
    # flag unset -> Rung 0 equal weight, byte-identical to margins.mean()
    os.environ.pop("CV_BRAIN_GLS", None)
    preds = _preds(7)
    w = cb.engine_weights(preds)
    assert np.allclose(w, 1.0 / 7)
    margins = np.array([p["margin_home"] for p in preds])
    assert abs(float((w * margins).sum()) - float(margins.mean())) < 1e-12


def test_gls_on_routes_through_rung1(monkeypatch):
    decorr = {"corr_matrix": _CORR, "engines": ["e0", "e1", "e2", "e3"], "n_eff_full": 1.6}
    monkeypatch.setattr(cb, "_load_decorr", lambda: decorr)
    monkeypatch.setattr(cb.os.path, "exists", lambda p: True)  # decorr artifact "present"
    monkeypatch.setenv("CV_BRAIN_GLS", "1")
    w = cb.engine_weights(_preds(4))
    assert abs(float(w.sum()) - 1.0) < 1e-9
    assert w[3] > w[0]  # decorrelated engine up-weighted vs the cluster -> NOT equal weight
    assert not np.allclose(w, 1.0 / 4)
