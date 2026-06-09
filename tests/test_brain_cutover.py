"""P2 cutover — the control-brain hook in predict_ensemble16.py.

Proves the cutover is SAFE: with CV_BRAIN_WEIGHTS unset the hook returns None so the live ensemble's
equal-weight path is byte-identical; with the flag ON (Rung 0) it returns equal weights, so the fused
eq_margin == margins.mean() exactly. Any failure path returns None (never regresses the ensemble).
This tests the extracted seam directly — no heavy 16-engine run required.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import predict_ensemble16 as pe  # noqa: E402


def _preds(n):
    return [{"engine": f"e{i}", "margin_home": float(i) - n / 2.0, "margin_sd": 5.0,
             "total": 220.0, "win_prob_home": 0.5} for i in range(n)]


def test_hook_off_is_byte_identical():
    # flag unset -> hook returns None -> eq_margin path = margins.mean() (unchanged live behaviour)
    os.environ.pop("CV_BRAIN_WEIGHTS", None)
    assert pe._brain_eng_w(_preds(16)) is None


def test_hook_on_equal_weight_equals_mean(monkeypatch):
    monkeypatch.setenv("CV_BRAIN_WEIGHTS", "1")
    preds = _preds(16)
    w = pe._brain_eng_w(preds)
    assert w is not None and len(w) == 16
    assert np.allclose(w, 1.0 / 16)
    margins = np.array([p["margin_home"] for p in preds])
    # the exact invariant the live fusion relies on: (eng_w * margins).sum() == margins.mean()
    assert abs(float((w * margins).sum()) - float(margins.mean())) < 1e-12


def test_hook_on_empty_preds_is_safe(monkeypatch):
    # engine_weights raises ValueError on empty preds -> hook swallows -> None (no regression)
    monkeypatch.setenv("CV_BRAIN_WEIGHTS", "1")
    assert pe._brain_eng_w([]) is None
