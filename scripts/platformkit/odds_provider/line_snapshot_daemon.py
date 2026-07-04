"""scripts.platformkit.odds_provider.line_snapshot_daemon -- phase-aware capture loop.

Captures team-market line HISTORY continuously and -- crucially -- grabs the CLOSE
near tip-off so line_store.get_close can return a TRUE close (is_true_close=True ->
MarketRow.clv_is_proxy=False). It is the always-on producer behind the M3 CLV
pipeline: it never predicts, never bets, never fabricates a price; it only RECORDS
the keyless consensus (ESPN / Kalshi / Polymarket) slate over time.

HOW THE CLOSE IS CAPTURED (no separate "mark" step, by design):
  Each tick pulls quotes_from_aggregate(sport) and appends them via
  snapshot.write_quotes with commence_by_game (game_id -> tipoff ISO). The
  commence_time on every row is what line_store.get_close uses to tell a TRUE close
  (a quote at-lock before tip) from a last-observed PROXY. The daemon polls FASTER
  as tip approaches (phase-aware cadence) so a fresh tick lands inside the lock.

FRESHNESS SIDECAR (LA-P0-b): each successful poll writes a per-sport
_freshness.json carrying the slate's TRUE source as_of (the oldest line's fetch
time) so the serving-path guard (freshness.sidecar_status) turns the dashboard RED
when the feed goes dead/cached. A failed/unavailable poll leaves it untouched.

HONESTY (binding):
  * PAPER/measurement only: no orders, no $-edge, CLV-not-ROI.
  * Never fabricates a quote or a close -- a feed/parse miss is logged + skipped.
  * Never raises out of the public API: a feed error on one sport is isolated and
    the loop continues with the other sports.

INJECTABLES (tested path touches NO network / NO real sleep): agg (canned payload),
now (UTC clock), clock (serve_forever clock), sleep (no-op), agg_fn (fetcher).

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; stdlib
only here (aggregate/markets do any network); reuses snapshot + http-cached
providers -- never duplicates the fetcher.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_line_snapshot_daemon.py -q
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .aggregate import aggregate
from .markets import quotes_from_aggregate
from .snapshot import DEFAULT_HISTORY_DIR, write_quotes

logger = logging.getLogger(__name__)

# Default slate of active sports the daemon rotates through each tick.
# wnba/npb/kbo added 2026-07-04 (LANE 4 close-capture widening): all three ride
# the SAME quotes_from_aggregate/write_quotes machinery unchanged; Kalshi is
# their ONLY odds source (ESPN/fanduel/polymarket/pinnacle report "unsupported"
# for all three), so this pregame capture daemon is what gives them a real
# close to grade against (verified live: KalshiProvider now returns real
# priced events for wnba/npb/kbo after the series_ticker fix in kalshi.py).
DEFAULT_SPORTS: tuple = ("nba", "mlb", "soccer", "soccer_intl", "tennis",
                         "wnba", "npb", "kbo")

# Liveness heartbeat (RB-P0-03): supervised as m1_line_daemon. serve_forever beats
# this every tick so the supervisor's HEARTBEAT readiness reads the service
# not-ready when the heartbeat is absent (fresh boot) OR stale (a hung tick) --
# never a stale-green NONE. poll_once itself stays heartbeat-free / test-pure; the
# beat lives only in the long-running serve_forever loop.
HEARTBEAT_COMPONENT = "m1_line_daemon"


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the m1_line_daemon liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- heartbeat write must never sink a tick
        logger.debug("line_snapshot_daemon heartbeat skipped: %s", exc)

# Phase-aware cadence: poll FAST when any tracked game is near tip (so a tick lands
# inside the lock window -> a true close), slow when the next tip is far away.
NEAR_TIP_MIN = 45          # "near tip" = a game commences within this many minutes.
FAST_INTERVAL_SEC = 60     # cadence while a game is near tip (catch the close).
SLOW_INTERVAL_SEC = 900    # cadence when no game is near tip (be polite to feeds).


def _as_utc(dt: Optional[datetime]) -> datetime:
    d = dt if dt is not None else datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _parse_iso(value: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _commence_by_game(agg: Dict[str, Any]) -> Dict[str, str]:
    """game_id -> commence_time ISO, read off the aggregate events.

    This is what lets line_store.get_close prove a TRUE close. A game with no
    commence_time is simply absent (its rows can never be a true close).
    """
    out: Dict[str, str] = {}
    for ev in (agg.get("events") or []):
        if not isinstance(ev, dict):
            continue
        gid = str(ev.get("event_id") or "").strip()
        commence = ev.get("commence_time")
        if gid and commence:
            out[gid] = str(commence)
    return out


def _minutes_to_next_tip(commence_map: Dict[str, str], now: datetime
                         ) -> Optional[float]:
    """Minutes until the soonest FUTURE tip among tracked games (None if none)."""
    best: Optional[float] = None
    for iso in commence_map.values():
        tip = _parse_iso(iso)
        if tip is None or tip < now:
            continue
        mins = (tip - now).total_seconds() / 60.0
        if best is None or mins < best:
            best = mins
    return best


def _default_agg_fn(sport: str, *, now: Optional[datetime] = None
                    ) -> Dict[str, Any]:
    """The real keyless aggregate(); *now* is accepted (and ignored) so a custom
    agg_fn and the default share one (sport, *, now) contract."""
    return aggregate(sport)


def _write_freshness(sport_dir: Path, source_as_of: Optional[str],
                     poll_at: datetime, n_quotes: int) -> None:
    """Atomically write the pregame freshness sidecar for a sport.

    {source_as_of, poll_at, n_quotes}. source_as_of is the slate's TRUE fetched-at
    (the oldest line's fetch time, from aggregate()), NOT the poll wall-clock -- so a
    dead/cached feed that keeps being re-polled records its STALE source time and the
    serving-path guard (freshness.sidecar_status) can turn the dashboard RED. Written
    ONLY on a successful poll; a failed/unavailable poll leaves the sidecar untouched
    (a dead feed must NEVER read fresh). Never raises out.
    """
    try:
        sport_dir.mkdir(parents=True, exist_ok=True)
        target = sport_dir / "_freshness.json"
        payload = {
            "source_as_of": source_as_of,
            "poll_at": poll_at.isoformat(timespec="seconds"),
            "n_quotes": int(n_quotes),
        }
        tmp = target.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(str(tmp), str(target))
    except Exception as exc:  # noqa: BLE001 -- sidecar write must never sink a poll
        logger.debug("pregame freshness sidecar write skipped: %s", exc)


def poll_once(sport: str, *, now: Optional[datetime] = None,
              agg: Optional[Dict[str, Any]] = None,
              out_dir: Optional[Path] = None,
              lock_window_min: int = 30,
              agg_fn: Optional[Callable[..., Dict[str, Any]]] = None,
              ) -> Dict[str, Any]:
    """Capture one tick of *sport*'s consensus line history.

    Pulls quotes_from_aggregate(sport), appends them via write_quotes with the
    per-game tipoff (so get_close can prove a TRUE close), writes the freshness
    sidecar, and reports how many games are at-lock THIS tick. NEVER raises -- a
    feed/parse failure returns an error status + empty capture.

    *agg* / *now* / *agg_fn* are injectable for offline tests; when *agg* is None
    the daemon fetches via *agg_fn* (default = the real keyless aggregate()).
    """
    nowdt = _as_utc(now)
    res: Dict[str, Any] = {
        "sport": sport, "status": "ok", "as_of": nowdt.isoformat(timespec="seconds"),
        "logged": 0, "skipped": 0, "games": 0, "at_lock_games": 0,
    }
    try:
        fetch = agg_fn or _default_agg_fn
        payload = agg if agg is not None else fetch(sport, now=nowdt)
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            res["status"] = "unavailable"
            return res
        quotes = quotes_from_aggregate(sport, agg=payload, now=nowdt)
        commence_map = _commence_by_game(payload)
        written = write_quotes(quotes, out_dir=out_dir, now=nowdt,
                               commence_by_game=commence_map)
        res["logged"] = written.get("logged", 0)
        res["skipped"] = written.get("skipped", 0)
        res["status"] = written.get("status", "ok")
        res["files"] = written.get("files", [])
        # Count games whose tip is within the lock window NOW: their tick = the close.
        seen: set = set()
        at_lock = 0
        for gid, iso in commence_map.items():
            tip = _parse_iso(iso)
            if tip is None:
                continue
            seen.add(gid)
            if (tip - timedelta(minutes=lock_window_min)) <= nowdt <= tip:
                at_lock += 1
        res["games"] = len(seen)
        res["at_lock_games"] = at_lock
        res["next_tip_min"] = _minutes_to_next_tip(commence_map, nowdt)
        # Pregame freshness sidecar (LA-P0-b): stamp the slate's TRUE source as_of
        # so a serving-path staleness guard turns RED when the feed goes dead/cached.
        base = Path(out_dir) if out_dir is not None else DEFAULT_HISTORY_DIR
        _write_freshness(base / sport.lower(), payload.get("as_of"), nowdt,
                         res["logged"])
        res["source_as_of"] = payload.get("as_of")
    except Exception as exc:  # noqa: BLE001 -- one sport must never sink the loop
        logger.warning("poll_once(%s) failed: %s", sport, exc)
        res["status"] = "error: %s" % type(exc).__name__
    return res


def _next_interval(near_min: Optional[float]) -> int:
    """Phase-aware cadence: fast near a tip, slow when the next tip is far away."""
    if near_min is not None and near_min <= NEAR_TIP_MIN:
        return FAST_INTERVAL_SEC
    return SLOW_INTERVAL_SEC


def serve_forever(interval: Optional[int] = None, *,
                  sports: Sequence[str] = DEFAULT_SPORTS,
                  clock: Optional[Callable[[], datetime]] = None,
                  sleep: Optional[Callable[[float], None]] = None,
                  max_ticks: Optional[int] = None,
                  out_dir: Optional[Path] = None,
                  lock_window_min: int = 30,
                  agg_fn: Optional[Callable[..., Dict[str, Any]]] = None,
                  ) -> List[Dict[str, Any]]:
    """Continuously poll every active sport, capturing line history + closes.

    Each tick polls poll_once(sport) across *sports*, isolating a per-sport feed
    error so the others still capture. Cadence is phase-aware: it polls FAST while
    any game is near tip (to land a tick inside the lock window = the close) and
    SLOW otherwise; pass a fixed *interval* to override.

    The tested path injects *clock* (-> UTC now), a no-op *sleep*, and a *max_ticks*
    bound so it runs N ticks with NO real sleep and NO network. Returns the list of
    per-tick reports. NEVER raises out of a tick.
    """
    _clock = clock or (lambda: datetime.now(timezone.utc))
    _sleep = sleep or _real_sleep
    ticks: List[Dict[str, Any]] = []
    n = 0
    _beat()  # live before the first tick completes
    while True:
        now = _as_utc(_clock())
        _beat(now.timestamp())  # beat each tick: a hung tick ages out -> not-ready
        tick: Dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"),
                                "sports": []}
        soonest: Optional[float] = None
        for sport in sports:
            rep = poll_once(sport, now=now, out_dir=out_dir,
                            lock_window_min=lock_window_min, agg_fn=agg_fn)
            tick["sports"].append(rep)
            nm = rep.get("next_tip_min")
            if isinstance(nm, (int, float)):
                soonest = nm if soonest is None else min(soonest, nm)
        ticks.append(tick)
        n += 1
        if max_ticks is not None and n >= max_ticks:
            return ticks
        wait = interval if interval is not None else _next_interval(soonest)
        try:
            _sleep(max(1, int(wait)))
        except Exception as exc:  # noqa: BLE001 -- sleep must never sink the loop
            logger.warning("serve_forever sleep failed: %s", exc)


def _real_sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


__all__ = [
    "DEFAULT_SPORTS",
    "NEAR_TIP_MIN",
    "FAST_INTERVAL_SEC",
    "SLOW_INTERVAL_SEC",
    "poll_once",
    "serve_forever",
]


def _main() -> int:
    """Entry: python -m ...line_snapshot_daemon. PAPER/measurement only."""
    import argparse as _ap

    p = _ap.ArgumentParser(
        description="Line/close capture daemon -- phase-aware poll for all active sports.")
    p.add_argument("--interval", type=int, default=None,
                   help="Fixed poll interval in seconds (omit for phase-aware cadence).")
    p.add_argument("--sports", default=",".join(DEFAULT_SPORTS),
                   help="Comma-separated sport ids (default: %s)." % ",".join(DEFAULT_SPORTS))
    a = p.parse_args()
    sport_list = tuple(s.strip() for s in a.sports.split(",") if s.strip())
    print("line_snapshot_daemon | started sports=%s interval=%s"
          % (",".join(sport_list),
             "%ss" % a.interval if a.interval else "phase-aware"), flush=True)
    try:
        serve_forever(interval=a.interval, sports=sport_list)
    except KeyboardInterrupt:
        print("line_snapshot_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
