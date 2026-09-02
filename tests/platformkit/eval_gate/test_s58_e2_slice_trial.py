"""S58 trial-1 module: seal-before-charge on a TMP ledger, K read from the row, planted verdicts.
python -m pytest tests/platformkit/eval_gate/test_s58_e2_slice_trial.py -q"""
import hashlib, json

import numpy as np
import pytest

from scripts.platformkit.eval_gate import s58_e2_slice_trial as T


def _ticks(n_games=8, per=25, seed=0):
    rng = np.random.default_rng(seed)
    ticks, cand, inc = [], [], []
    for g in range(n_games):
        y = int(rng.integers(0, 2))
        for k in range(per):
            p = float(np.clip(0.5 + (0.3 if y else -0.3) + rng.normal(0, 0.1), 0.02, 0.98))
            ticks.append({"game": "2026-07-%02d-AAABBB%d" % (1 + g // 4, g), "timestamp": "2026-07-%02dT%02d:00:00Z" % (1 + g // 4, k),
                          "outcome": y, "market_prob": p, "model_prob": p, "_row_id": len(ticks)})
            inc.append(p)                                     # incumbent = calibrated
            cand.append(float(np.clip(p + rng.normal(0, 0.25), 0.02, 0.98)))  # candidate = noisier (worse)
    return ticks, cand, inc


def test_seal_then_charge_then_score(tmp_path):
    ticks, cand, inc = _ticks()
    prereg = tmp_path / "prereg.md"; prereg.write_text("frozen text", "ascii")
    ledger = tmp_path / "ledger.jsonl"
    with pytest.raises(AssertionError):                        # bad seal: nothing charged
        T.run_trial(ticks, cand, inc, range(len(ticks)), ledger_path=ledger, prereg_path=prereg, prereg_sha256="00")
    assert not ledger.exists()
    seal = hashlib.sha256(prereg.read_bytes()).hexdigest()
    res = T.run_trial(ticks, cand, inc, range(len(ticks)), ledger_path=ledger, prereg_path=prereg, prereg_sha256=seal,
                      repro=[("inc", inc, range(len(ticks)), T.brier(inc, [t["outcome"] for t in ticks]))],
                      out_path=tmp_path / "out.json")
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["k_cumulative"] == 1 == res["k_at_launch"]
    assert rows[0]["family"] == T.FAMILY and rows[0]["tier"] == "T2" and rows[0]["prereg_sha256"] == seal
    assert res["verdict"] == "BEHIND" and res["improvement"] < 0 and res["n_games"] == 8
    assert res["bars"]["n_family"] == 1 and res["single_window"] is True
    assert json.loads((tmp_path / "out.json").read_text())["prereg_sha256"] == seal


def test_repro_gate_stops_trial_after_charge(tmp_path):
    ticks, cand, inc = _ticks(seed=1)
    prereg = tmp_path / "p.md"; prereg.write_text("x", "ascii"); ledger = tmp_path / "l.jsonl"
    with pytest.raises(AssertionError, match="ARM REPRODUCTION FAILED"):
        T.run_trial(ticks, cand, inc, range(len(ticks)), ledger_path=ledger, prereg_path=prereg,
                    prereg_sha256=hashlib.sha256(b"x").hexdigest(), repro=[("inc", inc, range(len(ticks)), 0.123)])
    assert len(ledger.read_text().splitlines()) == 1       # charged (Q2), then stopped with no verdict
