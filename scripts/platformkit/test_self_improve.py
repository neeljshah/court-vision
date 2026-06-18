"""Per-file tests for scripts.platformkit.self_improve -- the calibration ratchet.

Synthetic accumulated-results sets only (NO network, NO real data). We assert:
  * cold start (tiny input) -> INSUFFICIENT_DATA, nothing fabricated;
  * the recalibration path is LEAK-FREE (order-sensitive: shuffling the settled
    stream changes the leak-free walk-forward result, proving each prediction used
    ONLY earlier games);
  * a GENUINE calibration improvement (mis-scaled raw probs) -> SHIP;
  * an injected REGRESSION (already-perfect raw probs that recal can only blur) is
    NOT shipped (HOLD/REJECT, never SHIP) -- the ratchet cannot move backward;
  * the improve_ledger is APPEND-ONLY (each cycle adds exactly one line).

Run ONLY this file:
  python -m pytest scripts/platformkit/test_self_improve.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit import self_improve as SI


# ---------------------------------------------------------------------------
# Synthetic settled-results builders (write the grader's JSONL shape)
# ---------------------------------------------------------------------------


def _write_settled(path: Path, rows, sport="nba"):
    """Write rows as clv_ledger-shaped settled JSONL lines."""
    with path.open("w", encoding="utf-8") as fh:
        for i, (p_raw, y, p_close) in enumerate(rows):
            rec = {
                "sport": sport, "status": "settled", "graded": True,
                "matchup": f"T{i}A vs T{i}B", "side": "home",
                "model_prob": p_raw, "outcome": "win" if y == 1 else "loss",
                "ts": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}+00:00",
            }
            if p_close is not None:
                rec["fair_close_prob"] = p_close
            fh.write(json.dumps(rec) + "\n")


def _miscalibrated_stream(n=300, seed=0):
    """Raw probs that are systematically OVER-confident -> recal can genuinely help.

    True P(win) = q in [0.2,0.8]; the raw model reports a stretched prob (pushed away
    from 0.5), so it is mis-calibrated and an isotonic map fit on history corrects it.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        q = float(rng.uniform(0.2, 0.8))
        y = int(rng.random() < q)
        stretched = float(np.clip(0.5 + (q - 0.5) * 1.8, 0.02, 0.98))
        rows.append((stretched, y, None))
    return rows


