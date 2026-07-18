"""scripts.platformkit.live_edge.shadow.live_session -- LIVE-EDGE D1 bounded
live shadow session runner.

STEP 0 premise check (2026-07-14, see report): the FotMob live files this
session was pointed at (5113941/5113943/5113944 = Argentine lower-division
friendlies: Deportivo Armenio, Dock Sud, Flandria, etc.) do NOT correspond to
the actual live World Cup semifinal markets moving on the odds bus (game_ids
KXWCGAME-26JUL15ENGARG / 760514 / 1632485246, England/Argentina/France/Spain).
The two feeds track disjoint games -- no team-name join exists. This loop
therefore prices real live odds:* ticks (the actual semifinal markets) through
the existing conditioner with an empty pregame-knowable state (soccer has NO
validated mechanism today anyway -- conditioned == unconditioned always, see
conditioner.py's MECHANISM_REGISTRY). FotMob ticks still flow onto the bus via
bus_ingest.ingest_fotmob for latency/volume bookkeeping but do not (today)
pair with a priced market, so they do not produce a shadow row.

Reusable across sports/slates (max_iterations/sleep_sec/staleness_stop_sec are
all parameters) -- the same loop arms for the MLB slate (~07-17).

Imports bus_ingest/bus/conditioner/shadow_ledger only -- never edits them.

INVARIANTS: stdlib only; ASCII stdout; <=300 LOC; no $/edge claims;
edge_claimed is always False (shadow_ledger's own default); never writes the
claims journal or data/registry/; bounded foreground loop, never parks on a
background process.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scripts.platformkit.live_edge import bus_ingest
from scripts.platformkit.live_edge.bus import FileCursor, read_events
from scripts.platformkit.live_edge.shadow import conditioner, shadow_ledger

_ODDS_PREFIX = "odds:"
_BUS_OFFSET_CURSOR = "live_session_bus_offset"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sec_delta(ts_a: str, ts_b: str) -> Optional[float]:
    """(ts_b - ts_a) in seconds; None if either timestamp doesn't parse."""
    try:
        a = datetime.fromisoformat(str(ts_a).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(ts_b).replace("Z", "+00:00"))
        return (b - a).total_seconds()
    except (ValueError, AttributeError, TypeError):
        return None


def process_odds_row(bus_row: Dict[str, Any], *, wall_ts: str) -> Optional[Dict[str, Any]]:
    """One bus row (source startswith 'odds:') -> {row, latency_sec}, or None if
    the payload isn't a devig-able market tick. `row` is unappended (caller
    persists via shadow_ledger.append_shadow_row)."""
    payload = bus_row.get("payload") or {}
    if "devigged_prob" not in payload:
        return None
    cond = conditioner.condition_tick(payload, state={})
    row = shadow_ledger.make_shadow_row(
        ts=wall_ts,
        sport=str(payload.get("sport", "unknown")),
        game=str(payload.get("game_id", f"{payload.get('home','?')}@{payload.get('away','?')}")),
        market=cond["market_family"],
        book=str(payload.get("book", "unknown")),
        unconditioned_pred=cond["unconditioned_pred"],
        conditioned_pred=cond["conditioned_pred"],
        market_price=cond["unconditioned_pred"],
        mechanism_applied=cond["mechanism_applied"],
    )
    latency_sec = _sec_delta(bus_row.get("ts_knowable", ""), wall_ts)
    return {"row": row, "latency_sec": latency_sec}


def run_iteration(*, ingest_cursor: FileCursor, bus_cursor: FileCursor, date: str,
                   shadow_dir=None) -> Dict[str, Any]:
    """One loop tick: tee fresh source files onto the bus, read new bus rows
    since the persisted offset, condition+append a shadow row per odds tick."""
    ingested = bus_ingest.ingest_all(cursor=ingest_cursor)
    offset = bus_cursor.get(date)
    rows, new_offset = read_events(date, offset=offset)
    bus_cursor.set(date, new_offset)
    wall_ts = _now_iso()
    n_shadow = 0
    latencies: List[float] = []
    for bus_row in rows:
        if not str(bus_row.get("source", "")).startswith(_ODDS_PREFIX):
            continue
        result = process_odds_row(bus_row, wall_ts=wall_ts)
        if result is None:
            continue
        kwargs = {} if shadow_dir is None else {"shadow_dir": shadow_dir}
        shadow_ledger.append_shadow_row(result["row"], date=date, **kwargs)
        n_shadow += 1
        if result["latency_sec"] is not None:
            latencies.append(result["latency_sec"])
    return {"ingested": ingested, "n_bus_rows_seen": len(rows),
            "n_shadow_rows": n_shadow, "latencies_sec": latencies}


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, int(round(pct / 100.0 * (len(s) - 1))))
    return s[idx]


def run_live_session(*, max_iterations: int = 90, sleep_sec: float = 30.0,
                      staleness_stop_sec: float = 600.0, date: Optional[str] = None,
                      shadow_dir=None, sleep_fn=time.sleep) -> Dict[str, Any]:
    """Bounded foreground loop -- stops at max_iterations OR once no new bus
    rows have appeared for staleness_stop_sec (matches ended/feed stalled).
    Blocks the caller for the whole session; never spawns a background proc."""
    ingest_cursor = FileCursor(bus_ingest.CURSOR_NAME)
    bus_cursor = FileCursor(_BUS_OFFSET_CURSOR)
    d = date or _now_iso()[:10]
    total_shadow = 0
    total_bus_rows = 0
    all_latencies: List[float] = []
    last_progress = time.monotonic()
    iterations_run = 0
    for i in range(max_iterations):
        result = run_iteration(ingest_cursor=ingest_cursor, bus_cursor=bus_cursor,
                                date=d, shadow_dir=shadow_dir)
        iterations_run = i + 1
        total_shadow += result["n_shadow_rows"]
        total_bus_rows += result["n_bus_rows_seen"]
        all_latencies.extend(result["latencies_sec"])
        print(f"[live_session] iter={i} bus_rows={result['n_bus_rows_seen']} "
              f"shadow_rows={result['n_shadow_rows']} total_shadow={total_shadow} "
              f"ingested={result['ingested']}")
        if result["n_bus_rows_seen"] > 0:
            last_progress = time.monotonic()
        elif time.monotonic() - last_progress > staleness_stop_sec:
            print(f"[live_session] stale >{staleness_stop_sec}s with no new bus rows, stopping")
            break
        if i < max_iterations - 1:
            sleep_fn(sleep_sec)
    return {
        "date": d, "iterations_run": iterations_run,
        "total_bus_rows": total_bus_rows, "total_shadow_rows": total_shadow,
        "latencies_sec": all_latencies,
        "latency_p50": _percentile(all_latencies, 50),
        "latency_p95": _percentile(all_latencies, 95),
    }


def _main() -> int:  # pragma: no cover
    result = run_live_session()
    print(f"DONE date={result['date']} iterations={result['iterations_run']} "
          f"total_shadow_rows={result['total_shadow_rows']} "
          f"p50={result['latency_p50']} p95={result['latency_p95']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["run_live_session", "run_iteration", "process_odds_row"]
