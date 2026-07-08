"""scripts.platformkit.edge_engine.injury_daemon -- supervised M39 entry.

THE GAP: injury_facts.store_injuries (ESPN availability feed -> structured fact
rows) had NO scheduled caller. MLB context (m31) snapshots MLB injuries every 6h,
but NBA/WNBA injuries were only ever written by a manual CLI run. This daemon is
the missing NBA (+WNBA) sibling: every ~6h it fetches the ESPN injuries feed for
each wired basketball sport, SNAPSHOT-DATES every row (as-of usable history: the
same injury re-captured on a new day is a fresh vintage row; a same-day re-run
adds 0), and beats the M39 heartbeat.

KNOWLEDGE/SUBSTRATE ONLY -- adds data depth, not edge. Snapshot-append JSONL with
snapshot_date vintages; downstream joins must be as-of on snapshot_date. Independent
branch (no depends_on): a dead tick is one red status entry, never blocks the stack.
NO $ field, NO flag flip, NO data/registry/ write.

Heartbeat: m39_injury_facts_nba -> data/cache/daemon_heartbeats/m39_injury_facts_nba.txt
Cadence: DEFAULT_INTERVAL_SEC = 21600 s (4 snapshots/day; injury reports move on
hour scales, not minutes -- mirrors m31_mlb_context).
Repo-internal only; ASCII only; <=300 LOC.

Per-file test: scripts/platformkit/edge_engine/test_injury_daemon.py
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

try:  # package import
    from scripts.platformkit.edge_engine.injury_facts import store_injuries  # type: ignore
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.edge_engine.injury_facts import store_injuries  # type: ignore

logger = logging.getLogger("injury_daemon")

HEARTBEAT_COMPONENT = "m39_injury_facts_nba"
DEFAULT_INTERVAL_SEC = 21600.0

# Basketball sports the ESPN injuries feed is wired for (injury_facts._SPORT_PATHS).
# MLB injuries are already snapshotted by m31_mlb_context, so this daemon deliberately
# covers only the basketball sports that had no scheduled caller.
SPORTS: Tuple[str, ...] = ("nba", "wnba")


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M39 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("injury_daemon heartbeat skipped: %s", exc)


def _today_iso() -> str:
    return _dt.date.today().isoformat()


def tick(*, now: float,
         sports: Tuple[str, ...] = SPORTS,
         snapshot_date: Optional[str] = None,
         http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
         store_fn: Optional[Callable[..., Tuple[int, int]]] = None) -> Dict[str, Any]:
    """One tick: snapshot-date + store injuries for each wired basketball sport,
    then heartbeat. Never raises; one sport raising never sinks the others."""
    snap = snapshot_date or _today_iso()
    store = store_fn if store_fn is not None else store_injuries
    doc: Dict[str, Any] = {"snapshot_date": snap, "sports": {}}
    for sport in sports:
        try:
            fetched, added = store(sport, http_get=http_get, snapshot_date=snap)
            doc["sports"][sport] = {"fetched": int(fetched), "added": int(added)}
        except Exception as exc:  # noqa: BLE001 -- one bad feed must not sink the tick
            logger.warning("injury_daemon %s tick raised: %s", sport, exc)
            doc["sports"][sport] = {"error": type(exc).__name__}
    _beat(now)
    return doc


def run(*, interval_sec: float = DEFAULT_INTERVAL_SEC,
        sports: Tuple[str, ...] = SPORTS,
        http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
        store_fn: Optional[Callable[..., Tuple[int, int]]] = None,
        clock: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Run the injury-snapshot loop forever (or max_ticks). Never raises out;
    everything injectable for offline tests. Returns ticks executed."""
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
        doc = tick(now=now, sports=sports, http_get=http_get, store_fn=store_fn)
        summary = " ".join(
            "%s=%s/%s" % (sp, d.get("added", "?"), d.get("fetched", d.get("error", "?")))
            for sp, d in doc.get("sports", {}).items())
        print("%s | tick=%d date=%s %s" % (
            HEARTBEAT_COMPONENT, ticks, doc.get("snapshot_date"), summary), flush=True)
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
        description="Supervised NBA/WNBA injury snapshotter (M39): ESPN injuries "
                    "feed -> snapshot-dated fact rows every 6h. Substrate, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("injury_daemon | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("injury_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
