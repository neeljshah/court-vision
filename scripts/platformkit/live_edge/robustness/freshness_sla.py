"""scripts.platformkit.live_edge.robustness.freshness_sla -- per-source
freshness SLA rows for the A1 bus sources + A2 news capture (LIVE-EDGE A3).

PATTERN SOURCE (copied, not edited): scripts/platformkit/autonomy/freshness_sla.py
(declarative TABLE -> check -> write_status/load_status, NA-never-GREEN
discipline). This module re-derives the same shape for the live_edge sources
because those live inside shared per-date bus/news files (not one heartbeat
file per source), so "last seen" here means "max ts_knowable/report_ts for
this source across today's + yesterday's file", not an mtime probe.

SOURCES WIRED (verified fresh 2026-07-14 against real data):
  - bus_ingest.py L89/101/113/125 write source keys "odds:<sport>",
    "injury:<sport>", "gumbo:mlb", "fotmob:soccer_intl" (NOT "fotmob:soccer"
    -- the real bus key includes the domain suffix, confirmed by reading
    data/omni/live_edge/bus/2026-07-13.jsonl and 2026-07-14.jsonl, which show
    {odds:nba, odds:mlb, odds:wnba, odds:soccer, odds:soccer_intl, odds:tennis,
    odds:npb, odds:kbo, injury:nba, injury:wnba, gumbo:mlb, fotmob:soccer_intl}.
  - news/fetch.py capture_once() writes data/omni/live_edge/news/raw/<date>.jsonl
    with a "report_ts" field per row (no per-sport split -- one logical
    "news:espn" source covering both espn_nba_injuries + espn_nba_news).

STATUS: OK (within SLA) / STALE (1x-3x SLA) / DOWN (>3x SLA or never seen).
No ProcSpec/daemon owns these ingesters today (grepped supervisor/stack_specs
-- no hit), so SLA values here are conservative caps cited per-row, not tuned
against a verified daemon cadence (unlike the autonomy/ pattern's daemon rows).

HONESTY: read-only, no restart authority, no $ field, never writes
data/registry/, never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_freshness_sla.py -q
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

from scripts.platformkit.live_edge import bus
from scripts.platformkit.live_edge.bus import BUS_DIR

_REPO = Path(__file__).resolve().parents[4]
_NEWS_RAW_DIR = _REPO / "data" / "omni" / "live_edge" / "news" / "raw"
OUT_DIR = _REPO / "data" / "omni" / "live_edge" / "freshness"

OK = "OK"
STALE = "STALE"
DOWN = "DOWN"

# STALE/DOWN split: staleness within 1x SLA -> OK; 1x-3x -> STALE (probably a
# slow tick, not yet an incident); beyond 3x (or never seen) -> DOWN. The 3x
# multiplier mirrors the ~2.2x-3x house margin the autonomy/ pattern uses per
# daemon row, widened slightly here since these sources have no verified
# per-daemon cadence to anchor a tighter number to.
_STALE_MULTIPLE = 3.0


class SlaEntry(NamedTuple):
    kind: str  # "bus" or "news"
    sla_sec: float


# source -> SlaEntry. Every row cites the wiring evidence in the module docstring.
TABLE: Dict[str, SlaEntry] = {
    # odds:<sport> -- bus_ingest.ingest_odds, no verified capture-loop cadence
    # (script, not a ProcSpec); 1800s is a conservative cap, not a tuned value.
    "odds:nba": SlaEntry("bus", 1800.0),
    "odds:mlb": SlaEntry("bus", 1800.0),
    "odds:wnba": SlaEntry("bus", 1800.0),
    "odds:soccer": SlaEntry("bus", 1800.0),
    "odds:soccer_intl": SlaEntry("bus", 1800.0),
    "odds:tennis": SlaEntry("bus", 1800.0),
    "odds:npb": SlaEntry("bus", 1800.0),
    "odds:kbo": SlaEntry("bus", 1800.0),
    # injury:<sport> -- bus_ingest.ingest_injury; mirrors the 6h*2.2 margin the
    # autonomy/ TABLE uses for its own injury_facts_nba row (m39).
    "injury:nba": SlaEntry("bus", 45000.0),
    "injury:wnba": SlaEntry("bus", 45000.0),
    # gumbo:mlb -- bus_ingest.ingest_gumbo; live in-game tail, tight window.
    "gumbo:mlb": SlaEntry("bus", 900.0),
    # fotmob:soccer_intl -- bus_ingest.ingest_fotmob; live in-game tail.
    "fotmob:soccer_intl": SlaEntry("bus", 900.0),
    # news:espn -- news/fetch.capture_once, manual/CLI cadence (no daemon);
    # mirrors the autonomy/ TABLE's 48h manual-report margin.
    "news:espn": SlaEntry("news", 172800.0),
}


def _dates_back(n: int, *, now: Optional[float] = None) -> List[str]:
    ts = now if now is not None else time.time()
    today = datetime.fromtimestamp(ts, tz=timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n)]


def _latest_bus_ts(source: str, *, now: Optional[float] = None,
                    bus_dir: Path = BUS_DIR) -> Optional[str]:
    """Max ts_knowable for *source* across today + yesterday's bus file."""
    latest: Optional[str] = None
    for d in _dates_back(2, now=now):
        rows, _ = bus.read_events(d, bus_dir=bus_dir)
        for row in rows:
            if row.get("source") != source:
                continue
            ts = row.get("ts_knowable")
            if ts and (latest is None or ts > latest):
                latest = ts
    return latest


