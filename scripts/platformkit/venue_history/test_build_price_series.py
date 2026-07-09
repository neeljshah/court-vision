"""Tests for scripts.platformkit.venue_history.build_price_series. Offline,
tmp_path only -- NEVER writes a production parquet from a test."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.platformkit.venue_history import build_price_series as bps


def _write_jsonl(path: Path, docs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps(d) + "\n")


def test_kalshi_doc_to_rows_maps_market_type_and_side() -> None:
    doc = {
        "ticker": "KXMLBGAME-26JUN01-KC", "event_ticker": "KXMLBGAME-26JUN01",
        "series_ticker": "KXMLBGAME", "sport": "mlb",
        "close_time": "2026-06-01T23:00:00Z", "result": "yes",
        "candles": [{"ts": "2026-06-01T22:00:00Z", "prob": 0.55, "traded": True}],
    }
    rows = bps.kalshi_doc_to_rows(doc, bps.series_to_market_type())
    assert len(rows) == 1
    r = rows[0]
    assert r["market_type"] == "moneyline"
    assert r["side"] == "KC"
    assert r["game_date"] == "2026-06-01"
    assert isinstance(r["ts"], int)


def test_kalshi_doc_unknown_series_degrades_to_unknown_market_type() -> None:
    doc = {"ticker": "KXFOO-1-A", "series_ticker": "KXFOO", "sport": "mlb",
           "close_time": "2026-06-01T00:00:00Z", "result": "",
           "candles": [{"ts": "2026-06-01T00:00:00Z", "prob": 0.5, "traded": False}]}
    rows = bps.kalshi_doc_to_rows(doc, bps.series_to_market_type())
    assert rows[0]["market_type"] == "unknown"


def test_polymarket_doc_to_rows_home_side_only() -> None:
    doc = {"date": "2025-04-02", "event_slug": "mlb-dailies-2025-04-02",
           "market_slug": "mlb-nyy-bos-2025-04-02", "sport": "mlb",
           "home": "BOS", "away": "NYY", "outcome_home_win": 1, "closed": True,
           "token_home": "123", "prices": [{"ts": "2025-04-02T20:00:00Z", "prob_home": 0.6}]}
    rows = bps.polymarket_doc_to_rows(doc)
    assert len(rows) == 1
    r = rows[0]
    assert r["side"] == "home"
    assert r["result_where_known"] == "home"
    assert r["market_type"] == "moneyline"


def test_build_all_buckets_by_doc_sport_not_directory_name(tmp_path: Path) -> None:
    kalshi_dir = tmp_path / "kalshi"
    poly_dir = tmp_path / "polymarket"
    # kalshi file physically lives under a "wnba" dir but its own doc.sport
    # says "wnba" too -- consistent case, plus a mismatched-dir case below.
    _write_jsonl(kalshi_dir / "wnba" / "kxwnbaspread" / "A.jsonl", [{
        "ticker": "KXWNBASPREAD-1-A", "series_ticker": "KXWNBASPREAD", "sport": "wnba",
        "close_time": "2026-07-01T00:00:00Z", "result": "no",
        "candles": [{"ts": "2026-07-01T00:00:00Z", "prob": 0.4, "traded": True}],
    }])
    _write_jsonl(poly_dir / "mlb_2024plus" / "2025-04-02_mlb-games.jsonl", [{
        "date": "2025-04-02", "event_slug": "mlb-nyy-bos-2025-04-02",
        "market_slug": "mlb-nyy-bos-2025-04-02", "sport": "mlb",
        "outcome_home_win": None, "prices": [{"ts": "2025-04-02T20:00:00Z", "prob_home": 0.5}],
    }])
    frames = bps.build_all(kalshi_dir=kalshi_dir, polymarket_dir=poly_dir)
    assert set(frames.keys()) == {"wnba", "mlb"}
    assert len(frames["wnba"]) == 1
    assert len(frames["mlb"]) == 1
    assert list(frames["wnba"].columns) == bps.COLUMNS


def test_build_all_missing_dirs_returns_empty(tmp_path: Path) -> None:
    frames = bps.build_all(kalshi_dir=tmp_path / "no_kalshi", polymarket_dir=tmp_path / "no_poly")
    assert frames == {}


def test_write_all_emits_one_parquet_per_sport_with_int64_ts(tmp_path: Path) -> None:
    kalshi_dir = tmp_path / "kalshi"
    _write_jsonl(kalshi_dir / "nba" / "A.jsonl", [{
        "ticker": "KXNBAGAME-1-A", "series_ticker": "KXNBAGAME", "sport": "nba",
        "close_time": "2026-05-01T00:00:00Z", "result": "yes",
        "candles": [{"ts": "2026-05-01T00:00:00Z", "prob": 0.7, "traded": True}],
    }])
    out_dir = tmp_path / "out"
    counts = bps.write_all(out_dir=out_dir, kalshi_dir=kalshi_dir, polymarket_dir=tmp_path / "no_poly")
    assert counts == {"nba": 1}
    out_path = out_dir / "nba_price_series.parquet"
    assert out_path.is_file()
    df = pd.read_parquet(out_path)
    assert str(df["ts"].dtype) == "int64"
    assert len(df) == 1
