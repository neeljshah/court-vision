"""scripts.platformkit.combo.nested_cv -- L1: nested CV with a FROZEN outer holdout.

Selection-on-the-test-set is the #1 combination leak: pick the best combo (which
interaction / regime cut / blend weight) on the SAME fold you score it on and any
"win" is a selection artifact. This module makes that STRUCTURALLY IMPOSSIBLE:

  * Games are partitioned into OUTER folds by a STABLE blake2b hash of game_id (NOT
    row index, NOT time) -- deterministic across runs and disjoint (no game in two
    outer folds). One outer fold is the FROZEN holdout; the selector NEVER sees it.
  * select_then_score(select_fn, score_fn, games) passes the selector ONLY the inner
    (outer-train) game_ids; it scores the selected spec EXACTLY ONCE on the frozen
    outer holdout. The score that flows forward is the OUTER-HOLDOUT score, never an
    inner/selection score.
  * A select_fn SPY (SelectSpy) records every game_id the selector touched; a per-file
    test asserts it NEVER saw a holdout game_id (the #1-leak assertion).

NO corpus-seam re-selection (D1, baked MUST-FIX): the spec is SELECTED ONCE on the
inner folds, then the SAME FROZEN spec is what gets scored. This module returns the
frozen spec + its single outer-holdout score; the combo gate then scores that SAME
frozen spec across corpora / the sealed fold -- it never re-picks per corpus/fold.

Calibration, not edge. NO $ / ROI anywhere. numpy + stdlib (hashlib) only. ASCII.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Sequence, Set

# A fixed salt makes the game_id partition reproducible AND distinct from any other
# hash partition in the codebase (so combos cannot collide a known split).
_PARTITION_SALT = b"combo.nested_cv.outer.v1"


def outer_fold_of(game_id: Any, n_folds: int) -> int:
    """Deterministic outer-fold index for a game_id (stable blake2b hash, NOT row/time).

    A restart reproduces the identical split; a combo cannot "find" the holdout because
    the partition depends only on the salted game_id, never on row order or the outcome.
    """
    h = hashlib.blake2b(_PARTITION_SALT + str(game_id).encode("utf-8"), digest_size=8)
    return int.from_bytes(h.digest(), "big") % max(1, int(n_folds))


def partition_games(game_ids: Sequence[Any], n_folds: int) -> Dict[int, Set[Any]]:
    """Disjoint outer-fold -> set(game_id) partition. Every game in exactly one fold."""
    parts: Dict[int, Set[Any]] = {f: set() for f in range(max(1, int(n_folds)))}
    for gid in set(game_ids):
        parts[outer_fold_of(gid, n_folds)].add(gid)
    return parts


class SelectSpy:
    """Wraps a select_fn and RECORDS every game_id it is given (the #1-leak tripwire).

    The combo gate hands the selector a SelectSpy-wrapped view of the inner games only;
    a per-file test then asserts `seen_game_ids` is DISJOINT from the holdout games --
    proving selection never touched the sealed fold. If the selector somehow received a
    holdout game, `saw_any(holdout)` returns True and the test FAILS loudly.
    """

    def __init__(self, select_fn: Callable[[Sequence[Any]], Any]) -> None:
        self._fn = select_fn
        self.seen_game_ids: Set[Any] = set()
        self.call_count = 0

    def __call__(self, inner_game_ids: Sequence[Any]) -> Any:
        self.call_count += 1
        for gid in inner_game_ids:
            self.seen_game_ids.add(gid)
        # The selector receives ONLY the game_ids passed here (the inner folds); it has
        # no path to the holdout indices, which are never put in this list.
        return self._fn(list(inner_game_ids))

    def saw_any(self, game_ids: Sequence[Any]) -> bool:
        return bool(self.seen_game_ids & set(game_ids))


@dataclass(frozen=True)
class NestedResult:
    """The frozen outer-holdout result of one nested-CV selection (D1: one frozen spec)."""

    selected_spec: Any                  # the SINGLE spec chosen on inner folds (frozen)
    outer_score: float                  # scored ONCE on the sealed outer holdout
    holdout_fold: int                   # which outer fold was sealed
    n_inner_games: int
    n_holdout_games: int
    holdout_game_ids: List[Any] = field(default_factory=list)
    note: str = "score = sealed-outer-holdout, not selection; calibration not edge"


def select_then_score(
    select_fn: Callable[[Sequence[Any]], Any],
    score_fn: Callable[[Any, Sequence[Any]], float],
    game_ids: Sequence[Any],
    *,
    n_folds: int = 5,
    holdout_fold: int = 0,
) -> NestedResult:
    """SELECT a combo on INNER folds; SCORE it ONCE on the FROZEN outer holdout.

    Parameters
    ----------
    select_fn(inner_game_ids) -> spec
        Chooses the combination spec using ONLY the inner (outer-train) games. It is
        wrapped in a SelectSpy so a test can prove it never saw a holdout game.
    score_fn(spec, holdout_game_ids) -> float
        Scores the SELECTED spec on the sealed outer-holdout games (lower = better, a
        Brier-style loss). Called EXACTLY ONCE, on the holdout only.
    game_ids
        All game_ids in the corpus (the universe to partition).
    n_folds, holdout_fold
        The outer partition; `holdout_fold` is the sealed fold the selector never reads.

    Returns NestedResult with the frozen spec + the single sealed-holdout score. The
    selector is structurally unable to read the holdout: only the inner game_ids are
    ever passed to it. NO corpus-seam re-selection -- the returned spec is FROZEN.
    """
    parts = partition_games(game_ids, n_folds)
    holdout = sorted(parts.get(int(holdout_fold), set()), key=str)
    inner = sorted(
        (g for f, gs in parts.items() if f != int(holdout_fold) for g in gs), key=str
    )
    spy = SelectSpy(select_fn)
    selected = spy(inner)                       # selection sees ONLY inner games
    # Defense-in-depth: the spy MUST NOT have touched any holdout game. This mirrors the
    # per-file test's assertion at the source, so a future refactor that leaks a holdout
    # game into selection fails here too, not just in the test.
    if spy.saw_any(holdout):
        raise AssertionError(
            "SELECTION LEAK: select_fn was given a holdout game_id -- nested CV "
            "violated; the sealed outer fold must never reach the selector.")
    # RT-12: an EMPTY sealed holdout used to return a score anyway. MEASURED: 3
    # game_ids over n_folds=5 leaves folds 3 and 4 empty, and holdout_fold=3 gave
    # n_holdout_games=0 with outer_score=0.0 -- a caller reading outer_score could
    # not tell a 0-game holdout from a real one. Fail closed instead.
    if not holdout:
        raise ValueError(
            "sealed outer holdout is empty: fold %d of %d holds 0 of %d game_ids; "
            "an outer score over 0 games is not a score"
            % (int(holdout_fold), int(n_folds), len(list(game_ids))))
    score = float(score_fn(selected, holdout))  # scored ONCE on the sealed fold
    return NestedResult(
        selected_spec=selected, outer_score=score, holdout_fold=int(holdout_fold),
        n_inner_games=len(inner), n_holdout_games=len(holdout),
        holdout_game_ids=list(holdout),
    )


__all__ = [
    "outer_fold_of", "partition_games", "SelectSpy",
    "NestedResult", "select_then_score",
]
