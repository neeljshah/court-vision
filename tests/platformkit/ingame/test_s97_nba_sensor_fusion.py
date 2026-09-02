"""S97 per-file test -- two-sensor Kalman fusion of the NBA in-play line and the as-of prior.

Run: python -m pytest tests/platformkit/ingame/test_s97_nba_sensor_fusion.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate import s94_nba_early_shrinkage as s94
from scripts.platformkit.eval_gate import s97_nba_sensor_fusion as s97

Q_TRUE, RM_TRUE, RP_TRUE = 0.04, 0.02, 0.30


def _frame(n_games: int = 120, ticks: int = 60, seed: int = 11,
           q: float = Q_TRUE, r_m: float = RM_TRUE, r_p: float = RP_TRUE) -> pd.DataFrame:
    """A synthetic screen frame whose two series really are noisy reads of one latent walk."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        date = "2025-01-%02d" % (1 + g % 28)
        x = np.cumsum(rng.normal(0.0, np.sqrt(q), ticks)) + rng.normal(0.0, 0.8)
        zm = x + rng.normal(0.0, np.sqrt(r_m), ticks)
        zp = x + rng.normal(0.0, np.sqrt(r_p), ticks)
        y = (rng.random(ticks) < s97.sigmoid(x)).astype(int)
        for t in range(ticks):
            rows.append({"game_id": 2000 + g, "game_date": date, "ts": t,
                         "period_bucket": "P1", "margin_bucket": "close_le5",
                         "rem_bucket": "rem_gt12", "model": float(s97.sigmoid(zp[t])),
                         "market": float(s97.sigmoid(zm[t])), "y": int(y[t])})
    return s94.prepare(pd.DataFrame(rows))


def test_fit_noise_recovers_a_planted_local_level():
    """The innovation-variance moments must recover the planted q, r_m and r_p."""
    by_cell, pooled = s97.fit_noise(_frame(n_games=300))
    assert set(by_cell) == {"P1|close_le5|rem_gt12"}
    for q, r_m, r_p in (by_cell["P1|close_le5|rem_gt12"], pooled):
        assert abs(q - Q_TRUE) < 0.01, q
        assert abs(r_m - RM_TRUE) < 0.01, r_m
        assert abs(r_p - RP_TRUE) < 0.05, r_p


def test_filter_is_strictly_before_only():
    """Truncating a game after k ticks leaves its first k posteriors bit-identical."""
    frame = _frame(n_games=3, ticks=30)
    par = {"P1|close_le5|rem_gt12": (Q_TRUE, RM_TRUE, RP_TRUE)}
    pooled = (Q_TRUE, RM_TRUE, RP_TRUE)
    mean, var = s97.kalman(frame, par, pooled)
    first = sorted(frame["game"].unique())[0]
    keep = ~((frame["game"] == first) & (frame["ts"] >= 12))
    cut_mean, cut_var = s97.kalman(frame[keep], par, pooled)
    head = ((frame["game"] == first) & (frame["ts"] < 12)).to_numpy()
    cut_head = ((frame[keep]["game"] == first) & (frame[keep]["ts"] < 12)).to_numpy()
    assert np.array_equal(mean[head], cut_mean[cut_head])
    assert np.array_equal(var[head], cut_var[cut_head])


def test_filter_output_is_row_aligned_under_shuffling():
    """kalman must return values against the caller's row order, not its own sort order."""
    frame = _frame(n_games=4, ticks=25)
    par, pooled = {}, (Q_TRUE, RM_TRUE, RP_TRUE)
    mean, _ = s97.kalman(frame, par, pooled)
    shuffled = frame.sample(frac=1.0, random_state=3)
    shuf_mean, _ = s97.kalman(shuffled, par, pooled)
    assert np.array_equal(pd.Series(shuf_mean, index=shuffled.index).sort_index().to_numpy(),
                          pd.Series(mean, index=frame.index).sort_index().to_numpy())


def test_a_worthless_prior_leaves_the_market_untouched():
    """r_p enormous and r_m tiny: the posterior collapses onto the line itself."""
    frame = _frame(n_games=3, ticks=20)
    pooled = (1e6, 1e-9, 1e9)
    mean, _ = s97.kalman(frame, {}, pooled)
    assert np.allclose(s97.sigmoid(mean), frame["market"].to_numpy(float), atol=1e-6)


def test_walk_forward_is_game_purged_and_embargoed():
    frame = _frame()
    scored, folds = s97.walk_forward(frame, n_folds=3)
    ok = [f for f in folds if f["status"] == "OK"]
    assert ok, folds
    for f in ok:
        assert f["train_date_max"] < f["embargo_cut"] <= f["test_start"]
        block = scored[scored["fold"] == f["fold"]]
        assert block["date"].min() >= f["test_start"]
        assert set(block["game"]).isdisjoint(set(frame[frame["date"] < f["embargo_cut"]]["game"]))
    assert (scored["lo90"] <= scored["p_posterior"]).all()
    assert (scored["p_posterior"] <= scored["hi90"]).all()


def test_no_test_row_informs_its_own_fit():
    """Flipping the LAST fold's own held-out outcomes must not move its posterior at all."""
    frame = _frame()
    base, folds = s97.walk_forward(frame, n_folds=3)
    last = max(f["fold"] for f in folds if f["status"] == "OK")
    span = base[base["fold"] == last]
    poisoned = frame.copy()
    hit = poisoned["date"].between(span["date"].min(), span["date"].max())
    poisoned.loc[hit, "y"] = 1 - poisoned.loc[hit, "y"]
    after, _ = s97.walk_forward(poisoned, n_folds=3)
    assert np.allclose(span["p_posterior"].to_numpy(),
                       after[after["fold"] == last]["p_posterior"].to_numpy(), atol=0.0)


def test_coverage_is_bounded_by_the_interval_width():
    """A width-1 interval covers every group; a zero-width one off the frequency covers none."""
    n = 4000
    rng = np.random.default_rng(5)
    base = pd.DataFrame({"y": rng.integers(0, 2, n), "p_posterior": rng.random(n)})
    wide = s97.coverage(base.assign(lo90=0.0, hi90=1.0))
    narrow = s97.coverage(base.assign(lo90=-1.0, hi90=-0.9))
    assert wide["coverage"] == 1.0 and wide["n_groups"] >= 2
    assert narrow["coverage"] == 0.0 and narrow["mean_miss"] > 0.0
    assert s97.coverage(base.head(100))["coverage"] is None       # too few ticks to group


def test_score_cell_arms_and_sign_convention():
    scored, _ = s97.walk_forward(_frame(), n_folds=3)
    row = s97.score_cell(scored)
    y = scored["y"].to_numpy(float)
    assert row["brier"]["market"] == float(np.mean((scored["market"].to_numpy() - y) ** 2))
    # d > 0 means the posterior lost less; a posterior equal to the market scores exactly 0.
    same = scored.assign(p_posterior=scored["market"])
    assert s97.score_cell(same)["improvement"]["posterior_vs_market"] == 0.0
    assert row["n_informative"] <= row["n"] and 0.0 <= row["n_eff"] <= row["n"]


def test_bars_are_not_moved():
    assert s97.IMPROVEMENT_BAR == 0.004
    assert (s97.NOMINAL_COVERAGE, s97.COVERAGE_TOL) == (0.90, 0.02)
    assert s97.TARGET == ("P1", "P2", "close_le5", "rem_gt12")
    assert s97.IMPROVEMENT_BAR == s94.IMPROVEMENT_BAR
