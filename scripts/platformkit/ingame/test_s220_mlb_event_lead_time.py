"""Focused checks for the S220 read-only lead-time analyzer."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame import s220_mlb_event_lead_time as s220


def _row(ts, runs, outs, pitcher):
    return {"ts": ts, "captured_at": ts, "score_home": runs, "score_away": 0,
            "outs": outs, "pitcher_id": pitcher}


def _write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="ascii")


def test_events_quantiles_placebo_and_censoring_are_reproducible(tmp_path):
    events = tmp_path / "events"
    ticks = tmp_path / "ticks"
    _write(events / "g1.jsonl", [_row("2026-09-01T00:00:00Z", 0, 0, 1),
                                   _row("2026-09-01T00:01:00Z", 1, 0, 1),
                                   _row("2026-09-01T00:02:00Z", 1, 1, 1),
                                   _row("2026-09-01T00:03:00Z", 1, 1, 2),
                                   _row("2026-09-01T00:04:00Z", 1, 2, 2)])
    _write(ticks / "g1.jsonl", [{"ts": "2026-08-31T23:57:00Z", "market_prob": 0.50},
                                  {"ts": "2026-08-31T23:58:00Z", "market_prob": 0.50},
                                  {"ts": "2026-09-01T00:00:30Z", "market_prob": 0.50},
                                  {"ts": "2026-09-01T00:01:30Z", "market_prob": 0.51},
                                  {"ts": "2026-09-01T00:02:30Z", "market_prob": 0.51},
                                  {"ts": "2026-09-01T00:03:30Z", "market_prob": 0.52}])
    report, rows = s220.analyze(events, ticks)
    assert report["frozen_move_threshold"] == 0.004
    assert report["classes"]["run_scored"]["event"] == {"n": 1, "right_censored": 0, "p50_sec": 30.0, "p90_sec": 30.0, "max_sec": 30.0}
    assert report["classes"]["out_recorded"]["event"]["right_censored"] == 1
    assert report["classes"]["pitching_change"]["event"]["p50_sec"] == 30.0
    assert {row["series"] for row in rows} == {"event", "placebo"}
    assert report["verdict"] == "CLOSED AT LIMIT"


def test_missing_event_store_is_closed_at_limit_and_artifacts_are_written(tmp_path):
    ticks = tmp_path / "ticks"
    _write(ticks / "g1.jsonl", [{"ts": "2026-09-01T00:00:00Z", "market_prob": 0.5},
                                  {"ts": "2026-09-01T00:00:31Z", "market_prob": 0.5}])
    report, rows = s220.analyze(tmp_path / "absent", ticks)
    out_json, out_csv = tmp_path / "summary.json", tmp_path / "lead_times.csv"
    s220.write(report, rows, out_json, out_csv)
    assert report["cadence"]["gap_p50_sec"] == 31.0 and rows == []
    assert json.loads(out_json.read_text(encoding="ascii"))["verdict"] == "CLOSED AT LIMIT"
    assert out_csv.read_text(encoding="ascii").startswith("event_class,series")
