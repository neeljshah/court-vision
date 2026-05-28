"""arb_emitter_daemon.py — publish fresh cross-book arbs to the in-process event bus.

Polls api._courtvision_odds.cross_book_spread() on a configurable interval,
filters to is_arb=True rows with arb_quality in {tight, loose}, dedupes against
a 1-hour TTL set persisted at data/cache/arb_emitted_keys.json, and publishes
each NEW arb as an ``arb.detected`` event on the shared EventBus.

Subscribers on /sse/live_edges receive the event in real-time, so the
CourtVision /arbs UI can auto-refresh the moment a fresh arb appears.

NOTE — bus is in-process. For SSE subscribers to receive events the daemon
MUST run in the same Python process as the FastAPI app. The --in-process
flag (default True) controls this; with --in-process False the daemon
prints payloads to stdout for debugging only.

CLI
---
    python scripts/arb_emitter_daemon.py --once
    python scripts/arb_emitter_daemon.py --interval 30 --min-spread-pp 2.0
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# R19_L3 heartbeat import — copied from clv_tracker_daemon.py pattern.
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
except Exception:
    pass


PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


# Paths.
DEFAULT_DEDUP_PATH = PROJECT_DIR / "data" / "cache" / "arb_emitted_keys.json"
DEFAULT_HEARTBEAT_PATH = (
    PROJECT_DIR / "data" / "cache" / "daemon_heartbeats" / "arb_emitter_daemon.txt"
)

# Tuning.
DEFAULT_INTERVAL_SEC = 30
DEFAULT_MIN_SPREAD_PP = 2.0
DEFAULT_MAX_AGE_SEC = 60.0
DEDUP_TTL_SEC = 3600  # 1 hour — same arb can re-fire after this window

# Quality tiers we care about (skip "stale").
_PUBLISHABLE_QUALITY = {"tight", "loose"}

log = logging.getLogger("arb_emitter_daemon")
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# --------------------------------------------------------------------------- #
# Time helpers.                                                               #
# --------------------------------------------------------------------------- #
def _today_date_str() -> str:
    """Return today's date in YYYY-MM-DD. Use US/Eastern when zoneinfo is available."""
    try:
        from zoneinfo import ZoneInfo
        now = _dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = _dt.datetime.utcnow()
    return now.strftime("%Y-%m-%d")


def _iso_utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Dedupe set with TTL.                                                        #
# --------------------------------------------------------------------------- #
def make_dedup_key(arb: Dict[str, Any]) -> str:
    """Stable key for an arb row.

    Uses (player, stat, line, best_over_book, best_under_book, round(line, 2)).
    All components are normalised to a comparable form so two semantically
    identical arbs collapse to one key.
    """
    player = str(arb.get("player") or "").strip().lower()
    stat = str(arb.get("stat") or "").strip().lower()
    line_raw = arb.get("line")
    try:
        line_val = float(line_raw)
    except (TypeError, ValueError):
        line_val = 0.0
    bover = (
        arb.get("best_over_book")
        or arb.get("arb_best_over_book")
        or ""
    )
    bunder = (
        arb.get("best_under_book")
        or arb.get("arb_best_under_book")
        or ""
    )
    bover = str(bover).strip().lower()
    bunder = str(bunder).strip().lower()
    return "|".join([
        player,
        stat,
        f"{line_val:.4f}",
        bover,
        bunder,
        f"{round(line_val, 2):.2f}",
    ])


def load_dedup(path: Path) -> Dict[str, float]:
    """Return dict {key: emitted_at_unix} from the JSON file (empty on missing/corrupt)."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def prune_dedup(dedup: Dict[str, float], ttl_sec: float = DEDUP_TTL_SEC,
                now_ts: Optional[float] = None) -> Dict[str, float]:
    """Drop entries older than ttl_sec. Mutates and returns the same dict."""
    cutoff = (now_ts if now_ts is not None else time.time()) - ttl_sec
    stale = [k for k, ts in dedup.items() if ts < cutoff]
    for k in stale:
        dedup.pop(k, None)
    return dedup


def save_dedup(path: Path, dedup: Dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dedup, indent=0), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Payload construction.                                                       #
# --------------------------------------------------------------------------- #
def _best_price_from_books(books: List[Dict[str, Any]], book_name: str,
                           side: str) -> Optional[int]:
    """Look up the price for `side` ('over' / 'under') from the row's books list."""
    if not isinstance(books, list) or not book_name:
        return None
    key = f"{side}_price"
    target = str(book_name).strip().lower()
    for b in books:
        if not isinstance(b, dict):
            continue
        if str(b.get("book") or "").strip().lower() == target:
            v = b.get(key)
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None
    return None


