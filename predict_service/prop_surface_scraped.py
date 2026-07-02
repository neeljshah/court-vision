"""predict_service.prop_surface_scraped -- bridge the REAL scraped-book prop edge
board (scripts.platformkit.prop_edge, sport-dispatched: mlb + soccer_intl) into
the /api/predict/props/{sport} PlayerPropRow envelope.

WHY: props_routes.get_props_for_sport only ever looked at market_type=='player_prop'
MarketRows embedded in predict_service's OWN game snapshot -- nothing writes those
for mlb/soccer_intl (that pipeline is NBA-domain-pricer-only). The REAL multi-book
scraped props (DraftKings/Underdog/PrizePicks/FanDuel, Poisson/NB priced, 1600+/500+
edges live) already exist one snapshot-read away at scripts.platformkit.frontend.
snapshot_writer's per-sport snapshot 'props' sub-key -- the SAME on-disk artifact
:8098's /api/props serves. This module reads that snapshot directly (read-only, no
network, no re-pricing) so predict_service's front-end-facing endpoint finally
carries real data for these sports. Live-diagnosed + built 2026-07-02.

HONESTY: p_over/p_under are probabilities from the domain Poisson/NB model, never a
$ figure. clv_is_proxy is always True (no true prop closing lines). No fabrication --
a missing/stale/empty snapshot degrades to UNAVAILABLE, never invented rows.

INVARIANTS: <=300 LOC; ASCII only; no src/ imports; read-only; no network I/O.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SNAPSHOT_TTL_SECONDS = 3600.0
_SUPPORTED_SPORTS = ("mlb", "soccer_intl")

_HONEST_NOTE = (
    "Calibrated P(over) from the sport's Poisson/NegBin prop model, priced against "
    "real scraped sportsbook/DFS lines (DraftKings/Underdog/PrizePicks/FanDuel). "
    "No $ edge is claimed. clv_is_proxy=True: no true prop closing-line capture yet "
    "for this sport."
)


def supported(sport: str) -> bool:
    """True iff *sport* has a real scraped-book prop board to bridge from."""
    return (sport or "").lower() in _SUPPORTED_SPORTS


def _is_stale(generated_at: Any, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(tz=timezone.utc)
    if not generated_at:
        return True
    try:
        dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() > _SNAPSHOT_TTL_SECONDS


def _row_from_edge(edge: Dict[str, Any], sport: str) -> Optional[Dict[str, Any]]:
    """Map one prop_edge.build_prop_board() edge into a PlayerPropRow. None on an
    unusable edge (never fabricates a missing field)."""
    player = edge.get("player")
    stat = edge.get("stat")
    line = edge.get("line")
    if not player or not stat or line is None:
        return None
    p_over = edge.get("model_p_over")
    p_under = (1.0 - p_over) if isinstance(p_over, (int, float)) else None
    return {
        "player": player,
        "stat": stat,
        "line": line,
        "book": edge.get("source") or "",
        "p_over": p_over,
        "p_under": p_under,
        "proj_mean": edge.get("model_lam"),
        "proj_sigma": None,
        "edge_vs_market": None,  # no devigged book price on the pick'em side; never fabricated
        "tier": edge.get("tier"),
        "confidence": edge.get("confidence"),
        "clv_is_proxy": True,
        "match": edge.get("match"),
        "team": edge.get("team"),
        "date": edge.get("as_of"),
        "sport": sport,
        "honest_note": _HONEST_NOTE,
    }


def read_scraped_snapshot(sport: str, *, now: Optional[datetime] = None,
                          out_dir: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Read the SAME on-disk props snapshot :8098's /api/props serves. Returns the
    envelope's 'props' sub-dict (with 'edges'), or None on any miss/stale/empty --
    NEVER live-computes (that duplicates network I/O the daemon already owns) and
    NEVER raises."""
    try:
        from scripts.platformkit.frontend import snapshot_writer  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_surface_scraped: snapshot_writer import failed: %s", exc)
        return None
    try:
        envelope = snapshot_writer.read_snapshot(sport, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_surface_scraped: read_snapshot(%s) failed: %s", sport, exc)
        return None
    if not isinstance(envelope, dict) or envelope.get("status") != "ok":
        return None
    if _is_stale(envelope.get("generated_at"), now=now):
        return None
    part = envelope.get("props")
    if not isinstance(part, dict) or not part.get("edges"):
        return None
    return part


def build_scraped_props_response(sport: str, *, now: Optional[datetime] = None,
                                 out_dir: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Full /api/predict/props/{sport} response body sourced from the REAL scraped
    prop board, or None when unsupported/unavailable (caller falls back to the
    domain-pricer UNAVAILABLE response, never a raise)."""
    if not supported(sport):
        return None
    snap = read_scraped_snapshot(sport, now=now, out_dir=out_dir)
    if snap is None:
        return None
    edges = snap.get("edges") or []
    rows: List[Dict[str, Any]] = []
    for e in edges:
        if isinstance(e, dict):
            row = _row_from_edge(e, sport)
            if row is not None:
                rows.append(row)
    if not rows:
        return None
    return {
        "status": "ok",
        "sport": sport,
        "date": snap.get("as_of"),
        "rows": rows,
        "count": len(rows),
        "edge_claimed": False,
        "clv_is_proxy": True,
        "source": "scraped_book_snapshot",
        "honest_note": _HONEST_NOTE,
    }


__all__ = ["supported", "read_scraped_snapshot", "build_scraped_props_response"]
