"""Construct checks for the S215 exhaustive tennis price census."""
import csv
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.platformkit.ingame.s215_tennis_inplay_census import CLASSES, classify_price_row, run_census


def _write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path, row_group_size=2)


def _state_rows() -> list[dict]:
    return [{"game_id": "match", "asof_idx": 1, "date": "2026-07-01"}]


def _build_data_root(root: Path) -> None:
    _write_table(root / "cache/inplay_odds/tennis_price_series.parquet", [
        {"event_key": "A", "ticker_or_slug": "A1", "ts": 90, "close_time": "1970-01-01T00:01:40Z", "settled_at": None},
        {"event_key": "A", "ticker_or_slug": "A2", "ts": 110, "close_time": "1970-01-01T00:01:40Z", "settled_at": None},
        {"event_key": "B", "ticker_or_slug": "B1", "ts": 125, "close_time": "1970-01-01T00:01:40Z", "settled_at": "1970-01-01T00:01:55Z"},
        {"event_key": "", "ticker_or_slug": "X", "ts": 100, "close_time": "1970-01-01T00:01:40Z", "settled_at": None},
    ])
    for name in (
        "tennis_states__atp.parquet", "tennis_states__wta.parquet",
        "tennis_gamestate__atp.parquet", "tennis_gamestate__wta.parquet",
        "tennis_setdetail__atp.parquet", "tennis_setdetail__wta.parquet",
    ):
        _write_table(root / "cache/ingame" / name, _state_rows())
    grade = root / "cache/ingame_grade/tennis"
    grade.mkdir(parents=True)
    (grade / "one.jsonl").write_text(json.dumps({"state_summary": "FINAL", "market_prob": None}) + "\n", encoding="ascii")
    (grade / "two.jsonl").write_text(json.dumps({"state_summary": "score", "market_prob": 0.5}) + "\n", encoding="ascii")


def test_classify_price_row_uses_no_interpolation():
    assert classify_price_row("event", 99, "1970-01-01T00:01:40Z") == "PRE_MATCH"
    assert classify_price_row("event", 101, "1970-01-01T00:01:40Z") == "IN_PLAY_NO_STATE"
    assert classify_price_row("event", 101, "1970-01-01T00:01:40Z", state_joinable=True) == "IN_PLAY_JOINED"
    assert classify_price_row("", 101, "1970-01-01T00:01:40Z") == "UNRESOLVED_KEY"


def test_run_census_exhaustively_writes_recomputable_per_event_summary(tmp_path: Path):
    root = tmp_path / "data"
    output = tmp_path / "evidence"
    _build_data_root(root)
    summary = run_census(root, output)
    assert summary["class_counts"] == {
        "PRE_MATCH": 1, "IN_PLAY_JOINED": 0, "IN_PLAY_NO_STATE": 1,
        "POST_MATCH": 1, "UNRESOLVED_KEY": 1,
    }
    assert sum(summary["class_counts"].values()) == summary["price_source"]["rows"] == 4
    assert summary["resolved_event_count"] == 2
    assert summary["ticker_or_slug_count"] == 3
    assert summary["grade_store"] == {"rows": 2, "final": 1, "priced": 1}
    assert summary["recoverable_state_rows"] == 0
    assert all(not source["tick_joinable_timestamp_columns"] for source in summary["state_sources"])
    with (output / "S215_tennis_inplay_census_2026-09-04_per_event.csv").open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    assert {name: sum(int(row[name]) for row in rows) for name in CLASSES} == {
        "PRE_MATCH": 1, "IN_PLAY_JOINED": 0, "IN_PLAY_NO_STATE": 1,
        "POST_MATCH": 1, "UNRESOLVED_KEY": 0,
    }
