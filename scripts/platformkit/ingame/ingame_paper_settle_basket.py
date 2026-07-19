"""scripts.platformkit.ingame.ingame_paper_settle_basket -- NBA score-fn helper for
ingame_paper_settle.settle_open, split into its own module to keep
ingame_paper_settle.py under the 300-LOC cap (it was already at 355 lines before
this change; every other per-sport score_fn lives inline there).

NBA reuses the EXISTING nba_outcome_resolver.NbaOutcomeResolver as-is -- its
.final_score(ticker) already matches the ScoreFn contract (ticker ->
(home_score, away_score) | None) used by every other sport's wrapper in
ingame_paper_settle.py, so no new resolver was needed, only this thin
availability-gated wrapper (mirrors _wnba_score_fn / _npb_score_fn / _kbo_score_fn).

HONESTY: an unavailable resolver (no local games.parquet / no home_win rows)
returns None -- the bet just stays open, never a fabricated settle.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network; never writes data/registry/; never raises out.

Per-file test: exercised via test_ingame_paper_settle.py (this module has no
branching logic of its own beyond the try/except availability gate).
"""
from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

ScoreFn = Callable[[str], Optional[Tuple[int, int]]]


def nba_score_fn() -> Optional[ScoreFn]:
    """NbaOutcomeResolver.final_score already matches the ScoreFn contract
    (ticker -> (home_score, away_score) | None) -- no wrapper needed beyond
    the availability gate. None (bets stay open) if the resolver has no
    usable local games.parquet."""
    try:
        from scripts.platformkit.ingame.nba_outcome_resolver import NbaOutcomeResolver
        res = NbaOutcomeResolver()
        if res.available:
            return res.final_score
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_paper_settle_basket NBA resolver unavailable: %s", exc)
    return None


__all__ = ["ScoreFn", "nba_score_fn"]
