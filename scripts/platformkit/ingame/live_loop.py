"""scripts.platformkit.ingame.live_loop -- the always-on in-game spine loop.

One tick of the loop (poll_once):
  1. For each configured sport, fetch the live scoreboard payload (INJECTED in
     tests; defaults to live_board's keyless ESPN GET in production).
  2. ingest_router.ingest -> GameStates onto the process-wide STATE_BUS.
  3. For each LIVE game, pull that game's pregame PRIOR from the canonical
     predict_service store (read_latest), reprice it (repricer_router.reprice),
     build the per-game market_set (market_set.build), and write the live
     snapshot atomically (snapshot.write_live).
  4. Write a heartbeat envelope so an operator / the frontend can see liveness.

serve_forever(interval, *, clock=None, max_ticks=None):
  The daemon entrypoint. Drives poll_once on a cadence with an INJECTABLE clock
  (no real sleep in the tested path) and phase-aware cadence (poll faster when
  there are live games, slow when the slate is quiet). max_ticks bounds the loop
  in tests.

HONEST + SAFE (binding):
  * NEVER raises on a feed error: a down feed -> [] live games -> a clean
    heartbeat, never a fabricated game. Per-game error isolation: one bad game's
    reprice/write failure never stops the others.
  * No dollar edge. The only validated lever is FRESHNESS; the repriced number's
    variance SHRINKS as the game progresses (enforced upstream by apply_surface).
    Whether it beats the close is a gate question (fit_w_surface / eval_gate),
    never asserted here.
  * No prediction math lives here -- the loop only ORCHESTRATES the existing,
    tested ingest -> reprice -> snapshot pipeline.

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

# Sports the loop polls each tick. Sport-blind: add a sport here once it has a
# parser in ingest_router and a surface seed.
DEFAULT_SPORTS: List[str] = ["nba"]

# Phase-aware cadence (seconds): poll fast while games are live, slow when quiet.
LIVE_INTERVAL_SEC = 20.0
IDLE_INTERVAL_SEC = 120.0


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_fetch(sport: str) -> Dict[str, Any]:
    """Default production fetch: live_board's keyless ESPN scoreboard GET.

    Returns {} on any error (the loop treats {} as "no live games", never raises).
    """
    try:
        from scripts.platformkit.frontend import live_board as _lb
        site_path, _league = _lb._ESPN_ROUTES.get(_lb._norm_sport(sport), (None, None))
        if site_path is None:
            return {}
        return _lb._http_json(_lb._SITE_BASE.format(path=site_path))
    except Exception as exc:  # noqa: BLE001 - a feed error is never fatal
        logger.warning("live_loop fetch failed sport=%s: %s", sport, exc)
        return {}


def _pregame_prior(sport: str, game_state: GameState,
                   out_dir: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Pull this game's pregame PRIOR from the canonical predict_service store.

    Returns a dict the repricer reads ({'p0', 'variance', ...}) or None when no
    usable prior exists (caller SKIPS the game cleanly -- never fabricates one).
    """
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
    meta: Dict[str, Any] = {}
    for k in ("home_team", "away_team", "home_abbr", "away_abbr", "detail"):
        if ex.get(k) is not None:
            meta[k] = ex[k]
    meta["period"] = gs.period
    meta["home_score"] = gs.home_score
    meta["away_score"] = gs.away_score
    return meta


