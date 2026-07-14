"""scripts.platformkit.live_edge.paper.tennis_model -- thin wrapper: (home,
away) -> real tennis model_prob, via the EXISTING calibrated forecaster
domains.tennis.predictor.TennisPredictor (walk-forward surface Elo + leak-free
recal; the a4872ee8-era work). Imported, never reimplemented.

WHY THIS FILE EXISTS: the live shadow rows this lane's bridge.py consumes
(data/omni/live_edge/shadow/<date>.jsonl) carry conditioned_pred IDENTICAL to
market_price for every tennis row today (mechanism_applied=None) -- a market-
echo placeholder, not a model. bridge.select()'s divergence gate can therefore
never fire for tennis via that shadow feed. This module supplies the missing
real per-match probability so slate_trader can build tennis shadow rows that
actually carry a model opinion.

Build cost: TennisPredictor() replays the ~30k-match corpus once (~9s). A
lazy module-level singleton amortizes that across a whole slate.

HONEST: Elo+recal trails the efficient Pinnacle ATP close (see predictor.py's
own docstring). No tour label survives into the live odds feed, so tour is
pinned to "ATP" and surface to "Hard" -- a simplification, not a claim of
per-tournament accuracy. edge_claimed is never set here.

INVARIANTS: import domains.tennis.predictor only, never reimplement Elo/
recal; ASCII; <=300 LOC; never raises out of model_prob (honest None on any
resolution failure).
"""
from __future__ import annotations

from typing import Optional

_predictor = None  # lazy singleton -- ponytail: one process-wide instance,
                    # rebuild only by restarting the process (corpus is as-of
                    # build time; fine for a same-day slate run).


def _get_predictor():
    global _predictor
    if _predictor is None:
        from domains.tennis.predictor import TennisPredictor  # noqa: PLC0415
        _predictor = TennisPredictor(tour="ATP")
    return _predictor


def model_prob(home: str, away: str, *, surface: str = "Hard") -> Optional[float]:
    """Calibrated P(home wins) from the existing tennis forecaster. None on
    any failure (unknown predictor state, bad names) -- an honest skip, never
    a fabricated number."""
    if not home or not away:
        return None
    try:
        tp = _get_predictor()
        out = tp.predict(home, away, surface=surface)
        return float(out["p1_match_win"])
    except Exception:
        return None


def reset() -> None:
    """Test/CLI hook: drop the cached singleton so the next call rebuilds."""
    global _predictor
    _predictor = None


__all__ = ["model_prob", "reset"]
