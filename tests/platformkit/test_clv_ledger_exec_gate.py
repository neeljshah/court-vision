"""Tests for the record_bet exec-quality stamps (pregame exec-gate wiring, F1).

The pregame funnel (run_paper_today._record_priced -> clv_ledger.record_bet)
wrote NO execution-quality fields, so the m44 exec-evidence reader counted every
pregame row as ungated. Fix: record_bet now persists optional exec_gate /
placement_latency_ms / exec_gate_error, additive + backward-compat (absent ->
field omitted, byte-identical to a pre-fix row), mirroring the paper_ingame path.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/test_clv_ledger_exec_gate.py -q
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit import clv_ledger as clv


def test_exec_stamps_persisted_when_present(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    gate = {"passed": True, "expected_clv_pct": 12.0, "threshold_pct": 1.0}
    row = clv.record_bet(
        "nba", "BOS@NYK", "home", "DraftKings", 1.91,
        model_prob=0.58, stake_units=1.0, event_id="evt1", path=ledger,
        exec_gate=gate, placement_latency_ms=3.5,
    )
    assert row["exec_gate"] == gate
    assert row["placement_latency_ms"] == 3.5
    assert "exec_gate_error" not in row
    on_disk = ledger.read_text(encoding="utf-8")
    assert "expected_clv_pct" in on_disk


def test_exec_gate_error_stamped_when_present(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    row = clv.record_bet(
        "nba", "BOS@NYK", "home", "DraftKings", 1.91,
        model_prob=0.58, stake_units=1.0, event_id="evt1", path=ledger,
        exec_gate=None, placement_latency_ms=1.0, exec_gate_error="RuntimeError",
    )
    assert row["exec_gate_error"] == "RuntimeError"
    assert "exec_gate" not in row  # ungated on error -> field absent


def test_exec_stamps_omitted_when_absent_backward_compat(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    row = clv.record_bet(
        "nba", "BOS@NYK", "home", "DraftKings", 1.91,
        model_prob=0.55, stake_units=1.0, event_id="evt1", path=ledger,
    )
    assert "exec_gate" not in row
    assert "placement_latency_ms" not in row
    assert "exec_gate_error" not in row
    # bet_id unchanged by the additive stamps (excludes them by construction).
    assert row["bet_id"] == clv.bet_id(row)
