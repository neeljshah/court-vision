"""predict_service.surface_uniformity_annotate -- surface-level MLB degenerate annotator.

BE-R5-2-predict-mlb-degenerate-annotate (iter1 P0 + iter2 P0):

The /api/predict/{sport} (build_surface) and /api/v1/edges/{sport} (build_edge_view)
faces were serving the flat MLB moneyline prior (0.5345 home / 0.4655 away, 1 unique
pair across all games) as individualised calibrated forecasts without any flag or note.

This module provides annotate_surface_games(), which runs the existing
mlb_prob_uniformity_guard.check_uniformity on the MLB moneyline probability slice
extracted from the surface games list.  When the guard returns FALLBACK_SUSPECTED
(i.e. the slice collapses to <= 2 unique prob values), every affected game record is
stamped:

    degenerate_model  -> True
    degenerate_note   -> DEGENERATE_NOTE  (ASCII, no $)
    tier              -> None  (remove/null -- not a calibrated divergence)

Records for non-MLB sports are NEVER touched.  A diverse (non-degenerate) MLB
surface is returned unchanged.  On any guard error the function degrades safely and
returns the games list unchanged.

RAILS:
  - Pure module: no IO, no network, no global mutable state.
  - Never raises; degrades to input-unchanged on any error.
  - Returns the same list; affected game dicts mutated in place.
  - ASCII only; <= 300 LOC.
  - No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# -- Constants -----------------------------------------------------------------

#: Written onto every relabelled game record as an honest disclosure.
DEGENERATE_NOTE: str = (
    "MLB moneyline model uniform -- base-rate only, not a per-game "
    "calibrated divergence"
)

#: Sport value that triggers this annotator.
_MLB_SPORT: str = "mlb"

#: Minimum distinct moneyline prob values a healthy MLB surface should show.
#: The canonical QA failure was 1 unique pair across 11 games.
_DISTINCT_PROB_FLOOR: int = 3

#: Moneyline label keys expected inside an estimate dict.
_MONEYLINE_LABELS = frozenset({"home_ml", "away_ml", "ml_home", "ml_away"})

#: market_type values treated as moneyline.
_MONEYLINE_MARKET_TYPES = frozenset({
    "moneyline", "ml", "game_result", "h2h",
})


# -- Internal helpers ----------------------------------------------------------

def _prob_from_estimate(est: Any) -> Optional[float]:
    """Return prob as a rounded float from an estimate dict, or None."""
    if not isinstance(est, dict):
        return None
    raw = est.get("prob")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val):
        return None
    return round(val, 6)


def _is_moneyline_estimate(est: Any) -> bool:
    """True when the estimate dict represents a moneyline market cell."""
    if not isinstance(est, dict):
        return False
    label = str(est.get("label", "")).lower()
    mt = str(est.get("market_type", "")).lower()
    return label in _MONEYLINE_LABELS or mt in _MONEYLINE_MARKET_TYPES


def _collect_mlb_ml_probs(games: List[Dict[str, Any]], sport: str) -> List[float]:
    """Extract all moneyline prob values from the games list for *sport*."""
    probs: List[float] = []
    if sport != _MLB_SPORT:
        return probs
    for game in games:
        if not isinstance(game, dict):
            continue
        for est in (game.get("estimates") or []):
            if _is_moneyline_estimate(est):
                p = _prob_from_estimate(est)
                if p is not None:
                    probs.append(p)
    return probs


def _build_guard_cards(probs: List[float]) -> List[Dict[str, Any]]:
    """Wrap prob values as minimal card dicts for check_uniformity."""
    return [{"model_prob": p} for p in probs]


def _run_guard(probs: List[float]) -> bool:
    """Return True when the uniformity guard flags the MLB ML slice as degenerate."""
    if not probs:
        return False
    # Two-value collapse check (catches the QA canonical 11-game / 2-value case
    # even when the guard threshold is not met by any single value alone).
    unique = set(probs)
    if len(probs) >= _DISTINCT_PROB_FLOOR and 0 < len(unique) <= 2:
        return True
    # Delegate to the existing guard for single-value collapse + threshold cases.
    try:
        from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (  # noqa: PLC0415
            check_uniformity,
        )
        result = check_uniformity(_build_guard_cards(probs))
        return bool(result.get("uniform"))
    except Exception:  # noqa: BLE001
        return False


def _stamp_game(game: Dict[str, Any]) -> None:
    """Mutate *game* in place: stamp degenerate flags and null tier."""
    game["degenerate_model"] = True
    game["degenerate_note"] = DEGENERATE_NOTE
    # Null out any tier value on the game record itself (surface records carry
    # no top-level tier, but stamp None defensively for edge-view consumers).
    if "tier" in game:
        game["tier"] = None
    # Also null tier on every moneyline estimate inside the game.
    for est in (game.get("estimates") or []):
        if isinstance(est, dict) and _is_moneyline_estimate(est):
            est["tier"] = None


# -- Public API ----------------------------------------------------------------

def annotate_surface_games(
    games: List[Dict[str, Any]],
    sport: str,
) -> List[Dict[str, Any]]:
    """Stamp degenerate_model=True on each MLB game when moneyline probs collapse.

    Inspects the moneyline probability slice of the *games* list (from
    build_surface).  When the uniformity guard detects a flat-prior collapse
    (i.e. the whole MLB moneyline surface shares <= 2 distinct probability values),
    every game record is stamped with degenerate_model=True, an honest note, and
    its tier is nulled.  Non-MLB sports are never touched.  A healthy, diverse MLB
    surface is returned unchanged.

    Parameters
    ----------
    games:
        The 'games' list from build_surface output (each dict has game_id, home,
        away, tipoff, estimates=[...]).  Dicts are mutated in place when degenerate.
    sport:
        The sport key (lower-cased by build_surface before reaching here).

    Returns
    -------
    List[Dict[str, Any]]
        The same *games* list (same object).  Never raises; returns *games*
        unchanged if an unexpected error occurs.
    """
    if not games:
        return games
    try:
        return _annotate_inner(games, sport)
    except Exception:  # noqa: BLE001
        logger.debug(
            "annotate_surface_games(%s): unexpected error; returning games unchanged",
            sport,
        )
        return games


def _annotate_inner(
    games: List[Dict[str, Any]],
    sport: str,
) -> List[Dict[str, Any]]:
    """Inner implementation; always called through annotate_surface_games."""
    if sport != _MLB_SPORT:
        return games  # fast-path: non-MLB sports never touched

    probs = _collect_mlb_ml_probs(games, sport)
    if not probs:
        return games  # no moneyline estimates -- nothing to check

    if not _run_guard(probs):
        return games  # diverse probs -- surface is healthy

    # Guard tripped: stamp every game record.
    for game in games:
        if isinstance(game, dict):
            _stamp_game(game)

    n_unique = len(set(probs))
    logger.warning(
        "annotate_surface_games: MLB moneyline surface (%d games, %d unique prob "
        "values) collapsed to flat prior; all game records stamped degenerate.",
        len(games),
        n_unique,
    )
    return games


__all__ = [
    "DEGENERATE_NOTE",
    "annotate_surface_games",
]
