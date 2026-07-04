"""scripts.platformkit.odds_provider.inplay_snapshot_daemon -- IN-PLAY capture loop.

Sibling of line_snapshot_daemon (PREGAME): captures the LIVE in-game price path
while a game is IN PROGRESS. Polls our OWN keyless venues (Kalshi primary; ESPN/PM
corroborators) every few seconds and appends each live quote, freshness-stamped, to
a per-sport in-play store. Gate: capture only IN-PROGRESS games, decided
VENUE-NATIVELY (no ESPN id cross-join). Canonical tick (one JSON/line, == inplay_history):
  {"sport","game_id","venue","market_type","side","ticker",
   "prob"(float[0,1]),"ts"(ISO-8601 UTC),"phase":"in_play"} (+ optional source_ts).

HONESTY (binding): PAPER/measurement only (no $-edge); never fabricates a tick; only
a PROVEN-tradeable (liquidity-gated) tick is an in-play price (4b); a frozen/cached
feed's tick is DROPPED, never re-stamped fresh (2a); the freshness sidecar advances
ONLY on a successful poll and carries the TRUE source time (stale-never-green);
per-sport isolation. Injectables (tested path: NO network/sleep): now/clock, fetch_fn,
is_live_fn, sleep, out_dir, max_ticks.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; stdlib only here; reuses
inplay_history schema; plain JSONL append (RB-P0-01) -- never duplicates a fetcher.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_snapshot_daemon.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .inplay_freshness import freshest_source_ts, source_fresh, write_freshness

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
# data/ is the gitignored runtime tree (see data-vault-nocommit rule).
DEFAULT_INPLAY_DIR = _HERE.parents[2] / "data" / "cache" / "inplay_history"

# wnba/npb/kbo added 2026-07-04 (LANE 4): kalshi_series_spec.SERIES_SPEC already
# wires all three for in-play (fetch_inplay is unaffected by the pregame-provider
# fix in kalshi.py -- it always queried series_ticker= server-side correctly).
DEFAULT_SPORTS: tuple = ("nba", "mlb", "soccer", "soccer_intl", "tennis",
                         "wnba", "npb", "kbo")

# Cadence: poll every FAST_INTERVAL_SEC while a game is live; back off to
# IDLE_INTERVAL_SEC when none are. Exponential backoff on repeated fetch errors.
FAST_INTERVAL_SEC = 5
IDLE_INTERVAL_SEC = 120
MAX_BACKOFF_SEC = 300

# Retention: keep this many recent UTC day-buckets of in-play history per sport.
# The sweep itself is a cheap dir-listing folded into the loop (see _maybe_sweep)
# at most ONCE per UTC day change -- no new always-on daemon. Generous on purpose:
# keeping MORE days is always the safe error (a wrong delete overnight is not).
RETENTION_KEEP_DAYS = 7


def _as_utc(dt: Optional[datetime]) -> datetime:
    d = dt if dt is not None else datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_of(dt: datetime) -> str:
    return _as_utc(dt).date().isoformat()


def _to_prob(value: Any) -> Optional[float]:
    """Coerce to an implied prob in [0,1]; None if out of range / non-numeric."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _clean_tick(raw: Dict[str, Any], sport: str, now: datetime
                ) -> Optional[Dict[str, Any]]:
    """Normalise one fetched dict into a canonical in-play tick, or None to skip.

    Stamps CAPTURE ts = now() and carries the TRUE feed time as source_ts when given
    (LA-P0-a). DROPPED (None) when: no usable prob/game_id (never fabricated); NOT
    tradeable (4b: an ungated/depthless ESPN/PM line is not an in-play price); or
    source_ts is STALE (2a: a frozen/cached body must never be re-stamped fresh).
    """
    if not isinstance(raw, dict):
        return None
    prob = _to_prob(raw.get("prob"))
    game_id = str(raw.get("game_id") or "").strip()
    if prob is None or not game_id:
        return None
    if not bool(raw.get("tradeable", False)):  # 4b: only PROVEN-liquid is in-play
        return None
    # 2a: a TRADEABLE in-play tick (the only kind persisted/graded) MUST carry a present
    # source_ts so the frozen-feed check is unavoidable -- a tradeable tick with NO
    # source_ts is an unverifiable-freshness escape hatch and is DROPPED. (source_ts
    # stays optional only for tradeable=False corroborators, which are never persisted.)
    source_ts = raw.get("source_ts")
    if source_ts is None:                       # tradeable but no frozen-feed proof
        return None
    if not source_fresh(source_ts, now):        # drop a frozen-feed re-serve
        return None
    tick: Dict[str, Any] = {
        "sport": str(raw.get("sport") or sport or ""),
        "game_id": game_id,
        "venue": str(raw.get("venue") or ""),
        "market_type": str(raw.get("market_type") or "moneyline"),
        "side": str(raw.get("side") or ""),
        "ticker": str(raw.get("ticker") or ""),
        "prob": prob,
        "ts": _iso(now),
        "phase": "in_play",
    }
    if source_ts is not None:
        tick["source_ts"] = str(source_ts)   # TRUE feed time, distinct from poll ts
    return tick


