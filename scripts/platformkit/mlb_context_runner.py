"""scripts.platformkit.mlb_context_runner -- supervised M31 entry.

Every ~6h: snapshots the keyless MLB pregame CONTEXT the models were blind to --
(1) probable pitchers + weather + HP umpire for today AND tomorrow (one statsapi
    schedule call per date, hydrate=probablePitcher,weather,officials) via
    domains.mlb.ingest_probables.ingest_range,
(2) the ESPN injury report snapshot + deterministic edge-fact extraction
    (edge_engine.extract_rule over the beat-writer comment text) via
    domains.mlb.ingest_injuries, and
(3) the FULL umpire crew assignments (HP/1B/2B/3B) for today AND tomorrow via
    domains.mlb.ingest_umpire_assignments.ingest_range (same schedule endpoint,
    long-format as-of store keyed by game_pk -- added 2026-07-09, PENDING-RESTART).

KNOWLEDGE/SUBSTRATE ONLY -- adds data depth, not edge. Snapshot-append parquets
with captured_at vintages; downstream joins must be as-of on snapshot_date.
Independent branch (no depends_on): a dead tick is one red status entry, never
blocks the stack. NO $ field, NO flag flip, NO data/registry/ write.

Heartbeat: m31_mlb_context -> data/cache/daemon_heartbeats/m31_mlb_context.txt
Cadence: DEFAULT_INTERVAL_SEC = 21600 s (4 snapshots/day; probables and injury
reports move on hour scales, not minutes).
Repo-internal only; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("mlb_context_runner")

HEARTBEAT_COMPONENT = "m31_mlb_context"
DEFAULT_INTERVAL_SEC = 21600.0


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M31 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("mlb_context heartbeat skipped: %s", exc)


def _tick_probables() -> int:
    """Snapshot probables/weather/umps for today + tomorrow. Returns rows fetched."""
    from domains.mlb.ingest_probables import ingest_range
    import pandas as pd
    today = _dt.date.today()
    dates = [str(today), str(today + _dt.timedelta(days=1))]
    out = ingest_range(dates)
    try:
        df = pd.read_parquet(out)
        return int((df["snapshot_date"] == str(today)).sum())
    except Exception:  # noqa: BLE001
        return 0


def _tick_umpires() -> int:
    """Snapshot full umpire crew assignments for today + tomorrow. Returns
    today's snapshot row count."""
    from domains.mlb.ingest_umpire_assignments import ingest_range
    import pandas as pd
    today = _dt.date.today()
    out = ingest_range([str(today), str(today + _dt.timedelta(days=1))])
    try:
        df = pd.read_parquet(out)
        return int((df["snapshot_date"] == str(today)).sum())
    except Exception:  # noqa: BLE001
        return 0


def _tick_injuries() -> Dict[str, int]:
    """Snapshot the injury report + emit deterministic edge facts."""
    from domains.mlb.ingest_injuries import (
        build_edge_facts, ingest_snapshot, write_edge_facts,
    )
    snap_df = ingest_snapshot()
    today_rows = []
    if not snap_df.empty:
        snap_date = snap_df["snapshot_date"].iloc[-1]
        today_rows = snap_df[snap_df["snapshot_date"] == snap_date].to_dict("records")
    facts_df = write_edge_facts(build_edge_facts(today_rows))
    return {"injury_rows": len(today_rows),
            "edge_facts": 0 if facts_df is None or facts_df.empty else len(facts_df)}


def tick(*, now: float,
         probables_fn: Optional[Callable[[], int]] = None,
         injuries_fn: Optional[Callable[[], Dict[str, int]]] = None,
         umpires_fn: Optional[Callable[[], int]] = None) -> Dict[str, Any]:
    """One context tick: probables -> injuries+facts -> umpire crews ->
    heartbeat. Never raises."""
    doc: Dict[str, Any] = {"probable_rows": 0, "injury_rows": 0, "edge_facts": 0,
                           "umpire_rows": 0}
    _probables = probables_fn if probables_fn is not None else _tick_probables
    _injuries = injuries_fn if injuries_fn is not None else _tick_injuries
    _umpires = umpires_fn if umpires_fn is not None else _tick_umpires
    try:
        doc["probable_rows"] = int(_probables())
    except Exception as exc:  # noqa: BLE001
        logger.warning("mlb_context probables tick raised: %s", exc)
    try:
        doc.update(_injuries() or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("mlb_context injuries tick raised: %s", exc)
    try:
        doc["umpire_rows"] = int(_umpires())
    except Exception as exc:  # noqa: BLE001
        logger.warning("mlb_context umpires tick raised: %s", exc)
    _beat(now)
    return doc


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        probables_fn: Optional[Callable[[], int]] = None,
        injuries_fn: Optional[Callable[[], Dict[str, int]]] = None,
        umpires_fn: Optional[Callable[[], int]] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the context loop forever (or max_ticks). Never raises out. Everything
    injectable for offline tests. Returns ticks executed."""
    import time as _time
    _clock = clock if clock is not None else _time.time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    try:
        _beat(float(_clock()))
    except Exception:  # noqa: BLE001
        _beat()
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            now = float(_clock())
        except Exception:  # noqa: BLE001
            now = _time.time()
        doc = tick(now=now, probables_fn=probables_fn, injuries_fn=injuries_fn,
                   umpires_fn=umpires_fn)
        print("%s | tick=%d probables=%d injuries=%d facts=%d umps=%d" % (
            HEARTBEAT_COMPONENT, ticks, doc.get("probable_rows", 0),
            doc.get("injury_rows", 0), doc.get("edge_facts", 0),
            doc.get("umpire_rows", 0)), flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def _main() -> int:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(
        description="Supervised MLB context snapshotter (M31): probables/weather/"
                    "umps + injuries + deterministic edge facts, every 6h. No $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("mlb_context_runner | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("mlb_context_runner | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