def _well_calibrated_stream(n=300, seed=1):
    """Raw probs that already equal the true P(win) -> recal can only add noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        q = float(rng.uniform(0.2, 0.8))
        y = int(rng.random() < q)
        rows.append((q, y, q))
    return rows


# ---------------------------------------------------------------------------
# Cold start
# ---------------------------------------------------------------------------


def test_insufficient_data_on_tiny_input(tmp_path):
    clv = tmp_path / "clv.jsonl"
    _write_settled(clv, _miscalibrated_stream(n=5))
    rec = SI.improve_cycle("nba", clv_path=clv,
                           predictions_path=tmp_path / "none.jsonl",
                           ledger_path=tmp_path / "imp.jsonl")
    assert rec["verdict"] == "INSUFFICIENT_DATA"
    assert rec["n_settled"] == 5
    # nothing fabricated: no ship metrics present
    assert "recal_brier" not in rec


def test_insufficient_data_when_no_files(tmp_path):
    rec = SI.improve_cycle("tennis", clv_path=tmp_path / "nope.jsonl",
                           predictions_path=tmp_path / "nope2.jsonl",
                           ledger_path=tmp_path / "imp.jsonl")
    assert rec["verdict"] == "INSUFFICIENT_DATA"
    assert rec["n_settled"] == 0


# ---------------------------------------------------------------------------
# Leak-free: order sensitivity (the honest signature of a leak-free walk-forward)
# ---------------------------------------------------------------------------


def test_recalibration_is_leak_free_order_sensitive():
    """A leak-free expanding-window recal MUST depend on order: shuffling the stream
    yields a different recalibrated sequence (a leaky full-data fit would not)."""
    rows = _miscalibrated_stream(n=200, seed=7)
    p_raw = [r[0] for r in rows]
    y = [r[1] for r in rows]
    cal_ordered = SI.walk_forward_recalibrate(p_raw, y, min_history=30)

    idx = list(range(len(rows)))
    rng = np.random.default_rng(99)
    rng.shuffle(idx)
    cal_shuffled = SI.walk_forward_recalibrate([p_raw[i] for i in idx],
                                               [y[i] for i in idx], min_history=30)
    # Re-align the shuffled result back to original order and compare.
    realigned = np.empty(len(idx))
    for pos, orig in enumerate(idx):
        realigned[orig] = cal_shuffled[pos]
    assert not np.allclose(cal_ordered, realigned), \
        "recal identical under shuffle -> NOT leak-free (used future games)"


def test_leak_guard_rejects_injected_future_feature(tmp_path, monkeypatch):
    """If a state carries a feature_avail >= state_ts (a leak), the gate's vintage
    assert fires and improve_cycle returns REJECT, never SHIP."""
    rows = _miscalibrated_stream(n=120)
    clv = tmp_path / "clv.jsonl"
    _write_settled(clv, rows)

    real_to_states = SI._to_states

    def _leaky_to_states(settled):
        states = real_to_states(settled)
        # poison one state's vintage: feature available AFTER the prediction time
        states[50]["feature_avail"]["p_raw"] = "2099-01-01T00:00:00.000000"
        return states

    monkeypatch.setattr(SI, "_to_states", _leaky_to_states)
    rec = SI.improve_cycle("nba", clv_path=clv,
                           predictions_path=tmp_path / "none.jsonl",
                           ledger_path=tmp_path / "imp.jsonl")
    assert rec["verdict"] == "REJECT"
    assert rec.get("leaked") is True


# ---------------------------------------------------------------------------
# SHIP on genuine improvement / no-SHIP (ratchet) on no improvement
# ---------------------------------------------------------------------------


def test_ship_on_genuine_calibration_improvement(tmp_path):
    clv = tmp_path / "clv.jsonl"
    _write_settled(clv, _miscalibrated_stream(n=400, seed=3))
    rec = SI.improve_cycle("nba", clv_path=clv,
                           predictions_path=tmp_path / "none.jsonl",
                           ledger_path=tmp_path / "imp.jsonl")
    assert rec["verdict"] == "SHIP"
    assert rec["recal_brier"] < rec["baseline_brier"]
    assert rec["delta_brier"] > SI.BRIER_IMPROVE_TOL
    assert rec["regressed"] is False


def test_no_ship_when_already_well_calibrated(tmp_path):
    """The ratchet cannot move backward: on already-well-calibrated raw probs the
    recal cannot beat baseline -> HOLD or REJECT, NEVER SHIP."""
    clv = tmp_path / "clv.jsonl"
    _write_settled(clv, _well_calibrated_stream(n=400, seed=5))
    rec = SI.improve_cycle("nba", clv_path=clv,
                           predictions_path=tmp_path / "none.jsonl",
                           ledger_path=tmp_path / "imp.jsonl")
    assert rec["verdict"] in ("HOLD", "REJECT")
    assert rec["verdict"] != "SHIP"
    # baseline was already good; recal did not meaningfully beat it
    assert rec["delta_brier"] <= SI.BRIER_IMPROVE_TOL


def test_gate_rejects_injected_regression(tmp_path, monkeypatch):
    """Inject a regression by forcing the candidate predictor to blur every prob hard
    toward 0.5; the no-regression DM rule must REJECT (and never SHIP)."""
    clv = tmp_path / "clv.jsonl"
    _write_settled(clv, _well_calibrated_stream(n=400, seed=11))

    def _regressed_predictor(states):
        def _fn(train, test, select_inside):
            assert select_inside is True
            p = float(test["_p_raw"])
            return 0.1 * p + 0.9 * 0.5  # heavy pull to 0.5 -> worse Brier
        return _fn

    monkeypatch.setattr(SI, "_recal_predictor", _regressed_predictor)
    rec = SI.improve_cycle("nba", clv_path=clv,
                           predictions_path=tmp_path / "none.jsonl",
                           ledger_path=tmp_path / "imp.jsonl")
    assert rec["verdict"] == "REJECT"
    assert rec["regressed"] is True
    assert rec["delta_brier"] < 0  # candidate worse than baseline


# ---------------------------------------------------------------------------
# Honest readout + append-only ledger
# ---------------------------------------------------------------------------


def test_honest_readout_metrics(tmp_path):
    rows = _miscalibrated_stream(n=300, seed=2)
    settled = [{"p_raw": p, "y": y, "p_close": (p if p is not None else None)}
               for (p, y, _c) in rows]
    out = SI.honest_readout(settled)
    assert out["n"] == 300
    assert 0.0 <= out["raw_brier"] <= 1.0
    assert out["bss_vs_close"] is not None  # close present
    assert "calibration != edge" in out["note"]


def test_ledger_is_append_only(tmp_path):
    clv = tmp_path / "clv.jsonl"
    _write_settled(clv, _miscalibrated_stream(n=120))
    ledger = tmp_path / "imp.jsonl"
    SI.improve_cycle("nba", clv_path=clv, predictions_path=tmp_path / "n.jsonl",
                     ledger_path=ledger)
    after_one = ledger.read_text(encoding="utf-8").strip().splitlines()
    SI.improve_cycle("nba", clv_path=clv, predictions_path=tmp_path / "n.jsonl",
                     ledger_path=ledger)
    after_two = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(after_one) == 1
    assert len(after_two) == 2
    # first line is untouched by the second append (append-only, never overwritten)
    assert after_two[0] == after_one[0]
    for line in after_two:
        json.loads(line)  # every line is valid JSON


def test_improve_all_runs_every_sport(tmp_path):
    out = SI.improve_all(clv_path=tmp_path / "none.jsonl",
                         predictions_path=tmp_path / "none2.jsonl",
                         ledger_path=tmp_path / "imp.jsonl")
    assert set(out["verdicts"]) == set(SI.SPORTS)
    assert all(v == "INSUFFICIENT_DATA" for v in out["verdicts"].values())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
