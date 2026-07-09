"""scripts.platformkit.venue_history.build_price_series -- consolidator: reads
every per-market/per-game JSONL doc under data/venue_history/{kalshi,polymarket}/
(any depth -- flat sport dirs AND the series-keyed subdirs run_all_backfills
writes) and emits one GAME-DATED parquet per sport:
data/cache/inplay_odds/<sport>_price_series.parquet.

Sport bucketing uses each DOC's own "sport" field (every writer already
stamps it), never the directory name -- so it is correct regardless of
whether a file lives at kalshi/mlb/*.jsonl, kalshi/mlb/kxmlbtotal/*.jsonl, or
polymarket/mlb_2024plus/*.jsonl.

COLUMNS: sport, venue, game_date, ticker_or_slug, event_key, market_type,
side, ts (int64 epoch seconds), prob (float), traded (bool or None),
close_time, result_where_known. market_type for kalshi comes from the
series_ticker -> market_type map already declared in kalshi_series_spec
(moneyline|total|spread|team_total); polymarket rows are always "moneyline"
(the only market family either polymarket lane backfills). No $ or edge
columns (see no-edge-claims rule) -- this is a coverage/price corpus only.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no data/registry writes; every
int id column is .astype('int64'), never .astype(int).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_build_price_series.py -q
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.platformkit.odds_provider.kalshi_series_spec import SERIES_SPEC

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KALSHI_DIR = _REPO_ROOT / "data" / "venue_history" / "kalshi"
DEFAULT_POLYMARKET_DIR = _REPO_ROOT / "data" / "venue_history" / "polymarket"
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "cache" / "inplay_odds"

COLUMNS = ["sport", "venue", "game_date", "ticker_or_slug", "event_key",
           "market_type", "side", "ts", "prob", "traded", "close_time",
           "result_where_known"]

PARQUET_SCHEMA = pa.schema([
    ("sport", pa.string()), ("venue", pa.string()), ("game_date", pa.string()),
    ("ticker_or_slug", pa.string()), ("event_key", pa.string()),
    ("market_type", pa.string()), ("side", pa.string()),
    ("ts", pa.int64()), ("prob", pa.float64()), ("traded", pa.bool_()),
    ("close_time", pa.string()), ("result_where_known", pa.string()),
])

# The corpus (kalshi settled candles + polymarket price ticks, growing daily
# across every sport) is tens of millions of rows -- converting a whole
# sport's row-of-dicts list to a DataFrame in one shot OOM'd on a machine
# already under memory pressure from concurrent processes (see write_all).
# Flushing a bounded batch straight to the parquet's row groups keeps peak
# memory to BATCH_SIZE rows per sport in flight, never the full corpus.
BATCH_SIZE = 200_000


def series_to_market_type() -> Dict[str, str]:
    """series_ticker -> market_type, flattened from SERIES_SPEC (every sport,
    every pair). A series absent here (future spec addition) degrades to
    "unknown" at read time, never raises."""
    return {series: mt for pairs in SERIES_SPEC.values() for series, mt in pairs}


def _iter_jsonl(fp: Path) -> Iterator[Dict[str, Any]]:
    """Yield each parseable JSON-doc line of *fp*; a malformed line is
    skipped, never raises (one bad line must not drop a whole file)."""
    try:
        with fp.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(doc, dict):
                    yield doc
    except OSError:
        return


def _iso_to_epoch(ts: Any) -> Optional[int]:
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def kalshi_doc_to_rows(doc: Dict[str, Any], market_type_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """One kalshi settled-market doc -> one row per candle."""
    ticker = str(doc.get("ticker") or "")
    series = str(doc.get("series_ticker") or "")
    sport = str(doc.get("sport") or "unknown")
    close_time = doc.get("close_time") or None
    result = doc.get("result") or None
    market_type = market_type_map.get(series, "unknown")
    side = ticker.rsplit("-", 1)[-1] if "-" in ticker else None
    event_key = str(doc.get("event_ticker") or "")
    game_date = str(close_time)[:10] if close_time else None
    rows: List[Dict[str, Any]] = []
    for c in doc.get("candles") or []:
        if not isinstance(c, dict):
            continue
        ts = _iso_to_epoch(c.get("ts"))
        if ts is None:
            continue
        rows.append({
            "sport": sport, "venue": "kalshi", "game_date": game_date,
            "ticker_or_slug": ticker, "event_key": event_key,
            "market_type": market_type, "side": side,
            "ts": ts, "prob": c.get("prob"), "traded": c.get("traded"),
            "close_time": close_time, "result_where_known": result,
        })
    return rows


def polymarket_doc_to_rows(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One polymarket per-game doc (dailies lane1 or game_slug lane3, same
    shape) -> one row per price tick, HOME side only (the only side either
    lane fetches -- away = 1-prob is never fabricated here)."""
    sport = str(doc.get("sport") or "unknown")
    date = doc.get("date") or None
    slug = str(doc.get("market_slug") or doc.get("event_slug") or "")
    event_key = str(doc.get("event_slug") or "")
    outcome = doc.get("outcome_home_win")
    result = "home" if outcome == 1 else ("away" if outcome == 0 else None)
    rows: List[Dict[str, Any]] = []
    for p in doc.get("prices") or []:
        if not isinstance(p, dict):
            continue
        ts = _iso_to_epoch(p.get("ts"))
        if ts is None:
            continue
        rows.append({
            "sport": sport, "venue": "polymarket", "game_date": date,
            "ticker_or_slug": slug, "event_key": event_key,
            "market_type": "moneyline", "side": "home",
            "ts": ts, "prob": p.get("prob_home"), "traded": None,
            "close_time": None, "result_where_known": result,
        })
    return rows


