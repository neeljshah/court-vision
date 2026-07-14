"""Tests for the record_bet claim_tags persistence fix (claims-engine gap).

Grader found: run_paper_today._record_priced computed pregame claim_tags but
record_bet dropped the field on write, so pregame cards had zero on-disk
source. Fix: record_bet now persists an optional claim_tags field, additive
and backward-compat (absent -> field omitted, byte-identical to a pre-fix row).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/test_clv_ledger_claim_tags.py -q
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit import clv_ledger as clv


def test_claim_tags_persisted_when_present(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    row = clv.record_bet(
        "nba", "BOS@NYK", "home", "DraftKings", 1.91,
        model_prob=0.55, stake_units=1.0, event_id="evt1", path=ledger,
        claim_tags={"card_abc123": True, "card_def456": False},
    )
    assert row["claim_tags"] == {"card_abc123": True, "card_def456": False}
    on_disk = ledger.read_text(encoding="utf-8")
    assert "card_abc123" in on_disk


def test_claim_tags_omitted_when_absent_backward_compat(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    row = clv.record_bet(
        "nba", "BOS@NYK", "home", "DraftKings", 1.91,
        model_prob=0.55, stake_units=1.0, event_id="evt1", path=ledger,
    )
    assert "claim_tags" not in row


def test_claim_tags_empty_dict_also_omitted(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    row = clv.record_bet(
        "nba", "BOS@NYK", "home", "DraftKings", 1.91,
        model_prob=0.55, stake_units=1.0, event_id="evt1", path=ledger,
        claim_tags={},
    )
    assert "claim_tags" not in row
