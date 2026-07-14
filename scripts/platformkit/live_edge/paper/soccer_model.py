"""scripts.platformkit.live_edge.paper.soccer_model -- thin wrapper: (home,
away) -> real soccer model_prob (P(home wins), two-way normalized excluding
draw), for BOTH club soccer (domains.soccer.SoccerPredictor) and
international/World Cup soccer (domains.soccer_intl.IntlSoccerPredictor,
neutral=True -- "the World Cup case", per that module's own docstring).
Imported, never reimplemented.

Same rationale as tennis_model.py/wnba_model.py: today's shadow feed carries
conditioned_pred == market_price for soccer/soccer_intl (market-echo
placeholder), so bridge.select()'s divergence gate can never fire via that
feed. This module supplies a real per-match probability so slate_trader can
build shadow rows carrying an actual model opinion.

HONEST 1X2->2-WAY COLLAPSE: both predictors return a full 1X2 surface
(p_home_win/p_draw/p_away_win) but the live odds capture (line_history) only
carries a two-way moneyline tick per side. model_prob here returns
p_home_win / (p_home_win + p_away_win) -- draw probability mass is dropped,
not folded in as a guess. This is a simplification for the two-way paper
bridge, not a claim that soccer is a two-way market.

Build cost: SoccerPredictor/IntlSoccerPredictor each replay their own
results corpus once at construction. Lazy module-level singletons (one per
sport family) amortize that across a whole slate.

INVARIANTS: import domains.soccer.predictor / domains.soccer_intl.predictor
only, never reimplement Dixon-Coles/Platt; ASCII; <=300 LOC; never raises
out of model_prob (honest None on any resolution failure).
"""
from __future__ import annotations

from typing import Optional

_predictors: dict = {}  # lazy singletons keyed by sport -- ponytail: one
                         # process-wide instance per sport family.


def _get_predictor(sport: str):
    if sport not in _predictors:
        if sport == "soccer_intl":
            from domains.soccer_intl.predictor import IntlSoccerPredictor  # noqa: PLC0415
            _predictors[sport] = IntlSoccerPredictor()
        elif sport == "soccer":
            from domains.soccer.predictor import SoccerPredictor  # noqa: PLC0415
            _predictors[sport] = SoccerPredictor()
        else:
            raise ValueError(f"unsupported soccer sport: {sport}")
    return _predictors[sport]


def model_prob(home: str, away: str, *, sport: str = "soccer_intl") -> Optional[float]:
    """Calibrated two-way P(home wins) (draw mass dropped, see module
    docstring) from the existing soccer forecaster. sport selects club
    (domains.soccer) vs international/World Cup (domains.soccer_intl,
    neutral=True by default). None on any failure -- an honest skip."""
    if not home or not away:
        return None
    try:
        pred = _get_predictor(sport)
        out = pred.predict(home, away)
        ph, pa = float(out["p_home_win"]), float(out["p_away_win"])
        denom = ph + pa
        if denom <= 0.0:
            return None
        return ph / denom
    except Exception:
        return None


def reset() -> None:
    """Test/CLI hook: drop cached singletons so the next call rebuilds."""
    global _predictors
    _predictors = {}


__all__ = ["model_prob", "reset"]
