"""Focused synthetic tests for the measurement-only subshock latency audit."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame import subshock_latency_race as race


def _event(ts: str = "2026-01-01T12:00:00Z", **extra):
    row = {"game_id": "G1", "player": "Player One", "detect_ts": ts,
           "timestamp_basis": "pbp_ingest_ts", "source_path": "pbp/G1.json",
           "impact_on_home": -1, "line_history_date": "2026-01-01"}
    row.update(extra)
    return row


def _quotes(tmp_path: Path, rows: list[dict]) -> Path:
    root = tmp_path / "lines"
    root.mkdir()
    with (root / "2026-01-01.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return root


def _quote(ts: str, prob: float) -> dict:
    return {"game_id": "G1", "captured_at": ts, "market_type": "moneyline",
            "side": "home", "book": "book_a", "devigged_prob": prob}


def test_scores_pbp_detection_before_market_reprice(tmp_path):
    lines = _quotes(tmp_path, [_quote("2026-01-01T11:44:00Z", 0.60),
                               _quote("2026-01-01T11:50:00Z", 0.56)])
    row = race.score_event(_event(), lines)
    assert row["verdict"] == "AT_OR_BEFORE"
    assert row["delta_s"] == -600


def test_scores_detection_after_market_reprice(tmp_path):
    lines = _quotes(tmp_path, [_quote("2026-01-01T11:44:00Z", 0.60),
                               _quote("2026-01-01T12:10:00Z", 0.56)])
    row = race.score_event(_event(), lines)
    assert row["verdict"] == "AFTER"
    assert row["delta_s"] == 600


def test_reconstructed_clock_is_rejected(tmp_path):
    row = race.score_event(_event(timestamp_basis="pbp_clock_reconstructed"), tmp_path)
    assert row["verdict"] == "UNSCOREABLE"
    assert row["reason"] == "missing_data_native_pbp_or_stint_timestamp"


def test_missing_line_history_is_explicit_and_insufficient(tmp_path):
    row = race.score_event(_event(), tmp_path)
    report = race.render([row], 1)
    assert row["reason"] == "no_matching_line_history_quotes"
    assert "FAIL: INSUFFICIENT_SCOREABLE_EVENTS" in report
    assert "scoreable: 0" in report


def test_gate_requires_30_and_60_percent():
    rows = [{"verdict": "AT_OR_BEFORE"}] * 18 + [{"verdict": "AFTER"}] * 12
    assert race.verdict(rows) == ("PASS", 30, 0.6)
    assert race.verdict(rows[:-1]) == ("FAIL: INSUFFICIENT_SCOREABLE_EVENTS", 29, None)


def test_run_missing_event_manifest_has_zero_events(tmp_path):
    rows, count = race.run(tmp_path / "missing.jsonl", tmp_path / "lines")
    assert rows == []
    assert count == 0
