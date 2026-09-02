"""S98 per-file test -- a better as-of pregame prior + a state-dependent margin sigma.

Run: python -m pytest tests/platformkit/ingame/test_s98_nba_better_prior.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s94_nba_early_shrinkage as s94
from scripts.platformkit.eval_gate import s98_nba_better_prior as s98
from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes, price_checkpoint


def _frame(n_games: int = 60, ticks: int = 30, sigma_true: float = 9.0, seed: int = 11):
    """A synthetic screen frame whose outcomes are drawn from a KNOWN margin sigma."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        date = "2025-01-%02d" % (1 + g % 28)
        p0 = float(rng.uniform(0.35, 0.65))
        cand = float(np.clip(p0 + rng.normal(0.0, 0.01), 0.02, 0.98))
        for t in range(ticks):
            period = 1 + (t % 4)
            clock = float(720 - 24 * t % 720)
            margin = int(rng.integers(-14, 15))
            elapsed = _elapsed_minutes(period, clock)
            p = float(s98.price_vec([p0], [margin], [elapsed], sigma_true)[0])
            rows.append({"game_id": 1000 + g, "game_date": date, "ts": t, "period": period,
                         "game_clock_s": clock, "score_home": 50 + margin, "score_away": 50,
                         "margin": margin, "elapsed": elapsed, "period_bucket": "P%d" % period,
                         "margin_bucket": "close_le5" if abs(margin) <= 5 else "mid_06_12",
                         "rem_bucket": "rem_gt12", "p0_asof": p0, "p0_cand": cand,
                         "model": p, "market": float(np.clip(p + rng.normal(0, 0.02), 0.01, 0.99)),
                         "y": int(rng.random() < p)})
    out = pd.DataFrame(rows)
    out["game"] = out["game_id"].astype(str)
    out["date"] = out["game"].map(out.groupby("game")["game_date"].min())
    out["cell"] = out["period_bucket"] + "|" + out["margin_bucket"] + "|" + out["rem_bucket"]
    return out.sort_values(["date", "game", "ts"], kind="stable").reset_index(drop=True)


def test_price_vec_reproduces_the_scalar_price_checkpoint():
    """The vectorised repricer must be the SAME function as the incumbent's scalar one."""
    frame = _frame(n_games=20)
    repro = s98.assert_reproduces_scalar(frame, n=400)
    assert repro["max_abs_delta_vs_price_checkpoint"] <= 1e-15, repro   # a few ulps, not a rule
    # and at a NON-default sigma, where the fitted arms live
    got = s98.price_vec(frame["p0_asof"], frame["margin"], frame["elapsed"], 7.5)
    want = np.array([price_checkpoint(p, h, a, int(per), c, margin_sigma=7.5) for p, h, a, per, c
                     in zip(frame["p0_asof"], frame["score_home"], frame["score_away"],
                            frame["period"], frame["game_clock_s"])])
    assert float(np.max(np.abs(got - want))) <= 1e-15


def test_bar_is_byte_identical_to_s94():
    """Q3: the row's bar is defined once and never lowered."""
    assert s98.IMPROVEMENT_BAR == s94.IMPROVEMENT_BAR == 0.004
    assert s98.SIGMA_DEFAULT == 13.5


def test_strictly_before_guard_passes_and_catches_a_planted_leak():
    frame = _frame(n_games=30)
    for col in s98.PRIOR_COLS.values():
        guard = s98.assert_no_future_read(frame, col)
        assert guard["max_abs_delta"] == 0.0 and guard["max_prior_values_per_game"] == 1
    leaky = frame.copy()                       # a "prior" that moves inside the game is tick data
    leaky["p0_asof"] = leaky.groupby("game")["market"].transform("cummax")
    with pytest.raises(AssertionError):
        s98.assert_no_future_read(leaky, "p0_asof")


def test_guard_limit_a_per_game_constant_future_read_is_NOT_detectable_here():
    """Honest limit: this guard proves row-wiseness and within-game constancy only. The as-of
    property of the prior VALUES is inherited -- S86's replay(until=game_date) for p0_asof and
    walk_forward_elo's strictly-pre-game snapshot for p0_cand -- not re-proved here."""
    leaky = _frame(n_games=30).copy()
    leaky["p0_asof"] = leaky.groupby("game")["market"].transform("last")   # a future read
    assert s98.assert_no_future_read(leaky, "p0_asof")["max_abs_delta"] == 0.0


