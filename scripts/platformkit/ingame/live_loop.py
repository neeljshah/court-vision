"""scripts.platformkit.ingame.live_loop -- the always-on MULTI-SPORT in-game loop.

poll_once, per configured sport (DEFAULT_SPORTS = mlb/soccer/soccer_intl/nba/
tennis): fetch the live scoreboard -> ingest GameStates onto STATE_BUS (dedicated
ingest_router parser, else a generic ESPN-shape ingest via live_board) -> per LIVE
game, pull its pregame PRIOR and reprice it (repricer_router), or when a sport has
no freshness surface yet (e.g. MLB) carry the pregame prior forward HONESTLY
labelled -> write the snapshot. Then write one UNION heartbeat across all sports.
serve_forever drives this on a phase-aware cadence with an INJECTABLE clock.

HONEST + SAFE (binding): never raises on a feed error; per-game + per-sport error
isolation; an offseason / down-feed sport is an honest idle that never blocks the
live ones; no dollar edge; the only validated lever is FRESHNESS; no prediction
math here -- it ORCHESTRATES the existing ingest -> reprice -> snapshot pipeline.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame import ingest_router, market_set as ms
from scripts.platformkit.ingame import repricer_router as rr
from scripts.platformkit.ingame import snapshot as igsnap
from scripts.platformkit.ingame.state_bus import GameState, StateBus, STATE_BUS

logger = logging.getLogger(__name__)

# A payload fetcher: sport id -> the raw ESPN scoreboard dict (or {} on failure).
FetchFn = Callable[[str], Dict[str, Any]]

# Sports the loop polls each tick. A sport with a dedicated ingest_router parser
# uses it; any other falls back to a generic ESPN-shape ingest (live_board.
# _parse_event), so the loop COVERS every sport that can be live -- MLB (live
# mid-season), soccer (club + World Cup), NBA (offseason), tennis -- not just NBA.
DEFAULT_SPORTS: List[str] = ["mlb", "soccer", "soccer_intl", "nba", "tennis"]

# Phase-aware cadence (seconds): poll fast while games are live, slow when quiet.
LIVE_INTERVAL_SEC = 20.0
IDLE_INTERVAL_SEC = 120.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_fetch(sport: str) -> Dict[str, Any]:
    """Default prod fetch: live_board's keyless ESPN GET. {} on any error (the loop
    treats {} as "no live games", never raises)."""
    try:
        from scripts.platformkit.frontend import live_board as _lb
        site_path, _league = _lb._ESPN_ROUTES.get(_lb._norm_sport(sport), (None, None))
        if site_path is None:
            return {}
        return _lb._http_json(_lb._SITE_BASE.format(path=site_path))
    except Exception as exc:  # noqa: BLE001 - a feed error is never fatal
        logger.warning("live_loop fetch failed sport=%s: %s", sport, exc)
        return {}


_STATE_MAP = {"pre": "pre", "in": "live", "post": "final"}


def _generic_states(sport: str, payload: Dict[str, Any]) -> List[GameState]:
    """Sport-blind ESPN scoreboard -> [GameState] for sports without a dedicated
    ingest_router parser (mlb, soccer, soccer_intl, tennis). Reuses
    live_board._parse_event (the SINGLE ESPN-shape normalizer) so we never re-derive
    the shape; a malformed event is skipped. elapsed_min is carried only where a
    wall-clock minute exists (soccer) so clock-less sports (mlb innings) honestly get
    fraction_elapsed()=None and fall back to the carried pregame prior."""
    out: List[GameState] = []
    try:
        from scripts.platformkit.frontend import live_board as _lb
    except Exception as exc:  # noqa: BLE001 - no normalizer -> no generic states
        logger.warning("live_loop generic import failed sport=%s: %s", sport, exc)
        return out
    events = payload.get("events") if isinstance(payload, dict) else None
    for ev in events if isinstance(events, list) else []:
        if not isinstance(ev, dict):
            continue
        try:
            row = _lb._parse_event(ev, sport)
        except Exception as exc:  # noqa: BLE001 - one bad event never sinks ingest
            logger.warning("live_loop generic parse failed sport=%s: %s", sport, exc)
            row = None
        if not row:
            continue
        norm = row.get("sport") or sport
        extras: Dict[str, Any] = {
            "detail": row.get("detail"), "home_team": row.get("home"),
            "away_team": row.get("away"), "home_abbr": row.get("home_abbr"),
            "away_abbr": row.get("away_abbr")}
        if norm in ("soccer", "soccer_intl"):
            minute = _lb._soccer_minute(row.get("clock")) if row.get("clock") else None
            if minute is not None:
                extras["elapsed_min"] = float(minute)
        gid = ev.get("id") or "%s@%s" % (row.get("away_abbr") or row.get("away"),
                                         row.get("home_abbr") or row.get("home"))
        out.append(GameState(
            sport=norm, game_id=str(gid), period=row.get("period"), clock_sec=None,
            home_score=row.get("home_score") or 0,
            away_score=row.get("away_score") or 0, possession=None,
            status=_STATE_MAP.get(row.get("state") or "", "pre"), extras=extras))
    return out


def _ingest(sport: str, payload: Dict[str, Any], bus: StateBus) -> List[GameState]:
    """Ingest *payload* for *sport*: prefer the dedicated ingest_router parser, else
    fall back to the generic ESPN-shape ingest. Never raises; no events -> [] idle."""
    try:
        if ingest_router.get_parser(sport) is not None:
            return ingest_router.ingest(sport, payload, bus=bus)
    except Exception as exc:  # noqa: BLE001 - router error -> generic fallback
        logger.warning("live_loop router ingest error sport=%s: %s", sport, exc)
    states = _generic_states(sport, payload if isinstance(payload, dict) else {})
    for gs in states:
        bus.publish(gs)
    return states


def _pregame_prior(sport: str, game_state: GameState,
                   out_dir: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Pull this game's pregame PRIOR from predict_service. Returns {'p0': ...} or
    None when no usable prior exists (caller SKIPS cleanly -- never fabricates)."""
    try:
        from predict_service import store as ps_store
        env = ps_store.read_latest(sport, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001 - a store miss is just "no prior"
        logger.warning("live_loop prior read failed sport=%s: %s", sport, exc)
        return None
    if env is None or getattr(env, "status", "") != "ok":
        return None
    gid = str(game_state.game_id)
    for rec in getattr(env, "predictions", []) or []:
        if str(getattr(rec, "game_id", "")) != gid:
            continue
        probs = dict(getattr(rec, "pregame_probs", {}) or {})
        p_home = probs.get("home_ml")
        if p_home is None and probs.get("away_ml") is not None:
            p_home = 1.0 - float(probs["away_ml"])
        if p_home is None:
            return None
        return {"p0": float(p_home)}
    return None


def _game_meta(gs: GameState) -> Dict[str, Any]:
    """Light display metadata for the snapshot (team names/abbrs from extras)."""
    ex = gs.extras or {}
    meta: Dict[str, Any] = {k: ex[k] for k in
                            ("home_team", "away_team", "home_abbr", "away_abbr",
                             "detail") if ex.get(k) is not None}
    meta.update(period=gs.period, home_score=gs.home_score, away_score=gs.away_score)
    return meta


def poll_once(*, now: Optional[str] = None, fetch: Optional[FetchFn] = None,
              sports: Optional[List[str]] = None, bus: Optional[StateBus] = None,
              out_dir: Optional[Path] = None,
              store_out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Run ONE in-game tick across *sports*. Returns a heartbeat dict. Never raises.

    fetch (sport -> scoreboard payload) and sports (default DEFAULT_SPORTS) are
    injectable in tests; out_dir / store_out_dir override the snapshot + store dirs.

    Heartbeat (UNION across all polled sports): {'as_of', 'sports', 'n_live',
    'n_written', 'n_skipped', 'per_sport': {sport: {n_live,n_written,n_skipped}},
    'games'}. A sport with zero live games adds a clean {0,0,0} row, never blocking
    the sports that DO have live games.
    """
    as_of = now if isinstance(now, str) and now else _utc_iso()
    getter = fetch if fetch is not None else _default_fetch
    target_bus = bus if bus is not None else STATE_BUS
    sport_list = list(sports) if sports else list(DEFAULT_SPORTS)

    n_live = n_written = n_skipped = 0
    games_seen: List[Dict[str, Any]] = []
    per_sport: Dict[str, Dict[str, int]] = {}

    for sport in sport_list:
        s_live = s_written = s_skipped = 0
        try:
            payload = getter(sport)
        except Exception as exc:  # noqa: BLE001 - feed error never sinks the tick
            logger.warning("live_loop fetch error sport=%s: %s", sport, exc)
            payload = {}
        try:
            published = _ingest(sport, payload, target_bus)
        except Exception as exc:  # noqa: BLE001 - ingest guarded, defensive anyway
            logger.warning("live_loop ingest error sport=%s: %s", sport, exc)
            published = []
        for gs in published:
            if not isinstance(gs, GameState) or not gs.is_live():
                continue
            s_live += 1
            res = _process_game(sport, gs, out_dir=out_dir,
                                store_out_dir=store_out_dir, as_of=as_of)
            games_seen.append(res)
            s_written += 1 if res.get("written") else 0
            s_skipped += 0 if res.get("written") else 1
        # Honest per-sport idle row (0/0/0) even when this sport had no live games.
        per_sport[sport] = {"n_live": s_live, "n_written": s_written,
                            "n_skipped": s_skipped}
        n_live, n_written, n_skipped = (
            n_live + s_live, n_written + s_written, n_skipped + s_skipped)

    heartbeat = {
        "as_of": as_of, "sports": sport_list, "n_live": n_live,
        "n_written": n_written, "n_skipped": n_skipped,
        "per_sport": per_sport, "games": games_seen,
        "edge_claimed": False,
        "_honest_note": (
            "In-game loop heartbeat (UNION across all polled sports). Snapshots are "
            "calibrated freshness re-prices (or an honestly-labelled pregame-carry "
            "for sports without an in-game surface); no dollar edge. A down feed or "
            "offseason sport yields zero live games there, never blocking the rest."
        ),
    }
    _write_heartbeat(heartbeat, out_dir=out_dir)
    return heartbeat


def _process_game(sport: str, gs: GameState, *, out_dir: Optional[Path],
                  store_out_dir: Optional[Path], as_of: str) -> Dict[str, Any]:
    """Reprice + snapshot ONE live game. Per-game guarded: never raises. Returns a
    heartbeat status row. No prior -> SKIPPED (written=False, reason='no_prior')."""
    gid = str(gs.game_id)
    try:
        prior = _pregame_prior(sport, gs, store_out_dir)
        if prior is None:
            return {"game_id": gid, "sport": sport, "written": False,
                    "reason": "no_prior"}
        rp = rr.reprice(sport, gs, prior)
        if not rp.get("available"):
            # No freshness-blend surface for this sport yet (e.g. MLB is inning-
            # based with no clock). Rather than EXCLUDE the live game, carry the
            # calibrated PREGAME prior forward, honestly labelled, so the live card
            # updates with realized state + a 'pregame_carry' basis, not a corpse.
            rp = _pregame_carry(sport, prior, reason=str(rp.get("reason", "")))
        market = ms.build(gid, sport, rp, as_of=as_of, game_meta=_game_meta(gs))
        igsnap.write_live(gid, market, out_dir=out_dir)
        return {"game_id": gid, "sport": sport, "written": True,
                "available": bool(rp.get("available")),
                "basis": rp.get("basis"),
                "variance": market.get("variance")}
    except Exception as exc:  # noqa: BLE001 - one bad game never stops the others
        logger.warning("live_loop process error game=%s: %s", gid, exc)
        return {"game_id": gid, "sport": sport, "written": False,
                "reason": "error:%s" % type(exc).__name__}


def _pregame_carry(sport: str, prior: Dict[str, Any],
                   *, reason: str) -> Dict[str, Any]:
    """HONEST reprice-shaped dict carrying the pregame prior forward when *sport*
    has no freshness surface yet (e.g. MLB). NOT a fabricated edge: the win-prob is
    the UNCHANGED prior, variance None, basis='pregame_carry'. Realized score/period
    still rides along via game_meta."""
    try:
        p_home = float(prior.get("p0", prior.get("win_home")))
    except (TypeError, ValueError):
        p_home = None
    probs: Dict[str, float] = {}
    if p_home is not None:
        probs = {"p_home": p_home, "p_away": 1.0 - p_home, "p_live": p_home}
    return {
        "available": True, "sport": str(sport).lower(),
        "probs": probs, "markets": [], "variance": None,
        "remaining_frac": None, "basis": "pregame_carry",
        "edge_claimed": False,
        # UNMISTAKABLE carry markers: a consumer reading only top-level flags (NOT
        # the _honest_note) must be able to tell this is the UNCHANGED pregame prior
        # carried forward, NOT a fresh in-game reprice. reprice=False / is_carry=True
        # say so directly. status stays "live" downstream (the game IS live and the
        # webapp /live classifier keys on status=="live" -> LIVE), so these flags are
        # ADDITIVE and break no status-based filter.
        "reprice": False, "is_carry": True,
        "_honest_note": (
            "No in-game surface for this sport yet (%s); win-prob is the UNCHANGED "
            "calibrated PREGAME prior (no in-game conditioning, no dollar edge). "
            "Realized score/period shown live." % (reason or "no surface")),
    }


def _write_heartbeat(heartbeat: Dict[str, Any], *, out_dir: Optional[Path]) -> None:
    """Best-effort heartbeat write under data/frontend/ingame/_heartbeat.json."""
    try:
        base = Path(out_dir) if out_dir is not None else igsnap.DEFAULT_OUT_DIR
        base.mkdir(parents=True, exist_ok=True)
        igsnap._atomic_write(base / "_heartbeat.json", heartbeat)
    except Exception as exc:  # noqa: BLE001 - heartbeat is observability, not critical
        logger.warning("live_loop heartbeat write failed: %s", exc)


def serve_forever(interval: Optional[float] = None, *,
                  clock: Optional[Callable[[float], None]] = None,
                  max_ticks: Optional[int] = None,
                  fetch: Optional[FetchFn] = None,
                  sports: Optional[List[str]] = None,
                  bus: Optional[StateBus] = None,
                  out_dir: Optional[Path] = None,
                  store_out_dir: Optional[Path] = None) -> int:
    """Run the loop until *max_ticks* ticks (or forever if None). interval overrides
    the base sleep; when None the cadence is phase-aware (LIVE_INTERVAL_SEC when any
    sport is live, else IDLE_INTERVAL_SEC). clock is the injectable sleep (tests
    avoid real time.sleep). Returns ticks executed; never raises on a tick error."""
    sleep = clock if clock is not None else time.sleep
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        try:
            hb = poll_once(fetch=fetch, sports=sports, bus=bus,
                           out_dir=out_dir, store_out_dir=store_out_dir)
        except Exception as exc:  # noqa: BLE001 - a tick error never stops the loop
            logger.warning("live_loop tick error: %s", exc)
            hb = {"n_live": 0}
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        wait = float(interval) if interval is not None else (
            LIVE_INTERVAL_SEC if hb.get("n_live") else IDLE_INTERVAL_SEC)
        try:
            sleep(wait)
        except Exception as exc:  # noqa: BLE001 - a clock error never sinks the loop
            logger.warning("live_loop sleep error: %s", exc)
    return ticks


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint (`python -m ...ingame.live_loop`). Runs serve_forever with
    DEFAULT_SPORTS coverage; --sports (comma-separated) overrides the polled set for
    deterministic coverage. The heartbeat is written every tick (even on a quiet
    slate) so the supervisor's heartbeat readiness probe passes when nothing is live.
    """
    import argparse
    ap = argparse.ArgumentParser(prog="live_loop")
    ap.add_argument("--interval", type=float, default=None,
                    help="base poll interval seconds (default: phase-aware)")
    ap.add_argument("--sports", type=str, default=None,
                    help="comma-separated sports to poll (default: DEFAULT_SPORTS)")
    args = ap.parse_args(argv)
    sports = None
    if args.sports:
        sports = [s.strip().lower() for s in args.sports.split(",") if s.strip()]
    serve_forever(interval=args.interval, sports=sports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FetchFn", "DEFAULT_SPORTS", "LIVE_INTERVAL_SEC", "IDLE_INTERVAL_SEC",
    "poll_once", "serve_forever",
]
