"""src/ingame/trust_curve.py — P3.2: per-(stat, remaining-frac bucket, regime) trust weight.

Pure lookup, no refit at serve (D04 §module-layout). IDENTITY (default / no json on disk) returns 0.0
so the posterior reproduces the BASE prior EXACTLY — byte-identical, the validated no-shrink baseline.

The fitted json (``data/models/ingame/trust_curve.json``) is GATED and DATA-BLOCKED until it can be fit
on a SAME-ERA held-out fold (the fit corpus is 2022-23 PBP, live is 2025-26 — RED-A A4 / RED-B B10):
each cell's ``trust_w`` minimizes RMSE+bias (NOT MAE — the shrink-artifact guard), with an n_min floor
and seed stability (Δtrust_w ≤ 0.15 across 3 seeds); a cell that cannot beat BASE on RMSE reproduces BASE
(``trust_w=0``). Until that artifact exists, this returns 0.0 everywhere.

DEFAULT-OFF: reached only under CV_INGAME_STATE; with no json it is a no-op identity. stdlib only.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_JSON = os.path.join(_ROOT, "data", "models", "ingame", "trust_curve.json")

# remaining-game-fraction bucket edges (matches the in-game state-mult grid granularity)
REMAINING_FRAC_EDGES = (0.0, 0.125, 0.25, 0.5, 0.75, 1.0)


def remaining_frac_bucket(remaining_frac: float) -> int:
    """Index of the remaining-fraction bucket for ``remaining_frac`` in [0,1]."""
    rf = min(1.0, max(0.0, float(remaining_frac)))
    for i in range(len(REMAINING_FRAC_EDGES) - 1):
        if rf <= REMAINING_FRAC_EDGES[i + 1]:
            return i
    return len(REMAINING_FRAC_EDGES) - 2


def _regime_key(regime: Optional[Any]) -> str:
    """Coarse, deterministic regime key. None -> 'base'. Dict/obj -> a few coarse buckets."""
    if regime is None:
        return "base"
    if isinstance(regime, dict):
        playoff = bool(regime.get("is_playoff", False))
        mb = int(regime.get("margin_bucket", 0))
        return f"po{int(playoff)}_m{mb}"
    playoff = bool(getattr(regime, "is_playoff", False))
    mb = int(getattr(regime, "margin_bucket", 0))
    return f"po{int(playoff)}_m{mb}"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not os.path.exists(_JSON):
        return {}
    try:
        with open(_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def trust_w(stat: str, remaining_frac: float, regime: Optional[Any] = None,
            min_so_far: Optional[float] = None) -> float:
    """Weight on the EVIDENCE (current-pace extrapolation); (1-trust_w) on the prior.

    IDENTITY default = 0.0 (reproduce BASE / prior, byte-identical). When the gated json exists it
    supplies the per-cell RMSE-fit weight. Always clamped to [0,1].
    """
    data = _load()
    if not data:
        return 0.0  # IDENTITY: reproduce BASE — the validated no-shrink default
    cells = data.get("cells", {})
    key = f"{stat}|{remaining_frac_bucket(remaining_frac)}|{_regime_key(regime)}"
    val = cells.get(key, data.get("default", 0.0))
    return min(1.0, max(0.0, float(val)))


def is_identity() -> bool:
    """True iff no fitted curve is on disk (every trust_w returns 0.0 -> posterior == BASE)."""
    return not _load()