def build_all(kalshi_dir: Path = DEFAULT_KALSHI_DIR,
             polymarket_dir: Path = DEFAULT_POLYMARKET_DIR) -> Dict[str, pd.DataFrame]:
    """Walk both venue trees (any depth), bucket rows by each doc's own
    "sport" field, return {sport: DataFrame}. Missing/empty trees -> {}."""
    market_type_map = series_to_market_type()
    by_sport: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if kalshi_dir.is_dir():
        for fp in kalshi_dir.rglob("*.jsonl"):
            for doc in _iter_jsonl(fp):
                for row in kalshi_doc_to_rows(doc, market_type_map):
                    by_sport[row["sport"]].append(row)
    if polymarket_dir.is_dir():
        for fp in polymarket_dir.rglob("*.jsonl"):
            for doc in _iter_jsonl(fp):
                for row in polymarket_doc_to_rows(doc):
                    by_sport[row["sport"]].append(row)
    frames: Dict[str, pd.DataFrame] = {}
    for sport, rows in by_sport.items():
        df = pd.DataFrame(rows, columns=COLUMNS)
        df["ts"] = df["ts"].astype("int64")
        frames[sport] = df
    return frames


def write_all(out_dir: Path = DEFAULT_OUT_DIR, kalshi_dir: Path = DEFAULT_KALSHI_DIR,
             polymarket_dir: Path = DEFAULT_POLYMARKET_DIR,
             batch_size: int = BATCH_SIZE) -> Dict[str, int]:
    """Stream every row straight to its sport's parquet in bounded batches
    (never holds a whole sport's rows in memory -- see BATCH_SIZE). One
    ParquetWriter per sport, opened lazily on that sport's first flush.
    Returns {sport: n_rows_written} -- never a $ or edge field."""
    out_dir.mkdir(parents=True, exist_ok=True)
    market_type_map = series_to_market_type()
    buffers: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    writers: Dict[str, pq.ParquetWriter] = {}
    counts: Dict[str, int] = defaultdict(int)

    def _flush(sport: str) -> None:
        rows = buffers[sport]
        if not rows:
            return
        table = pa.Table.from_pylist(rows, schema=PARQUET_SCHEMA)
        if sport not in writers:
            path = out_dir / ("%s_price_series.parquet" % sport)
            writers[sport] = pq.ParquetWriter(str(path), PARQUET_SCHEMA)
        writers[sport].write_table(table)
        counts[sport] += len(rows)
        buffers[sport] = []

    def _absorb(rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            sport = row["sport"]
            buffers[sport].append(row)
            if len(buffers[sport]) >= batch_size:
                _flush(sport)

    try:
        if kalshi_dir.is_dir():
            for fp in kalshi_dir.rglob("*.jsonl"):
                for doc in _iter_jsonl(fp):
                    _absorb(kalshi_doc_to_rows(doc, market_type_map))
        if polymarket_dir.is_dir():
            for fp in polymarket_dir.rglob("*.jsonl"):
                for doc in _iter_jsonl(fp):
                    _absorb(polymarket_doc_to_rows(doc))
        for sport in list(buffers.keys()):
            _flush(sport)
    finally:
        for w in writers.values():
            w.close()
    return dict(counts)


def main() -> None:
    counts = write_all()
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()


__all__ = [
    "series_to_market_type", "kalshi_doc_to_rows", "polymarket_doc_to_rows",
    "build_all", "write_all", "COLUMNS", "PARQUET_SCHEMA", "BATCH_SIZE",
    "DEFAULT_KALSHI_DIR", "DEFAULT_POLYMARKET_DIR", "DEFAULT_OUT_DIR",
]
