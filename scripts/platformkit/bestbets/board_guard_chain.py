"""board_guard_chain.py -- ordered guard chain applied before best-bet cards are served.

QA P1 fix: wires the already-built guard modules into ONE ordered, pre-serve chain
so that Polymarket 'Yes vs No' binary cards, past-tipoff stale cards, dead/degenerate
market cards, and flat-prior sport model cards are ALL filtered or demoted before the
board reaches the UI.

Guard order
-----------
Step 1 -- DROP (board_sanitizer.sanitize):
    Removes cards that must NEVER reach the UI:
      * matchup contains 'yes vs no'          -- Polymarket binary (P1 QA bug)
      * market_prob < 0.02                     -- degenerate market
      * market_prob < 0.001                    -- dead/resolved binary contract
      * best_odds > 50.0                       -- extreme longshot
      * |edge_vs_market| > 0.30               -- corrupt data / stale gap
      * tipoff_utc at-or-before now            -- past-tipoff stale event (stale-never-green)

    NOTE: board_sanitizer.sanitize is a strict superset of
    predict_service.frontend.bestbets_board_filter.filter_cards; the sanitizer
    is used here as the single authoritative drop gate.

Step 2 -- DEMOTE degenerate sports (degenerate_guard.mark_degenerate_sports):
    Stamps edge_claimed=False / tier='C' / degenerate_model=True onto every card
    from a sport whose model has collapsed to <=2 distinct model_prob values over
    >= MIN_CARDS games (flat-prior / model-unavailable signal).

Step 3 -- DEMOTE uniform-fallback sports (uniformity_enforce.enforce_uniformity):
    Stamps the same demotion fields onto every card from a sport whose model_prob
    distribution triggers the constant-fallback uniformity guard.

Both demote steps are idempotent when both fire on the same sport.

Public API
----------
apply_guard_chain(cards, now=None) -> List[Dict[str, Any]]
    Pure function: never mutates the input list or input card dicts.
    Returns a new list of new card-dict copies with all guards applied.
    Never raises.
    Empty input -> empty output.

RAILS:
  - ASCII only; <= 300 LOC.
  - No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  - Pure (new list, new dict copies); input is never mutated.
  - Never raises from the public surface.
  - stale-never-green: past-tipoff cards are dropped, not demoted.
  - Per-file test: python -m pytest scripts/platformkit/bestbets/test_board_guard_chain.py -q
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guard imports -- all degrade gracefully on ImportError so tests can run
# without the full platformkit stack.
# ---------------------------------------------------------------------------

def _sanitize(cards: List[Dict[str, Any]], now: Optional[datetime]) -> List[Dict[str, Any]]:
    """Step 1: drop degenerate / binary / stale cards via board_sanitizer.sanitize."""
    try:
        from scripts.platformkit.bestbets.board_sanitizer import sanitize  # noqa: PLC0415
        return sanitize(cards, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("board_guard_chain: board_sanitizer unavailable (%s); skip drop step", exc)
        return list(cards)


def _mark_degenerate(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Step 2: demote flat-prior sports via degenerate_guard.mark_degenerate_sports."""
    try:
        from scripts.platformkit.bestbets.degenerate_guard import (  # noqa: PLC0415
            mark_degenerate_sports,
        )
        return mark_degenerate_sports(cards)
    except Exception as exc:  # noqa: BLE001
        logger.debug("board_guard_chain: degenerate_guard unavailable (%s); skip", exc)
        return cards


def _enforce_uniform(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Step 3: demote constant-fallback sports via uniformity_enforce.enforce_uniformity."""
    try:
        from scripts.platformkit.bestbets.uniformity_enforce import (  # noqa: PLC0415
            enforce_uniformity,
        )
        return enforce_uniformity(cards)
    except Exception as exc:  # noqa: BLE001
        logger.debug("board_guard_chain: uniformity_enforce unavailable (%s); skip", exc)
        return cards


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_guard_chain(
    cards: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Apply the ordered guard chain and return a filtered/demoted card list.

    This is the single pre-serve gate that callers (board routes, snap runners)
    invoke before sending cards to the UI or caching them.

    Parameters
    ----------
    cards:
        List of BestBetCard dicts as produced by bestbets_compute.
        The input list and all input card dicts are NEVER mutated.
    now:
        Optional UTC reference datetime for the stale-tipoff check.
        Defaults to datetime.now(timezone.utc) inside board_sanitizer.

    Returns
    -------
    List[Dict[str, Any]]
        New list of new card-dict copies (deep-copied from survivors) with:
          * Polymarket 'Yes vs No' cards removed.
          * market_prob < 0.02 / dead-market cards removed.
          * Past-tipoff stale cards removed.
          * Flat-prior / uniform-fallback sport cards demoted (not removed).
        Never raises; returns [] on any unexpected error.

    Guard order
    -----------
    1. board_sanitizer.sanitize     -- DROP degenerate / binary / stale cards
    2. degenerate_guard             -- DEMOTE flat-prior sports
    3. uniformity_enforce           -- DEMOTE constant-fallback sports
    """
    if not cards:
        return []
    try:
        return _apply_inner(cards, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.warning("board_guard_chain.apply_guard_chain: unexpected error (%s); returning []", exc)
        return []


def _apply_inner(
    cards: List[Dict[str, Any]],
    now: Optional[datetime],
) -> List[Dict[str, Any]]:
    """Inner implementation; always called through apply_guard_chain()."""
    # Deep-copy the input so all downstream mutations are on our copies.
    working: List[Dict[str, Any]] = [copy.deepcopy(c) for c in cards if isinstance(c, dict)]

    # Step 1: DROP
    working = _sanitize(working, now=now)

    # Step 2: DEMOTE degenerate sports (mutates working copies in-place)
    working = _mark_degenerate(working)

    # Step 3: DEMOTE uniform-fallback sports (mutates working copies in-place)
    working = _enforce_uniform(working)

    return working


# ---------------------------------------------------------------------------
# Chain metadata (useful for logging / introspection)
# ---------------------------------------------------------------------------

CHAIN_STEPS: tuple = (
    "board_sanitizer.sanitize",
    "degenerate_guard.mark_degenerate_sports",
    "uniformity_enforce.enforce_uniformity",
)

__all__ = [
    "apply_guard_chain",
    "CHAIN_STEPS",
]
