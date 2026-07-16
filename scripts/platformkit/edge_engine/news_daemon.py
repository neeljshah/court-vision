"""scripts.platformkit.edge_engine.news_daemon -- supervised M45 entry.

THE GAP: news_facts.store_news (ESPN news feed -> headline fact rows) had NO
scheduled caller anywhere -- news_facts_nba.jsonl / news_facts_mlb.jsonl were
frozen at whatever the one-shot CLI backfill left them. This daemon is the news
sibling of m39's injury_daemon (same loop/heartbeat skeleton): every ~6h it
fetches the ESPN news feed for each wired sport and beats the M45 heartbeat.
Dedupe is (headline, published) -- the store is naturally append-only vintage
history without a snapshot_date stamp (unlike injury status, a headline+
timestamp pair never needs re-dating).

KNOWLEDGE/SUBSTRATE ONLY -- adds data depth, not edge. NO $ field, NO flag flip,
NO data/registry/ write.

Heartbeat: m45_news_facts -> data/cache/daemon_heartbeats/m45_news_facts.txt
Cadence: DEFAULT_INTERVAL_SEC = 21600 s (4 snapshots/day; mirrors m39/m31).
Repo-internal only; ASCII only; <=300 LOC.

Per-file test: scripts/platformkit/edge_engine/test_news_daemon.py
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

try:  # package import
    from scripts.platformkit.edge_engine.news_facts import store_news  # type: ignore
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.edge_engine.news_facts import store_news  # type: ignore

logger = logging.getLogger("news_daemon")

HEARTBEAT_COMPONENT = "m45_news_facts"
DEFAULT_INTERVAL_SEC = 21600.0

# Sports the ESPN news feed is wired for (news_facts._SPORT_PATHS).
SPORTS: Tuple[str, ...] = ("nba", "mlb")


def _beat(now_epoch: Optional[float] = None) -> None:
    """Write the M45 liveness heartbeat. Never raises."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("news_daemon heartbeat skipped: %s", exc)


def tick(*, now: float,
         sports: Tuple[str, ...] = SPORTS,
         http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
         store_fn: Optional[Callable[..., Tuple[int, int]]] = None) -> Dict[str, Any]:
    """One tick: fetch + store news for each wired sport, then heartbeat. Never
    raises; one sport raising never sinks the others."""
    store = store_fn if store_fn is not None else store_news
    doc: Dict[str, Any] = {"sports": {}}
    for sport in sports:
        try:
            fetched, added = store(sport, http_get=http_get)
            doc["sports"][sport] = {"fetched": int(fetched), "added": int(added)}
        except Exception as exc:  # noqa: BLE001 -- one bad feed must not sink the tick
            logger.warning("news_daemon %s tick raised: %s", sport, exc)
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
    """Run the news-fetch loop forever (or max_ticks). Never raises out;
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
        print("%s | tick=%d %s" % (HEARTBEAT_COMPONENT, ticks, summary), flush=True)
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
        description="Supervised NBA/MLB news snapshotter (M45): ESPN news feed "
                    "-> headline fact rows every 6h. Substrate, no $.")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("news_daemon | started interval=%ss component=%s"
          % (a.interval, HEARTBEAT_COMPONENT), flush=True)
    try:
        run(interval_sec=a.interval)
    except KeyboardInterrupt:
        print("news_daemon | stopped by KeyboardInterrupt", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
