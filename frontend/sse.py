"""frontend.sse -- Server-Sent Events stream endpoints for the predict-service.

Payloads are BYTE-IDENTICAL to the corresponding REST bodies -- no new data,
no new claims, no fabricated fields.  Every event is the same dict that the
matching REST endpoint would return; the stream is just a periodic re-delivery
of that same honest snapshot.

Endpoints
---------
GET /api/stream/game/{sport}/{game_id}
    text/event-stream.  Emits the current build_report(sport, game_id) dict as
    one SSE 'data:' JSON frame every SSE_INTERVAL_SEC seconds (default 5).
    An initial event is sent immediately (no first-tick delay).
    A per-tick build_report failure emits {"status": "unavailable", ...} rather
    than killing the stream.

GET /api/stream/paper
    text/event-stream.  Emits the current paper trail + CLV summary on the same
    interval.  Payload == the REST /api/paper/trail body merged with the CLV
    summary block (byte-identical to what the two REST endpoints would return).

Both streams emit a heartbeat comment (': heartbeat') every SSE_HEARTBEAT_SEC
seconds (default 15) to keep proxies from closing idle connections.

Environment variables
---------------------
SSE_INTERVAL_SEC     -- tick interval in seconds (float, default 5).
SSE_MAX_DURATION_SEC -- stream closes after this many seconds (float, default
                        3600 = 1 hour).  0 means unlimited.
SSE_HEARTBEAT_SEC    -- how often to emit a heartbeat comment (float, default 15).
PREDICT_SERVICE_STORE_DIR -- forwarded to build_report (same as rest of the API).

HONESTY: payloads are identical to REST; no $-edge / roi / profit key is added;
no new claim is made.  All sentinel / unavailable paths are preserved verbatim.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter
    from fastapi.responses import StreamingResponse
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "frontend.sse requires fastapi (pip install fastapi)."
    ) from exc

router = APIRouter()

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _interval() -> float:
    return max(1.0, _float_env("SSE_INTERVAL_SEC", 5.0))


def _max_duration() -> float:
    return _float_env("SSE_MAX_DURATION_SEC", 3600.0)


def _heartbeat_sec() -> float:
    return max(1.0, _float_env("SSE_HEARTBEAT_SEC", 15.0))


def _store_out_dir() -> Optional[str]:
    val = os.environ.get("PREDICT_SERVICE_STORE_DIR")
    return val or None


# ---------------------------------------------------------------------------
# SSE frame helpers
# ---------------------------------------------------------------------------

def _data_frame(payload: Dict[str, Any]) -> str:
    """Encode a dict as a single 'data: <json>\n\n' SSE frame (ASCII)."""
    return "data: %s\n\n" % json.dumps(payload, ensure_ascii=True)


_HEARTBEAT_FRAME = ": heartbeat\n\n"


# ---------------------------------------------------------------------------
# Per-tick payload builders (guarded; never raise)
# ---------------------------------------------------------------------------

def _report_payload(sport: str, game_id: str) -> Dict[str, Any]:
    """Return build_report(sport, game_id) or an unavailable sentinel on error."""
    try:
        from frontend.report import build_report  # noqa: PLC0415
        return build_report(sport, game_id, store_out_dir=_store_out_dir())
    except Exception as exc:  # noqa: BLE001
        logger.warning("sse: build_report(%s, %s) failed: %s", sport, game_id, exc)
        return {
            "status": "unavailable",
            "sport": str(sport),
            "game_id": str(game_id),
            "reason": "build_report error (%s)" % type(exc).__name__,
        }


def _paper_payload(ledger_path: Optional[str] = None) -> Dict[str, Any]:
    """Return the paper trail + CLV summary merged dict, or unavailable on error."""
    try:
        from pathlib import Path  # noqa: PLC0415
        from frontend.paper_trail import read_trail, clv_summary  # noqa: PLC0415
        lp = Path(ledger_path) if ledger_path else None
        trail = read_trail(ledger_path=lp)
        summary = clv_summary(ledger_path=lp)
        _HONEST_NOTE = (
            "Paper-only. executed is always False. "
            "Edges are EV/CLV (probability-space); no $ edge is claimed. "
            "CLV = better-number-than-close (positive = good). "
            "Proxy closes are labelled clv_is_proxy=true."
        )
        return {
            "status": "ok",
            "count": len(trail),
            "trail": trail,
            "honest_note": _HONEST_NOTE,
            "clv": summary,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("sse: paper_payload failed: %s", exc)
        return {
            "status": "unavailable",
            "reason": "paper trail error (%s)" % type(exc).__name__,
            "trail": [],
            "count": 0,
        }


# ---------------------------------------------------------------------------
# Async generator core
# ---------------------------------------------------------------------------

async def _sse_stream(
    first_payload: Dict[str, Any],
    payload_fn: Any,
) -> AsyncGenerator[str, None]:
    """Core SSE generator: emit initial event, then tick until max_duration."""
    interval = _interval()
    max_dur = _max_duration()
    hb_sec = _heartbeat_sec()
    started = time.monotonic()
    last_hb = started

    # -- initial event (sent immediately) ------------------------------------
    yield _data_frame(first_payload)

    # -- periodic ticks ------------------------------------------------------
    while True:
        now = time.monotonic()
        elapsed = now - started

        # Check max_duration (0 = unlimited).
        if max_dur > 0 and elapsed >= max_dur:
            break

        # Sleep until next tick, yielding heartbeats at hb_sec sub-intervals.
        next_tick = started + interval * (int(elapsed / interval) + 1)
        while True:
            now = time.monotonic()
            if now >= next_tick:
                break
            # Heartbeat if overdue.
            if now - last_hb >= hb_sec:
                yield _HEARTBEAT_FRAME
                last_hb = now
            remaining = min(next_tick - now, hb_sec - (now - last_hb))
            await asyncio.sleep(max(0.05, remaining))

        # Emit heartbeat if overdue after sleep.
        now = time.monotonic()
        if now - last_hb >= hb_sec:
            yield _HEARTBEAT_FRAME
            last_hb = now

        # Fetch and emit payload.
        try:
            payload = payload_fn()
        except Exception as exc:  # noqa: BLE001
            payload = {
                "status": "unavailable",
                "reason": "tick error (%s)" % type(exc).__name__,
            }
        yield _data_frame(payload)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/stream/game/{sport}/{game_id}")
async def stream_game(sport: str, game_id: str) -> StreamingResponse:
    """SSE stream: periodic build_report(sport, game_id) events.

    Payload is byte-identical to GET /api/report/{sport}/{game_id} body.
    Emits immediately then every SSE_INTERVAL_SEC seconds.
    Build errors emit {"status": "unavailable", ...} -- never a 500.
    """
    sport = str(sport)
    game_id = str(game_id)
    first = _report_payload(sport, game_id)

    def _tick() -> Dict[str, Any]:
        return _report_payload(sport, game_id)

    return StreamingResponse(
        _sse_stream(first, _tick),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/stream/paper")
async def stream_paper(
    ledger: Optional[str] = None,
) -> StreamingResponse:
    """SSE stream: periodic paper trail + CLV summary events.

    Payload merges the /api/paper/trail body with a 'clv' key holding the
    /api/paper/clv summary -- both REST bodies, no new data, no new claims.
    Emits immediately then every SSE_INTERVAL_SEC seconds.
    """
    first = _paper_payload(ledger)

    def _tick() -> Dict[str, Any]:
        return _paper_payload(ledger)

    return StreamingResponse(
        _sse_stream(first, _tick),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
