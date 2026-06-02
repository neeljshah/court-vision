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
    Depends, FastAPI, HTTPException, Query, Request, WebSocket,
    WebSocketDisconnect, status,
)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

from src.live.event_bus import (  # noqa: E402
    TOPIC_BET_RECOMMENDED, TOPIC_LINES_REFRESHED, TOPIC_PREGAME_INFO,
    TOPIC_PROJECTION_UPDATED, TOPIC_SNAPSHOT_UPDATED, get_bus,
)
from scripts.task_supervisor import create_supervised_task  # noqa: E402
from scripts.freshness_watchdog import (  # noqa: E402
    run_freshness_watchdog, check_book_freshness,
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

# Strong references to background asyncio Tasks.
# asyncio.create_task / create_supervised_task returns a Task that the event loop
# holds only via a WEAK reference.  Without an explicit strong-ref container the
# GC can collect the Task object mid-run, silently killing background workers.
# NOTE: live_v2_app is NOT the currently served production app (api.main is);
# this is a hygiene fix for when it is activated.
_BG_TASKS: set = set()


# ── auth ───────────────────────────────────────────────────────────────
def _required_token() -> Optional[str]:
    return os.environ.get("LIVE_V2_AUTH_TOKEN") or None


def _cookie_valid(request: Request) -> bool:
    """Return True if the cv_session HttpOnly cookie carries the right value."""
    required = _required_token()
    if required is None:
        return True
    cookie_val = request.cookies.get("cv_session")
    return bool(cookie_val) and cookie_val == required


def auth_dep(request: Request, token: Optional[str] = Query(None)) -> None:
    """Auth via HttpOnly cookie (preferred) or ?token= query param (curl compat).

    Cookie is set by GET /auth/init so the browser never exposes the token in
    page source.  Existing curl-with-token flows still work via ?token=.
    If LIVE_V2_AUTH_TOKEN is unset, the API is open (local-dev mode).
    """
    required = _required_token()
    if required is None:
        return
    # Cookie-first: browser sends it automatically — token never in HTML/JS
    if _cookie_valid(request):
        return
    # Fallback: explicit ?token= for curl / server-to-server callers
    if token and token == required:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="invalid or missing token")