def build_payload(arb: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a cross_book_spread row into the SSE payload."""
    bover = arb.get("best_over_book") or arb.get("arb_best_over_book")
    bunder = arb.get("best_under_book") or arb.get("arb_best_under_book")
    books = arb.get("books") or []
    over_price = arb.get("best_over_price")
    if over_price is None:
        over_price = _best_price_from_books(books, bover, "over")
    under_price = arb.get("best_under_price")
    if under_price is None:
        under_price = _best_price_from_books(books, bunder, "under")
    # arb_pct: prefer explicit field, else derive from arb_sum_pct (the
    # "guaranteed profit %" = 100 - arb_sum).
    arb_pct = arb.get("arb_pct")
    if arb_pct is None:
        arb_sum = arb.get("arb_sum_pct")
        if isinstance(arb_sum, (int, float)):
            arb_pct = round(100.0 - float(arb_sum), 2)
    return {
        "topic": "arb.detected",
        "player": arb.get("player"),
        "stat": arb.get("stat"),
        "line": arb.get("line"),
        "best_over_book": bover,
        "best_over_price": over_price,
        "best_under_book": bunder,
        "best_under_price": under_price,
        "arb_pct": arb_pct,
        "implied_total": arb.get("implied_total") or arb.get("arb_sum_pct"),
        "arb_quality": arb.get("arb_quality"),
        "detected_at": _iso_utc_now(),
    }


# --------------------------------------------------------------------------- #
# Heartbeat.                                                                  #
# --------------------------------------------------------------------------- #
def write_heartbeat(path: Path, n_new: int, n_total: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{int(time.time())} | {n_new} | {n_total}\n", encoding="utf-8"
        )
    except OSError as exc:
        log.warning("heartbeat write failed: %s", exc)


# --------------------------------------------------------------------------- #
# Bus publish.                                                                #
# --------------------------------------------------------------------------- #
async def _publish_all(bus: Any, payloads: List[Dict[str, Any]]) -> int:
    """Publish each payload to the bus. Returns count dispatched."""
    n = 0
    for p in payloads:
        try:
            await bus.publish("arb.detected", p)
            n += 1
        except Exception as exc:  # pragma: no cover — never let one bad event halt the loop
            log.warning("bus.publish failed: %s", exc)
    return n


# --------------------------------------------------------------------------- #
# One tick — factored for testability.                                        #
# --------------------------------------------------------------------------- #
def _tick(
    dedup: Dict[str, float],
    bus: Any,
    *,
    fetcher: Callable[[str, float, float], List[Dict[str, Any]]],
    date: Optional[str] = None,
    min_spread_pp: float = DEFAULT_MIN_SPREAD_PP,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    in_process: bool = True,
    now_ts: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Run one tick.

    Parameters
    ----------
    dedup : mutable dict of {key: emitted_at_unix}; pruned and updated in place.
    bus   : event bus exposing ``async publish(topic, event)``. May be None if
            in_process is False — in that case payloads are printed.
    fetcher : callable that returns a list of arb-row dicts. Default in
              `run_main` is api._courtvision_odds.cross_book_spread.

    Returns
    -------
    (new_payloads, total_arbs_seen)
    """
    date = date or _today_date_str()
    now = now_ts if now_ts is not None else time.time()
    prune_dedup(dedup, DEDUP_TTL_SEC, now)

    try:
        rows = fetcher(date, min_spread_pp, max_age_sec) or []
    except Exception as exc:
        log.error("fetcher failed: %s", exc)
        return [], 0

    arbs = [
        r for r in rows
        if r.get("is_arb") is True
        and r.get("arb_quality") in _PUBLISHABLE_QUALITY
    ]

    new_payloads: List[Dict[str, Any]] = []
    for arb in arbs:
        # Normalise the alias fields once so make_dedup_key + build_payload agree.
        if "best_over_book" not in arb and "arb_best_over_book" in arb:
            arb["best_over_book"] = arb["arb_best_over_book"]
        if "best_under_book" not in arb and "arb_best_under_book" in arb:
            arb["best_under_book"] = arb["arb_best_under_book"]
        key = make_dedup_key(arb)
        if key in dedup:
            continue
        dedup[key] = now
        new_payloads.append(build_payload(arb))

    if new_payloads:
        if in_process and bus is not None:
            try:
                asyncio.run(_publish_all(bus, new_payloads))
            except RuntimeError as exc:
                # Already-running event loop — happens if a caller is itself async.
                log.warning("asyncio.run skipped (%s); using existing loop", exc)
                loop = asyncio.get_event_loop()
                loop.run_until_complete(_publish_all(bus, new_payloads))
        else:
            for p in new_payloads:
                print(json.dumps(p, separators=(",", ":")))

    return new_payloads, len(arbs)


# --------------------------------------------------------------------------- #
# Main loop.                                                                  #
# --------------------------------------------------------------------------- #
_STOP = False


def _on_signal(signum, frame):  # pragma: no cover
    global _STOP
    _STOP = True


def _default_fetcher(date: str, min_spread_pp: float,
                     max_age_sec: float) -> List[Dict[str, Any]]:
    from api._courtvision_odds import cross_book_spread
    return cross_book_spread(date, min_spread_pp=min_spread_pp,
                             max_age_sec=max_age_sec)


def run_main(
    interval: float = DEFAULT_INTERVAL_SEC,
    min_spread_pp: float = DEFAULT_MIN_SPREAD_PP,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    once: bool = False,
    in_process: bool = True,
    dedup_path: Path = DEFAULT_DEDUP_PATH,
    heartbeat_path: Path = DEFAULT_HEARTBEAT_PATH,
    fetcher: Optional[Callable[..., List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Persistent emitter loop. Returns the final summary dict."""
    try:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    except (ValueError, AttributeError):
        # Signals unavailable in some test/embedded contexts.
        pass

    fetch = fetcher or _default_fetcher
    bus = None
    if in_process:
        try:
            from src.live.event_bus import get_bus
            bus = get_bus()
        except Exception as exc:
            log.warning("event bus unavailable: %s — falling back to stdout", exc)
            in_process = False

    dedup = load_dedup(dedup_path)
    log.info(
        "arb_emitter_daemon starting (interval=%ss min_spread=%.2fpp "
        "max_age=%.0fs in_process=%s dedup_loaded=%d)",
        interval, min_spread_pp, max_age_sec, in_process, len(dedup),
    )

    cycle = 0
    last_new = 0
    last_total = 0
    while not _STOP:
        cycle += 1
        try:
            new, total = _tick(
                dedup, bus,
                fetcher=fetch,
                min_spread_pp=min_spread_pp,
                max_age_sec=max_age_sec,
                in_process=in_process,
            )
            last_new = len(new)
            last_total = total
            log.info("cycle=%d new=%d total=%d", cycle, last_new, last_total)
        except Exception as exc:  # pragma: no cover — never let a tick kill the daemon
            log.exception("tick failed: %s", exc)

        try:
            save_dedup(dedup_path, dedup)
        except OSError as exc:
            log.warning("dedup save failed: %s", exc)
        write_heartbeat(heartbeat_path, last_new, last_total)

        if once:
            break

        # Sleep in small slices so SIGTERM is responsive.
        slept = 0.0
        while slept < interval and not _STOP:
            chunk = min(1.0, interval - slept)
            time.sleep(chunk)
            slept += chunk

    return {
        "cycles": cycle,
        "last_new_arbs": last_new,
        "last_total_arbs": last_total,
        "dedup_size": len(dedup),
    }


# --------------------------------------------------------------------------- #
# CLI.                                                                        #
# --------------------------------------------------------------------------- #
def _str2bool(v: str) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y", "on"):
        return True
    if s in ("false", "0", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"expected bool, got {v!r}")


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live arb emitter daemon")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between ticks (default 30)")
    p.add_argument("--min-spread-pp", type=float, default=DEFAULT_MIN_SPREAD_PP,
                   help="Minimum spread in percentage points (default 2.0)")
    p.add_argument("--max-age-sec", type=float, default=DEFAULT_MAX_AGE_SEC,
                   help="Max age of book snapshots in seconds (default 60.0)")
    p.add_argument("--once", action="store_true",
                   help="Run one tick and exit")
    p.add_argument("--in-process", type=_str2bool, default=True,
                   help="Publish to in-process bus (True) or print to stdout (False)")
    p.add_argument("--dedup-path", default=str(DEFAULT_DEDUP_PATH))
    p.add_argument("--heartbeat-path", default=str(DEFAULT_HEARTBEAT_PATH))
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    summary = run_main(
        interval=args.interval,
        min_spread_pp=args.min_spread_pp,
        max_age_sec=args.max_age_sec,
        once=args.once,
        in_process=args.in_process,
        dedup_path=Path(args.dedup_path),
        heartbeat_path=Path(args.heartbeat_path),
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
