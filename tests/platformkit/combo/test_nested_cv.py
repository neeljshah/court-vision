"""Negative control (a): nested CV seals the outer holdout; selection never sees it.

Plants an IN-FOLD-LEAK input -- a "combo" whose apparent quality is read off outer-fold
games -- and asserts it does NOT clear the sealed fold, AND the select_fn-spy never saw a
holdout game_id (the #1-leak assertion).
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.combo.nested_cv import (
    SelectSpy, outer_fold_of, partition_games, select_then_score,
)

_GAMES = [f"G{i:03d}" for i in range(60)]


def test_partition_is_deterministic_and_disjoint():
    p1 = partition_games(_GAMES, 5)
    p2 = partition_games(_GAMES, 5)
    # deterministic across runs
    assert p1 == p2
    # disjoint: every game in exactly one outer fold
    seen = set()
    for fold, gs in p1.items():
        assert not (gs & seen)
        seen |= gs
    assert seen == set(_GAMES)
    # stable per-game hash
    assert all(outer_fold_of(g, 5) == outer_fold_of(g, 5) for g in _GAMES)


def test_selector_never_sees_holdout_game():
    """The spy records every game the selector touched; it must be disjoint from holdout."""
    captured = {}

    def select_fn(inner_ids):
        captured["inner"] = list(inner_ids)
        return {"spec": "pick"}

    def score_fn(spec, holdout_ids):
        return 0.20  # arbitrary held-out loss

    parts = partition_games(_GAMES, 5)
    holdout_games = parts[0]

    spy = SelectSpy(select_fn)
    # mimic what select_then_score does internally to inspect the spy
    inner = sorted((g for f, gs in parts.items() if f != 0 for g in gs), key=str)
    spy(inner)
    assert not spy.saw_any(holdout_games)        # THE #1-leak assertion
    assert spy.seen_game_ids == set(inner)
    assert spy.call_count == 1

    res = select_then_score(select_fn, score_fn, _GAMES, n_folds=5, holdout_fold=0)
    assert set(captured["inner"]) == set(inner)
    assert not (set(captured["inner"]) & holdout_games)
    assert res.outer_score == 0.20
    assert set(res.holdout_game_ids) == holdout_games


def test_in_fold_leak_does_not_clear_the_sealed_fold():
    """A combo that 'looks great' by cheating on inner folds is scored on the SEALED fold.

    The selector returns a spec that secretly memorized inner-fold labels (inner Brier
    ~0). But the score that flows forward is the SEALED-holdout score, where the memorized
    map is worthless (Brier ~0.25). select_then_score returns the WORTHLESS holdout score.
    """
    rng = np.random.default_rng(0)
    # true label per game (the holdout map cannot know these for holdout games)
    labels = {g: int(rng.integers(0, 2)) for g in _GAMES}

    def select_fn(inner_ids):
        # "memorize" only the inner games -- a leaky selector
        return {"memorized": {g: labels[g] for g in inner_ids}}

    def score_fn(spec, holdout_ids):
        mem = spec["memorized"]
        # on the SEALED holdout the memorized map has no entry -> predict 0.5 (no skill)
        preds = np.array([mem.get(g, 0.5) for g in holdout_ids], dtype=float)
        y = np.array([labels[g] for g in holdout_ids], dtype=float)
        return float(np.mean((preds - y) ** 2))  # Brier on the sealed fold

    res = select_then_score(select_fn, score_fn, _GAMES, n_folds=5, holdout_fold=0)
    # worthless on the sealed fold: ~0.25 (predicting 0.5 everywhere), NOT ~0.0
    assert res.outer_score > 0.15, res.outer_score
    # and the selector provably never saw a holdout game
    assert res.n_holdout_games > 0 and res.n_inner_games > 0
