"""scripts.platformkit.frontend.serve -- always-on decision-support front end for a bettor.

A SMALL, self-contained FastAPI service (distinct from api/main.py AND frontend/app.py).
Serves a static polling UI and exposes /health, /api/slate + /api/live + /api/props
(honest boards from the REAL predictor, PREFERRING a precomputed snapshot), /api/game,
/api/intent (append a paper "I placed this" record to a local JSONL), and / (the UI).

HONEST + SAFE: every number comes from the real predictor or is marked unavailable. NO
sportsbook connection, NO auto-execution -- /api/intent only logs the human's stated
intent. Port 8098 (override FRONTEND_PORT); never collides with api/main.py (8077) or
frontend/app.py (8099). Run: python -m scripts.platformkit.frontend.serve

INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC; no secrets.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import HTMLResponse, JSONResponse
except Exception as exc:  # pragma: no cover - dependency guard
    raise ImportError("scripts.platformkit.frontend.serve requires fastapi "
                      "(pip install fastapi uvicorn).") from exc

from scripts.platformkit.frontend import slate as slate_mod
from scripts.platformkit.frontend import slate_dead_market_filter as _dead_filter
from scripts.platformkit.frontend import slate_recency_gate as _recency_gate

# All optional collaborators are GUARDED (try/except -> None): bet_board (per-game
# board), live_board (today's games + in-game preds), our keyless odds API + CLV
# ledger, the precomputed snapshots (fast path), and the prop-edge board (/api/props
# live-compute fallback). A refactor of any of these never sinks the server; missing
# pieces degrade to status='unavailable' / live compute (never fabricated).
try:
    from scripts.platformkit.frontend import bet_board as _bet_board
except Exception:  # pragma: no cover - optional
    _bet_board = None
try:
    from scripts.platformkit.frontend import live_board as _live_board
except Exception:  # pragma: no cover - optional
    _live_board = None
try:
    from scripts.platformkit.odds_provider.aggregate import to_odds_lookup as _to_odds_lookup
except Exception:  # pragma: no cover - provider optional
    _to_odds_lookup = None
try:
    from scripts.platformkit import clv_ledger as _clv
except Exception:  # pragma: no cover - ledger optional
    _clv = None
try:
    from scripts.platformkit.frontend import snapshot_writer as _snapshot_writer
except Exception:  # pragma: no cover - optional
    _snapshot_writer = None
try:
    from scripts.platformkit.prop_edge import build_prop_board as _build_prop_board
except Exception:  # pragma: no cover - optional
    _build_prop_board = None

try:  # predict_service.store: ONE canonical store; preferred over snapshot_writer
    from predict_service import store as _ps_store
except Exception:  # pragma: no cover - optional
    _ps_store = None

# M6 in-game spine snapshot reader (PREFERRED for /api/live when files exist).
# Guarded like every other optional collaborator: a missing or broken ingame
# snapshot is just a cache miss; /api/live falls back unchanged to live_board.
try:
    from scripts.platformkit.ingame import snapshot as _igsnap
except Exception:  # pragma: no cover - optional
    _igsnap = None

# Live odds on the board are ON by default; FRONTEND_LIVE_ODDS=0 disables (model-only).
_LIVE_ODDS = os.environ.get("FRONTEND_LIVE_ODDS", "1") != "0"

_HERE = Path(__file__).resolve().parent
_STATIC = _HERE / "static"
_INDEX = _STATIC / "index.html"

# Paper/intent log under the gitignored data/ tree -- the human's own record, never sent
# anywhere. Override with FRONTEND_INTENT_LOG.
DEFAULT_INTENT_LOG = (
    Path(os.environ.get("FRONTEND_INTENT_LOG", ""))
    if os.environ.get("FRONTEND_INTENT_LOG")
    else _HERE.parents[2] / "data" / "frontend" / "bet_intents.jsonl"
)

DEFAULT_PORT = int(os.environ.get("FRONTEND_PORT", "8098"))


def _index_html() -> str:
    if _INDEX.exists():
        return _INDEX.read_text(encoding="utf-8")
    return ("<!DOCTYPE html><html><body><h1>Bettor decision-support</h1><p>static/"
            "index.html missing; API still live at /api/slate.</p></body></html>")


def _game_unavailable(sport: str, home: str, away: str, note: str) -> Dict[str, Any]:
    """Uniform bet-board shape, status='unavailable' (never fabricated rows)."""
    return {"sport": sport, "home": home, "away": away, "status": "unavailable",
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "live": None, "best_bets": [], "groups": [], "honest_note": note}


def _odds_or_none(sport: str) -> Any:
    """Keyless multi-book odds for *sport*, or None (odds off / feed down). GUARDED."""
    if not _LIVE_ODDS or _to_odds_lookup is None:
        return None
    try:
        return _to_odds_lookup(sport)
    except Exception:  # noqa: BLE001
        return None


# STALE-NEVER-GREEN: the legacy data/frontend/snapshots/<sport>.json cache is
# written by snapshot_writer, which is NOT on the supervised daemon roster -- a
# stale file (yesterday's slate) must NOT serve as current. A snapshot older than
# this TTL is a CACHE MISS -> canonical predict_service store (m1_producer-refreshed
# + stale-purged) or fresh live compute.
_SNAPSHOT_TTL_SECONDS = 3600.0


def _snapshot_is_stale(generated_at: Any, now: Optional[datetime] = None) -> bool:
    """True when *generated_at* (ISO UTC) is older than the TTL, or absent/bad.

    A missing/unparseable timestamp is STALE -- never serve unproven-fresh data.
    """
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


def _read_snapshot_part(sport: str, key: str) -> Optional[Dict[str, Any]]:
    """Return the *key* ('slate'|'live'|'props'|...) sub-payload from *sport*'s
    snapshot, else None. Serves only a FRESH ok-envelope carrying a non-empty dict
    at *key*; anything else (incl. a stale snapshot past the TTL) -> None so the
    caller falls back to the canonical store / live compute (a cache miss must
    never dark-screen, a stale cache must never read green). NEVER raises."""
    if _snapshot_writer is None:
        return None
    try:
        envelope = _snapshot_writer.read_snapshot(sport)
    except Exception:  # noqa: BLE001 - a bad snapshot is just a cache miss
        return None
    if not isinstance(envelope, dict) or envelope.get("status") != "ok":
        return None
    if _snapshot_is_stale(envelope.get("generated_at")):
        return None  # stale-never-green: past TTL -> miss -> canonical/live fallback
    part = envelope.get(key)
    if not isinstance(part, dict) or not part:
        return None
    payload = dict(part)
    payload["freshness"] = {"as_of": envelope.get("generated_at"), "source": "snapshot"}
    payload["served_from"] = "snapshot"
    return payload


def _read_ps_store_slate(sport: str) -> Optional[Dict[str, Any]]:
    """Preferred slate: predict_service.store canonical envelope. None on any miss."""
    if _ps_store is None:
        return None
    try:
        env = _ps_store.read_latest(sport)
    except Exception:  # noqa: BLE001
        return None
    if env.status != "ok" or not env.predictions:
        return None
    if _snapshot_is_stale(env.generated_at):
        # golive_hardening_backlog_2026_07_17 finding #13: a stalled producer
        # (scheduler wedged, or repeated write failures) left this the ONLY
        # read path with no staleness guard -- _demote_if_all_past only fires
        # once games have started, not while a slate is still upcoming. Apply
        # the same TTL used by the legacy snapshot path so a stall degrades
        # to the live-compute/"unavailable" fallback instead of silently
        # serving an arbitrarily old envelope as status="ok".
        return None
    edgemap = {}
    for e in env.edges:
        edgemap.setdefault(e.game_id, []).append(e.to_dict())
    games = [{"game_id": p.game_id, "home": p.home, "away": p.away, "tipoff": p.tipoff,
              "pregame_probs": dict(p.pregame_probs), "note": p.note,
              "markets": [m.to_dict() for m in p.markets],
              "edges": edgemap.get(p.game_id, [])} for p in env.predictions]
    return {"sport": sport, "status": "ok", "games": games, "as_of": env.generated_at,
            "honest_note": env.honest_note,
            "freshness": {"as_of": env.generated_at, "source": "predict_service_store"},
            "served_from": "predict_service_store"}


def log_intent(record: Dict[str, Any], *, path: Optional[Path] = None) -> Dict[str, Any]:
    """Append a paper/intent record to the local JSONL; returns the stored record.
    Pure local I/O -- NO network, NO book API. Stamps server time + a hard flag that
    this is a non-binding intent log, never an executed bet."""
    target = Path(path) if path is not None else DEFAULT_INTENT_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    stored = dict(record)
    stored["logged_at"] = datetime.now(timezone.utc).isoformat()
    stored["executed"] = False  # invariant: this tool NEVER places a real bet
    stored["channel"] = "manual_human"  # the human places it on their own book
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(stored, default=str) + "\n")
    return stored


def create_app(*, intent_log: Optional[Path] = None) -> "FastAPI":
    """Build the FastAPI app. *intent_log* is injectable for tests."""
    app = FastAPI(title="Bettor decision-support (platformkit)",
                  description=slate_mod.HONEST_NOTE)
    log_path = Path(intent_log) if intent_log is not None else DEFAULT_INTENT_LOG

    @app.get("/health")
    def health() -> Dict[str, str]:  # noqa: ANN202
        return {"status": "ok"}

    @app.get("/api/sports")
    def sports() -> Dict[str, Any]:  # noqa: ANN202
        return {"sports": list(slate_mod.SPORTS), "honest_note": slate_mod.HONEST_NOTE}

    @app.get("/api/slate")
    def api_slate(sport: str = Query("nba")) -> JSONResponse:  # noqa: ANN202
        # Read precedence: predict_service.store (canonical) -> snapshot_writer
        # (legacy) -> live compute.  Each miss is a transparent fallthrough.
        # Each path is sanitized: dead-market filter first, then recency gate
        # (drops past-tipoff games; stale-never-green invariant).
        for payload in (_read_ps_store_slate(sport), _read_snapshot_part(sport, "slate")):
            if payload is not None:
                sanitized = _dead_filter.sanitize_slate(payload)
                return JSONResponse(_recency_gate.apply_recency_gate(sanitized))
        odds_lookup = _odds_or_none(sport)
        payload = (slate_mod.build_slate(sport, odds_lookup=odds_lookup)
                   if odds_lookup is not None else slate_mod.build_slate(sport))
        if isinstance(payload, dict):
            payload["served_from"] = "live_compute"
        sanitized = _dead_filter.sanitize_slate(payload)
        return JSONResponse(_recency_gate.apply_recency_gate(sanitized))

    @app.get("/api/live")
    def api_live(sport: str = Query("nba")) -> JSONResponse:  # noqa: ANN202
        """Today's real games + LIVE in-game predictions from ESPN's keyless scoreboard.
        Guarded -> status='unavailable' on a down feed/missing module (never fabricates
        a score). Never raises -- always 200.

        Read precedence:
          1. M6 ingame spine snapshot (data/frontend/ingame/<sport>/) -- PREFERRED.
             read_live_part returns a "live" block, or None on miss (cache miss).
          2. Legacy snapshot_writer live block (_read_snapshot_part).
          3. live_board.todays_live_games (keyless ESPN, live compute).
        Each miss is a transparent fallthrough; the ingame path is additive + guarded.
        """
        # M6 preferred: ingame spine snapshot (None -> transparent fall-through).
        if _igsnap is not None:
            try:
                ig_live = _igsnap.read_live_part(sport)
            except Exception:  # noqa: BLE001 - a corrupt snapshot is a cache miss
                ig_live = None
            if ig_live is not None:
                return JSONResponse(ig_live)

        # Legacy snapshot_writer live board.
        snap_live = _read_snapshot_part(sport, "live")
        if snap_live is not None:
            return JSONResponse(snap_live)
        if _live_board is None:
            return JSONResponse({"sport": sport, "status": "unavailable",
                                 "games": [], "note": "live_board module not importable",
                                 "served_from": "live_compute"})
        try:
            payload = _live_board.todays_live_games(sport)
        except Exception as exc:  # noqa: BLE001 - the live endpoint must never 500
            payload = {"sport": sport, "status": "unavailable", "games": [],
                       "note": f"live board error ({type(exc).__name__})"}
        if isinstance(payload, dict):
            payload["served_from"] = "live_compute"
        return JSONResponse(payload)

    @app.get("/api/props")
    def api_props(sport: str = Query("soccer_intl")) -> JSONResponse:  # noqa: ANN202
        """Ranked player-prop edge board (soccer_intl today). PREFERS the snapshot; a
        miss falls back to build_prop_board. Guarded -> 'unavailable' on error, never 500."""
        snap = _read_snapshot_part(sport, "props")
        if snap is not None:
            return JSONResponse(snap)
        if _build_prop_board is None:
            return JSONResponse({"sport": sport, "status": "unavailable",
                                 "edges": [], "served_from": "live_compute",
                                 "note": "prop_edge module not importable"})
        try:
            # m13-breaker-bypass (bare-caller close-out): route through the SAME
            # circuit-breaker-gated providers helper the wave-35 prop_cards.py fix
            # uses, never bare build_prop_board(sport) (which re-derives
            # cfg.default_providers() UN-GATED inside prop_edge.py). None/missing
            # helper -> explicit empty providers list, never an unfiltered fallback.
            from scripts.platformkit.bestbets import prop_cards_circuit_io as _pcio  # noqa: PLC0415
            provs = _pcio.breaker_filtered_providers(sport)
            payload = _build_prop_board(sport, providers=(provs if provs is not None else []))
        except Exception as exc:  # noqa: BLE001 - the props endpoint must never 500
            payload = {"sport": sport, "status": "unavailable", "edges": [],
                       "note": f"prop board error ({type(exc).__name__})"}
        if isinstance(payload, dict):
            payload["served_from"] = "live_compute"
        return JSONResponse(payload)

    @app.get("/api/game")
    def api_game(sport: str = Query("nba"), home: str = Query(...),
                 away: str = Query(...), live_state: Optional[str] = Query(None),
                 home_score: Optional[int] = Query(None),
                 away_score: Optional[int] = Query(None),
                 clock: Optional[str] = Query(None), elapsed: Optional[float] = Query(None),
                 inning: Optional[int] = Query(None), half: Optional[str] = Query(None),
                 sets_home: Optional[int] = Query(None),
                 sets_away: Optional[int] = Query(None),
                 games_home: Optional[int] = Query(None),
                 games_away: Optional[int] = Query(None),
                 surface: str = Query("Hard")) -> JSONResponse:  # noqa: ANN202
        """Per-game bet board (every market for ONE game): model view + best price +
        EV + ranked best bets. Guarded -> status='unavailable', NEVER 500. Live params
        opt the in-game block in + attach keyless multi-book odds for moneyline EV."""
        if _bet_board is None:
            return JSONResponse(_game_unavailable(sport, home, away,
                                "bet_board module not importable"))
        odds_lookup = _odds_or_none(sport)
        live = None
        if any(v is not None for v in (home_score, away_score, live_state, elapsed,
                                       inning, sets_home)):
            live = {"state": live_state or "live", "home_score": home_score,
                    "away_score": away_score, "clock": clock, "elapsed": elapsed,
                    "inning": inning, "half": half, "sets_home": sets_home,
                    "sets_away": sets_away, "games_home": games_home,
                    "games_away": games_away}
        try:
            payload = _bet_board.game_bet_board(sport, home, away,
                                                odds_lookup=odds_lookup, live=live,
                                                surface=surface)
        except Exception as exc:  # noqa: BLE001 - the board must never 500
            payload = _game_unavailable(sport, home, away,
                                        f"bet board error ({type(exc).__name__})")
        return JSONResponse(payload)

    @app.get("/api/clv")
    def api_clv() -> Dict[str, Any]:  # noqa: ANN202
        """Closing-line-value summary over the bet ledger -- the honest track record."""
        if _clv is None:
            return {"status": "unavailable", "reason": "clv_ledger not importable"}
        return _clv.clv_summary(_clv.load_ledger())

    @app.post("/api/clv/record")
    def api_clv_record(bet: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ANN202
        """Record a placed bet (taken price/book) for later CLV settlement. Paper only."""
        if _clv is None:
            return {"status": "unavailable", "reason": "clv_ledger not importable"}
        try:
            rec = _clv.record_bet(
                sport=bet.get("sport"), matchup=bet.get("matchup"),
                side=bet.get("side"), taken_book=bet.get("taken_book"),
                taken_decimal=float(bet.get("taken_decimal")),
                model_prob=bet.get("model_prob"), stake=float(bet.get("stake", 0.0)))
            return {"status": "recorded", "record": rec}
        except (ValueError, TypeError) as exc:
            return {"status": "error", "reason": str(exc)}

    @app.post("/api/intent")
    def api_intent(record: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ANN202
        stored = log_intent(record, path=log_path)
        return {"status": "logged", "record": stored, "note": ("Paper/intent log only"
                " -- no real bet was placed. Place it yourself on your own book.")}

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:  # noqa: ANN202
        return HTMLResponse(_index_html())

    return app


# Module-level app so `uvicorn scripts.platformkit.frontend.serve:app` works too.
app = create_app()


def main() -> int:
    try:
        import uvicorn  # noqa: PLC0415
    except Exception:  # pragma: no cover
        print("uvicorn not installed; pip install uvicorn to serve.")
        return 1
    host = os.environ.get("FRONTEND_HOST", "127.0.0.1")
    print(f"Serving bettor decision-support on http://{host}:{DEFAULT_PORT}/  (Ctrl-C to stop)")
    print("HONEST: " + slate_mod.HONEST_NOTE)
    uvicorn.run(app, host=host, port=DEFAULT_PORT, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
