"""Per-file test for scripts.platformkit.eval_gate.s80_player_grain_screen (S80).

Covers the three rails the screen rests on: the tick-time leak guard, the
purge + embargo of the walk-forward, and the archived series length.
python -m pytest tests/platformkit/ingame/test_s80_player_grain_screen.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s80_player_grain_screen as S


def _logs(dates, pid=1):
    return pd.DataFrame({"player_id": [pid] * len(dates), "date": pd.to_datetime(list(dates)),
                         "is_pitcher": [True] * len(dates), "outs": [18.0] * len(dates),
                         "earnedRuns": [2.0] * len(dates)})


def test_leak_guard_raises_on_a_same_tick_read():
    with pytest.raises(S.AsOfLeak):
        S.assert_asof(["2026-07-08", "2026-07-09"], "2026-07-09", "unit")
    with pytest.raises(S.AsOfLeak):
        S.assert_asof(["2026-07-10"], "2026-07-09", "unit")
    S.assert_asof(["2026-07-07", "2026-07-08"], "2026-07-09", "unit")   # strictly prior is fine


def test_pitcher_residuals_uses_only_strictly_prior_appearances():
    logs = _logs(["2026-07-01", "2026-07-09"])                # the 07-09 row is the tick's own game
    resid = S.pitcher_residuals(logs, [1], "2026-07-09")
    assert set(resid) == {1} and np.isfinite(resid[1])
    assert S.pitcher_residuals(logs, [1], "2026-07-01") == {1: 0.0}     # no prior work -> no signal
    assert S.pitcher_residuals(logs, [999], "2026-07-09") == {999: 0.0}  # unknown pitcher -> 0.0


def _synthetic(n_dates=4, games_per_date=8, ticks=40, seed=7):
    rng = np.random.default_rng(seed)
    rows = []
    for di in range(n_dates):
        day = "2026-07-%02d" % (9 + di)
        for gi in range(games_per_date):
            game = "G%d_%d" % (di, gi)
            y = float(gi % 2)
            for ti in range(ticks):
                rows.append({"game": game, "date": day, "timestamp": "%sT%02d:00:00Z" % (day, ti),
                             "outcome": y, "model_prob": float(np.clip(0.5 + 0.1 * rng.normal(), .05, .95)),
                             "market_prob": float(np.clip(0.5 + 0.1 * rng.normal(), .05, .95)),
                             "signal": float(rng.integers(-3, 4)), "z": float(rng.normal()),
                             "pitcher_id": int(rng.integers(1, 20))})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("embargo, expected_ok_dates", [(0, 3), (1, 2)])
def test_walk_forward_purges_by_game_and_honours_the_embargo(embargo, expected_ok_dates):
    frame = _synthetic()
    scored, folds = S.walk_forward(frame, embargo_days=embargo)
    ok = [f for f in folds if f["status"] == "OK"]
    assert len(folds) == 4 and len(ok) == expected_ok_dates
    for fold in ok:
        # embargo: the newest train date is strictly before test_date - embargo_days
        assert fold["train_date_max"] < fold["embargo_cut"] <= fold["test_date"]
        gap = (pd.Timestamp(fold["test_date"]) - pd.Timestamp(fold["train_date_max"])).days
        assert gap >= embargo + 1
    # purge: no scored game ever appears on more than one test date
    assert scored.groupby("game")["date"].nunique().max() == 1
    assert set(scored["date"]) == {f["test_date"] for f in ok}


def test_beta_zero_reproduces_the_incumbent_and_series_length_equals_screen_ticks(tmp_path):
    frame = _synthetic()
    scored, folds = S.walk_forward(frame, embargo_days=0)
    assert np.allclose(scored["p_incumbent"], scored["p_zero_beta"], atol=1e-12)

    class _Part:
        basis, seed = "corpus_unit", 0
        screen_sha256 = verdict_sha256 = "0" * 64
        screen_ids = frozenset(frame["game"].unique())
        verdict_ids = frozenset()
    summary, series = S.score(scored, folds, _Part(), embargo_days=0)
    assert len(series) == len(scored) == summary["n_ticks"]
    assert summary["n_ticks"] == int(frame["date"].isin({f["test_date"] for f in folds
                                                         if f["status"] == "OK"}).sum())
    assert list(series["cluster_id"]) == list(scored["game"])
    assert np.allclose(series["loss_differential"], series["loss_incumbent"] - series["loss_candidate"])
    assert summary["verdict"].startswith("SCREEN_")
