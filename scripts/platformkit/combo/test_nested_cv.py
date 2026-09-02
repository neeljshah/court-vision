"""Per-file test for combo/nested_cv.py. Calibration only; no corpus, no ledger."""
from __future__ import annotations

import pytest

from scripts.platformkit.combo.nested_cv import partition_games, select_then_score


def test_empty_sealed_holdout_fails_closed():
    """RT-12: an empty sealed outer holdout used to return a score. MEASURED: 3
    game_ids over n_folds=5 leaves folds 3 and 4 empty and holdout_fold=3 gave
    n_holdout_games=0, outer_score=0.0, nothing raised -- a caller could not tell
    a 0-game holdout from a real one."""
    ids = ["g1", "g2", "g3"]
    parts = partition_games(ids, 5)
    empty = [f for f in range(5) if not parts.get(f)]
    assert empty, "fixture must leave at least one outer fold empty"
    with pytest.raises(ValueError, match="sealed outer holdout is empty"):
        select_then_score(lambda inner: "spec", lambda spec, hold: 0.0, ids,
                          n_folds=5, holdout_fold=empty[0])
    # a real holdout still scores, and the selector never sees it
    seen = []
    result = select_then_score(lambda inner: seen.extend(inner) or "spec",
                               lambda spec, hold: 0.25,
                               ["g%d" % i for i in range(40)], n_folds=5, holdout_fold=0)
    assert result.n_holdout_games > 0 and result.outer_score == 0.25
    assert not set(seen) & set(result.holdout_game_ids)
