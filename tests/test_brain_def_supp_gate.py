"""P1.3 — the defender-suppression gate's DECISION logic (pure helpers; no GPU sim).

The full gate (scripts/team_system/gate_def_supp.py) runs the A/B walk-forward on the GPU; this file pins
its honest SHIP/REJECT arithmetic: MAE must strictly improve AND bias/coverage/PIT must not regress, on BOTH
the FIT and HOLDOUT groups. A lever that improves MAE but worsens bias or coverage must NOT ship.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
sys.path.insert(0, os.path.join(ROOT, "src"))

from gate_def_supp import _mid_pit, _summ, _group_ships, _blank  # noqa: E402


def test_mid_pit_handles_ties():
    import numpy as np
    sm = np.array([1, 2, 3, 4], dtype=float)
    assert abs(_mid_pit(sm, 2) - 0.375) < 1e-9   # (lt=0.25 + le=0.5)/2
    assert abs(_mid_pit(sm, 5) - 1.0) < 1e-9      # above all
    assert abs(_mid_pit(sm, 0) - 0.0) < 1e-9      # below all


def test_summ_aggregates():
    acc = _blank()
    acc["team_err"] = [1.0, -1.0, 2.0, -2.0]
    acc["team_pit"] = [0.4, 0.6]
    acc["team_cov"] = [1.0, 0.0, 1.0, 1.0]
    acc["team_games"] = 4
    s = _summ(acc)
    assert abs(s["team_mae"] - 1.5) < 1e-9
    assert abs(s["team_bias"] - 0.0) < 1e-9
    assert abs(s["team_pit"] - 0.5) < 1e-9
    assert abs(s["team_cov"] - 0.75) < 1e-9


def _grp(mae, bias=0.0, cov=0.8, pit=0.5):
    return {"team_mae": mae, "team_bias": bias, "team_cov": cov, "team_pit": pit, "team_games": 20}


def test_ships_on_clear_improvement():
    ship, d = _group_ships(_grp(10.0), _grp(8.0))
    assert ship is True and d["mae_better"] is True


def test_no_ship_without_mae_gain():
    ship, _ = _group_ships(_grp(8.0), _grp(8.0))      # identical MAE -> not better
    assert ship is False


def test_no_ship_when_bias_worsens():
    ship, d = _group_ships(_grp(10.0, bias=0.5), _grp(8.0, bias=3.0))  # MAE down but |bias| up
    assert ship is False and d["bias_ok"] is False


def test_no_ship_when_coverage_collapses():
    ship, d = _group_ships(_grp(10.0, cov=0.80), _grp(8.0, cov=0.65))  # MAE down but coverage drops
    assert ship is False and d["cov_ok"] is False
