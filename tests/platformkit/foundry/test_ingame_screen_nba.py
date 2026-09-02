"""S102 -- the NBA loader and the vectorised scorer for the S82 in-game screen tier.

Run ONLY this file: python -m pytest tests/platformkit/foundry/test_ingame_screen_nba.py -q
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.foundry import ingame_grammar_nba as G
from scripts.platformkit.foundry import ingame_screen_nba as N
from scripts.platformkit.foundry.ingame_screen import score_feature, walk_forward_feature

LEDGER = Path("data/cache/eval_gate/backtest_fwer.jsonl")
TOLERANCE = 1e-12


@pytest.fixture(scope="module")
def rows() -> pd.DataFrame:
    if not N.S86_CSV.exists():
        pytest.skip("the S86 screen archive is local-only and absent here")
    return N.load_screen()


@pytest.fixture(scope="module")
def small(rows: pd.DataFrame) -> pd.DataFrame:
    """A real 150-game slice, re-blocked so the walk-forward still has 5 fittable folds."""
    keep = sorted(rows["game"].unique())[:150]
    slice_ = rows[rows["game"].isin(keep)].reset_index(drop=True)
    slice_["game_date"] = N.fold_blocks(slice_)
    return slice_


def test_the_loader_puts_the_market_in_the_anchor_slot_and_blocks_whole_games(rows):
    """p_e4 IS the in-play line here, and no game straddles two folds (S36 disjointness)."""
    assert len(rows) == 232951 and rows["game"].nunique() == 797
    assert (rows["p_e4"] == rows["market"]).all()
    assert rows["ts"].is_monotonic_increasing
    assert rows["ts"].str.len().nunique() == 1, "fixed-width stamps, so `<` is a real ordering"
    assert rows["game_date"].nunique() == N.N_FOLDS + 1
    assert (rows.groupby("game")["game_date"].nunique() == 1).all()
    # blocks are contiguous in calendar time and roughly equal in ticks
    spans = rows.groupby("game_date")["date"].agg(["min", "max"]).sort_index()
    assert list(spans["max"][:-1]) < list(spans["min"][1:])
    sizes = rows.groupby("game_date").size()
    assert sizes.max() / sizes.min() < 1.5


def test_the_vectorised_dm_reproduces_the_reference_implementation():
    """`_dm_fast` is the same arithmetic as `dm_test.diebold_mariano`, not an approximation."""
    rng = np.random.default_rng(20260903)
    for scale in (1.0, 1e-4):
        delta = rng.normal(0.0, scale, 5000) + 0.1 * scale
        games = np.repeat(np.arange(120), 5000 // 120 + 1)[:5000]
        codes, uniques = pd.factorize(pd.Series(games), sort=False)
        stat, p_value, ci = N._dm_fast(delta, codes, len(uniques))
        reference = diebold_mariano(delta.tolist(), list(games))
        assert abs(stat - reference.dm_stat) < TOLERANCE
        assert abs(p_value - reference.p_value) < TOLERANCE
        assert abs(ci[0] - reference.ci95[0]) < TOLERANCE * max(1.0, abs(ci[0]))
        assert abs(ci[1] - reference.ci95[1]) < TOLERANCE * max(1.0, abs(ci[1]))


def test_score_fast_reproduces_the_s82_scorer_on_real_rows(small):
    """Same rows, same fits: every shared metric must agree with S82's own scorer."""
    column = "dmargin_k10|raw"
    frame = small.assign(**{column: G.build_grid(N.causal_source(small))[column].to_numpy()})
    candidate, null, folds = walk_forward_feature(frame, column, embargo_days=N.EMBARGO_DAYS)
    assert candidate.notna().any() and any(f["status"] == "OK" for f in folds)
    fast, reference = N.score_fast(frame, candidate, null, column), score_feature(
        frame, candidate, null, column)
    for key in ("n_ticks", "n_games", "brier_e4", "brier_null_recal", "brier_candidate",
                "brier_market", "improvement_vs_null", "dm_stat", "dm_p_raw",
                "improvement_vs_market", "feature_coverage", "clears_bar", "bar"):
        assert abs(float(fast[key]) - float(reference[key])) < TOLERANCE, key
    for i in (0, 1):
        assert abs(fast["dm_ci95"][i] - reference["dm_ci95"][i]) < TOLERANCE
    assert fast["brier_e4"] == fast["brier_market"], "the anchor IS the line on this corpus"


def test_every_fold_is_game_disjoint_purged_and_strictly_ordered(small):
    """The S82 purge is inherited unchanged: train outlives nothing in the fold."""
    column = "margin|raw"
    frame = small.assign(**{column: G.build_grid(N.causal_source(small))[column].to_numpy()})
    _, _, folds = walk_forward_feature(frame, column, embargo_days=N.EMBARGO_DAYS)
    fitted = [f for f in folds if f["status"] == "OK"]
    assert fitted, "the slice produced no fittable fold"
    for fold in fitted:
        test = frame[frame["game_date"] == fold["date"]]
        train = frame[frame["ts"] <= fold["cut"]]
        assert not set(train["game"]) & set(test["game"])
        assert train["ts"].max() < test["ts"].min()
        assert fold["n_train_games"] >= 1


def test_the_sweep_writes_one_committed_row_per_hypothesis_and_charges_nothing(small, tmp_path):
    """A screen is a NON-FINDING: no ledger row, no seal, no K -- asserted on the real file."""
    # the module BODY, past the docstring that NAMES what it must not import
    body = Path("scripts/platformkit/foundry/ingame_screen_nba.py").read_text("ascii").split(
        '"""', 2)[2]
    for banned in ("_charge_ledger", "backtest_runner", "backtest_fwer", "prereg_sha256",
                   "PREREG", "charge_tier"):
        assert banned not in body, banned
    before = LEDGER.read_bytes() if LEDGER.exists() else b""
    grid = G.build_grid(N.causal_source(small))
    hypotheses = G.enumerate_hypotheses()[:4]
    db = tmp_path / "s102_probe.sqlite"
    stats = N.sweep(small, grid, hypotheses, db, verbose=False)
    assert stats["n_scored_this_run"] == 4 and stats["screens_per_hour"] > 0
    written = sqlite3.connect(str(db)).execute(
        "SELECT hypothesis_id, status, n_ticks FROM screen").fetchall()
    assert len(written) == 4
    assert all(row[1] in ("SCREENED", "UNSCORED") for row in written)
    # a second pass resumes instead of rescoring, so a killed job is restartable
    assert N.sweep(small, grid, hypotheses, db, verbose=False)["n_scored_this_run"] == 0
    assert (LEDGER.read_bytes() if LEDGER.exists() else b"") == before