def poll_once(*, now: Optional[str] = None, fetch: Optional[FetchFn] = None,
              sports: Optional[List[str]] = None, bus: Optional[StateBus] = None,
              out_dir: Optional[Path] = None,
              store_out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Run ONE in-game tick across *sports*. Returns a heartbeat dict. Never raises.

    Parameters
    ----------
    now : str, optional        ISO timestamp to stamp (defaults to UTC now).
    fetch : FetchFn, optional  sport -> scoreboard payload (defaults to ESPN GET).
                               Injected in tests with a canned payload.
    sports : list, optional    sports to poll (defaults to DEFAULT_SPORTS).
    bus : StateBus, optional   the bus to publish onto (defaults to STATE_BUS).
    out_dir : Path, optional   snapshot output dir override (tests).
    store_out_dir : Path, optional  predict_service store dir override (tests).

    Heartbeat shape:
      {'as_of', 'sports', 'n_live', 'n_written', 'n_skipped', 'games': [...]}
    """
    as_of = now if isinstance(now, str) and now else _utc_iso()
    getter = fetch if fetch is not None else _default_fetch
    target_bus = bus if bus is not None else STATE_BUS
    sport_list = list(sports) if sports else list(DEFAULT_SPORTS)

    n_live = n_written = n_skipped = 0
    games_seen: List[Dict[str, Any]] = []

    for sport in sport_list:
        try:
            payload = getter(sport)
        except Exception as exc:  # noqa: BLE001 - feed error never sinks the tick
            logger.warning("live_loop fetch error sport=%s: %s", sport, exc)
            payload = {}
        try:
            published = ingest_router.ingest(sport, payload, bus=target_bus)
        except Exception as exc:  # noqa: BLE001 - ingest guarded, defensive anyway
            logger.warning("live_loop ingest error sport=%s: %s", sport, exc)
            published = []
        for gs in published:
            if not isinstance(gs, GameState) or not gs.is_live():
                continue
            n_live += 1
            res = _process_game(sport, gs, out_dir=out_dir, store_out_dir=store_out_dir,
                                as_of=as_of)
            games_seen.append(res)
            if res.get("written"):
                n_written += 1
            else:
                n_skipped += 1

    heartbeat = {
        "as_of": as_of, "sports": sport_list, "n_live": n_live,
        "n_written": n_written, "n_skipped": n_skipped, "games": games_seen,
        "edge_claimed": False,
        "_honest_note": (
            "In-game loop heartbeat. Snapshots are calibrated freshness re-prices; "
            "no dollar edge is claimed. A down feed yields zero live games, never a "
            "fabricated one."
        ),
    }
    _write_heartbeat(heartbeat, out_dir=out_dir)
    return heartbeat


def _process_game(sport: str, gs: GameState, *, out_dir: Optional[Path],
                  store_out_dir: Optional[Path], as_of: str) -> Dict[str, Any]:
    """Reprice + snapshot ONE live game. Per-game guarded: never raises.

    Returns a small status row for the heartbeat. A game with no prior is SKIPPED
    cleanly (written=False, reason='no_prior') -- never written with a faked number.
    """
    gid = str(gs.game_id)
    try:
        prior = _pregame_prior(sport, gs, store_out_dir)
        if prior is None:
            return {"game_id": gid, "sport": sport, "written": False,
                    "reason": "no_prior"}
        rp = rr.reprice(sport, gs, prior)
        market = ms.build(gid, sport, rp, as_of=as_of, game_meta=_game_meta(gs))
        igsnap.write_live(gid, market, out_dir=out_dir)
        return {"game_id": gid, "sport": sport, "written": True,
                "available": bool(rp.get("available")),
                "variance": market.get("variance")}
    except Exception as exc:  # noqa: BLE001 - one bad game never stops the others
        logger.warning("live_loop process error game=%s: %s", gid, exc)
        return {"game_id": gid, "sport": sport, "written": False,
                "reason": "error:%s" % type(exc).__name__}


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
    """Run the in-game loop until *max_ticks* ticks (or forever if None).

    Parameters
    ----------
    interval : float, optional   base sleep override; when None, the cadence is
                                 phase-aware (LIVE_INTERVAL_SEC when live games
                                 exist, IDLE_INTERVAL_SEC when quiet).
    clock : callable, optional   sleep(seconds) injectable -- tests pass a fake
                                 clock so the tested path NEVER calls time.sleep.
    max_ticks : int, optional    stop after this many ticks (None = run forever).

    Returns the number of ticks executed. Never raises on a per-tick error.
    """
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
    """CLI entrypoint so the supervisor can run `python -m ...ingame.live_loop`.

    Runs serve_forever (phase-aware cadence by default). poll_once writes the
    ingame heartbeat every tick -- including when no game is live -- so the
    supervisor's heartbeat readiness probe passes even on a quiet slate.
    """
    import argparse
    ap = argparse.ArgumentParser(prog="live_loop")
    ap.add_argument("--interval", type=float, default=None,
                    help="base poll interval seconds (default: phase-aware)")
    args = ap.parse_args(argv)
    serve_forever(interval=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FetchFn", "DEFAULT_SPORTS", "LIVE_INTERVAL_SEC", "IDLE_INTERVAL_SEC",
    "poll_once", "serve_forever",
]
