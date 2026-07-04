"""scripts.platformkit.bestbets.prop_cards_circuit_io -- circuit-breaker glue for
prop_cards.py (kept in its own module so prop_cards.py stays <=300 LOC).

Wires prop_circuit_breaker into the prop-line fetch path: filter dead providers
out BEFORE dispatch (apply_circuit_breaker), then feed the real _gather() outcome
back in (record_circuit_results). HONESTY: every skip is recorded in
_LAST_CIRCUIT_SKIPS (never silently dropped) and readable via last_circuit_skips()
for the board/snapshot metadata. Never raises; fails OPEN (unfiltered providers)
on any breaker error.

Stdlib + repo-internal only. ASCII-only. <=100 LOC.
Per-file test: scripts/platformkit/odds_provider/test_prop_circuit_breaker.py
covers the underlying breaker; this thin adapter has no independent behavior to
test beyond what prop_cards.py's own tests already exercise via _capped_lines.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Last-tick circuit-breaker skip metadata per sport (provider -> SKIPPED_CIRCUIT
# reason/since), for honest board/snapshot reporting. Never fabricated; empty
# until a provider actually trips the breaker. Module-level (single-threaded
# per-tick caller) -- read via last_circuit_skips().
_LAST_CIRCUIT_SKIPS: Dict[str, List[Dict[str, Any]]] = {}


def last_circuit_skips(sport: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Circuit-breaker SKIPPED_CIRCUIT entries recorded on the most recent
    apply_circuit_breaker() call, keyed by sport. Pass *sport* to get just that
    sport's list ({} / [] when nothing has ever been skipped). Never raises."""
    if sport is not None:
        return {sport: list(_LAST_CIRCUIT_SKIPS.get(sport, []))}
    return {k: list(v) for k, v in _LAST_CIRCUIT_SKIPS.items()}


def apply_circuit_breaker(sport: str, providers: List[Any]) -> List[Any]:
    """Filter dead providers out via the file-backed circuit breaker (m13-circuit:
    3 consecutive failures -> ~6h cooldown skip). Records skips into
    _LAST_CIRCUIT_SKIPS for honest reporting; never silently drops -- the skip is
    always visible via last_circuit_skips(). Never raises -> returns *providers*
    unfiltered on any breaker failure (fail open)."""
    try:
        from scripts.platformkit.odds_provider import prop_circuit_breaker as _pcb  # noqa: PLC0415
        kept, skipped = _pcb.filter_providers(providers)
        _LAST_CIRCUIT_SKIPS[sport] = skipped
        for s in skipped:
            logger.debug("prop_cards: %s circuit OPEN for %s (since=%s, reason=%s)",
                        sport, s.get("provider"), s.get("since"), s.get("last_reason"))
        return kept
    except Exception as exc:  # noqa: BLE001 -- breaker must never sink the fetch
        logger.debug("prop_cards: circuit breaker unavailable(%s): %s", sport, exc)
        return providers


def breaker_filtered_providers(sport: str) -> Optional[List[Any]]:
    """Circuit-BREAKER-GATED cfg.default_providers() for *sport*; None when sport
    config is unavailable. BYPASS FIX (m13-breaker-bypass): _board_edges' no-cache
    fallback used to call build_prop_board(sport) bare, which re-derives
    default_providers() UN-GATED -- re-dispatching to providers the breaker just
    opened. This is the ONE gated source for that fallback's providers. Never
    raises."""
    try:
        from scripts.platformkit import prop_edge_config  # noqa: PLC0415
        cfg = prop_edge_config.get_config(sport)
        if cfg is None:
            return None
        return apply_circuit_breaker(sport, cfg.default_providers())
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_cards: breaker_filtered_providers(%s) unavailable: %s",
                    sport, exc)
        return None


def record_circuit_results(sources: Dict[str, str]) -> None:
    """Feed each provider's _gather status string back into the circuit breaker
    (ok (N rows) -> success; timeout/error/unavailable -> failure). Never raises."""
    try:
        from scripts.platformkit.odds_provider import prop_circuit_breaker as _pcb  # noqa: PLC0415
        for name, status in (sources or {}).items():
            ok = str(status).startswith("ok")
            _pcb.record_result(name, ok, reason=("" if ok else str(status)))
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_cards: circuit breaker record failed: %s", exc)


def stamp_circuit_skips(cards: List[Dict[str, Any]], sport: str) -> None:
    """HONESTY (m13-circuit fix round): stamp this tick's SKIPPED_CIRCUIT entries
    for *sport* onto every card of that sport, in place (adds a `circuit_skips`
    key). This is the path a circuit skip actually reaches an on-disk artifact --
    props_pred_tick_runner writes build_bounded_prop_cards()'s card rows verbatim
    into props_snapshot.json's "rows", so a card-level field is the honest,
    minimally-invasive way to surface SKIPPED_CIRCUIT without editing the runner
    (out of this lane's OWNS). [] when nothing is skipped (never fabricated); the
    same list object is shared across cards (cheap, read-only downstream). Never
    raises."""
    try:
        skips = last_circuit_skips(sport).get(sport) or []
    except Exception:  # noqa: BLE001 -- stamping must never sink card output
        skips = []
    for card in cards:
        card["circuit_skips"] = skips


__all__ = ["last_circuit_skips", "apply_circuit_breaker", "breaker_filtered_providers",
           "record_circuit_results", "stamp_circuit_skips"]
