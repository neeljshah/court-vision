"""Per-file tests for proof_mlb.ingame_tto (run THIS file only; never full pytest).

Locks in: leak-free TRAIN/VAL split, RMSE+bias (not MAE) shape, the phase map, and that
run() returns a coherent verdict. Run:
  python -m pytest scripts/platformkit/proof_mlb/test_ingame_tto.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.proof_mlb import ingame_tto as M


def test_phase_map_partitions_all_nine_innings():
    assert set(M._PHASE_OF_INNING) == set(range(1, 10))
    assert set(M._PHASE_OF_INNING.values()) == {0, 1, 2}
    # phases are contiguous & ordered: early(1-4) < 3rd(5-6) < bullpen(7-9)
    assert all(M._PHASE_OF_INNING[i] <= M._PHASE_OF_INNING[i + 1] for i in range(1, 9))


def test_train_val_eras_disjoint():
    assert M._TRAIN[1] < M._VAL[0]            # no season overlap -> leak-free OOS


def test_parse_innings_drops_x_marker():
    assert M._parse_innings("0,1,0,2,x") == [0, 1, 0, 2]
    assert M._parse_innings(None) is None


def test_parse_innings_returns_none_on_garbage():
    assert M._parse_innings("1,foo,2") is None


def test_rmse_bias_matches_definition():
    pred = np.array([1.0, 2.0, 3.0])
    truth = np.array([1.0, 1.0, 1.0])
    rmse, bias = M._rmse_bias(pred, truth)
    assert abs(rmse - np.sqrt(np.mean((pred - truth) ** 2))) < 1e-12
    assert abs(bias - np.mean(pred - truth)) < 1e-12     # signed, not absolute (not MAE)


def test_remaining_after_sums_remaining_innings_doubled():
    rate = np.array([1.0] * 9)                # 1 run/inning/team
    assert M._remaining_after(rate, 7) == 4.0   # innings 8,9 * 2 teams
    assert M._remaining_after(rate, 9) == 0.0   # game over
    assert M._remaining_after(rate, 0) == 18.0  # all 9 innings * 2


def test_phase_fit_collapses_to_three_levels():
    # synthetic: build a tiny df where every inning scores its inning-number of runs.
    import pandas as pd
    line = ",".join(str(i) for i in range(1, 10))
    df = pd.DataFrame({"home_innings": [line] * 5, "away_innings": [line] * 5})
    phase_rate = M._fit_phase(df)
    # within a phase, all innings share one rate
    assert phase_rate[0] == phase_rate[3]      # innings 1-4 same level
    assert phase_rate[4] == phase_rate[5]      # innings 5-6 same level
    assert phase_rate[6] == phase_rate[8]      # innings 7-9 same level
    # early phase mean of 1..4 = 2.5; 3rd-time mean of 5,6 = 5.5; bullpen mean of 7,8,9 = 8
    assert abs(phase_rate[0] - 2.5) < 1e-9
    assert abs(phase_rate[4] - 5.5) < 1e-9
    assert abs(phase_rate[6] - 8.0) < 1e-9


def test_run_returns_coherent_verdict():
    r = M.run()
    if r.get("status") != "ok":
        return                                  # corpus absent on a clean clone -> skip
    assert r["verdict_kind"] in ("sharpens", "neutral_null")
    assert r["n_checkpoints"] > 0
    # decisive metric present and finite
    for k in ("curve_final_total_rmse", "phase_final_total_rmse",
              "curve_final_total_bias", "phase_final_total_bias"):
        assert np.isfinite(r[k])
    # sharper flag is consistent with the RMSE gain sign
    if r["tto_phase_sharper"]:
        assert r["rmse_gain_phase_minus_curve"] < 0
    else:
        assert r["rmse_gain_phase_minus_curve"] >= -1e-4
