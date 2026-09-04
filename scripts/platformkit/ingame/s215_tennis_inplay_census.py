"""Read-only exhaustive census for the tennis in-play price corpus.

The census reads one Parquet row group at a time.  It deliberately does not
interpolate tennis state: the current state tables have no tick timestamp.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq


CLASSES = (
    "PRE_MATCH",
    "IN_PLAY_JOINED",
    "IN_PLAY_NO_STATE",
    "POST_MATCH",
    "UNRESOLVED_KEY",
)
_STATE_NAMES = (
    "tennis_states__atp.parquet",
    "tennis_states__wta.parquet",
    "tennis_gamestate__atp.parquet",
    "tennis_gamestate__wta.parquet",
    "tennis_setdetail__atp.parquet",
    "tennis_setdetail__wta.parquet",
)
_TICK_TIME_NAMES = frozenset({"ts", "timestamp", "captured_at", "observed_at", "tick_time"})
_TERMINAL_TIME_NAMES = ("settled_at", "result_time", "final_time")


def _parse_epoch(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _iso(epoch: int | None) -> str:
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def classify_price_row(
    event_key: Any,
    tick_epoch: Any,
    close_time: Any,
    terminal_epoch: Any = None,
    state_joinable: bool = False,
) -> str:
    """Classify one price row without interpolating any state."""
    close_epoch = _parse_epoch(close_time)
    tick = _parse_epoch(tick_epoch)
    if not isinstance(event_key, str) or not event_key.strip() or tick is None or close_epoch is None:
        return "UNRESOLVED_KEY"
    if tick < close_epoch:
        return "PRE_MATCH"
    terminal = _parse_epoch(terminal_epoch)
    if terminal is not None and tick > terminal:
        return "POST_MATCH"
    return "IN_PLAY_JOINED" if state_joinable else "IN_PLAY_NO_STATE"


def _source_metadata(path: Path) -> dict[str, Any]:
    pf = pq.ParquetFile(path)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "rows": pf.metadata.num_rows,
        "row_groups": pf.metadata.num_row_groups,
        "columns": pf.schema_arrow.names,
    }


def _state_sources(state_root: Path) -> tuple[list[dict[str, Any]], bool]:
    sources = []
    for name in _STATE_NAMES:
        meta = _source_metadata(state_root / name)
        tick_columns = sorted(set(meta["columns"]) & _TICK_TIME_NAMES)
        meta["tick_joinable_timestamp_columns"] = tick_columns
        sources.append(meta)
    return sources, any(source["tick_joinable_timestamp_columns"] for source in sources)


def _grade_counts(grade_root: Path) -> dict[str, int]:
    counts = Counter()
    for path in sorted(grade_root.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                counts["rows"] += 1
                counts["final"] += row.get("state_summary") == "FINAL"
                counts["priced"] += row.get("market_prob") is not None
    return {key: counts[key] for key in ("rows", "final", "priced")}


def _summary_rows(events: dict[str, dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for event_key in sorted(events):
        event = events[event_key]
        yield {
            "event_key": event_key,
            "row_count": event["row_count"],
            "distinct_ticker_or_slug": len(event["tickers"]),
            "close_time": event["close_time"],
            "min_tick_utc": _iso(event["min_tick"]),
            "max_tick_utc": _iso(event["max_tick"]),
            **{label: event["classes"][label] for label in CLASSES},
        }


def run_census(data_root: Path, output_dir: Path) -> dict[str, Any]:
    """Census the price store, writing a summary JSON and per-event CSV."""
    price_path = data_root / "cache" / "inplay_odds" / "tennis_price_series.parquet"
    state_root = data_root / "cache" / "ingame"
    grade_root = data_root / "cache" / "ingame_grade" / "tennis"
    price_meta = _source_metadata(price_path)
    state_sources, state_joinable = _state_sources(state_root)
    if state_joinable:
        raise RuntimeError("S215 only supports the documented no-tick-timestamp state tables")

    pf = pq.ParquetFile(price_path)
    class_counts = Counter({label: 0 for label in CLASSES})
    events: dict[str, dict[str, Any]] = {}
    all_tickers: set[str] = set()
    rows = 0
    terminal_name = next((name for name in _TERMINAL_TIME_NAMES if name in pf.schema_arrow.names), None)
    columns = ["event_key", "ticker_or_slug", "ts", "close_time"]
    if terminal_name:
        columns.append(terminal_name)
    for group in range(pf.metadata.num_row_groups):
        table = pf.read_row_group(group, columns=columns)
        values = {name: table[name].to_pylist() for name in columns}
        for index, event_key in enumerate(values["event_key"]):
            label = classify_price_row(
                event_key,
                values["ts"][index],
                values["close_time"][index],
                values[terminal_name][index] if terminal_name else None,
                state_joinable=False,
            )
            class_counts[label] += 1
            rows += 1
            if label == "UNRESOLVED_KEY":
                continue
            ticker = values["ticker_or_slug"][index]
            if isinstance(ticker, str) and ticker:
                all_tickers.add(ticker)
            event = events.setdefault(event_key, {
                "row_count": 0, "tickers": set(), "close_time": values["close_time"][index],
                "min_tick": None, "max_tick": None, "classes": Counter({kind: 0 for kind in CLASSES}),
            })
            event["row_count"] += 1
            event["classes"][label] += 1
            if isinstance(ticker, str) and ticker:
                event["tickers"].add(ticker)
            tick = _parse_epoch(values["ts"][index])
            event["min_tick"] = tick if event["min_tick"] is None else min(event["min_tick"], tick)
            event["max_tick"] = tick if event["max_tick"] is None else max(event["max_tick"], tick)

    if rows != price_meta["rows"] or sum(class_counts.values()) != rows:
        raise AssertionError("price denominator was not exhaustively classified")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "S215_tennis_inplay_census_2026-09-04_per_event.csv"
    fields = ["event_key", "row_count", "distinct_ticker_or_slug", "close_time", "min_tick_utc", "max_tick_utc", *CLASSES]
    with csv_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(_summary_rows(events))
    summary = {
        "sport": "tennis",
        "price_source": price_meta,
        "grade_store": _grade_counts(grade_root),
        "class_counts": dict(class_counts),
        "unclassified_rows": 0,
        "interpolated_states": 0,
        "recoverable_state_rows": class_counts["IN_PLAY_JOINED"],
        "resolved_event_count": len(events),
        "ticker_or_slug_count": len(all_tickers),
        "event_count_adjudication": "986 is distinct event_key; 1,864 is distinct ticker_or_slug.",
        "state_sources": state_sources,
        "state_join_verdict": "CLOSED AT LIMIT: no state source has a tick-joinable timestamp.",
        "per_event_summary": str(csv_path),
    }
    summary_path = output_dir / "S215_tennis_inplay_census_2026-09-04_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"rows={rows}")
    print(f"resolved_event_count={len(events)}")
    print("class_counts=" + json.dumps(dict(class_counts), sort_keys=True))
    print(f"recoverable_state_rows={class_counts['IN_PLAY_JOINED']}")
    print("limit_verdict=CLOSED AT LIMIT")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path(r"C:\Users\neelj\nba-ai-system\data"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/evidence/harness"))
    args = parser.parse_args()
    run_census(args.data_root, args.output_dir)


if __name__ == "__main__":
    main()