def _latest_news_ts(*, now: Optional[float] = None,
                     raw_dir: Path = _NEWS_RAW_DIR) -> Optional[str]:
    """Max report_ts across today + yesterday's news raw file."""
    latest: Optional[str] = None
    for d in _dates_back(2, now=now):
        p = raw_dir / f"{d}.jsonl"
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                ts = row.get("report_ts")
                if ts and (latest is None or ts > latest):
                    latest = ts
        except (OSError, json.JSONDecodeError):
            continue
    return latest


def _parse_iso(ts: str) -> Optional[float]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def check_one(source: str, *, now: Optional[float] = None,
              table: Optional[Dict[str, SlaEntry]] = None,
              bus_dir: Path = BUS_DIR, news_dir: Path = _NEWS_RAW_DIR) -> Dict[str, Any]:
    """OK/STALE/DOWN verdict for one source. A name absent from *table* is
    DOWN (unmonitored is never a silent pass). Never raises."""
    ts = float(now) if now is not None else time.time()
    tbl = table if table is not None else TABLE
    entry = tbl.get(source)
    if entry is None:
        return {"source": source, "status": DOWN, "last_seen": None,
                "staleness_sec": None, "sla_sec": None, "reason": "no_sla_entry"}
    try:
        last_seen = (_latest_bus_ts(source, now=ts, bus_dir=bus_dir) if entry.kind == "bus"
                     else _latest_news_ts(now=ts, raw_dir=news_dir))
        if last_seen is None:
            return {"source": source, "status": DOWN, "last_seen": None,
                    "staleness_sec": None, "sla_sec": entry.sla_sec, "reason": "never_seen"}
        last_epoch = _parse_iso(last_seen)
        if last_epoch is None:
            return {"source": source, "status": DOWN, "last_seen": last_seen,
                    "staleness_sec": None, "sla_sec": entry.sla_sec, "reason": "bad_ts"}
        staleness = max(0.0, ts - last_epoch)
        if staleness <= entry.sla_sec:
            status, reason = OK, None
        elif staleness <= entry.sla_sec * _STALE_MULTIPLE:
            status, reason = STALE, "stale"
        else:
            status, reason = DOWN, "down"
        return {"source": source, "status": status, "last_seen": last_seen,
                "staleness_sec": round(staleness, 1), "sla_sec": entry.sla_sec,
                "reason": reason}
    except Exception as exc:  # noqa: BLE001 -- a probe failure is DOWN, not a crash
        return {"source": source, "status": DOWN, "last_seen": None,
                "staleness_sec": None, "sla_sec": entry.sla_sec,
                "reason": f"error:{str(exc)[:80]}"}


def check_all(sources: Optional[List[str]] = None, *, now: Optional[float] = None,
              table: Optional[Dict[str, SlaEntry]] = None,
              bus_dir: Path = BUS_DIR, news_dir: Path = _NEWS_RAW_DIR) -> List[Dict[str, Any]]:
    """SLA rows for every wired source (or *sources* if given). Order-preserving."""
    tbl = table if table is not None else TABLE
    names = sources if sources is not None else list(tbl.keys())
    return [check_one(n, now=now, table=tbl, bus_dir=bus_dir, news_dir=news_dir) for n in names]


def sla_path(date: str, *, out_dir: Path = OUT_DIR) -> Path:
    return out_dir / f"sla_{date}.jsonl"


def write_rows(rows: List[Dict[str, Any]], *, date: Optional[str] = None,
               out_dir: Path = OUT_DIR) -> Path:
    """Append SLA rows to data/omni/live_edge/freshness/sla_<date>.jsonl (the
    pulse-surfaced artifact). One line per row, ascii, tmp+replace-free simple
    append (this is an append-only ledger like bus.py, not an atomic full-doc
    rewrite -- matches append_jsonl_atomic's own file shape)."""
    d = date or datetime.now(timezone.utc).date().isoformat()
    path = sla_path(d, out_dir=out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="ascii") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    return path


__all__ = [
    "SlaEntry", "TABLE", "OK", "STALE", "DOWN", "OUT_DIR",
    "check_one", "check_all", "sla_path", "write_rows",
]


if __name__ == "__main__":
    _rows = check_all()
    _path = write_rows(_rows)
    print(json.dumps({"path": str(_path), "rows": _rows}, indent=2))
