"""scripts.platformkit.tip_capture.ingame_capture -- LIVE tick capture daemon.

Companion to daemon.py's PRE-game T-60/T-30/T-5 capture: this one runs while a
game is actually IN PROGRESS. Every ~60s, for each currently-live NBA/WNBA/MLB
game, it appends one JSONL row carrying: the live score/clock state, our own
re-priced win-prob (via answers.winprob_dispatch.dispatch fed the live state),
a best-effort market snapshot (SAME kalshi/polymarket sources capture.py's
capture_market already uses), and a short pbp tail (last ~5 plays, with
on-floor participants when the feed exposes them).

Slate discovery reuses ingame.ingame_live_state.live_states(sport) -- the
ALREADY-shipped ESPN live-scoreboard reader every other in-game consumer in
this repo (live_loop.py, wnba_ingame_shadow.py, ...) reads from; no new
transport. Team-code resolution (capture.capture._code_for), market capture
(capture.capture_market) and git_sha are imported straight from capture.py
-- byte-identical to what daemon.py already uses, per this lane's mandate.

Store: data/cache/tip_capture/<sport>/ingame_<date>.jsonl (date=capture date
UTC), append-only, one row per (game, tick):
{"capture_ts": "...", "sport": "nba", "game_id": "...", "home": "...",
 "away": "...", "period": 3|None, "inning": None|2, "clock": 411.0|None,
 "score_home": 58, "score_away": 55, "source": "ingame_capture",
 "model_sha": "<git HEAD sha>",
 "payload": {"winprob": {...}, "market": {...}, "pbp_tail": {...}}}
period/clock are basketball-only (nba/wnba); inning is mlb-only -- the other
key is simply absent/None rather than fabricated (mirrors the live-state
reader's own honest-gap convention).

CAPTURES DATA ONLY -- places nothing, flips no flag. Own singleton lock
(ingame_capture.lock) + own heartbeat (data/cache/daemon_heartbeats/
ingame_capture.txt) so this can run alongside the pregame daemon.py without
contention.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII only; stdlib + in-repo
fetchers only; no data/registry/ writes; no $/edge claims.
Per-file test: tests/platformkit/tip_capture/test_ingame_capture.py
Run: python -m scripts.platformkit.tip_capture.ingame_capture --once
"""
from __future__ import annotations

import argparse
import json
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit import espn_wp_reference
from scripts.platformkit.answers import winprob_dispatch
from scripts.platformkit.ingame.ingame_live_state import live_states as _live_states

from .capture import _code_for, capture_market, git_sha
from .store import DEFAULT_OUT_DIR, acquire_singleton

logger = logging.getLogger("tip_capture")

SPORTS: tuple = ("nba", "wnba", "mlb")
TICK_SEC = 60.0
_REG_MINUTES = {"nba": 48.0, "wnba": 40.0}  # regulation length, for elapsed_minutes
DEFAULT_LOCK_PATH = DEFAULT_OUT_DIR / "ingame_capture.lock"
HEARTBEAT_COMPONENT = "ingame_capture"


