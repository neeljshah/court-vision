"""predict_service.registry -- capability map over the existing predictor builders.

Data-driven registry: the KNOWN_SPORTS table drives active_sports(), capabilities(), and
build_predictor(). Every entry is declarative; no new modelling lives here.

The registry delegates to scripts.platformkit.predictor_jd._build_predictor (which is
already guarded / cached / degradation-safe). A sport whose corpus is absent on disk
(gitignored parquets, fresh clone) returns None from build_predictor() and is absent from
active_sports() -- no crash, no fabrication.

Public API
----------
active_sports() -> list[str]
    Sports whose predictor built successfully (at least one available). Includes only
    sports that pass the build check; an absent corpus drops the sport silently.

capabilities(sport: str) -> dict
    Keys: has_predictor (bool), markets (list[str]), produce (bool), note (str).
    Safe for any unknown sport: returns a zeroed-out dict, never raises.

build_predictor(sport: str) -> object | None
    Thin wrapper around predictor_jd._build_predictor -- guarded so any failure
    returns None, never raises. Passes through the cached result on repeated calls.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $ edge fabrication; reuse _build_predictor verbatim (never duplicate corpus logic).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Declarative sport table.
# markets: the market types the domain predictor exposes in its predict() output.
# produce: True when produce.py's produce_sport() supports this sport end-to-end
#          (odds aggregate + schedule + prediction chain all work for it).
# note: one-line honest framing (no $ edge, calibration only).
# ---------------------------------------------------------------------------
_KNOWN_SPORTS: Dict[str, Dict[str, Any]] = {
    "nba": {
        "markets": ["moneyline", "spread", "total"],
        "produce": True,
        "note": "MOV-aware Elo ML + possessions totals; matches devigged close; no $ edge.",
    },
    "mlb": {
        "markets": ["moneyline", "run_line", "total"],
        "produce": True,
        "note": "MOV-Elo ML + NegBinom O/U (fitted dispersion); calibration only; no $ edge.",
    },
    "soccer": {
        "markets": ["moneyline", "draw", "total", "btts", "asian_handicap"],
        "produce": True,
        "note": "Dixon-Coles 1X2 + full market catalog (DC/DNB/BTTS/AH/EH); no $ edge.",
    },
    "soccer_intl": {
        "markets": ["moneyline", "draw", "total", "btts", "asian_handicap"],
        "produce": True,
        "note": "World Cup bivariate-Poisson 1X2 + full surface (neutral venue); no $ edge.",
    },
    "tennis": {
        # ENGINE_COHERENCE_GAP closed: the SAME Monte Carlo finished-match matrix
        # (domains.tennis.markets.markets_for_matchup, read off predict()'s serve
        # holds) already prices this whole surface coherently -- expose all of it,
        # not just moneyline + total_games. NO new data, NO learned signal: pure
        # structural read-off, every cell coherent with predict(). Tie-break /
        # within-set games are HONESTLY out of reach (POINT_MODEL_GAPS) and stay
        # off the list -- we never advertise a market the engine cannot price.
        "markets": [
            "moneyline", "total_games", "total_sets", "set_handicap",
            "correct_set_score", "set_score_dist", "game_handicap",
            "per_set_winner", "first_set_winner",
        ],
        "produce": True,
        "note": "Serve-prob MC matrix -> full coherent tennis surface (sets/handicaps/"
                "set-score/per-set) off ONE predict() matrix; calibration, no $ edge.",
    },
}

# ---------------------------------------------------------------------------
# Internal helper -- thin delegate to the guarded, cached predictor factory.
# ---------------------------------------------------------------------------

def _try_build(sport: str) -> Optional[Any]:
    """Attempt to build the predictor for *sport* via predictor_jd._build_predictor.

    Returns None on any failure (missing corpus, import error, unknown sport).
    Never raises.
    """
    s = sport.lower()
    if s not in _KNOWN_SPORTS:
        return None
    try:
        from scripts.platformkit.predictor_jd import _build_predictor  # noqa: PLC0415
        return _build_predictor(s)
    except Exception:  # noqa: BLE001
        logger.debug("registry: predictor build failed for %s", s, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_predictor(sport: str) -> Optional[Any]:
    """Return the predictor object for *sport*, or None if unavailable.

    Wraps scripts.platformkit.predictor_jd._build_predictor with an extra
    guard: an unknown sport (not in _KNOWN_SPORTS) short-circuits to None
    immediately. All failures degrade to None; never raises.

    The underlying _build_predictor caches per sport so repeated calls are
    cheap (no corpus replay on second call).
    """
    return _try_build(sport)


def capabilities(sport: str) -> Dict[str, Any]:
    """Return a capability descriptor dict for *sport*.

    Keys:
      has_predictor (bool): True when build_predictor(sport) returns non-None.
      markets (list[str]): market types the domain predictor exposes (empty for
          unknown sports).
      produce (bool): True when produce_sport() supports this sport end-to-end.
      note (str): one-line honest framing (calibration only; no $ edge).

    Safe for any input: an unknown sport returns a zeroed-out dict, never raises.
    """
    s = sport.lower()
    spec = _KNOWN_SPORTS.get(s)
    if spec is None:
        return {
            "has_predictor": False,
            "markets": [],
            "produce": False,
            "note": "unknown sport",
        }
    pred = _try_build(s)
    return {
        "has_predictor": pred is not None,
        "markets": list(spec["markets"]),
        "produce": bool(spec["produce"]),
        "note": str(spec.get("note", "")),
    }


def active_sports() -> List[str]:
    """List sports whose predictor built successfully on this machine.

    Iterates _KNOWN_SPORTS in definition order; includes only sports where
    build_predictor() returns a non-None object (i.e. the corpus is present).
    A fresh clone (no data/) returns an empty list -- never crashes.
    """
    out: List[str] = []
    for sport in _KNOWN_SPORTS:
        if _try_build(sport) is not None:
            out.append(sport)
    return out


__all__ = [
    "active_sports",
    "capabilities",
    "build_predictor",
]