def test_fit_sigma_recovers_a_planted_sigma_where_the_clock_identifies_it():
    """Early ticks (rem_frac ~ 0.75) identify sigma; the fit must land on the planted value."""
    frame = _frame(n_games=500, ticks=20, sigma_true=9.0)
    early = frame[frame["period"] == 1]
    fitted = s98.fit_sigma(early, "p0_asof")
    big = [c for c in fitted if (early["cell"] == c).sum() >= s98.MIN_CELL_TRAIN]
    assert big, fitted
    for cell in big:
        assert abs(fitted[cell] - 9.0) <= 2.0, (cell, fitted[cell])


def test_fitted_sigma_never_loses_to_the_default_on_its_own_train_rows():
    """The contract of fit_sigma: it MINIMISES the cell's train Brier, so it can only tie 13.5."""
    frame = _frame(n_games=200, ticks=20, sigma_true=9.0)
    fitted = s98.fit_sigma(frame, "p0_asof")
    for cell, sub in frame.groupby("cell"):
        if len(sub) < s98.MIN_CELL_TRAIN:
            continue
        y = sub["y"].to_numpy(float)
        args = (sub["p0_asof"], sub["margin"], sub["elapsed"])
        got = float(np.mean((s98.price_vec(*args, fitted[cell]) - y) ** 2))
        base = float(np.mean((s98.price_vec(*args, s98.SIGMA_DEFAULT) - y) ** 2))
        assert got <= base + 1e-12, (cell, fitted[cell], got, base)


def test_small_cell_keeps_the_default_sigma():
    """A cell below MIN_CELL_TRAIN is left at 13.5 -- missing evidence is not a fitted value."""
    fitted = s98.fit_sigma(_frame(n_games=2, ticks=8), "p0_asof")
    assert set(fitted.values()) == {s98.SIGMA_DEFAULT}


def test_walk_forward_is_game_purged_and_embargoed():
    frame = _frame(n_games=90)
    scored, folds = s98.walk_forward(frame)
    ok = [f for f in folds if f["status"] == "OK"]
    assert ok, folds
    for f in ok:
        assert f["train_date_max"] < f["embargo_cut"] <= f["test_start"]
        block = scored[scored["fold"] == f["fold"]]
        assert set(block["game"]).isdisjoint(set(frame[frame["date"] < f["embargo_cut"]]["game"]))


def test_test_fold_outcomes_never_reach_the_fitted_arms():
    """Flip the LAST fold's own held-out outcomes: no fitted arm on that fold may move."""
    frame = _frame(n_games=90)
    scored, folds = s98.walk_forward(frame)
    last = max(f["fold"] for f in folds if f["status"] == "OK")
    flipped = frame.copy()
    test_games = set(scored.loc[scored["fold"] == last, "game"])
    mask = flipped["game"].isin(test_games)
    flipped.loc[mask, "y"] = 1 - flipped.loc[mask, "y"]
    again, _ = s98.walk_forward(flipped)
    a = scored[scored["fold"] == last].reset_index(drop=True)
    b = again[again["fold"] == last].reset_index(drop=True)
    for arm in ("p_elo_sig", "p_cand_sig", "p_blend", "p_recal"):
        assert np.allclose(a[arm].to_numpy(), b[arm].to_numpy(), atol=0.0, rtol=0.0), arm


def test_score_cell_reports_n_informative_and_n_eff():
    scored, _ = s98.walk_forward(_frame(n_games=90))
    row = s98.score_cell(scored)
    assert row["n"] == len(scored) and row["n_games"] >= 2
    assert 0 < row["tick_informative"]["n_informative"] <= row["n"]
    assert 0 < row["n_eff"] <= row["n"]
    assert set(row["brier"]) == set(s98.ARMS) | {"market"}
    for arm in s98.ARMS:
        assert row["dm_ci95"][arm][0] <= row["improvement_vs_market"][arm] <= row["dm_ci95"][arm][1]


def test_clears_needs_the_bar_the_ci_and_the_recal_null():
    row = {"improvement_vs_market": {"x": 0.01}, "dm_ci95": {"x": [0.002, 0.02]},
           "brier": {"x": 0.20, "recal": 0.21}}
    assert s98.clears(row, "x")
    assert not s98.clears({**row, "dm_ci95": {"x": [-0.001, 0.02]}}, "x")     # CI includes 0
    assert not s98.clears({**row, "improvement_vs_market": {"x": 0.001}}, "x")  # under the bar
    assert not s98.clears({**row, "brier": {"x": 0.20, "recal": 0.19}}, "x")  # loses to the null