def _trim_play(p: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort trim of one ESPN play entry -- tolerant of the "clock"/
    "period" sub-object shape (dict with displayValue/number) OR a bare
    scalar; never assumes a key exists."""
    period = p.get("period")
    if isinstance(period, dict):
        period = period.get("number")
    clock = p.get("clock")
    if isinstance(clock, dict):
        clock = clock.get("displayValue")
    out: Dict[str, Any] = {
        "id": p.get("id"), "text": p.get("text") or p.get("shortText"),
        "period": period, "clock": clock,
        "home_score": p.get("homeScore"), "away_score": p.get("awayScore"),
        "scoring_play": bool(p.get("scoringPlay")),
    }
    participants = p.get("participants")
    if isinstance(participants, list) and participants:
        names = [((pt.get("athlete") or {}).get("displayName")
                 or (pt.get("athlete") or {}).get("shortName"))
                for pt in participants if isinstance(pt, dict)]
        names = [n for n in names if n]
        if names:
            out["on_floor"] = names
    return out


def capture_pbp_tail(sport: str, event_id: Optional[str], *,
                     fetch_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Last ~5 plays for *event_id* via espn_wp_reference.fetch_summary (same
    ESPN summary?event= route already used for the WP reference corpus --
    reused here purely for its plays[] tail, not its winprobability[])."""
    if not event_id:
        return {"status": "unavailable"}
    fn = fetch_fn if fetch_fn is not None else espn_wp_reference.fetch_summary
    try:
        summary = fn(sport, str(event_id))
        if not summary:
            return {"status": "unavailable"}
        plays = summary.get("plays") or []
        return {"status": "ok",
               "events": [_trim_play(p) for p in plays[-5:] if isinstance(p, dict)]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": type(exc).__name__}


def _ingame_state_for(sport: str, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map a live_states() row onto winprob_dispatch's generic ingame_state
    keys (elapsed/inning/half/home_score/away_score). None when the fields
    the sport needs are incomplete -- dispatch then degrades to pregame-only,
    never a fabricated live state."""
    hs, as_ = state.get("home_score"), state.get("away_score")
    if hs is None or as_ is None:
        return None
    if sport in ("nba", "wnba"):
        frac = state.get("frac_elapsed")
        if frac is None:
            return None
        return {"elapsed": round(float(frac) * _REG_MINUTES[sport], 2),
                "home_score": int(hs), "away_score": int(as_)}
    if sport == "mlb":
        inning, half = state.get("inning"), state.get("half")
        if inning is None or half is None:
            return None
        return {"inning": int(inning), "half": str(half),
                "home_score": int(hs), "away_score": int(as_)}
    return None


def capture_winprob_live(sport: str, home: str, away: str,
                         ingame_state: Optional[Dict[str, Any]], *,
                         dispatch_fn: Optional[Callable] = None) -> Dict[str, Any]:
    fn = dispatch_fn if dispatch_fn is not None else winprob_dispatch.dispatch
    try:
        return fn(sport, _code_for(sport, home), _code_for(sport, away), ingame_state)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": type(exc).__name__}


def build_row(state: Dict[str, Any], *, now: datetime,
             deps: Optional[Dict[str, Callable]] = None) -> Dict[str, Any]:
    """Capture everything for one live-game tick -> the store row."""
    deps = deps or {}
    sport = state["sport"]
    home = state.get("home_display") or state.get("home") or ""
    away = state.get("away_display") or state.get("away") or ""
    ingame_state = _ingame_state_for(sport, state)
    payload = {
        "winprob": capture_winprob_live(sport, home, away, ingame_state,
                                        dispatch_fn=deps.get("winprob")),
        "market": capture_market(sport, kalshi_fn=deps.get("kalshi"),
                                 polymarket_fn=deps.get("polymarket")),
        "pbp_tail": capture_pbp_tail(sport, state.get("espn_event_id") or state.get("game_id"),
                                     fetch_fn=deps.get("pbp")),
    }
    hs, as_ = state.get("home_score"), state.get("away_score")
    return {
        "capture_ts": now.isoformat(), "sport": sport, "game_id": state.get("game_id"),
        "home": home, "away": away,
        "period": state.get("period"), "inning": state.get("inning"),
        "clock": state.get("clock"),
        "score_home": int(hs) if hs is not None else None,
        "score_away": int(as_) if as_ is not None else None,
        "source": "ingame_capture", "model_sha": git_sha(), "payload": payload,
    }


def _store_path(sport: str, date_str: str, *, out_dir: Optional[Path] = None) -> Path:
    base = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    return base / sport.lower() / f"ingame_{date_str}.jsonl"


def _append_row(row: Dict[str, Any], *, out_dir: Optional[Path] = None) -> Path:
    """Crash-safe O(1) append -- same one-open('a')-write idiom as
    store.append_row, but keyed by capture date (not tip_time/capture_pass)
    and the ingame_<date>.jsonl filename this lane's schema calls for."""
    path = _store_path(row["sport"], row["capture_ts"][:10], out_dir=out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
        fh.flush()
    return path


def _beat(now_epoch: Optional[float] = None) -> None:
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception:  # noqa: BLE001
        logger.debug("ingame_capture heartbeat skipped", exc_info=True)


def tick(*, sports: Sequence[str] = SPORTS, now: Optional[datetime] = None,
        out_dir: Optional[Path] = None, deps: Optional[Dict[str, Callable]] = None,
        live_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """One pass: capture every currently-live game across *sports*. Never raises."""
    nowdt = now if now is not None else datetime.now(timezone.utc)
    fn = live_fn if live_fn is not None else _live_states
    summary: Dict[str, Any] = {"as_of": nowdt.isoformat(), "sports": {}}
    for sport in sports:
        try:
            states = fn(sport)
        except Exception as exc:  # noqa: BLE001 -- one sport must never sink the tick
            logger.warning("ingame_capture live_states failed sport=%s: %s", sport, exc)
            states = []
        n_captured = 0
        for state in states:
            try:
                row = build_row(state, now=nowdt, deps=deps)
                _append_row(row, out_dir=out_dir)
                n_captured += 1
            except Exception as exc:  # noqa: BLE001 -- one bad game must not sink the tick
                logger.warning("ingame_capture row failed sport=%s game=%s: %s",
                               sport, state.get("game_id"), exc)
        summary["sports"][sport] = {"n_live": len(states), "n_captured": n_captured}
    _beat(nowdt.timestamp())
    return summary


def run(*, sports: Sequence[str] = SPORTS, out_dir: Optional[Path] = None,
       deps: Optional[Dict[str, Callable]] = None, live_fn: Optional[Callable] = None,
       clock: Optional[Callable[[], datetime]] = None,
       sleep: Optional[Callable[[float], None]] = None,
       tick_sec: float = TICK_SEC, max_ticks: Optional[int] = None,
       should_stop: Optional[Callable[[], bool]] = None) -> int:
    _clock = clock or (lambda: datetime.now(timezone.utc))
    _sleep = sleep or _time.sleep
    ticks = 0
    while True:
        if should_stop is not None and should_stop():
            break
        summary = tick(sports=sports, now=_clock(), out_dir=out_dir, deps=deps, live_fn=live_fn)
        print("ingame_capture | tick=%d as_of=%s %s" % (
            ticks, summary["as_of"],
            " ".join("%s=%s/%s" % (sp, d["n_captured"], d["n_live"])
                     for sp, d in summary["sports"].items())), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(tick_sec)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingame_capture sleep failed: %s", exc)
    return ticks


def _main() -> int:  # pragma: no cover -- thin CLI shim
    ap = argparse.ArgumentParser(description="Live in-game tick capture daemon.")
    ap.add_argument("--once", action="store_true", help="single pass, for cron")
    ap.add_argument("--sports", default=",".join(SPORTS))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--lock-path", default=None)
    ap.add_argument("--no-lock", action="store_true")
    ap.add_argument("--tick-sec", type=float, default=TICK_SEC)
    a = ap.parse_args()
    sports = tuple(s.strip() for s in a.sports.split(",") if s.strip())
    lock_path = Path(a.lock_path) if a.lock_path else DEFAULT_LOCK_PATH
    if not a.no_lock and not acquire_singleton(lock_path):
        print("ingame_capture: already running (lock held), exiting", flush=True)
        return 1
    out_dir = Path(a.out_dir) if a.out_dir else None
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if a.once:
        summary = tick(sports=sports, out_dir=out_dir)
        print(json.dumps(summary, default=str), flush=True)
        return 0
    print("ingame_capture | started sports=%s" % ",".join(sports), flush=True)
    try:
        run(sports=sports, out_dir=out_dir, tick_sec=a.tick_sec)
    except KeyboardInterrupt:
        print("ingame_capture | stopped", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "SPORTS", "TICK_SEC", "DEFAULT_OUT_DIR", "DEFAULT_LOCK_PATH", "HEARTBEAT_COMPONENT",
    "capture_pbp_tail", "capture_winprob_live", "build_row", "tick", "run",
]
