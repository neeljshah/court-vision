"""scripts.platformkit.clv.best_price_scan_daemon -- run the model-free best-price
+CLV scan CONTINUOUSLY, on the flywheel, with NO Claude in the loop.

THE GAP IT CLOSES: best_price_audit.audit() is the honest "use more books to find
gaps" lever -- across every wired sportsbook it takes the BEST price per side and
asks whether it beats the SHARP fair (Pinnacle / cross-book median). But a MANUAL
run only ever sees ONE instant, and cross-book mispricings are TRANSIENT: a book
lags the move for ~60-120s, then corrects. The single honest way "more books finds
gaps" pays off is to POLL all books continuously so a +CLV gap is caught in the
short window it exists. This daemon runs the scan every few minutes, writes a live
ops doc the frontend can read, and appends a catch-log row ONLY when a real +CLV
opportunity appears -- so the rare transient gaps accumulate into evidence.

HONEST RAILS: expected CLV is in PROBABILITY space (better-than-sharp-fair price),
explicitly NOT a $ edge claim and NOT a claim of beating a sharp market on average;
the COMMON, honest result is an empty scan on an efficient slate. Reads aggregated
public odds only; flips NO flag; places NO bet; writes NO data/registry/. Injectable
(audit_fn/clock/sleep/should_stop/max_ticks) for offline tests. ASCII; never raises out.

CLI:
    python -m scripts.platformkit.clv.best_price_scan_daemon            # ~4min loop
    python -m scripts.platformkit.clv.best_price_scan_daemon --once
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

_REPO = Path(__file__).resolve().parents[3]
SCAN_PATH = _REPO / "data" / "frontend" / "ops" / "best_price_scan.json"
CATCH_LOG = _REPO / "data" / "frontend" / "ops" / "best_price_catches.jsonl"
DEFAULT_INTERVAL_SEC = 240.0          # transient cross-book gaps -> poll often
DEFAULT_SPORTS = ("mlb", "soccer_intl", "wnba")  # wnba added 2026-07-03: >=2 books/game
                                                  # live (kalshi/espn/fanduel/pinnacle)
DEFAULT_MIN_CLV = 0.5                 # min expected CLV %% to call a row a "gap"
COMPONENT = "m_best_price_scan"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect(sports: Sequence[str] = DEFAULT_SPORTS, *,
            min_clv_pct: float = DEFAULT_MIN_CLV,
            audit_fn: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Run the best-price audit once and normalize to a compact ops doc."""
    af = audit_fn
    if af is None:
        from scripts.platformkit.clv.best_price_audit import audit as af  # noqa: N813
    res = af(sports, min_clv_pct=min_clv_pct) or {}
    by_sport = res.get("by_sport") or {}
    shoppable = sum(int(b.get("shoppable_games", 0)) for b in by_sport.values())
    max_books = max((int(b.get("max_books", 0)) for b in by_sport.values()), default=0)
    gaps: List[Dict[str, Any]] = []
    for sport, b in by_sport.items():
        for v in (b.get("value_bets") or []):
            row = dict(v)
            row["sport"] = sport
            gaps.append(row)
    return {"updated_at": _utc(), "component": COMPONENT,
            "note": "best available price vs sharp fair across all wired books; "
                    "+CLV in probability space, NOT a $ edge. Empty = efficient slate.",
            "min_clv_pct": float(min_clv_pct),
            "total_gaps": len(gaps),
            "shoppable_games": shoppable,
            "max_books": max_books,
            "gaps": gaps}


def write_scan(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else SCAN_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=0), encoding="ascii")
    tmp.replace(p)


def append_catches(doc: Dict[str, Any], path: Optional[Path] = None) -> int:
    """Append one jsonl row PER +CLV gap caught this tick (none if slate efficient).

    Returns the number of rows written -- the transient gaps the continuous scan
    caught that a one-shot manual run would have missed."""
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
        sports: Sequence[str] = DEFAULT_SPORTS,
        min_clv_pct: float = DEFAULT_MIN_CLV,
        audit_fn: Optional[Callable[..., Dict[str, Any]]] = None,
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
            doc = collect(sports, min_clv_pct=min_clv_pct, audit_fn=audit_fn)
            write_scan(doc, scan_path)
            caught = append_catches(doc, catch_path)
            print("%s | tick=%d gaps=%d caught=%d shoppable=%d max_books=%d"
                  % (COMPONENT, ticks, doc["total_gaps"], caught,
                     doc["shoppable_games"], doc["max_books"]), flush=True)
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
        description="Autonomous best-price +CLV scan daemon: every ~4min takes the "
                    "best price across all wired books vs sharp fair and logs any "
                    "transient gap. Model-free; calibration/CLV only; no edge claimed.")
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
