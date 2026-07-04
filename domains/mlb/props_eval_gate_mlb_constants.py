"""Shared constants for props_eval_gate_mlb.py + props_eval_gate_mlb_dist.py
(WAKE-31, queue item 3). Split into its own tiny module so neither of the two
larger files needs to import the other for these -- avoids a circular import
and keeps both files under the 300 LOC cap.

PURE stdlib; no src/kernel/api imports. ASCII only.
"""
from __future__ import annotations

from typing import Dict, Tuple

# Canonical props under test. col = the per-start realized-count column in
# player_gamelogs.parquet (already summed per start row -- one pitcher-row IS
# one start once filtered by _identify_starts upstream logic).
PROPS: Dict[str, str] = {
    "sp_strikeouts": "pitch_strikeOuts",
    "sp_hits_allowed": "hits_allowed",
    "sp_walks_allowed": "baseOnBalls_allowed",
}

CORPORA: Dict[str, Tuple[int, int]] = {
    "fit_2022_2023": (2022, 2023),
    "holdout_2024": (2024, 2024),
    "holdout_2025_2026": (2025, 2026),
}


def dispersion_for(stat_key: str) -> float:
    """Fixed NB dispersion prior per prop (mild over-dispersion prior, NOT fit on
    the eval corpus -- fitting sigma on the same data it is scored on would be a
    leak of a different kind, a look-ahead on the evaluation itself)."""
    return {"sp_strikeouts": 8.0, "sp_hits_allowed": 10.0,
            "sp_walks_allowed": 12.0}.get(stat_key, 10.0)
