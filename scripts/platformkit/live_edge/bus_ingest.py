"""scripts.platformkit.live_edge.bus_ingest -- tee-readers onto the event bus (A1).

Wraps EXISTING capture outputs -- never edits the writers (most are shared or
human-gated per L-S1). Each ingest_<source>() tails NEW lines since a stored
FileCursor offset (keyed by absolute source-file path) and appends them to the
bus with an HONEST ts_knowable: the record's own report/capture timestamp,
never event time (L-S2). Idempotent: a re-run with an unchanged corpus appends 0.

SOURCES DISCOVERED ON DISK (probed 2026-07-14):
  odds       data/cache/line_history/<sport>/<date>.jsonl   ts field: captured_at
  injuries   data/cache/edge_engine/injury_facts_<sport>.jsonl (m39)  ts: fetched_at
  gumbo      data/domains/mlb/gumbo_live/<game_pk>.jsonl     ts field: captured_at
  fotmob     data/domains/soccer_intl/fotmob_live/<match_id>.jsonl  ts: fetch_ts

PROBED-ABSENT (not wired here, documented honestly, no ingester written):
  wnba cdn -- data/domains/wnba/cdn_backfill/<game>/{boxscore,playbyplay}.json
  is a ONE-SHOT batch backfill file per game (no per-record capture timestamp,
  not an append-only incremental capture), so it does not fit the tail-since-
  cursor tee shape. Would need a different ingest pattern (whole-file diff) --
  out of A1 scope.

Repo-internal only; ASCII stdout; <=300 LOC.
"""
from __future__ import annotations

import json
import pathlib
from typing import Callable, Dict, Iterable, List

from scripts.platformkit.live_edge.bus import FileCursor, append_events

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LINE_HISTORY_DIR = REPO_ROOT / "data" / "cache" / "line_history"
INJURY_FACTS_DIR = REPO_ROOT / "data" / "cache" / "edge_engine"
GUMBO_LIVE_DIR = REPO_ROOT / "data" / "domains" / "mlb" / "gumbo_live"
FOTMOB_LIVE_DIR = REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_live"

CURSOR_NAME = "bus_ingest_cursors"


def _tail_new_lines(path: pathlib.Path, cursor: FileCursor) -> List[dict]:
    """Read lines appended to *path* since its stored cursor offset. Advances cursor."""
    key = str(path.resolve())
    offset = cursor.get(key)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= offset:
        return []
    new_lines = lines[offset:]
    cursor.set(key, len(lines))
    rows = []
    for ln in new_lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def _to_bus_rows(source: str, ts_field: str, records: Iterable[dict]) -> List[dict]:
    out = []
    for rec in records:
        ts = str(rec.get(ts_field, "")) if isinstance(rec, dict) else ""
        if not ts:
            continue  # ponytail: no honest ts_knowable -> drop rather than guess
        out.append({"source": source, "ts_captured": ts, "ts_knowable": ts, "payload": rec})
    return out


def ingest_odds(*, sports: Iterable[str] = (), cursor: FileCursor = None, bus_dir=None) -> int:
    """Tail every data/cache/line_history/<sport>/<date>.jsonl file. sports=() -> all discovered."""
    cursor = cursor or FileCursor(CURSOR_NAME)
    if not LINE_HISTORY_DIR.is_dir():
        return 0
    sport_dirs = [LINE_HISTORY_DIR / s for s in sports] if sports else [
        d for d in LINE_HISTORY_DIR.iterdir() if d.is_dir()
    ]
    n = 0
    for sdir in sport_dirs:
        if not sdir.is_dir():
            continue
        sport = sdir.name
        for f in sorted(sdir.glob("*.jsonl")):
            recs = _tail_new_lines(f, cursor)
            n += append_events(_to_bus_rows(f"odds:{sport}", "captured_at", recs), **_bd(bus_dir))
    return n


def ingest_injuries(*, sports: Iterable[str] = ("nba", "mlb", "wnba"), cursor: FileCursor = None,
                    bus_dir=None) -> int:
    """Tail data/cache/edge_engine/injury_facts_<sport>.jsonl (m39 output)."""
    cursor = cursor or FileCursor(CURSOR_NAME)
    n = 0
    for sport in sports:
        f = INJURY_FACTS_DIR / f"injury_facts_{sport}.jsonl"
        recs = _tail_new_lines(f, cursor)
        n += append_events(_to_bus_rows(f"injury:{sport}", "fetched_at", recs), **_bd(bus_dir))
    return n


def ingest_gumbo(*, cursor: FileCursor = None, bus_dir=None) -> int:
    """Tail every data/domains/mlb/gumbo_live/<game_pk>.jsonl file."""
    cursor = cursor or FileCursor(CURSOR_NAME)
    if not GUMBO_LIVE_DIR.is_dir():
        return 0
    n = 0
    for f in sorted(GUMBO_LIVE_DIR.glob("*.jsonl")):
        recs = _tail_new_lines(f, cursor)
        n += append_events(_to_bus_rows("gumbo:mlb", "captured_at", recs), **_bd(bus_dir))
    return n


def ingest_fotmob(*, cursor: FileCursor = None, bus_dir=None) -> int:
    """Tail every data/domains/soccer_intl/fotmob_live/<match_id>.jsonl file."""
    cursor = cursor or FileCursor(CURSOR_NAME)
    if not FOTMOB_LIVE_DIR.is_dir():
        return 0
    n = 0
    for f in sorted(FOTMOB_LIVE_DIR.glob("*.jsonl")):
        recs = _tail_new_lines(f, cursor)
        n += append_events(_to_bus_rows("fotmob:soccer_intl", "fetch_ts", recs), **_bd(bus_dir))
    return n


def _bd(bus_dir) -> Dict[str, pathlib.Path]:
    """Only pass bus_dir kwarg through when the caller set one (else use append_events' own default)."""
    return {} if bus_dir is None else {"bus_dir": bus_dir}


INGESTERS: Dict[str, Callable[..., int]] = {
    "odds": ingest_odds,
    "injuries": ingest_injuries,
    "gumbo": ingest_gumbo,
    "fotmob": ingest_fotmob,
}


def ingest_all(*, cursor: FileCursor = None, bus_dir=None) -> Dict[str, int]:
    """Run every wired ingester once (one shared cursor namespace). Returns counts appended."""
    cursor = cursor or FileCursor(CURSOR_NAME)
    return {name: fn(cursor=cursor, bus_dir=bus_dir) for name, fn in INGESTERS.items()}


def _main() -> int:  # pragma: no cover
    counts = ingest_all()
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
