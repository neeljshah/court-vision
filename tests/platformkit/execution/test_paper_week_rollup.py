import json
from datetime import datetime
from pathlib import Path

from scripts.platformkit.pm_trading.clv_daily_readout import rollup, write_readout


NOW = "2026-09-03T00:00:00+00:00"


def _maker(day: int, sport: str, index: int) -> dict:
    return {"status": "settled", "outcome": "win", "sport": sport,
            "settled_at": "2026-08-%02dT12:00:00+00:00" % day,
            "channel": "paper_ingame", "series": "paper_ingame_maker",
            "clv_units": 0.25 if index % 3 else -0.1,
            "tick_latency_sec": float(index + 1), "maker_fee_units": 0.01,
            "clv_status": "suspect_close" if index == 0 else "ok"}


def test_synthetic_week_reports_maker_series_and_wilson_interval() -> None:
    rows = [_maker(day, sport, index) for index, (day, sport) in enumerate(
        (day, sport) for day in range(1, 9) for sport in ("nba", "mlb", "nba"))]
    doc = rollup(rows, now_iso=NOW)
    assert doc["n_settled"] == 24
    assert doc["n_maker"] == 24
    assert doc["n_taker"] == 0
    assert doc["is_clv_suspect_share"] == round(1 / 24, 6)
    assert doc["fee_net_complete"] is True
    assert isinstance(doc["beat_rate_ci_95_pct"], list)
    assert len(doc["beat_rate_ci_95_pct"]) == 2
    assert doc["settled_by_sport"] == {"nba": 16, "mlb": 8}


def test_empty_and_absent_ledgers_are_no_data(tmp_path: Path) -> None:
    for ledger in (tmp_path / "empty.jsonl", tmp_path / "absent.jsonl"):
        if ledger.name == "empty.jsonl":
            ledger.write_text("", encoding="utf-8")
        out, memo = tmp_path / (ledger.stem + ".json"), tmp_path / (ledger.stem + ".md")
        doc = write_readout(ledger, out, memo, now_iso=NOW)
        assert doc["status"] == "no_data"
        numeric = ("n_records", "n_settled", "n_open", "n_integrity_flags", "n_legacy",
                   "n_maker", "n_taker", "gross_legacy_count", "is_clv_suspect_share",
                   "median_clv_units", "beat_rate_pct", "tick_latency_sec_p50",
                   "tick_latency_sec_p90", "staleness_days")
        assert all(doc[key] == "INSUFFICIENT" for key in numeric)
        assert json.loads(out.read_text(encoding="utf-8"))["n_settled"] == "INSUFFICIENT"
        # S71/F3: as_of stays ISO-parseable with no settled rows -- the caveat
        # moved to as_of_note. "<iso> (no rows)" made every consumer fail to
        # date the readout (envelope probe X06).
        assert doc["as_of"] == NOW
        assert datetime.fromisoformat(doc["as_of"]) is not None
        assert "no settled rows" in doc["as_of_note"]


def test_unit_result_without_outcome_is_integrity_flag() -> None:
    doc = rollup([{"status": "settled", "unit_result": 1.0}], now_iso=NOW)
    assert doc["n_settled"] == "INSUFFICIENT"
    assert doc["n_integrity_flags"] == 1
    assert doc["row_classes"]["integrity_flag"] == 1


def test_legacy_gross_row_never_counts_as_maker() -> None:
    row = {"status": "settled", "outcome": "win", "channel": "paper_ingame",
           "series": "paper_ingame", "taken_book": "paper_ingame",
           "exec_gate": {"execution_mode": "maker_only"}}
    doc = rollup([row], now_iso=NOW)
    assert doc["n_legacy"] == 1
    assert doc["gross_legacy_count"] == 1
    assert doc["n_maker"] == 0
