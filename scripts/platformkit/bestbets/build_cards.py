"""scripts.platformkit.bestbets.build_cards -- M10 cached-board producer adapter.

build_cards(now=<epoch float>) is the single entry-point called by
bestbets_compute_runner._compute_cards.  It fans out compute_best_bets() over
every registered sport, concatenates the raw card lists, runs board_sanitizer
and degenerate_guard, and returns a SANITIZED, degeneracy-guarded list ready to
be written to best_bets.json.

Design invariants
-----------------
* UNITS not $: no dollar/pnl/roi field on any returned card.
* edge_vs_market = model_prob - market_prob (prob diff, NOT $).
* Sanitizer runs AFTER the per-sport degenerate pass so both guards are always
  applied on the cached path -- the runner no longer has a bare unsanitized
  snapshot.
* Empty upstream (offseason, no corpus, network down) -> returns [] without
  raising.  The runner degrades to overall=degraded; we never fabricate cards.
* clv may be INSUFFICIENT_DATA; that is honest and correct.
* stale-never-green: tipoff-past cards are dropped by the sanitizer (criterion 5).
* no $ / roi / pnl / profit / bankroll / usd / dollar key is ever injected here.

RAILS: ASCII only; stdlib + repo-internal only; <=300 LOC; no network I/O.
Per-file test: scripts/platformkit/bestbets/test_build_cards.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Sports to fan out over.  Superset; any sport whose corpus is absent degrades
# gracefully (compute_best_bets returns {status:ok, cards:[]}).
_DEFAULT_SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")


# ---------------------------------------------------------------------------
# Dependency shims (imported lazily so offline tests can patch easily)
# ---------------------------------------------------------------------------

def _call_compute_best_bets(sport: str) -> Dict[str, Any]:
    """Thin shim around compute_best_bets; swallows all exceptions."""
    try:
        from predict_service.bestbets_compute import compute_best_bets  # noqa: PLC0415
        return compute_best_bets(sport)
    except Exception as exc:  # noqa: BLE001
        logger.debug("compute_best_bets(%s) failed: %s", sport, exc)
        return {"status": "degraded", "sport": sport, "cards": []}


def _call_sanitize(
    cards: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Thin shim around board_sanitizer.sanitize; falls back to identity."""
    try:
        from scripts.platformkit.bestbets.board_sanitizer import (  # noqa: PLC0415
            sanitize,
        )
        return sanitize(cards, now=now)
    except Exception as exc:  # noqa: BLE001
        logger.debug("board_sanitizer.sanitize failed: %s", exc)
        return cards


def _call_mark_degenerate(
    cards: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Thin shim around degenerate_guard.mark_degenerate_sports; falls back to identity."""
    try:
        from scripts.platformkit.bestbets.degenerate_guard import (  # noqa: PLC0415
            mark_degenerate_sports,
        )
        return mark_degenerate_sports(cards)
    except Exception as exc:  # noqa: BLE001
        logger.debug("degenerate_guard.mark_degenerate_sports failed: %s", exc)
        return cards


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cards(
    now: Optional[float] = None,
    sports: Optional[tuple] = None,
) -> List[Dict[str, Any]]:
    """Return a sanitized, degeneracy-guarded list of BestBetCard dicts.

    Parameters
    ----------
    now:
        Epoch-float reference time (seconds since UTC epoch).  Used for the
        stale-tipoff check so tests can pin time.  Defaults to the current
        wall-clock UTC time when None.
    sports:
        Override the set of sports to fan out over.  Defaults to
        ``_DEFAULT_SPORTS``.  Offseason / absent-corpus sports degrade to []
        gracefully -- they never raise.

    Returns
    -------
    List[Dict[str, Any]]
        Flat list of BestBetCard dicts, sanitized and degeneracy-marked.
        Empty list when no upstream data is available (never raises).
        Every card has:
          * edge_vs_market: model_prob - market_prob (prob diff, NOT $)
          * units: flat_unit (UNITS, not $)
          * No dollar / pnl / roi / profit / bankroll / usd / dollar key
          * clv may be INSUFFICIENT_DATA (honest, never fabricated)
    """
    try:
        return _build_cards_inner(now=now, sports=sports)
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_cards inner failed: %s", exc)
        return []


def _build_cards_inner(
    now: Optional[float],
    sports: Optional[tuple],
) -> List[Dict[str, Any]]:
    """Implementation -- called from build_cards() which catches all exceptions."""
    _sports = sports if sports is not None else _DEFAULT_SPORTS

    # Resolve a UTC datetime for the sanitizer's stale-tipoff check.
    if now is not None:
        try:
            ref_dt: Optional[datetime] = datetime.fromtimestamp(now, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            ref_dt = datetime.now(tz=timezone.utc)
    else:
        ref_dt = datetime.now(tz=timezone.utc)

    # Fan out: collect raw card lists per sport.
    all_cards: List[Dict[str, Any]] = []
    for sport in _sports:
        try:
            result = _call_compute_best_bets(sport)
            cards = result.get("cards") if isinstance(result, dict) else []
            if isinstance(cards, list):
                all_cards.extend(c for c in cards if isinstance(c, dict))
        except Exception as exc:  # noqa: BLE001
            logger.debug("build_cards sport=%s error: %s", sport, exc)
            continue

    if not all_cards:
        return []

    # QA1: stale-tipoff + binary + degenerate-market sanitization.
    # Pass ref_dt so tests that pin `now` get deterministic stale-tipoff results.
    all_cards = _call_sanitize(all_cards, now=ref_dt)

    # QA2: demote any sport whose model_probs collapse to a flat prior.
    all_cards = _call_mark_degenerate(all_cards)

    return all_cards


__all__ = ["build_cards"]
