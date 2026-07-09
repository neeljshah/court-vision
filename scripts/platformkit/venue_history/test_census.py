"""Tests for scripts.platformkit.venue_history.census. Offline, tmp_path only
-- never touches the real data/ tree."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.venue_history import census


def _write_jsonl(path: Path, docs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d) + "\n")


def test_census_dir_counts_files_and_sums_n_candles(tmp_path: Path) -> None:
    d = tmp_path / "mlb"
    _write_jsonl(d / "KXMLBGAME-A.jsonl", [{"n_candles": 10}])
    _write_jsonl(d / "KXMLBGAME-B.jsonl", [{"n_candles": 20}])
    result = census.census_dir(d)
    assert result["n_files"] == 2
    assert result["n_rows_estimate"] == 30


def test_census_dir_empty_returns_zero(tmp_path: Path) -> None:
    d = tmp_path / "empty_sport"
    d.mkdir()
    result = census.census_dir(d)
    assert result["n_files"] == 0
    assert result["n_rows_estimate"] == 0
    assert result["min_date"] is None


def test_census_dir_reads_polymarket_date_prefixed_filenames(tmp_path: Path) -> None:
    d = tmp_path / "mlb"
    _write_jsonl(d / "2025-04-02_mlb-games.jsonl", [{"n_prices": 5}])
    _write_jsonl(d / "2025-04-05_mlb-games.jsonl", [{"n_prices": 7}])
    result = census.census_dir(d)
    assert result["min_date"] == "2025-04-02"
    assert result["max_date"] == "2025-04-05"


def test_census_venue_walks_sport_and_series_subdirs(tmp_path: Path) -> None:
    venue = tmp_path / "kalshi"
    _write_jsonl(venue / "mlb" / "KXMLBGAME-A.jsonl", [{"n_candles": 3}])
    _write_jsonl(venue / "mlb" / "kxmlbtotal" / "KXMLBTOTAL-A.jsonl", [{"n_candles": 4}])
    result = census.census_venue(venue)
    assert "mlb" in result
    assert "mlb/kxmlbtotal" in result


def test_build_census_no_dollar_fields(tmp_path: Path) -> None:
    doc = census.build_census(tmp_path / "does_not_exist")
    dumped = json.dumps(doc)
    assert "$" not in dumped
    assert "roi" not in dumped.lower()


def test_write_census_writes_valid_json(tmp_path: Path) -> None:
    out = tmp_path / "ops" / "venue_history_census.json"
    doc = census.write_census(out_path=out, venue_history_dir=tmp_path / "vh_missing")
    assert out.is_file()
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["generated_at"] == doc["generated_at"]
