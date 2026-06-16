"""Per-file tests for the X3 track-record ledger. numpy + stdlib + pandas.

Run ONLY as:
    python -m pytest scripts/platformkit/ledger/test_ledger.py -q
(never the full suite -- it freezes the box). Standalone `python test_ledger.py` also works.
"""
from __future__ import annotations
import io
import os
import pathlib
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import schema
import ledger as L
import metrics
import grade_outcomes as GO
import drift_check as DC
import replay_proof as RP


def _base():
    d = tempfile.mkdtemp(prefix="ledger_test_")
    return d


# ---- schema / append idempotency + atomicity ---------------------------------

def test_append_idempotent_on_pred_id():
    bd = _base()
    inputs = {"home": "BOS", "away": "LAL", "k": 1}
    pid1 = L.append_prediction("nba", "pregame", "ml", "BOS", "LAL", 0.61, inputs,
                               "2026-01-01T15:00:00", game_date="2026-01-02", base_dir=bd)
    pid2 = L.append_prediction("nba", "pregame", "ml", "BOS", "LAL", 0.61, inputs,
                               "2026-01-01T15:00:00", game_date="2026-01-02", base_dir=bd)
    assert pid1 == pid2
    df = L.read_ledger(base_dir=bd)
    assert len(df) == 1, "double-append of same pred_id must collapse to one row"


def test_atomic_write_leaves_no_tmp():
    bd = _base()
    L.append_prediction("nba", "pregame", "ml", "A", "B", 0.5, {"x": 1},
                        "2026-01-01T15:00:00", game_date="2026-01-02", base_dir=bd)
    leftovers = [p for p in os.listdir(bd) if p.endswith(".tmp")]
    assert not leftovers, f"atomic write left temp files: {leftovers}"


def test_schema_has_no_money_columns():
    forbidden = {"units", "stake", "roi", "edge", "pnl", "profit"}
    assert not (forbidden & set(schema.SCHEMA_COLS)), "ledger must log probs+outcomes ONLY"


# ---- grading: fill once, refuse overwrite, vintage drop ----------------------

def test_grade_fills_once_and_refuses_overwrite():
    bd = _base()
    pid = L.append_prediction("nba", "pregame", "ml", "A", "B", 0.7, {"x": 1},
                              "2026-01-01T15:00:00", game_date="2026-01-02", base_dir=bd)
    s1 = GO.grade_outcomes({pid: {"outcome": 1, "devig_close_prob": 0.68}}, base_dir=bd)
    assert s1["filled"] == 1
    df = L.read_ledger(base_dir=bd)
    assert int(df.loc[df.pred_id == pid, "outcome"].iloc[0]) == 1
    # second grade attempt with a DIFFERENT outcome must be refused (immutable)
    s2 = GO.grade_outcomes({pid: {"outcome": 0, "devig_close_prob": 0.10}}, base_dir=bd)
    assert s2["skipped_already_graded"] == 1 and s2["filled"] == 0
    df2 = L.read_ledger(base_dir=bd)
    assert int(df2.loc[df2.pred_id == pid, "outcome"].iloc[0]) == 1, "outcome was overwritten!"
    assert float(df2.loc[df2.pred_id == pid, "devig_close_prob"].iloc[0]) == 0.68


def test_vintage_guard_drops_late_predictions():
    bd = _base()
    # planted LEAK: pred_ts >= game_date (made on/after the game)
    leak_pid = L.append_prediction("nba", "pregame", "ml", "A", "B", 0.9,
                                   {"x": 9}, "2026-01-05T15:00:00",
                                   game_date="2026-01-02", base_dir=bd)
    clean_pid = L.append_prediction("nba", "pregame", "ml", "C", "D", 0.5,
                                    {"x": 1}, "2026-01-01T15:00:00",
                                    game_date="2026-01-02", base_dir=bd)
    summary = GO.grade_outcomes({clean_pid: {"outcome": 1}}, base_dir=bd)
    assert summary["leak_dropped"] == 1 and leak_pid in summary["leak_ids"]
    df = L.read_ledger(base_dir=bd)
    assert leak_pid not in set(df.pred_id), "vintage violator must be dropped"
    assert clean_pid in set(df.pred_id)


# ---- metrics: known answers --------------------------------------------------

