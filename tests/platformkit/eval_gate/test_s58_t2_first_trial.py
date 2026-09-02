"""S58 T2 #1 module: seal refuses drift, one fresh fit per CPCV train set, d oriented model-better.
python -m pytest tests/platformkit/eval_gate/test_s58_t2_first_trial.py -q"""
import hashlib

import numpy as np
import pytest

from scripts.platformkit.eval_gate import s58_t2_first_trial as T


def test_seal_check_normalises_crlf_and_refuses_drift(tmp_path):
    body = b"line one\nline two\n"
    path = tmp_path / "prereg.md"
    path.write_bytes(body.replace(b"\n", b"\r\n"))
    assert T.seal_check(path, hashlib.sha256(body).hexdigest()) == hashlib.sha256(body).hexdigest()
    with pytest.raises(RuntimeError):
        T.seal_check(path, "0" * 64)


def _state(i, x):
    return {"game_id": "g%d" % i, "features": {"p_ref": 0.5, "f": x}, "outcome": i % 2}


def test_per_path_predictor_refits_when_the_train_set_changes():
    pred = T.PerPathPredictor("f")
    train_a = [_state(i, float(i)) for i in range(40)]
    train_b = [_state(i, float(-i)) for i in range(40)]   # same length, same bucket, different rows
    pred(train_a, _state(99, 1.0), True)
    pred(train_a, _state(98, 2.0), True)
    assert pred.archive()["n_paths"] == 1
    pred(train_b, _state(97, 1.0), True)
    assert pred.archive()["n_paths"] == 2                 # RealScreenPredictor alone would reuse fit A
    with pytest.raises(ValueError):
        pred(train_a, _state(96, 1.0), False)


def test_unit_improvement_is_close_minus_model():
    y = np.array([1, 0, 1, 0, 1, 0])
    model, close = np.array([0.9, 0.1, 0.9, 0.1, 0.9, 0.1]), np.array([0.6, 0.4, 0.6, 0.4, 0.6, 0.4])
    u = T._unit(model, close, y, ["a", "b", "c", "a", "b", "c"])
    assert u["improvement"] == pytest.approx(0.16 - 0.01) and u["ci_lo"] > 0 and u["n"] == 6