def _append_atomic(path: Path, lines: List[str]) -> None:
    """Append *lines* to *path* with a plain O(1) JSONL append (RB-P0-01) -- the
    crash-safe pattern (== snapshot.write_quotes): all rows in ONE write() with a
    trailing newline, so a crash can at worst lose the tail batch, never split a row.
    Readers (line_store/inplay_history) tolerate a partial trailing line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def poll_inplay_once(sport: str, *, now: Optional[datetime] = None,
                     fetch_fn: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
                     out_dir: Optional[Path] = None,
                     is_live_fn: Optional[Callable[..., bool]] = None,
                     ) -> Dict[str, Any]:
    """Capture one in-play tick batch for *sport*.

    Fetches *fetch_fn* (default = liquidity-gated Kalshi + ESPN/PM corroborators),
    keeps only IN-PROGRESS, tradeable, non-stale ticks (see _clean_tick), stamps
    each capture ts = now()/phase, and ATOMICALLY appends to
    data/cache/inplay_history/<sport>/<YYYY-MM-DD>.jsonl. On success advances the
    freshness sidecar (with the TRUE source time). NEVER raises -- a feed/parse
    failure returns an error status, zero ticks, and does NOT advance freshness.

    LIVENESS GATE: by DEFAULT each tick is judged VENUE-NATIVELY (default_is_live_native,
    no ESPN id cross-join); a pregame/settled market is NEVER captured. An *is_live_fn*
    (game_id-keyed) may be injected to OVERRIDE. Returns {sport, n_ticks, n_games_live,
    out_path, captured_at, status}.
    """
    nowdt = _as_utc(now)
    res: Dict[str, Any] = {
        "sport": sport, "n_ticks": 0, "n_games_live": 0,
        "out_path": None, "captured_at": _iso(nowdt), "status": "ok",
    }
    try:
        from .inplay_feed import default_fetch, default_is_live_native
        fetch = fetch_fn or default_fetch
        raw_ticks = fetch(sport) or []
        live_game_ids: set = set()
        kept: List[Dict[str, Any]] = []
        live_cache: Dict[str, bool] = {}  # only for an injected game-id gate
        for raw in raw_ticks:
            tick = _clean_tick(raw, sport, nowdt)
            if tick is None:
                continue
            gid = tick["game_id"]
            if is_live_fn is not None:
                # Injected override: game-id-keyed (back-compat with stubs/ESPN).
                if gid not in live_cache:
                    try:
                        live_cache[gid] = bool(is_live_fn(gid, sport=sport))
                    except TypeError:
                        live_cache[gid] = bool(is_live_fn(gid))
                is_live = live_cache[gid]
            else:
                # DEFAULT: venue-native, decided per raw tick (carries the venue's
                # own commence_time/close_time/status). No ESPN cross-join.
                is_live = default_is_live_native(raw, nowdt)
            if is_live:
                kept.append(tick)
                live_game_ids.add(gid)
        res["n_games_live"] = len(live_game_ids)
        if kept:
            base = Path(out_dir) if out_dir is not None else DEFAULT_INPLAY_DIR
            sport_dir = base / str(sport).lower()
            target = sport_dir / ("%s.jsonl" % _date_of(nowdt))
            _append_atomic(target, [json.dumps(t) for t in kept])
            res["out_path"] = str(target)
        # Freshness advances on a SUCCESSFUL poll, carrying the TRUE freshest source_ts
        # among kept ticks (frozen feed -> kept empty -> None -> sidecar reads RED).
        base = Path(out_dir) if out_dir is not None else DEFAULT_INPLAY_DIR
        write_freshness(base / str(sport).lower(), nowdt, len(kept),
                        freshest_source_ts(kept))
        res["n_ticks"] = len(kept)
    except Exception as exc:  # noqa: BLE001 -- one sport must never sink the loop
        logger.warning("poll_inplay_once(%s) failed: %s", sport, exc)
        res["status"] = "error: %s" % type(exc).__name__
    return res


def serve_inplay_forever(*, sports: Sequence[str] = DEFAULT_SPORTS,
                         clock: Optional[Callable[[], datetime]] = None,
                         sleep: Optional[Callable[[float], None]] = None,
                         fetch_fn: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
                         is_live_fn: Optional[Callable[..., bool]] = None,
                         out_dir: Optional[Path] = None,
                         interval: int = FAST_INTERVAL_SEC,
                         idle_interval: int = IDLE_INTERVAL_SEC,
                         max_ticks: Optional[int] = None,
                         ) -> List[Dict[str, Any]]:
    """Continuously capture in-play ticks across *sports*.

    Liveness-aware cadence: *interval* s while >=1 game is live for ANY sport, else
    back off to *idle_interval*. Per-sport isolation (one sport's exception is caught,
    others still capture). Rate-limit safe: exponential backoff (capped MAX_BACKOFF_SEC)
    after repeated all-sport errors. Tested path injects clock/no-op sleep/canned
    fetch_fn/is_live_fn + a max_ticks bound (NO sleep/network). NEVER raises.
    """
    _clock = clock or (lambda: datetime.now(timezone.utc))
    _sleep = sleep or _real_sleep
    base = Path(out_dir) if out_dir is not None else DEFAULT_INPLAY_DIR
    ticks: List[Dict[str, Any]] = []
    n = 0
    err_streak = 0
    last_sweep_day: Optional[str] = None
    while True:
        now = _as_utc(_clock())
        # Cheap retention sweep: at most ONCE per UTC day change (and once at start),
        # not on the hot poll path. Prunes only clearly-old dated files; keeps the
        # last RETENTION_KEEP_DAYS day-buckets incl. today's active file.
        today = _date_of(now)
        if today != last_sweep_day:
            _maybe_sweep(base, now)
            last_sweep_day = today
        tick: Dict[str, Any] = {"as_of": _iso(now), "sports": []}
        any_live = False
        all_error = True
        for sport in sports:
            rep = poll_inplay_once(sport, now=now, fetch_fn=fetch_fn,
                                   out_dir=out_dir, is_live_fn=is_live_fn)
            tick["sports"].append(rep)
            if rep.get("n_games_live", 0) > 0:
                any_live = True
            if not str(rep.get("status", "")).startswith("error"):
                all_error = False
        ticks.append(tick)
        n += 1
        if max_ticks is not None and n >= max_ticks:
            return ticks
        # Rate-limit-safe backoff: grow only while EVERY sport is erroring.
        if all_error:
            err_streak += 1
        else:
            err_streak = 0
        if err_streak > 0:
            wait = min(MAX_BACKOFF_SEC, int(interval) * (2 ** err_streak))
        elif any_live:
            wait = int(interval)            # fast cadence while a game is live
        else:
            wait = int(idle_interval)       # idle back-off when nothing is live
        try:
            _sleep(max(1, wait))
        except Exception as exc:  # noqa: BLE001 -- sleep must never sink the loop
            logger.warning("serve_inplay_forever sleep failed: %s", exc)


def _real_sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


def _maybe_sweep(base: Path, now: datetime) -> None:
    """Run the conservative in-play history retention sweep. NEVER raises.

    Delegates to inplay_retention.sweep_all (keep last RETENTION_KEEP_DAYS UTC
    day-buckets per sport; prune only clearly-older dated files; never touch the
    freshness sidecar or today's active file). A sweep failure must never sink the
    capture loop, so any exception is swallowed.
    """
    try:
        from .inplay_retention import sweep_all
        res = sweep_all(base, keep_days=RETENTION_KEEP_DAYS, now=now)
        if res.get("total_pruned", 0):
            logger.info("inplay_retention: pruned %d old day-bucket file(s) "
                        "(keep_days=%d)", res["total_pruned"], RETENTION_KEEP_DAYS)
    except Exception as exc:  # noqa: BLE001 -- retention must never sink the loop
        logger.warning("inplay_retention sweep failed: %s", exc)


__all__ = [
    "DEFAULT_INPLAY_DIR", "DEFAULT_SPORTS", "FAST_INTERVAL_SEC",
    "IDLE_INTERVAL_SEC", "MAX_BACKOFF_SEC", "RETENTION_KEEP_DAYS",
    "poll_inplay_once", "serve_inplay_forever",
]


def _main() -> int:  # pragma: no cover -- thin CLI shim
    """Entry: python -m ...inplay_snapshot_daemon. PAPER/measurement only."""
    import argparse as _ap
    p = _ap.ArgumentParser(description="In-play (live) capture daemon.")
    p.add_argument("--sports", default=",".join(DEFAULT_SPORTS),
                   help="Comma-separated sport ids.")
    p.add_argument("--interval", type=int, default=FAST_INTERVAL_SEC,
                   help="Fast poll interval (s) while a game is live.")
    a = p.parse_args()
    sport_list = tuple(s.strip() for s in a.sports.split(",") if s.strip())
    print("inplay_snapshot_daemon | started sports=%s interval=%ss"
          % (",".join(sport_list), a.interval), flush=True)
    try:
        serve_inplay_forever(sports=sport_list, interval=a.interval)
    except KeyboardInterrupt:
        print("inplay_snapshot_daemon | stopped", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