def test_brier_ece_known_answers():
    # perfect predictions -> Brier 0, ECE 0
    p = np.array([1.0, 0.0, 1.0, 0.0])
    y = np.array([1, 0, 1, 0])
    assert metrics.brier(p, y) == 0.0
    assert metrics.ece(p, y) == 0.0
    # constant 0.5 vs balanced outcomes -> Brier 0.25
    p2 = np.full(4, 0.5)
    y2 = np.array([1, 0, 1, 0])
    assert abs(metrics.brier(p2, y2) - 0.25) < 1e-12


def test_dm_sign_when_model_beats_close():
    # model sharp+correct, close noisy -> d = loss_close - loss_model > 0 (model better)
    rng = np.random.default_rng(0)
    n = 120
    y = np.array([i % 2 for i in range(n)], float)
    # model: very close to truth (small Brier); close: persistently wrong-ish (larger Brier)
    p_model = np.where(y == 1, 0.9, 0.1)
    p_close = np.where(y == 1, 0.55, 0.45) + rng.normal(0, 0.02, n)
    p_close = np.clip(p_close, 0.01, 0.99)
    cids = [f"g{i}" for i in range(n)]
    dm = metrics.dm_vs_close(p_model, p_close, y, cids)
    assert dm["mean_diff"] > 0 and dm["p_value"] < 0.05


def test_compute_calibration_edge_never_claimed():
    bd = _base()
    rows = []
    for i in range(60):
        pid = L.append_prediction("nba", "pregame", "ml", f"H{i}", f"A{i}",
                                  0.6 if i % 2 else 0.4, {"i": i},
                                  f"2026-01-{1 + i // 5:02d}T15:00:00",
                                  game_date="2026-02-01", base_dir=bd)
        rows.append(pid)
    for i, pid in enumerate(rows):
        GO.grade_outcomes({pid: {"outcome": i % 2, "devig_close_prob": 0.55}}, base_dir=bd)
    df = L.read_ledger(graded_only=True, base_dir=bd)
    rep = metrics.compute_calibration(df, "nba", "ml")
    assert rep["edge_claimed"] is False
    assert rep["verdict"] in ("matches_close", "reported", "beats_close_oos_pending")


# ---- drift: exit 2 on rise, 0/fail-quiet otherwise ---------------------------

def _seed_drift(bd, degraded: bool):
    now = datetime(2026, 2, 1, 12, 0, 0)
    recs = []
    # baseline (8-30d ago): sharp + correct -> low Brier
    for i in range(40):
        ts = (now - timedelta(days=12) + timedelta(hours=i)).isoformat()
        y = i % 2
        recs.append((ts, 0.95 if y else 0.05, y))
    # recent (last 3d): degraded (sharp + WRONG) or stable (sharp + correct)
    for i in range(20):
        ts = (now - timedelta(days=2) + timedelta(hours=i)).isoformat()
        y = i % 2
        prob = (0.05 if y else 0.95) if degraded else (0.95 if y else 0.05)
        recs.append((ts, prob, y))
    rows = []
    for j, (ts, prob, y) in enumerate(recs):
        rows.append(schema.LedgerRow(
            pred_id=f"d{j}", pred_ts=ts, sport="nba", layer="pregame", market="ml",
            home="A", away="B", inputs_hash="h", model_version="v", calibrated_prob=prob,
            game_date="2026-03-01", outcome=y, graded_at=ts, game_id=f"g{j}"))
    L.append_rows(rows, base_dir=bd)
    return now


def test_drift_exit2_on_degradation():
    bd = _base()
    now = _seed_drift(bd, degraded=True)
    df = L.read_ledger(base_dir=bd)
    alerts = DC.run_drift(df, now=now)
    assert len(alerts) >= 1
    assert DC.main(base_dir=bd, now=now) == 2


def test_drift_exit0_when_stable():
    bd = _base()
    now = _seed_drift(bd, degraded=False)
    df = L.read_ledger(base_dir=bd)
    assert DC.run_drift(df, now=now) == []
    assert DC.main(base_dir=bd, now=now) == 0


def test_drift_fail_quiet_without_data():
    bd = _base()
    assert DC.main(base_dir=bd) == 0  # empty ledger -> no alert


# ---- replay_proof: reproduces fixture numbers + prints validation_pending -----

def test_replay_proof_reproduces_and_flags_pending():
    out1 = RP.replay_proof()
    out2 = RP.replay_proof()
    assert out1 == out2, "replay must be deterministic"
    assert out1["n_rows"] == 120
    assert set(out1["by_sport"]) == {"nba", "mlb", "soccer", "tennis"}
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = RP.main()
    text = buf.getvalue()
    assert rc == 0
    assert "VALIDATION_PENDING" in text
    assert "edge_claimed=False" in text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} ledger tests passed.")
