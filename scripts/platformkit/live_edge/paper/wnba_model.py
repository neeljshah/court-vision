"""scripts.platformkit.live_edge.paper.wnba_model -- thin wrapper: (home,
away) -> real WNBA model_prob, via the EXISTING leak-free
domains.basketball_wnba.adapter.WNBAAdapter (Elo baseline_probability;
moneyline only, no spread/total model exists yet for WNBA -- see the
adapter's own predict() honest_note). Imported, never reimplemented.

Same rationale as tennis_model.py: today's shadow feed
(data/omni/live_edge/shadow/<date>.jsonl) carries conditioned_pred ==
market_price for wnba (market-echo placeholder, mechanism_applied=None), so
bridge.select()'s divergence gate can never fire via that feed. This module
supplies a real per-match probability so slate_trader can build wnba rows
that carry an actual model opinion.

Build cost: WNBAAdapter() is cheap to construct (no corpus replay at
__init__; baseline_probability() itself replays lazily per call from
espn_scoreboard.parquet). A lazy module-level singleton still amortizes the
parquet load across a whole slate.

INVARIANTS: import domains.basketball_wnba.adapter only, never reimplement
Elo; ASCII; <=300 LOC; never raises out of model_prob (honest None on any
resolution failure, e.g. missing espn_scoreboard.parquet or unseen team).
"""
from __future__ import annotations

from typing import Optional

_adapter = None  # lazy singleton -- ponytail: one process-wide instance.


def _get_adapter():
    global _adapter
    if _adapter is None:
        from domains.basketball_wnba.adapter import WNBAAdapter  # noqa: PLC0415
        _adapter = WNBAAdapter()
    return _adapter


def model_prob(home: str, away: str) -> Optional[float]:
    """Calibrated P(home wins) from the existing WNBA Elo adapter. None on
    any failure (unknown predictor state, bad names, missing data file) --
    an honest skip, never a fabricated number."""
    if not home or not away:
        return None
    try:
        wa = _get_adapter()
        out = wa.predict(home, away)
        return float(out["p_home_win"])
    except Exception:
        return None


def reset() -> None:
    """Test/CLI hook: drop the cached singleton so the next call rebuilds."""
    global _adapter
    _adapter = None


__all__ = ["model_prob", "reset"]
