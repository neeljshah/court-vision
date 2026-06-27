"""frontend.edge_routes -- FastAPI APIRouter for the deep Edge API endpoints.

Exposes the canonical lines-vs-predictions comparison assembled by
frontend.edge_api over the predict_service canonical store:

  GET /api/v1/edges/{sport}           -> build_edge_view(sport)
  GET /api/v1/edges/{sport}/{game_id} -> build_game_edge(sport, game_id)

Both are pure, O(1) store reads backed by edge_api (NEVER raises, NEVER
fabricates). The router adds HTTP caching via ETag/If-None-Match: cache_key(sport)
returns the snapshot's generated_at, so an unchanged snapshot yields a 304 on the
repeat request without re-assembling the full view.

ETag / 304 behaviour
---------------------
  1. GET /api/v1/edges/nba      -> 200, ETag: "<generated_at>", Last-Modified: <ts>
  2. Repeat with If-None-Match: "<generated_at>"  -> 304 (no body)
  3. Snapshot refreshed       -> new generated_at -> 200 again

Both headers are set on every 200; If-None-Match matching is exact-string
(including optional double-quotes that clients may wrap the value in).

HONESTY: no $ / dollar / roi / profit / pnl / stake / bankroll key anywhere;
edges are probability/EV; edge_claimed is always False; every number is real or
labelled unavailable. The assembler already enforces this; the router surfaces it.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Header, Request
    from fastapi.responses import JSONResponse, Response
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.edge_routes requires fastapi.") from exc

import frontend.edge_api as _edge_mod
from frontend.edge_api import build_edge_view, build_game_edge, cache_key

router = APIRouter()

# Prefix applied to every route in this module.
_PREFIX = "/api/v1/edges"


# -- caching helpers ----------------------------------------------------------

def _etag_str(generated_at: str) -> str:
    """Wrap generated_at in double-quotes -> valid ETag value per RFC 7232."""
    return '"%s"' % generated_at if generated_at else '""'


def _matches(client_etag: Optional[str], current_etag: str) -> bool:
    """True iff the client's If-None-Match header matches *current_etag*.

    Strips outer double-quotes from both sides so 'abc' and '"abc"' both match.
    """
    if not client_etag or not current_etag.strip('"'):
        return False
    client = client_etag.strip().strip('"')
    server = current_etag.strip().strip('"')
    return client == server


def _cache_headers(generated_at: str) -> dict:
    """Build ETag + Last-Modified header dict for a 200 response."""
    headers: dict = {}
    if generated_at:
        headers["ETag"] = _etag_str(generated_at)
        # Last-Modified = same timestamp (ISO-8601 is fine as advisory).
        headers["Last-Modified"] = str(generated_at)
    return headers


# -- endpoints ----------------------------------------------------------------

@router.get(_PREFIX + "/{sport}")
def edges_for_sport(
    sport: str,
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    store_dir: Optional[str] = None,  # tests inject via query; runtime unused
) -> Response:
    """All games for *sport* as the deep edge comparison view.

    Returns build_edge_view(sport) -- a full SnapshotEnvelope cross-joined with
    the per-book market lines and the per-(market_type, side) model-vs-market
    comparison. The response carries ETag / Last-Modified so a client with an
    up-to-date copy can 304.

    Status 200  - snapshot ok (games may be empty list when none scheduled).
    Status 200  - status='unavailable' in body (no snapshot file on disk).
    Status 304  - If-None-Match matched; body omitted.
    """
    store_out_dir: Any = store_dir  # None unless injected by tests
    gen_at = cache_key(sport, store_out_dir=store_out_dir)
    etag = _etag_str(gen_at)

    if gen_at and _matches(if_none_match, etag):
        return Response(status_code=304, headers=_cache_headers(gen_at))

    try:
        view = build_edge_view(sport, store_out_dir=store_out_dir)
    except Exception as exc:  # noqa: BLE001 -- should never happen (api is pure)
        logger.warning("edge_routes /edges/%s: build_edge_view raised: %s", sport, exc)
        view = {
            "sport": sport, "status": "unavailable",
            "reason": "assembly error (%s)" % type(exc).__name__,
            "count": 0, "games": [],
            "edge_claimed": False, "schema_version": "1.0.0",
            "honest_note": ("Calibrated decision-support only. No $ edge claimed."),
            "edge_note": "edge = model_prob - market_prob (probability space).",
        }

    headers = _cache_headers(str(view.get("generated_at", "") or ""))
    return JSONResponse(content=view, headers=headers)


@router.get(_PREFIX + "/{sport}/{game_id}")
def edge_for_game(
    sport: str,
    game_id: str,
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    store_dir: Optional[str] = None,
) -> Response:
    """Single-game deep edge object for (sport, game_id).

    Returns build_game_edge(sport, game_id) -- same per-game shape as games[]
    in the sport-level view, with the top-level honest_note/edge_note/
    edge_claimed/schema_version hoisted to the top level. Unknown game_id or
    missing snapshot -> status='unavailable' object (never raises, never 404).

    Status 200  - game found (status='ok') or not found (status='unavailable').
    Status 304  - If-None-Match matched on the sport-level generated_at.
    """
    store_out_dir: Any = store_dir
    gen_at = cache_key(sport, store_out_dir=store_out_dir)
    etag = _etag_str(gen_at)

    if gen_at and _matches(if_none_match, etag):
        return Response(status_code=304, headers=_cache_headers(gen_at))

    try:
        game = build_game_edge(sport, game_id, store_out_dir=store_out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("edge_routes /edges/%s/%s: build_game_edge raised: %s",
                       sport, game_id, exc)
        game = {
            "sport": sport, "game_id": game_id,
            "status": "unavailable",
            "reason": "assembly error (%s)" % type(exc).__name__,
            "edge_claimed": False, "schema_version": "1.0.0",
            "honest_note": ("Calibrated decision-support only. No $ edge claimed."),
        }

    headers = _cache_headers(str(game.get("generated_at", "") or ""))
    return JSONResponse(content=game, headers=headers)


__all__ = ["router"]
