"""live_v2_app.py — FastAPI WebSocket + REST bridge for Live Engine v2.

Single-process ASGI app:
  * starts the LiveOrchestrator on app startup (configurable game IDs)
  * subscribes to the event bus and broadcasts every event to all
    connected WebSocket clients
  * exposes REST endpoints for initial page load (no waiting for the
    next bus event before the dashboard has data)
  * runs the ExplanationEngine in-process and surfaces /api/explain
  * optional bearer-token auth via LIVE_V2_AUTH_TOKEN env var

Run locally:
    uvicorn api.live_v2_app:app --host 0.0.0.0 --port 8000

Required env:
    LIVE_V2_GAME_IDS=0042500315,0042500316    # comma-separated
    LIVE_V2_AUTH_TOKEN=<long-random-string>    # optional but recommended
    LIVE_V2_ALLOWED_ORIGINS=https://yourapp.vercel.app,http://localhost:3000
"""
from __future__ import annotations

import asyncio
import csv as _csv_mod
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from fastapi import (  # noqa: E402
    Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

from src.live.event_bus import (  # noqa: E402
    TOPIC_BET_RECOMMENDED, TOPIC_LINES_REFRESHED, TOPIC_PREGAME_INFO,
    TOPIC_PROJECTION_UPDATED, TOPIC_SNAPSHOT_UPDATED, get_bus,
)
from src.live.explanation_engine import ExplanationEngine  # noqa: E402
from src.live.pregame_ev_engine import (  # noqa: E402
    book_grid_for as _book_grid_for,
    rank_pregame_bets as _rank_pregame_bets,
    slate_date as _slate_date,
)

log = logging.getLogger("live_v2_app")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


# ── auth ───────────────────────────────────────────────────────────────
def _required_token() -> Optional[str]:
    return os.environ.get("LIVE_V2_AUTH_TOKEN") or None


def auth_dep(token: Optional[str] = Query(None)) -> None:
    """Bearer-style auth via ?token=... query arg (also used for WS handshake).

    If LIVE_V2_AUTH_TOKEN is unset, the API is open (local-dev mode).
    """
    required = _required_token()
    if required is None:
        return
    if not token or token != required:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="invalid or missing token")


def _ws_auth_ok(token: Optional[str]) -> bool:
    required = _required_token()
    if required is None:
        return True
    return bool(token) and token == required


