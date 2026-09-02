"""Synthetic per-file tests for scripts.platformkit.eval_gate.stacker (S06).

Tmp ledger + tmp prereg ONLY -- the real ledger and real prereg are never touched.
Fixed seed; no network, no store. Run:
    python -m pytest scripts/platformkit/eval_gate/test_stacker.py -q
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from scripts.platformkit.eval_gate import stacker as S


def _mk(seed: int = 7, n_games: int = 64, n_dates: int = 8, tpg: int = 60, ghost: bool = False):
    """Deterministic-outcome corpus: arm 'raw_model' tracks the latent q (dominant);
    'arm_noise' is uninformative; optional 'ghost' arm is absent at EVERY tick."""
    rng = np.random.default_rng(seed)
    ticks, arms = [], {"raw_model": [], "arm_noise": []}
    if ghost:
        arms["ghost"] = []
    for g in range(n_games):
        date = "2026-06-%02d" % (1 + g % n_dates)
        gid = "%s-%06d" % (date, g)                       # unique fake team codes per game
        lo, hi = (0.1, 0.45) if rng.random() < 0.5 else (0.55, 0.9)
        q = float(rng.uniform(lo, hi))
        y = 1 if q > 0.5 else 0                            # deterministic, margin >= 0.05
        for j in range(tpg):
            ts = "%sT%02d:%02d:%02d+00:00" % (date, 18 + j // 60, j % 60, g % 60)
            inning = 2 if j < tpg // 2 else 8              # two planted regimes per game
            ticks.append({"game": gid, "timestamp": ts, "outcome": y,
                          "model_prob": float(np.clip(q + rng.normal(0, 0.01), 0.02, 0.98)),
                          "market_prob": float(np.clip(q + rng.normal(0, 0.01), 0.02, 0.98)),
                          "state_summary": "inning=%d" % inning, "_row_id": len(ticks)})
            arms["raw_model"].append(ticks[-1]["model_prob"])
            arms["arm_noise"].append(float(rng.uniform(0.05, 0.95)))
            if ghost:
                arms["ghost"].append(None)
    return ticks, arms, [S.inning_bucket(t) for t in ticks]


def test_dominant_arm_not_beaten():
    """Outer walk-forward stacker Brier <= the dominant arm's on the scored set."""
    ticks, arms, regimes = _mk()
    stack, folds = S.outer_walk_forward(ticks, arms, regimes, fallback="raw_model")
    assert any(not f["fallback_used"] for f in folds), "fitted path never exercised"
    idx = [i for i in range(len(ticks)) if stack[i] is not None]
    assert len(idx) > 1000
    y = [float(ticks[i]["outcome"]) for i in idx]
    b_stack = S.brier([stack[i] for i in idx], y)
    b_dom = S.brier([arms["raw_model"][i] for i in idx], y)
    assert b_stack <= b_dom, "stacker %.6f worse than dominant arm %.6f" % (b_stack, b_dom)


def test_masked_arm_never_contributes():
    """An arm absent at every tick changes NOTHING (mask semantics, never 0.5)."""
    ticks_a, arms_a, regimes = _mk(ghost=False)
    ticks_b, arms_b, _ = _mk(ghost=True)
    assert [t["timestamp"] for t in ticks_a] == [t["timestamp"] for t in ticks_b]
    out_a, _ = S.outer_walk_forward(ticks_a, arms_a, regimes, fallback="raw_model")
    out_b, _ = S.outer_walk_forward(ticks_b, arms_b, regimes, fallback="raw_model")
    assert out_a == out_b, "ghost arm changed predictions -- 0.5 imputation leaked in"


def test_regime_weights_differ():
    """fit_meta with a regime key learns DIFFERENT weights across two planted regimes."""
    rng = np.random.default_rng(11)
    n = 2000
    preds = rng.uniform(0.05, 0.95, size=(n, 2))
    reg = np.array(["rA"] * (n // 2) + ["rB"] * (n // 2))
    y = np.where(reg == "rA", (preds[:, 0] > 0.5), (preds[:, 1] > 0.5)).astype(float)
    W = S.fit_meta(preds, y, regime=reg)
    assert W.shape == (2, 3)
    assert W[0][1] > W[1][1], "arm-1 weight not higher in its own regime"
    assert W[1][2] > W[0][2], "arm-2 weight not higher in its own regime"


def test_trial_charges_tmp_ledger_and_seals(tmp_path):
    """SEAL -> CHARGE order on a tmp ledger: one row, K from the row, sha verified."""
    ticks, arms, regimes = _mk(n_games=32, tpg=30)
    prereg = tmp_path / "prereg.md"
    prereg.write_text("synthetic prereg for the stacker per-file test\n", encoding="ascii")
    sha = hashlib.sha256(prereg.read_bytes()).hexdigest()
    led, out, ser = tmp_path / "fwer.jsonl", tmp_path / "trial.json", tmp_path / "series.csv"
    result = S.run_stacker_trial(ticks, arms, sport="mlb", ledger_path=led, prereg_sha256=sha,
                                 prereg_path=prereg, regimes=regimes, fallback="raw_model",
                                 pair="raw_model", out_path=out, series_path=ser)
    rows = [json.loads(line) for line in led.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["k_cumulative"] == 1 and rows[0]["predictor"] == S.SPEC_ID
    assert result["k_at_launch"] == 1 and result["prereg_sha256"] == sha
    assert result["verdict"] in ("AHEAD", "BEHIND")
    assert result["n_scored_ticks"] > 0 and out.exists() and ser.exists()
    assert json.loads(out.read_text())["ledger_row"]["k_cumulative"] == 1
    # wrong sha: refused BEFORE any charge -- the tmp ledger must not grow
    with pytest.raises(AssertionError, match="prereg sha mismatch"):
        S.run_stacker_trial(ticks, arms, sport="mlb", ledger_path=led, prereg_sha256="0" * 64,
                            prereg_path=prereg, regimes=regimes, fallback="raw_model", pair="raw_model")
    assert len(led.read_text().splitlines()) == 1, "failed seal check still charged the ledger"
