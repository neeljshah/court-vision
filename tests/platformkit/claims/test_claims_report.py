"""Tests for scripts.platformkit.claims.claims_report -- P6 status report.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_claims_report.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.claims import claims_report as cr


class _FakeRegistry:
    def __init__(self, cards):
        self._cards = {c["card_id"]: c for c in cards}

    def get_all_latest(self):
        return self._cards


def _card(card_id, status="OPEN", scope="ingame"):
    return {"card_id": card_id, "status": status, "claim": "a test claim",
            "condition": {"scope": scope, "trigger": "quarter == 1"}, "expected_sign": "+"}


def test_build_rows_no_ledger_shows_zero_fired(tmp_path: Path):
    reg = _FakeRegistry([_card("card_a")])
    rows = cr.build_rows(registry_module=reg, ledger_path=tmp_path / "no_ledger.jsonl",
                         consumed_path=tmp_path / "no_consumed.jsonl")
    assert len(rows) == 1
    assert rows[0]["n_fired"] == 0
    assert rows[0]["fired_rate"] == "n/a (0 rows)"
    assert rows[0]["consumed"] is False


def test_build_rows_reads_ledger_and_consumed(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    consumed = tmp_path / "consumed.jsonl"
    ledger.write_text(json.dumps({"card_id": "card_a", "n_fired": 80, "n_total": 400,
                                  "verdict": "VALIDATED",
                                  "detail": {"cond_sign_match": True}}) + "\n", encoding="ascii")
    consumed.write_text(json.dumps({"card_id": "card_a"}) + "\n", encoding="ascii")
    reg = _FakeRegistry([_card("card_a", status="VALIDATED")])
    rows = cr.build_rows(registry_module=reg, ledger_path=ledger, consumed_path=consumed)
    assert rows[0]["n_fired"] == 80
    assert rows[0]["fired_rate"] == "20.0000%"
    assert rows[0]["halves_agree"] == "Y"
    assert rows[0]["consumed"] is True


def test_build_report_counts_and_no_edge_claim(tmp_path: Path):
    reg = _FakeRegistry([_card("card_a"), _card("card_b", status="REJECTED")])
    report = cr.build_report(registry_module=reg, ledger_path=tmp_path / "l.jsonl",
                             consumed_path=tmp_path / "c.jsonl")
    assert report["n_cards"] == 2
    assert report["counts"] == {"OPEN": 1, "REJECTED": 1}
    assert report["edge_claimed"] is False
    assert "highest_value_next_card" in report


def test_render_markdown_has_table_and_sections():
    report = cr.build_report(registry_module=_FakeRegistry([_card("card_a")]))
    md = cr.render_markdown(report)
    assert "# CLAIMS_STATUS" in md
    assert "card_a" in md
    assert "## Test commands + pass counts" in md
    assert "## Highest-value next card to register" in md
    assert "edge_claimed: False" in md


def test_write_status_writes_file_without_running_tests(tmp_path: Path):
    out = tmp_path / "sub" / "CLAIMS_STATUS.md"
    reg = _FakeRegistry([_card("card_a")])
    report = cr.write_status(path=out, run_test_files=False, registry_module=reg)
    assert out.is_file()
    assert "CLAIMS_STATUS" in out.read_text(encoding="ascii")
    assert report["test_results"] == []


def test_real_registry_report_is_honest_10_cards_zero_validated():
    """Sanity check against the real on-disk registry: matches the known engine state."""
    report = cr.build_report()
    assert report["n_cards"] == 10
    assert report["n_validated"] == 0
