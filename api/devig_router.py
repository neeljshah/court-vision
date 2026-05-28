"""Devig API router — converts vigged sportsbook odds into fair probabilities.

POST /api/devig
    body: {"over_odds": int, "under_odds": int, "method": str}
       or {"odds": [int, ...], "method": str}

    method ∈ {"shin", "additive", "proportional", "multiplicative", "power"}
    (default: "shin")

Returns:
    {
      "method":      str,
      "vigged":      [float, ...],   # implied probs straight from American odds
      "fair_probs":  [float, ...],   # de-vigged, sums to 1.0
      "fair_odds":   [int, ...],     # fair_probs converted back to American odds
      "overround":   float,          # sum(vigged) - 1
    }
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.devig import (  # noqa: E402
    american_to_prob,
    devig,
    prob_to_american,
)


router = APIRouter()


class DevigRequest(BaseModel):
    """Body for POST /api/devig.

    Either supply (over_odds, under_odds) for the common 2-way pair, or
    `odds` as a list for n-way markets. `method` is optional and defaults
    to Shin.
    """

    over_odds: Optional[int] = None
    under_odds: Optional[int] = None
    odds: Optional[List[int]] = None
    method: str = "shin"


_ALLOWED = {"additive", "proportional", "multiplicative", "power", "shin"}


@router.post("/api/devig", tags=["devig"])
def post_devig(req: DevigRequest) -> dict:
    method = (req.method or "shin").lower()
    if method not in _ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"method must be one of {sorted(_ALLOWED)}",
        )

    if req.odds is not None and len(req.odds) >= 2:
        american_odds: List[int] = [int(o) for o in req.odds]
    elif req.over_odds is not None and req.under_odds is not None:
        american_odds = [int(req.over_odds), int(req.under_odds)]
    else:
        raise HTTPException(
            status_code=400,
            detail="must supply either (over_odds, under_odds) or odds=[...]",
        )

    vigged = [american_to_prob(o) for o in american_odds]
    try:
        fair = devig(vigged, method=method)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    fair_odds = [prob_to_american(p) for p in fair]
    return {
        "method": method,
        "vigged": [round(float(v), 6) for v in vigged],
        "fair_probs": [round(float(p), 6) for p in fair],
        "fair_odds": fair_odds,
        "overround": round(float(sum(vigged) - 1.0), 6),
    }
