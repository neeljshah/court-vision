"""scripts.platformkit.clv.scraped_line_gaps_daemon -- run the scraped-line gap
finder CONTINUOUSLY on OUR OWN feed, on the flywheel, with NO Claude in the loop.

scraped_line_gaps.scan() finds +CLV line-shop gaps in the lines WE scrape
(data/cache/line_history/<sport>/<date>.jsonl -- DraftKings + FanDuel + Pinnacle,
ML/spread/total), freshness-gated so a stale quote can never manufacture a fake
edge. A manual run sees one instant; cross-book gaps are TRANSIENT, so this polls
every few minutes and appends a catch-log row ONLY when a real, fresh +CLV gap
appears -- accumulating the rare genuine gaps into evidence. NO OddsAPI, NO live
re-fetch: it reads the snapshot our scrapers already wrote to disk.

HONEST RAILS: +CLV is in PROBABILITY space, NOT a $ edge claim; the common honest
result is an empty scan on an efficient slate. Reads our own files only; flips NO
flag; places NO bet; writes NO data/registry/. Injectable (scan_fn/sleep/should_stop
/max_ticks) for offline tests. ASCII; never raises out.

CLI:
    python -m scripts.platformkit.clv.scraped_line_gaps_daemon            # ~4min loop
    python -m scripts.platformkit.clv.scraped_line_gaps_daemon --once
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

_REPO = Path(__file__).resolve().parents[3]
SCAN_PATH = _REPO / "data" / "frontend" / "ops" / "scraped_line_gaps.json"
CATCH_LOG = _REPO / "data" / "frontend" / "ops" / "scraped_line_catches.jsonl"
DEFAULT_INTERVAL_SEC = 240.0
DEFAULT_MIN_CLV = 0.5
COMPONENT = "m_scraped_line_gaps"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect(*, min_clv_pct: float = DEFAULT_MIN_CLV,
            scan_fn: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Run the scraped-line scan once and normalize to a compact ops doc."""
    sf = scan_fn
    if sf is None:
        from scripts.platformkit.clv.scraped_line_gaps import scan as sf
    res = sf(min_clv_pct=min_clv_pct) or {}
    by_sport = res.get("by_sport") or {}
    gaps: List[Dict[str, Any]] = []
    shoppable = 0
    max_books = 0
    for b in by_sport.values():
        shoppable += int(b.get("shoppable", 0))
        max_books = max(max_books, int(b.get("max_books", 0)))
        gaps.extend(b.get("gaps") or [])
    return {"updated_at": _utc(), "component": COMPONENT,
            "note": "best of OUR scraped books (DK/FD/Pinnacle) vs sharp fair, "
                    "freshness-gated; +CLV is probability space, NOT a $ edge. "
                    "Empty = efficient across our books.",
            "date": res.get("date"),
            "min_clv_pct": float(min_clv_pct),
            "total_gaps": int(res.get("total_gaps", len(gaps))),
            "shoppable_groups": shoppable,
            "max_books": max_books,
            "gaps": gaps}


def write_scan(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else SCAN_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=0), encoding="ascii")
    tmp.replace(p)


def append_catches(doc: Dict[str, Any], path: Optional[Path] = None) -> int:
    """Append one jsonl row PER real +CLV gap caught (none on an efficient slate)."""
    gaps = doc.get("gaps") or []
    if not gaps:
        return 0
    p = Path(path) if path is not None else CATCH_LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = doc.get("updated_at") or _utc()
    with p.open("a", encoding="ascii") as fh:
        for g in gaps:
            row = dict(g)
            row["caught_at"] = ts
            fh.write(json.dumps(row) + "\n")
    return len(gaps)


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        min_clv_pct: float = DEFAULT_MIN_CLV,
        scan_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        scan_path: Optional[Path] = None,
        catch_path: Optional[Path] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the scan loop forever (or ``max_ticks``). Survives any tick failure;
    returns ticks executed."""
    import time as _time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            doc = collect(min_clv_pct=min_clv_pct, scan_fn=scan_fn)
            write_scan(doc, scan_path)
            caught = append_catches(doc, catch_path)
            print("%s | tick=%d gaps=%d caught=%d shoppable=%d max_books=%d"
                  % (COMPONENT, ticks, doc["total_gaps"], caught,
                     doc["shoppable_groups"], doc["max_books"]), flush=True)
        except Exception as exc:  # noqa: BLE001 - survive any failure
            print("%s | tick=%d ERROR %s" % (COMPONENT, ticks, str(exc)[:160]),
                  flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Autonomous scraped-line +CLV gap daemon: every ~4min scans OUR "
                    "scraped DK/FD/Pinnacle feed (all sports, ML/spread/total), "
                    "freshness-gated, and logs any real transient gap. Model-free; "
                    "CLV only; no edge claimed; no OddsAPI.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between scans (default: %(default)s).")
    p.add_argument("--min-clv", type=float, default=DEFAULT_MIN_CLV,
                   help="Min expected CLV %% to log a gap (default: %(default)s).")
    p.add_argument("--once", action="store_true", help="Run a single scan and exit.")
    a = p.parse_args()
    print("%s | started interval=%ss min_clv=%s once=%s"
          % (COMPONENT, a.interval, a.min_clv, a.once), flush=True)
    try:
        run(interval_sec=a.interval, min_clv_pct=a.min_clv,
            max_ticks=1 if a.once else None)
    except KeyboardInterrupt:
        print("%s | stopped by KeyboardInterrupt" % COMPONENT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
