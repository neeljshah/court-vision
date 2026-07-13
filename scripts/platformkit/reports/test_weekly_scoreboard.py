"""Tests for scripts.platformkit.reports.weekly_scoreboard."""

import json
import re

from scripts.platformkit.reports import weekly_scoreboard as ws

BANNED = re.compile(r"(?i)\broi\b|\bbankroll\b|\bpnl\b|\$")


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_week_bounds_and_arg_roundtrip():
    start, end = ws.week_bounds(2026, 29)
    assert (start.isoformat(), end.isoformat()) == ("2026-07-13", "2026-07-19")
    assert ws.parse_week_arg("2026-W29") == (2026, 29)


def test_week_boundary_correctness(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _write_jsonl(ledger, [
        {"computed_at": "2026-07-12T10:00:00+00:00", "verdict": "NULL"},   # Sun, week 28 -- excluded
        {"computed_at": "2026-07-13T10:00:00+00:00", "verdict": "NULL"},   # Mon, week 29 -- included
        {"computed_at": "2026-07-19T23:59:00+00:00", "verdict": "NULL"},   # Sun, week 29 -- included
        {"computed_at": "2026-07-20T00:01:00+00:00", "verdict": "NULL"},   # Mon, week 30 -- excluded
    ])
    monkeypatch.setattr(ws, "INTERACTION_LEDGER", ledger)
    start, end = ws.week_bounds(2026, 29)
    _lines, week_rows = ws.render_gate_throughput(start, end)
    assert len(week_rows) == 2


def test_render_gate_throughput_survivors_and_histogram(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    _write_jsonl(ledger, [
        {"computed_at": "2026-07-13T10:00:00+00:00", "verdict": "NULL", "candidate_id": "a"},
        {"computed_at": "2026-07-14T10:00:00+00:00", "verdict": "SURVIVES_PREREG_PROVISIONAL", "candidate_id": "b"},
    ])
    monkeypatch.setattr(ws, "INTERACTION_LEDGER", ledger)
    start, end = ws.week_bounds(2026, 29)
    lines, week_rows = ws.render_gate_throughput(start, end)
    text = "\n".join(lines)
    assert "Candidates tested: 2" in text
    assert "NULL: 1" in text
    assert "Survivors (1):" in text
    assert "b [SURVIVES_PREREG_PROVISIONAL]" in text


def test_render_replications_filters_by_key(tmp_path):
    week_rows = [
        {"verdict": "NULL"},
        {"verdict": "REPLICATED", "replication_of": "some_candidate"},
    ]
    lines = ws.render_replications(week_rows)
    text = "\n".join(lines)
    assert "Rows with replication_of this week: 1" in text
    assert "REPLICATED: 1" in text


def test_render_false_discovery_in_and_out_of_week(tmp_path, monkeypatch):
    fd = tmp_path / "fd.jsonl"
    _write_jsonl(fd, [
        {"date": "2026-07-12", "n_tested": 5, "expected_false_survivors": 0.1,
         "observed_survivors": 0, "within_noise_floor": True},
        {"date": "2026-07-14", "n_tested": 9, "expected_false_survivors": 0.2,
         "observed_survivors": 1, "within_noise_floor": False},
    ])
    monkeypatch.setattr(ws, "FALSE_DISCOVERY_LEDGER", fd)
    start, end = ws.week_bounds(2026, 29)
    lines = ws.render_false_discovery(start, end)
    text = "\n".join(lines)
    assert "2026-07-14" in text
    assert "2026-07-12" not in text


def test_render_false_discovery_zero_rows_this_week(tmp_path, monkeypatch):
    fd = tmp_path / "fd.jsonl"
    _write_jsonl(fd, [{"date": "2026-06-01", "n_tested": 1, "expected_false_survivors": 0.0,
                        "observed_survivors": 0, "within_noise_floor": True}])
    monkeypatch.setattr(ws, "FALSE_DISCOVERY_LEDGER", fd)
    start, end = ws.week_bounds(2026, 29)
    lines = ws.render_false_discovery(start, end)
    assert "0 rows this week." in lines


def test_missing_sources_degrade_honestly(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist.jsonl"
    monkeypatch.setattr(ws, "COVERAGE_MAP", tmp_path / "missing.md")
    monkeypatch.setattr(ws, "INTERACTION_LEDGER", missing)
    monkeypatch.setattr(ws, "FALSE_DISCOVERY_LEDGER", missing)
    monkeypatch.setattr(ws, "ROADMAP", tmp_path / "missing_roadmap.md")

    coverage_text = "\n".join(ws.render_coverage())
    assert "source missing: docs/research/DATA_COVERAGE_MAP.md" in coverage_text

    start, end = ws.week_bounds(2026, 29)
    gate_lines, week_rows = ws.render_gate_throughput(start, end)
    assert week_rows is None
    assert "source missing" in "\n".join(gate_lines)
    assert "source missing" in "\n".join(ws.render_replications(week_rows))
    assert "source missing" in "\n".join(ws.render_false_discovery(start, end))
    assert "source missing" in "\n".join(ws.render_proof_milestones())


def test_render_model_fleet_uses_real_registry():
    lines = ws.render_model_fleet()
    text = "\n".join(lines)
    assert "mlb/total_runs: champion=mlb_total_runs_market_baseline" in text
    assert "challenger=mlb_total_runs_mechanism_stack" in text
    # BENCHMARKED challenger with an on-disk JSON benchmark exposes its verdict
    assert "verdict=UNDERPOWERED" in text


def test_full_week_render_has_no_banned_tokens_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "OUTPUT_DIR", tmp_path)
    out_path = ws.write_week(2026, 29)
    assert out_path.is_file()
    text = out_path.read_text(encoding="utf-8")
    assert not BANNED.search(text), BANNED.search(text)
    assert "Weekly Scoreboard -- 2026-W29" in text


def test_main_cli_writes_expected_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "OUTPUT_DIR", tmp_path)
    ws.main(["--week", "2026-W29"])
    assert (tmp_path / "2026-W29.md").is_file()
