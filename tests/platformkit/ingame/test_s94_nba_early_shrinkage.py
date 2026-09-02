"""S94 per-file test -- phase-conditioned shrinkage of the NBA in-play line.

Run: python -m pytest tests/platformkit/ingame/test_s94_nba_early_shrinkage.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s94_nba_early_shrinkage as s94


def _frame(n_games: int = 60, ticks: int = 40, w_true: float = 0.5, seed: int = 7) -> pd.DataFrame:
    """A synthetic screen frame whose outcomes really are drawn from a planted blend."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        date = "2025-01-%02d" % (1 + g % 28)
        lm = rng.normal(0.0, 1.2, ticks)
        lo = lm + rng.normal(0.0, 1.0, ticks)
        p = s94.sigmoid(lm + w_true * (lo - lm))
        y = (rng.random(ticks) < p).astype(int)
        for t in range(ticks):
            rows.append({"game_id": 1000 + g, "game_date": date, "ts": t,
                         "period_bucket": "P1" if t % 2 else "P2", "margin_bucket": "close_le5",
                         "rem_bucket": "rem_gt12", "model": float(s94.sigmoid(lo[t])),
                         "market": float(s94.sigmoid(lm[t])), "y": int(y[t])})
    return s94.prepare(pd.DataFrame(rows))


def test_fit_w_recovers_a_planted_blend():
    frame = _frame(n_games=250, w_true=0.5)
    fitted = s94.fit_w(frame)
    assert set(fitted) == {"P1|close_le5|rem_gt12", "P2|close_le5|rem_gt12"}
    for cell, w in fitted.items():
        assert abs(w - 0.5) < 0.1, (cell, w)


def test_small_cell_falls_back_to_the_raw_market():
    """A cell below MIN_CELL_TRAIN keeps w = 0, i.e. the candidate IS the market line."""
    frame = _frame(n_games=4, ticks=10)
    train, test = frame[frame["date"] < "2025-01-03"], frame[frame["date"] >= "2025-01-03"].copy()
    scored, w_by_cell = s94.apply_fold(train, test)
    assert set(w_by_cell.values()) == {0.0}
    assert np.allclose(scored["p_candidate"].to_numpy(), scored["market"].to_numpy(), atol=1e-9)


def test_walk_forward_is_game_purged_and_embargoed():
    scored, folds = s94.walk_forward(_frame(), n_folds=3)
    ok = [f for f in folds if f["status"] == "OK"]
    assert ok, folds
    for f in ok:
        assert f["train_date_max"] < f["embargo_cut"] <= f["test_start"]
        block = scored[scored["fold"] == f["fold"]]
        assert block["date"].min() >= f["test_start"]
        assert set(block["game"]).isdisjoint(
            set(_frame()[_frame()["date"] < f["embargo_cut"]]["game"]))


def test_no_test_row_informs_its_own_fit():
    """Flipping the LAST fold's own held-out outcomes must not move its candidate at all.

    Only that fold's test rows are touched, so nothing any fold trains on changes; a fit that
    peeked at its own test rows would move.
    """
    frame = _frame()
    base, folds = s94.walk_forward(frame, n_folds=3)
    last = max(f["fold"] for f in folds if f["status"] == "OK")
    span = base[base["fold"] == last]
    poisoned = frame.copy()
    hit = poisoned["date"].between(span["date"].min(), span["date"].max())
    poisoned.loc[hit, "y"] = 1 - poisoned.loc[hit, "y"]
    after, _ = s94.walk_forward(poisoned, n_folds=3)
    assert np.allclose(span["p_candidate"].to_numpy(),
                       after[after["fold"] == last]["p_candidate"].to_numpy(), atol=0.0)


def test_score_cell_arms_and_sign_convention():
    scored, _ = s94.walk_forward(_frame(), n_folds=3)
    row = s94.score_cell(scored)
    y = scored["y"].to_numpy(dtype=float)
    assert row["brier"]["market"] == pytest.approx(
        float(np.mean((scored["market"].to_numpy() - y) ** 2)))
    # d > 0 means the candidate lost less; a candidate equal to the market scores exactly 0.
    same = scored.assign(p_candidate=scored["market"])
    assert s94.score_cell(same)["improvement"]["candidate_vs_market"] == pytest.approx(0.0)
    assert row["n_informative"] <= row["n"] and 0.0 <= row["n_eff"] <= row["n"]


def test_bar_is_not_moved():
    assert s94.IMPROVEMENT_BAR == 0.004
    assert (s94.TARGET_PERIODS, s94.TARGET_MARGIN, s94.TARGET_REM) == (("P1", "P2"), "close_le5", "rem_gt12")
