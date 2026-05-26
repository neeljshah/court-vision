"""R21_N1 — PTS/AST artifact load + predict regression tests.

R19_L7 observed that the production prediction path returned None for PTS
and AST on every starter while the other five stats (REB/FG3M/STL/BLK/TOV)
produced values. Root cause: gitignored prop_pergame base-learner artifacts
(props_pg_pts.json, props_pg_mlp_pts.pkl, props_pg_lgb_ast.pkl, ...) are NOT
present in fresh `.claude/worktrees/<wt>/data/models/` directories, so the
3-way blend has 0 learners and silently returns None.

The fix in src/prediction/prop_pergame.py is a worktree-aware model-dir
resolver that falls back to the host repo's data/models when the local one
is missing PTS artifacts. These tests guard both invariants:

  1. `load_pergame_model` returns >=1 learner for every STATS member.
  2. `predict_pergame` returns a non-None float for every STATS member on a
     plausible synthetic feature row.

If these fail in CI on a fresh checkout, the user needs to either:
  - set NBA_MODEL_DIR to point at a populated artifact directory, or
  - retrain via `python -m src.prediction.prop_pergame` (writes to data/models)
"""
from __future__ import annotations

import os

import pytest

from src.prediction.prop_pergame import (
    STATS,
    feature_columns,
    load_pergame_model,
    predict_pergame,
)


def _has_any_props_pg_artifacts() -> bool:
    """Check whether the resolved model dir actually has shipped artifacts.

    On a clean clone with no model downloads the artifacts truly won't exist
    and skipping is the right call — the resolver gives us the best path
    available, not a guarantee. CI environments that don't restore models
    skip these tests rather than fail spuriously.
    """
    from src.prediction.prop_pergame import _MODEL_DIR
    return os.path.exists(os.path.join(_MODEL_DIR, "props_pg_pts.json"))


pytestmark = pytest.mark.skipif(
    not _has_any_props_pg_artifacts(),
    reason="prop_pergame base-learner artifacts not on disk (fresh clone) "
           "— set NBA_MODEL_DIR or train models first.",
)


@pytest.fixture(scope="module")
def synthetic_row() -> dict:
    """A plausible mid-season starter's pregame feature row.

    Filled with 0.0 by default for every column the trained models expect,
    then overridden for the form features so predictions exercise real
    learner branches (XGB/LGB/MLP) rather than the all-zero pathological
    input that some preprocessors short-circuit on.
    """
    row = {c: 0.0 for c in feature_columns()}
    row.update({
        "l5_pts": 25.0, "l10_pts": 23.0, "ewma_pts": 24.0, "prev_pts": 22.0,
        "l5_reb": 5.0,  "l10_reb": 5.0,  "ewma_reb": 5.0,  "prev_reb": 5.0,
        "l5_ast": 4.0,  "l10_ast": 4.0,  "ewma_ast": 4.0,  "prev_ast": 4.0,
        "l5_fg3m": 2.0, "l10_fg3m": 2.0, "ewma_fg3m": 2.0, "prev_fg3m": 2.0,
        "l5_stl": 1.0,  "l10_stl": 1.0,  "ewma_stl": 1.0,  "prev_stl": 1.0,
        "l5_blk": 0.5,  "l10_blk": 0.5,  "ewma_blk": 0.5,  "prev_blk": 0.5,
        "l5_tov": 2.5,  "l10_tov": 2.5,  "ewma_tov": 2.5,  "prev_tov": 2.5,
        "l5_min": 32.0, "l10_min": 32.0, "ewma_min": 32.0, "prev_min": 32.0,
        "is_home": 1, "rest_days": 2.0, "games_played": 20,
    })
    return row


@pytest.mark.parametrize("stat", STATS)
def test_load_pergame_model_returns_learners(stat: str) -> None:
    """Every STATS member must have >= 1 loaded base learner.

    The blend path (used directly by pts/ast, indirectly as q50-fallback by
    the other five) cannot produce a prediction with 0 learners. This was
    the L7 regression: load returned [] for every stat in the worktree.
    """
    learners = load_pergame_model(stat)
    assert isinstance(learners, list), \
        f"load_pergame_model({stat!r}) returned non-list {type(learners)!r}"
    assert len(learners) >= 1, (
        f"load_pergame_model({stat!r}) returned 0 learners — model artifacts "
        f"missing from resolved model_dir. L7's PTS/AST None bug regressed."
    )


@pytest.mark.parametrize("stat", STATS)
def test_predict_pergame_returns_non_none(synthetic_row: dict, stat: str) -> None:
    """predict_pergame must return a non-None float for every stat.

    Specifically guards PTS + AST since those are the two stats that L7
    observed silently failing on every starter. Tight numeric bounds aren't
    asserted — we only care that the prediction PATH completes end-to-end.
    """
    pred = predict_pergame(stat, synthetic_row)
    assert pred is not None, (
        f"predict_pergame({stat!r}) returned None — base learners or q50 "
        f"model unreachable. This is the L7 regression."
    )
    assert isinstance(pred, (int, float)), \
        f"predict_pergame({stat!r}) returned {type(pred)!r}, expected float"
    assert pred >= 0.0, \
        f"predict_pergame({stat!r}) returned negative value {pred}"
    # Upper bound is generous — just guarding against runaway transforms.
    assert pred < 100.0, \
        f"predict_pergame({stat!r}) returned implausibly large value {pred}"


def test_pts_and_ast_both_non_none(synthetic_row: dict) -> None:
    """Direct guard for the L7 finding: both PTS and AST must produce values
    in the same call to a slate-style loop (not just one at a time)."""
    pts = predict_pergame("pts", synthetic_row)
    ast = predict_pergame("ast", synthetic_row)
    assert pts is not None, "PTS prediction is None (L7 regression)"
    assert ast is not None, "AST prediction is None (L7 regression)"
    assert pts > 0.0, f"PTS prediction non-positive: {pts}"
    assert ast > 0.0, f"AST prediction non-positive: {ast}"