# ── connection manager ────────────────────────────────────────────────
class WSConnectionManager:
    """Tracks live WebSocket clients and broadcasts JSON events to them."""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        log.info("WS connected; total=%d", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        log.info("WS disconnected; total=%d", len(self._clients))

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        # Snapshot the client list so a slow client can't block others.
        async with self._lock:
            clients = list(self._clients)
        dead: List[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception as exc:  # noqa: BLE001
                log.info("WS send failed (%s); closing", exc)
                dead.append(ws)
        if dead:
            async with self._lock:
                for d in dead:
                    self._clients.discard(d)

    def client_count(self) -> int:
        return len(self._clients)


# ── shadow CSV cache ──────────────────────────────────────────────────
# Maps csv_path → (mtime_float, list[dict]) to avoid re-reading files
# that haven't changed.  Refreshed only when mtime shifts.
_shadow_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def _read_shadow_bets_today() -> List[Dict[str, Any]]:
    """Return all 'blocked' shadow rows for today's slate date.

    Re-reads a CSV only when its mtime changed in the last 30 s window
    (cheap stat() call avoids unnecessary disk I/O on every API hit).
    """
    from src.live.time_utils import slate_date as _slate_date_fn
    date_str = _slate_date_fn().isoformat()
    shadow_dir = os.path.join(PROJECT_DIR, "data", "shadow")
    if not os.path.isdir(shadow_dir):
        return []

    rows: List[Dict[str, Any]] = []
    for fname in os.listdir(shadow_dir):
        if not fname.endswith(".csv"):
            continue
        # Match files whose name contains today's date (format: <gid>_<date>.csv)
        if date_str not in fname:
            continue
        path = os.path.join(shadow_dir, fname)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue

        cached = _shadow_cache.get(path)
        if cached is not None and cached[0] == mtime:
            rows.extend(cached[1])
            continue

        # Re-read the CSV.
        file_rows: List[Dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                reader = _csv_mod.DictReader(fh)
                for rec in reader:
                    if rec.get("gate_status", "").strip().lower() == "blocked":
                        try:
                            parsed: Dict[str, Any] = {
                                "ts": rec.get("ts", ""),
                                "game_id": rec.get("game_id", ""),
                                "player_id": rec.get("player_id", ""),
                                "name": rec.get("name", ""),
                                "team": rec.get("team", ""),
                                "stat": rec.get("stat", ""),
                                "side": rec.get("side", ""),
                                "line": float(rec.get("line") or 0),
                                "book": rec.get("book", ""),
                                "odds": int(float(rec.get("odds") or 0)),
                                "model_proj": float(rec.get("model_proj") or 0),
                                "current_stat": float(rec.get("current_stat") or 0),
                                "raw_ev": float(rec.get("raw_ev") or 0),
                                "kelly": float(rec.get("kelly") or 0),
                                "tier": rec.get("tier", ""),
                                "gate_blocked_by": rec.get("gate_blocked_by", ""),
                                "source": rec.get("source", ""),
                            }
                            file_rows.append(parsed)
                        except (TypeError, ValueError):
                            continue
        except OSError:
            continue
        _shadow_cache[path] = (mtime, file_rows)
        rows.extend(file_rows)

    return rows


# ── module-level state (initialised at startup) ──────────────────────
manager = WSConnectionManager()
explainer = ExplanationEngine()
# Per-game snapshot + projection caches so REST clients get an
# immediate state object without waiting for the next bus event.
_latest_snapshot: Dict[str, Dict[str, Any]] = {}
_latest_projections: Dict[str, List[Dict[str, Any]]] = {}
_recent_bets: List[Dict[str, Any]] = []
_recent_alerts: List[Dict[str, Any]] = []
_pregame_info: Dict[str, Dict[str, Any]] = {}
_orchestrator = None   # set in startup
_orchestrator_task: Optional[asyncio.Task] = None


# ── bus subscriber callbacks ─────────────────────────────────────────
async def _on_any_event(topic: str, event: Dict[str, Any]) -> None:
    # Slim down monster payloads (matchups, players list) before WS push.
    out_event = dict(event)
    if topic == TOPIC_SNAPSHOT_UPDATED:
        snap = event.get("snapshot") or {}
        gid = event.get("game_id") or snap.get("game_id")
        if gid:
            _latest_snapshot[gid] = snap
    if topic == TOPIC_PROJECTION_UPDATED:
        gid = event.get("game_id")
        rows = event.get("rows") or []
        if gid:
            # reactive_projector emits SINGLE-player updates (carrying
            # event.player_id) when a PBP event fires. Replacing the whole
            # cache with one player's rows would wipe out the other 29
            # players' projections, leaving the dashboard with one player
            # to show. Merge per-(player_id, stat) instead.
            if event.get("player_id") is not None:
                existing = list(_latest_projections.get(gid) or [])
                new_keys = {(str(r.get("player_id")), str(r.get("stat")))
                            for r in rows}
                merged = [r for r in existing
                          if (str(r.get("player_id")), str(r.get("stat")))
                          not in new_keys]
                merged.extend(rows)
                _latest_projections[gid] = merged
            else:
                _latest_projections[gid] = rows
    if topic == TOPIC_BET_RECOMMENDED:
        # Dedup by prop identity + sort by EV desc so /api/bets always shows
        # the strongest pick first. Without this, the pregame scan re-publishes
        # the same 12 bets every 60s and insert(0,...) lands the LAST-published
        # (lowest EV) at the top of the list.
        key = (event.get("player_id"), event.get("stat"),
               event.get("side"), event.get("line"), event.get("book"))
        _recent_bets[:] = [
            b for b in _recent_bets
            if (b.get("player_id"), b.get("stat"), b.get("side"),
                b.get("line"), b.get("book")) != key
        ]
        _recent_bets.append(event)
        _recent_bets.sort(key=lambda b: -float(b.get("ev") or 0.0))
        del _recent_bets[100:]
    if topic == TOPIC_PREGAME_INFO:
        gid = event.get("game_id")
        if gid:
            _pregame_info[gid] = event
    if topic.startswith("pbp."):
        try:
            ev_for_explainer = dict(event)
            ev_for_explainer["topic"] = topic
            ev_for_explainer["ts"] = time.time()
            explainer.ingest_pbp(ev_for_explainer)
        except Exception as exc:  # noqa: BLE001
            log.warning("explainer.ingest_pbp failed: %s", exc)
    if topic == TOPIC_LINES_REFRESHED:
        # Lines list lives on disk; the explainer is hydrated lazily via
        # /api/explain when a bet is inspected. The full sweep happens
        # in _hydrate_line_ticks_for_all_active_bets below.
        try:
            await _hydrate_line_ticks_for_all_active_bets()
        except Exception as exc:  # noqa: BLE001
            log.warning("hydrate line ticks failed: %s", exc)

    await manager.broadcast({"topic": topic, "event": out_event,
                             "ts": time.time()})


def _player_current_stat(snapshot: Dict[str, Any], player_id: Any,
                          player_name: str, stat: str) -> Optional[float]:
    """Look up a player's current in-game value for ``stat`` from a snapshot.
    Returns None if the snapshot doesn't have the player (game hasn't started,
    snapshot stale, or wrong game)."""
    if not snapshot:
        return None
    for p in snapshot.get("players") or []:
        same_id = (str(p.get("player_id")) == str(player_id)) if player_id else False
        same_name = ((p.get("name") or "").strip().lower()
                     == (player_name or "").strip().lower())
        if same_id or same_name:
            try:
                return float(p.get(stat) or 0)
            except (TypeError, ValueError):
                return None
    return None


def _enrich_and_filter_with_snapshot(bets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach the player's current in-game stat to each pregame bet, then drop
    bets that have effectively resolved already. Without this the dashboard
    keeps surfacing "SGA UNDER 29.5 +110" even though SGA already has 30 PTS
    in Q4 — the math says "+3% EV" but the bet is mathematically dead."""
    if not _latest_snapshot:
        return bets
    out: List[Dict[str, Any]] = []
    for b in bets:
        gid = b.get("game_id")
        snap = (_latest_snapshot.get(gid) if gid else None) \
            or next(iter(_latest_snapshot.values()), None)
        if not snap:
            out.append(b)
            continue
        stat = (b.get("stat") or "").lower()
        cur = _player_current_stat(snap, b.get("player_id"),
                                    b.get("name") or "", stat)
        if cur is None:
            out.append(b)
            continue
        line = float(b.get("line") or 0)
        side = (b.get("side") or "").lower()
        # OVER already cleared by current value → bet is decided (still worth
        # showing as "info" but no longer a live edge); UNDER blown out.
        if side == "over" and cur > line:
            log.debug("pregame bet decided OVER: %s %s cur=%.1f > line=%.1f",
                      b.get("name"), stat, cur, line)
            continue
        if side == "under" and cur > line:
            log.debug("pregame bet busted UNDER: %s %s cur=%.1f > line=%.1f",
                      b.get("name"), stat, cur, line)
            continue
        b["current"] = cur
        b["delta"] = round(cur - line, 1)
        out.append(b)
    return out


async def _refresh_pregame_bets(_topic: str, _event: Dict[str, Any]) -> None:
    """Recompute the pregame EV+ ranking + publish bet.recommended.

    Evicts the previous pregame snapshot before publishing so bets that
    dropped below the EV floor (line moved, soft book corrected) disappear
    from the dashboard instead of lingering forever. In-play bet recs
    from the decision engine (source != "pregame_ev") are preserved.
    """
    bus = get_bus()
    loop = asyncio.get_event_loop()
    try:
        bets = await loop.run_in_executor(None, _rank_pregame_bets)
    except Exception as exc:  # noqa: BLE001
        log.warning("pregame EV scan failed: %s", exc)
        return
    bets = _enrich_and_filter_with_snapshot(bets)
    log.info("pregame EV scan emitted %d bets", len(bets))
    _recent_bets[:] = [b for b in _recent_bets if b.get("source") != "pregame_ev"]
    for b in bets:
        try:
            await bus.publish(TOPIC_BET_RECOMMENDED, b)
        except Exception as exc:  # noqa: BLE001
            log.warning("publish pregame bet failed: %s", exc)


async def _run_pregame_ev_loop() -> None:
    """Re-run the pregame scan every 60 sec so soft-book line moves
    are reflected promptly. Cheap (pure CSV math, no API calls)."""
    # First run after a 2-sec grace period to let pregame_probe + pollers spin up.
    await asyncio.sleep(2)
    while True:
        await _refresh_pregame_bets("pregame.tick", {})
        await asyncio.sleep(60)


async def _hydrate_line_ticks_for_all_active_bets() -> None:
    """Feed the explainer with one tick per book per (player, stat).

    Reads from the same CSVs the decision engine uses — picks the most
    recent row per (book, player_id, stat) so the explainer can show
    drift on demand without a full re-read.
    """
    import csv as _csv
    date_str = _slate_date().isoformat()
    lines_dir = os.path.join(PROJECT_DIR, "data", "lines")
    if not os.path.isdir(lines_dir):
        return
    for fname in os.listdir(lines_dir):
        if not fname.startswith(date_str) or not fname.endswith(".csv"):
            continue
        path = os.path.join(lines_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for row in _csv.DictReader(fh):
                    try:
                        explainer.ingest_line_tick(
                            game_id=row.get("game_id") or "",
                            player_id=row.get("player_id"),
                            stat=row.get("stat") or "",
                            book=row.get("book") or "",
                            line=float(row.get("line") or 0.0),
                            over_price=int(row.get("over_price") or 0),
                            under_price=int(row.get("under_price") or 0),
                        )
                    except (TypeError, ValueError):
                        continue
        except OSError:
            continue


# ── app factory ───────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(title="Live Engine v2", version="2.0")

    origins_raw = os.environ.get("LIVE_V2_ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in origins_raw.split(",") if o.strip()] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        global _orchestrator, _orchestrator_task

        log.info("live_v2_app build_marker=shadow-endpoint-2026-05-27")
        # Subscribe to every event bus topic.
        bus = get_bus()
        bus.subscribe("*", _on_any_event)
        # Pregame EV scanner — fires on lines.refreshed AND on the first
        # startup tick so the dashboard hydrates with bets immediately.
        bus.subscribe(TOPIC_LINES_REFRESHED, _refresh_pregame_bets)
        asyncio.create_task(_run_pregame_ev_loop())

        # Maybe spawn the orchestrator.
        game_ids_raw = os.environ.get("LIVE_V2_GAME_IDS", "").strip()
        demo_mode = os.environ.get("LIVE_V2_DEMO_MODE", "0").lower() in (
            "1", "true", "yes", "on")
        if not game_ids_raw and not demo_mode:
            log.warning("LIVE_V2_GAME_IDS unset and LIVE_V2_DEMO_MODE off — "
                        "running in passive mode (WS only relays events "
                        "published by another process).")
            return

        # In demo mode we don't need a real game id, but the orchestrator
        # signature still requires the list. Use a sentinel.
        game_ids = ([g.strip() for g in game_ids_raw.split(",") if g.strip()]
                    or ["DEMO"])
        from scripts.live_orchestrator import LiveOrchestrator
        _orchestrator = LiveOrchestrator(
            game_ids=game_ids,
            pbp_interval_sec=float(os.environ.get("LIVE_V2_PBP_INTERVAL", 10)),
            snapshot_interval_sec=float(os.environ.get("LIVE_V2_SNAPSHOT_INTERVAL", 30)),
            lineup_interval_sec=float(os.environ.get("LIVE_V2_LINEUP_INTERVAL", 30)),
            line_scrape_interval_sec=float(os.environ.get("LIVE_V2_LINE_INTERVAL", 30)),
            enable_dashboard=False,
            enable_alerts=True,
            demo_mode=demo_mode,
        )
        await _orchestrator.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if _orchestrator is not None:
            try:
                await _orchestrator.stop()
            except Exception:  # noqa: BLE001
                pass

    # ── static dashboard (served at /) ───────────────────────────
    # Public — anyone with the URL gets the HTML; the API + WS
    # underneath still require ?token=... when LIVE_V2_AUTH_TOKEN set.
    @app.get("/")
    async def root_dashboard():
        path = os.path.join(STATIC_DIR, "dashboard.html")
        return FileResponse(path, media_type="text/html")

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ── REST endpoints ────────────────────────────────────────────
    @app.get("/api/health")
    async def health() -> Dict[str, Any]:
        return {
            "ok": True,
            "ws_clients": manager.client_count(),
            "active_games": list(_latest_snapshot.keys()),
            "recent_bets_count": len(_recent_bets),
            "orchestrator_started": _orchestrator is not None,
        }

    @app.get("/api/state")
    async def state(_: None = Depends(auth_dep)) -> Dict[str, Any]:
        """Single-shot snapshot for fresh page loads."""
        return {
            "snapshots": _latest_snapshot,
            "projections": _latest_projections,
            "recent_bets": _recent_bets[:20],
            "recent_alerts": _recent_alerts[:10],
            "pregame": _pregame_info,
            "ts": time.time(),
        }

    @app.get("/api/bets")
    async def bets(_: None = Depends(auth_dep),
                   limit: int = 20) -> Dict[str, Any]:
        return {"bets": _recent_bets[:limit]}

    @app.get("/api/shadow")
    async def shadow(_: None = Depends(auth_dep),
                     limit: int = 50) -> Dict[str, Any]:
        """Return today's blocked-but-logged shadow bets, sorted by raw_ev DESC.

        Shadow rows are written by the decision engine for every bet evaluation
        the gate chain or EV floor silently dropped.  This endpoint gives the
        dashboard (and operators) full visibility into *why* bets were blocked
        without changing the live-bet recommendation logic.
        """
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, _read_shadow_bets_today)
        rows.sort(key=lambda r: -float(r.get("raw_ev") or 0))
        return {"shadow_bets": rows[:limit]}

    @app.get("/api/book-grid")
    async def book_grid(player: str, stat: str, line: float,
                        _: None = Depends(auth_dep)) -> Dict[str, Any]:
        """Per-book side-by-side line+price comparison for one prop."""
        try:
            grid = _book_grid_for(player, stat, line)
        except Exception as exc:  # noqa: BLE001
            log.warning("book_grid failed: %s", exc)
            grid = []
        return {"player": player, "stat": stat, "line": line, "books": grid}

    @app.post("/api/explain")
    async def explain(payload: Dict[str, Any],
                      _: None = Depends(auth_dep)) -> Dict[str, Any]:
        """Build a structured explanation for one bet.

        Body shape::

            {
              "bet": { ... bet.recommended payload ... }
            }
        """
        bet = payload.get("bet") or {}
        gid = bet.get("game_id")
        pid = bet.get("player_id")
        stat = (bet.get("stat") or "").lower()
        snap = _latest_snapshot.get(gid) if gid else None
        row = None
        for r in (_latest_projections.get(gid) or []):
            try:
                if str(r.get("player_id")) == str(pid) and \
                   (r.get("stat") or "").lower() == stat:
                    row = r
                    break
            except Exception:  # noqa: BLE001
                continue
        return explainer.explain_bet(bet, snapshot=snap, projection_row=row)

    # ── WebSocket endpoint ────────────────────────────────────────
    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket, token: Optional[str] = Query(None)):
        if not _ws_auth_ok(token):
            await ws.close(code=4401)
            return
        await manager.connect(ws)
        # Push a hydration message so the new client doesn't wait for
        # the next bus event to populate its UI.
        try:
            await ws.send_json({
                "topic": "hello",
                "event": {
                    "snapshots": _latest_snapshot,
                    "projections": _latest_projections,
                    "recent_bets": _recent_bets[:20],
                    "recent_alerts": _recent_alerts[:10],
                    "pregame": _pregame_info,
                },
                "ts": time.time(),
            })
        except Exception:  # noqa: BLE001
            pass
        try:
            # Keep-alive loop — we don't expect client messages but we
            # need to drain the receive queue so disconnects surface.
            while True:
                msg = await ws.receive_text()
                # Optional client ping/pong for keep-alive.
                if msg.strip().lower() == "ping":
                    try:
                        await ws.send_json({"topic": "pong",
                                            "event": {}, "ts": time.time()})
                    except Exception:  # noqa: BLE001
                        break
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            log.info("WS loop ended: %s", exc)
        finally:
            await manager.disconnect(ws)

    return app


app = create_app()
