"""Per-file test for S103 (the margin sigma past S98's grid limit).

Covers the rails the verifier contract makes automatic rejects: the bar is imported not copied
(Q3/B10), the widened grid is a declared constant that strictly contains S98's, the parametric
sigma is ROW-WISE in the current state only and survives truncation exactly (the strictly-before
guard), the vectorised price still equals the scalar `price_checkpoint` at a NON-default sigma
(where every fitted arm actually lives), a cell under MIN_CELL_TRAIN falls through to the default
instead of being quarantined (B3), and flipping the held-out fold's own outcomes moves no fitted
arm by one bit (B8 / Q4). ASCII only.

Run: python -m pytest tests/platformkit/ingame/test_s103_nba_sigma.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s94_nba_early_shrinkage as s94
from scripts.platformkit.eval_gate import s98_nba_better_prior as s98
from scripts.platformkit.eval_gate import s103_nba_sigma as s103
from scripts.platformkit.ingame.nba_checkpoint_benchmark import price_checkpoint

BUCKETS = (("close_le5", 5), ("mid_06_12", 12), ("blowout_gt12", 99))


def _bucket(margin: int) -> str:
    return next(name for name, hi in BUCKETS if abs(margin) <= hi)


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    """A synthetic screen: 90 games x 48 ticks, with a real (if weak) signal in the margin."""
    rng = np.random.default_rng(20260903)
    rows = []
    for g in range(90):
        date = "2025-01-%02d" % (1 + g // 6)
        p0 = float(rng.uniform(0.30, 0.70))
        drift = rng.normal(0.0, 6.0)
        y = int(rng.random() < p0)
        for t in range(48):
            elapsed = t * 1.0
            period = min(4, int(elapsed // 12) + 1)
            margin = int(round(drift + (2 * y - 1) * t * 0.25 + rng.normal(0.0, 3.0)))
            rows.append({
                "game_id": "G%03d" % g, "game_date": date, "ts": t, "period": period,
                "game_clock_s": 720.0 - (elapsed % 12) * 60.0, "score_home": 50 + margin,
                "score_away": 50, "margin": margin, "elapsed": elapsed,
                "period_bucket": "P%d" % period, "margin_bucket": _bucket(margin),
                "rem_bucket": "rem_gt12" if elapsed < 36 else "rem_02_06",
                "p0_asof": p0, "model": p0,
                "market": float(np.clip(p0 + rng.normal(0.0, 0.05), 0.02, 0.98)), "y": y})
    out = pd.DataFrame(rows)
    out["game"] = out["game_id"]
    out["date"] = out["game_date"]
    out["cell"] = out["period_bucket"] + "|" + out["margin_bucket"] + "|" + out["rem_bucket"]
    return out


@pytest.fixture(scope="module")
def scored(frame: pd.DataFrame):
    return s103.walk_forward(frame)


def test_bar_is_imported_not_copied_and_never_lowered():
    assert s103.IMPROVEMENT_BAR is s94.IMPROVEMENT_BAR
    assert s103.IMPROVEMENT_BAR == s98.IMPROVEMENT_BAR == 0.004
    assert (s103.MIN_CELL_TRAIN, s103.N_FOLDS, s103.EMBARGO_DAYS) == (
        s94.MIN_CELL_TRAIN, s94.N_FOLDS, s94.EMBARGO_DAYS)


def test_wide_grid_is_the_declared_constant_and_contains_the_s98_grid():
    grid = s103.SIGMA_GRID_WIDE
    assert (float(grid[0]), float(grid[-1])) == (3.0, 60.0)
    assert np.allclose(np.diff(grid), 0.5)
    assert set(np.round(s98.SIGMA_GRID, 4)).issubset(set(np.round(grid, 4)))


def test_rem_seconds_is_the_same_clock_price_vec_prices_on():
    elapsed = np.array([0.0, 12.0, 47.5, 48.0, 50.0, 53.0, 55.0])
    rem = s103.rem_seconds(elapsed)
    assert rem[0] == 48.0 * 60.0 and rem[3] == 0.0 and rem[4] == 3.0 * 60.0
    # rem = 0 exactly where price_vec collapses to the deterministic buzzer surface, nowhere else
    priced = s98.price_vec(np.full(len(elapsed), 0.5), np.full(len(elapsed), 7.0), elapsed, 13.5)
    assert np.array_equal(priced == 1.0, rem == 0.0)
    assert priced[3] == 1.0 and 0.0 < priced[0] < 1.0


def test_param_sigma_is_row_wise_and_clipped():
    theta = (2.9, 0.05, 0.01, -0.2)
    rem, marg, p4 = np.array([2880.0, 600.0, 0.0]), np.array([0.0, 8.0, 20.0]), np.array([0., 1., 1.])
    full = s103.param_sigma(theta, rem, marg, p4)
    for i in range(3):     # one row at a time must equal that row of the whole-frame call
        assert s103.param_sigma(theta, rem[i:i + 1], marg[i:i + 1], p4[i:i + 1])[0] == full[i]
    assert s103.param_sigma((99.0, 0.0, 0.0, 0.0), [0.0], [0.0], [0.0])[0] == s103.SIGMA_CLIP[1]
    assert s103.param_sigma((-99.0, 0.0, 0.0, 0.0), [0.0], [0.0], [0.0])[0] == s103.SIGMA_CLIP[0]


def test_price_vec_equals_price_checkpoint_at_a_non_default_fitted_sigma(frame):
    sub = frame.iloc[np.unique(np.linspace(0, len(frame) - 1, 400).astype(int))]
    for sigma in (4.5, 27.5, 47.0):       # inside the WIDE grid, outside the S98 one
        scalar = np.array([price_checkpoint(r.p0_asof, r.score_home, r.score_away, int(r.period),
                                            r.game_clock_s, sigma) for r in sub.itertuples()])
        vec = s98.price_vec(sub["p0_asof"], sub["margin"], sub["elapsed"], sigma)
        assert float(np.max(np.abs(vec - scalar))) <= 1e-12


def test_strictly_before_guard_holds_for_the_parametric_arm(frame):
    out = s103.assert_param_no_future_read(frame, (2.9, 0.05, 0.01, -0.2))
    assert out["max_abs_delta"] == 0.0 and out["n_ticks_repriced"] == 4 * 90


def test_planted_within_game_leak_is_caught(frame):
    leaked = frame.copy()
    leaked["p0_asof"] = leaked.groupby("game")["market"].transform("cummax")
    with pytest.raises(AssertionError, match="not a pregame prior"):
        s98.assert_no_future_read(leaked, s103.PRIOR)


def test_cell_under_min_train_falls_through_to_the_default(frame):
    thin = frame.head(s103.MIN_CELL_TRAIN - 1)
    fitted = s103.fit_cell_sigma(thin, s103.SIGMA_GRID_WIDE)
    assert fitted and set(fitted.values()) == {s98.SIGMA_DEFAULT}


def test_folds_are_purged_by_game_and_embargoed(scored):
    _, folds = scored
    ok = [f for f in folds if f.get("status") == "OK"]
    assert len(ok) == s103.N_FOLDS
    for f in ok:
        assert f["train_date_max"] < f["embargo_cut"] <= f["test_start"]
        assert f["n_train_games"] > 0 and f["n_test_games"] > 0


def test_flipping_the_held_out_outcomes_moves_no_fitted_arm(frame, scored):
    base, folds = scored
    last = max(f["fold"] for f in folds if f.get("status") == "OK")
    test_games = set(base.loc[base["fold"] == last, "game"])
    flipped = frame.copy()
    mask = flipped["game"].isin(test_games)
    flipped.loc[mask, "y"] = 1 - flipped.loc[mask, "y"]
    other, _ = s103.walk_forward(flipped)
    a = base[base["fold"] == last].reset_index(drop=True)
    b = other[other["fold"] == last].reset_index(drop=True)
    for col in ["sigma_cell98", "sigma_wide", "sigma_param"] + ["p_" + n for n in s103.ARMS]:
        assert np.array_equal(a[col].to_numpy(), b[col].to_numpy()), col


def test_clears_is_the_full_conjunction():
    row = {"improvement_vs_market": {"a": 0.005}, "dm_ci95": {"a": [0.001, 0.009]},
           "brier": {"a": 0.10, "recal": 0.11}}
    assert s103.clears(row, "a")
    assert not s103.clears({**row, "improvement_vs_market": {"a": 0.0039}}, "a")   # under the bar
    assert not s103.clears({**row, "dm_ci95": {"a": [-0.001, 0.011]}}, "a")        # CI spans zero
    assert not s103.clears({**row, "brier": {"a": 0.12, "recal": 0.11}}, "a")      # behind the null


def test_end_to_end_run_writes_the_paired_loss_series(tmp_path, frame):
    summary = s103.run(out_dir=tmp_path, stem="t103", frame=frame)
    series = pd.read_csv(summary["per_tick_csv"])
    assert summary["tier"].startswith("SCREEN") and summary["label"] == "SINGLE-WINDOW"
    assert summary["edge_claimed"] is False
    assert set(series["cluster_id"]) == set(series["game"])
    for arm in s103.ARMS:                     # Q9: both losses and the differential, per arm
        assert {"loss_" + arm, "d_" + arm + "_vs_market"}.issubset(series.columns)
        assert np.allclose(series["d_" + arm + "_vs_market"],
                           series["loss_market"] - series["loss_" + arm])
    assert len(summary["coefficient_stability"]["a_intercept"]) == s103.N_FOLDS