def _ws_auth_ok(token: Optional[str], conn=None) -> bool:
    """Authenticate a WebSocket or HTTP connection.

    `conn` may be a Request or WebSocket — both expose .cookies (HTTPConnection).
    """
    required = _required_token()
    if required is None:
        return True
    # Cookie path: browser sends cv_session cookie on the WS upgrade handshake
    if conn is not None:
        try:
            cookie_val = conn.cookies.get("cv_session")
            if cookie_val and cookie_val == required:
                return True
        except Exception:
            pass
    # Fallback: explicit ?token= query param (curl / server-to-server)
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

    # ── per-route timing middleware ───────────────────────────────────
    @app.middleware("http")
    async def _timing_middleware(request, call_next):
        t0 = time.time()
        response = await call_next(request)
        elapsed = time.time() - t0
        path = request.url.path
        log.info("[req] %s took %.2fs (status=%s)", path, elapsed, response.status_code)
        if elapsed > 1.0:
            log.warning("[SLOW] %s took %.2fs — investigate cache misses", path, elapsed)
        return response

    @app.on_event("startup")
    async def _startup() -> None:
        global _orchestrator, _orchestrator_task

        log.info("live_v2_app build_marker=scraper-probe-dk-direct-2026-05-27")
        # Subscribe to every event bus topic.
        bus = get_bus()
        bus.subscribe("*", _on_any_event)
        # Pregame EV scanner — fires on lines.refreshed AND on the first
        # startup tick so the dashboard hydrates with bets immediately.
        bus.subscribe(TOPIC_LINES_REFRESHED, _refresh_pregame_bets)
        _t = asyncio.create_task(_run_pregame_ev_loop())
        _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)

        # DK WebSocket prop subscriber (sub-second line-move latency).
        # Gate on DK_WS_ENABLED=1 so prod can disable without code changes.
        if os.environ.get("DK_WS_ENABLED", "").strip() in ("1", "true", "yes", "on"):
            try:
                from scripts.draftkings_ws import start_dk_ws
                _t = create_supervised_task("dk_ws", start_dk_ws)
                _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
                log.info("live_v2_app DK WS subscriber task started (supervised)")
            except Exception as _dk_exc:  # noqa: BLE001
                log.warning("live_v2_app DK WS import failed (non-fatal): %s", _dk_exc)

        # BetRivers KAMBI WebSocket prop subscriber (CometD/Bayeux push).
        # Gate on BR_WS_ENABLED=1 so prod can disable without code changes.
        if os.environ.get("BR_WS_ENABLED", "").strip() in ("1", "true", "yes", "on"):
            try:
                from scripts.betrivers_ws import start_br_ws
                _t = create_supervised_task("br_ws", start_br_ws)
                _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
                log.info("live_v2_app BR WS subscriber task started (supervised)")
            except Exception as _br_exc:  # noqa: BLE001
                log.warning("live_v2_app BR WS import failed (non-fatal): %s", _br_exc)

        # FD WebSocket prop subscriber (CometD/Bayeux; falls back to 30s HTTP poll).
        # Gate on FD_WS_ENABLED=1. From geo-restricted IPs uses poll fallback.
        if os.environ.get("FD_WS_ENABLED", "").strip() in ("1", "true", "yes", "on"):
            try:
                from scripts.fanduel_ws import start_fd_ws
                _t = create_supervised_task("fd_ws", start_fd_ws)
                _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
                log.info("live_v2_app FD WS subscriber task started (supervised)")
            except Exception as _fd_exc:  # noqa: BLE001
                log.warning("live_v2_app FD WS import failed (non-fatal): %s", _fd_exc)

        # Freshness watchdog — monitors all books for stale data and low volume.
        _t = create_supervised_task("freshness_watchdog", run_freshness_watchdog)
        _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)

        # Steam / sharp-move detector — emits sharp.steam / sharp.rlm events.
        # Gate on STEAM_DETECTOR_ENABLED (default on).
        if os.environ.get("STEAM_DETECTOR_ENABLED", "1").strip() in ("1", "true", "yes", "on"):
            try:
                from scripts.steam_detector import run_steam_detector  # noqa: PLC0415
                _t = create_supervised_task("steam_detector", run_steam_detector)
                _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
                log.info("live_v2_app steam_detector task started (supervised)")
            except Exception as _sd_exc:  # noqa: BLE001
                log.warning("live_v2_app steam_detector import failed (non-fatal): %s", _sd_exc)

        # Nightly CLV grader — fires at 06:00 UTC, loops every 24h.
        # Supervised so it auto-restarts on crash.  Gate on
        # NIGHTLY_GRADER_DISABLED=1 to disable without code changes.
        if os.environ.get("NIGHTLY_GRADER_DISABLED", "").strip() not in ("1", "true", "yes"):
            try:
                from scripts import nightly_grader as _ng  # noqa: PLC0415
                _t = create_supervised_task("nightly_grader", _ng.schedule_nightly)
                _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
                log.info("live_v2_app nightly_grader task scheduled (06:00 UTC daily)")
            except Exception as _ng_exc:  # noqa: BLE001
                log.warning("live_v2_app nightly_grader import failed (non-fatal): %s", _ng_exc)

        # Nightly NBA roster refresh — fires at 05:00 UTC, loops every 24h.
        # Keeps players_nba_active.json current so the WNBA filter in
        # _courtvision_odds picks up roster moves without a server restart.
        try:
            from scripts import refresh_nba_roster as _rnr  # noqa: PLC0415
            _t = create_supervised_task("roster_refresh", _rnr.schedule_nightly)
            _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
            log.info("live_v2_app roster_refresh task scheduled (05:00 UTC daily)")
        except Exception as _rnr_exc:  # noqa: BLE001
            log.warning("live_v2_app roster_refresh import failed (non-fatal): %s", _rnr_exc)

        # Spawn the orchestrator. LIVE_V2_GAME_IDS is honored when set, but
        # the default behavior is to AUTO-DISCOVER any NBA games happening
        # right now (in-progress OR scheduled within the next 12 hours) by
        # calling NBA's public scoreboard API. This makes the system "just
        # work" for any game any time — no env var, no restart required.
        game_ids_raw = os.environ.get("LIVE_V2_GAME_IDS", "").strip()
        demo_mode = os.environ.get("LIVE_V2_DEMO_MODE", "0").lower() in (
            "1", "true", "yes", "on")

        def _autodiscover_game_ids() -> list:
            try:
                import requests as _req  # noqa: PLC0415
                _r = _req.get(
                    "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json",
                    headers={"User-Agent": "Mozilla/5.0",
                             "Referer": "https://www.nba.com/"},
                    timeout=10)
                _sb = _r.json().get("scoreboard", {})
                _games = _sb.get("games", []) or []
                # Statuses we care about: 1=upcoming, 2=in-progress, 3=final
                # Watch in-progress + upcoming so we capture games before tipoff
                # and follow them through to the buzzer.
                return [g.get("gameId") for g in _games
                        if g.get("gameStatus") in (1, 2)
                        and g.get("gameId")]
            except Exception as _exc:
                log.warning("auto-discover NBA games failed: %s", _exc)
                return []

        if game_ids_raw:
            game_ids = [g.strip() for g in game_ids_raw.split(",") if g.strip()]
        else:
            game_ids = _autodiscover_game_ids()
            if not game_ids and not demo_mode:
                log.warning("No live or upcoming NBA games on today's scoreboard. "
                            "Orchestrator will run in passive mode until games "
                            "appear. Refresh every 5 min.")
                game_ids = []  # passive but watchful

        if not game_ids and not demo_mode:
            # Spawn a watcher task that re-checks every 5 min and starts the
            # orchestrator the moment a game appears.
            async def _watch_for_games():
                global _orchestrator
                while _orchestrator is None:
                    await asyncio.sleep(300)
                    ids = _autodiscover_game_ids()
                    if ids:
                        log.info("auto-discovered %d game(s): %s", len(ids), ids)
                        from scripts.live_orchestrator import LiveOrchestrator as _LO  # noqa: PLC0415
                        _orchestrator = _LO(
                            game_ids=ids,
                            pbp_interval_sec=float(os.environ.get("LIVE_V2_PBP_INTERVAL", 10)),
                            snapshot_interval_sec=float(os.environ.get("LIVE_V2_SNAPSHOT_INTERVAL", 30)),
                            lineup_interval_sec=float(os.environ.get("LIVE_V2_LINEUP_INTERVAL", 30)),
                            line_scrape_interval_sec=float(os.environ.get("LIVE_V2_LINE_INTERVAL", 30)),
                            enable_dashboard=False,
                            enable_alerts=True,
                            demo_mode=False,
                        )
                        await _orchestrator.start()
                        return
            _t = asyncio.create_task(_watch_for_games())
            _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
            log.info("No games yet; watcher task armed (re-checks every 5 min).")
            return

        # In demo mode we don't need a real game id, but the orchestrator
        # signature still requires the list. Use a sentinel.
        if not game_ids:
            game_ids = ["DEMO"]
        log.info("starting orchestrator on games: %s", game_ids)
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

    # ── static dashboard (served at /dashboard) ──────────────────
    # Moved from / to /dashboard so the CourtVision games hub (courtvision_router)
    # owns the root path as the casual-bettor landing page.
    @app.get("/dashboard")
    async def root_dashboard():
        path = os.path.join(STATIC_DIR, "dashboard.html")
        if not os.path.exists(path):
            from fastapi.responses import HTMLResponse as _HR
            return _HR("<h2>Live dashboard not built yet</h2>", status_code=200)
        return FileResponse(path, media_type="text/html")

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ── REST endpoints ────────────────────────────────────────────
    @app.get("/api/health")
    async def health() -> Dict[str, Any]:
        _ngrok_url_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "cache", "ngrok_url.txt"
        )
        try:
            with open(_ngrok_url_path, encoding="utf-8") as _f:
                _public_url: Any = _f.read().strip() or None
        except Exception:
            _public_url = None
        return {
            "ok": True,
            "ws_clients": manager.client_count(),
            "active_games": list(_latest_snapshot.keys()),
            "recent_bets_count": len(_recent_bets),
            "orchestrator_started": _orchestrator is not None,
            "public_url": _public_url,
        }

    @app.get("/api/health/books")
    async def health_books(_: None = Depends(auth_dep)) -> Dict[str, Any]:
        """Per-book staleness + volume health.

        Returns the last watchdog observation for every registered book.
        ``overall`` is "healthy" iff every book reports status "ok".
        Polled by the dashboard's live-status indicator.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, check_book_freshness)

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

    @app.get("/api/scraper-probe/{book}")
    async def scraper_probe(book: str,
                            _: None = Depends(auth_dep)) -> Dict[str, Any]:
        """Probe a sportsbook's candidate endpoints FROM the Railway prod IP.

        Dev machines get WAF-blocked by most US books, so probing locally
        wastes cycles. This endpoint runs the same curl_cffi chrome120 probe
        from Railway and reports which URLs respond — tells us which book to
        invest scraper LOC in next.
        """
        from api.scraper_probe import probe_book  # local import (lazy)
        try:
            return await probe_book(book)
        except Exception as exc:  # noqa: BLE001
            log.warning("scraper_probe failed for %s: %s", book, exc)
            return {"book": book, "error": str(exc)}

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

    # ── /auth/init — sets HttpOnly cookie so /odds never leaks token ──
    @app.get("/auth/init")
    async def auth_init(request: Request):
        """Issue an HttpOnly cv_session cookie.

        The browser calls this once on /odds page load (credentials:'include').
        After that the cookie rides every request automatically — the token is
        never visible to JS or in page source.
        """
        required = _required_token()
        resp = JSONResponse({"ok": True})
        if required:
            resp.set_cookie(
                key="cv_session",
                value=required,
                httponly=True,
                samesite="lax",
                secure=False,   # flip to True behind TLS (Railway/Vercel)
                max_age=86400,  # 24 h; re-issued on each /odds load
                path="/",
            )
        return resp

    # ── WebSocket endpoint ────────────────────────────────────────
    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket, token: Optional[str] = Query(None)):
        if not _ws_auth_ok(token, ws):
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

    try:
        from api.courtvision_router import router as _cv_router
        from api.courtvision_router import register_with_app as _cv_register
        app.include_router(_cv_router, tags=["courtvision"])
        _cv_register(app)
        log.info("courtvision_router included on live_v2_app")
    except Exception as _cv_exc:
        log.warning("courtvision_router unavailable on live_v2_app: %s", _cv_exc)

    try:
        from api._risk_router import router as _risk_router
        app.include_router(_risk_router, tags=["risk"])
        log.info("risk_router included on live_v2_app")
    except Exception as _risk_exc:
        log.warning("risk_router unavailable on live_v2_app: %s", _risk_exc)

    return app


app = create_app()
