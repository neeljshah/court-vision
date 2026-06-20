"""test_ledger_completeness_audit.py -- per-file tests for ledger_completeness_audit.

Acceptance criteria (BE8-4):
  1. 5 clean + 2 status-dup rows -> dup_key_count==2, pass==False
  2. All-distinct status keys -> pass==True
  3. Missing-tier open rows are counted in missing_tier
  4. Settled rows without clv_pct are counted in missing_closing_line
  5. Report written to sidecar (atomic); ledger file byte-identical after run (no mutation)
  6. Missing ledger -> status=UNAVAILABLE, pass=False, never raises
  7. No $ key in report dict or written JSON
  8. CLI exits 0 on pass, 1 on fail

Run ONLY this file (full suite freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    scripts/platformkit/pm_trading/test_ledger_completeness_audit.py -q
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Hermetic import: prefer package path, fall back to inserting repo root
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.pm_trading.ledger_completeness_audit import (
    DEFAULT_REPORT,
    INSUFFICIENT_DATA,
    _main,
    run_audit,
)


# ---------------------------------------------------------------------------
# Row-builder helpers
# ---------------------------------------------------------------------------

def _open(bet_id: str, tier: object = "B", sport: str = "nba") -> Dict[str, Any]:
    """Build a synthetic open CLV row."""
    row: Dict[str, Any] = {
        "status": "open",
        "bet_id": bet_id,
        "sport": sport,
        "matchup": "BOS@NYK",
        "side": "home",
        "taken_book": "kalshi",
        "taken_decimal": 1.95,
        "stake_units": 1.0,
        "executed": False,
    }
    if tier is not None:
        row["tier"] = tier
    return row


def _settled(bet_id: str, clv_pct: object = 1.5) -> Dict[str, Any]:
    """Build a synthetic settled CLV row."""
    row: Dict[str, Any] = {
        "status": "settled",
        "bet_id": bet_id,
        "sport": "nba",
        "matchup": "BOS@NYK",
        "side": "home",
        "taken_decimal": 1.95,
        "stake_units": 1.0,
        "beat_close": True,
        "graded": True,
    }
    if clv_pct is not None:
        row["clv_pct"] = clv_pct
    return row


def _stamp(bet_id: str, tier: str = "A") -> Dict[str, Any]:
    """Build a policy_stamp row."""
    return {
        "status": "policy_stamp",
        "bet_id": bet_id,
        "tier": tier,
        "flat_unit": 1.0,
        "quarter_kelly": 0.05,
    }


# ---------------------------------------------------------------------------
# Test 1: 5 clean + 2 status-dup rows -> dup_key_count==2, pass==False
# ---------------------------------------------------------------------------

def test_five_clean_two_status_dups():
    """Core acceptance: 5 clean rows + 2 open-dup rows yields dup_key_count==2."""
    clean = [_open("C%d" % i) for i in range(5)]
    # Add 2 rows that share a status_key with existing clean rows
    # (same bet_id AND same status = true status-aware dup)
    dup1 = _open("C0")   # bet_id C0, status open -- same key as clean[0]
    dup2 = _open("C1")   # bet_id C1, status open -- same key as clean[1]
    rows = clean + [dup1, dup2]

    result = run_audit(raw_rows=rows)

    assert result["dup_key_count"] == 2, (
        "Expected 2 dup keys, got %d" % result["dup_key_count"]
    )
    assert result["pass"] is False, "pass must be False when dup_key_count>0"
    assert len(result["dup_keys"]) == 2


def test_five_clean_plus_settled_twins_not_dups():
    """open + settled twin share bet_id but have DISTINCT status keys -- not dups."""
    rows = []
    for i in range(5):
        bid = "BET_%d" % i
        rows.append(_open(bid))
        rows.append(_settled(bid))  # twin: same bet_id, different status

    result = run_audit(raw_rows=rows)

    assert result["dup_key_count"] == 0, (
        "Open+settled twins must NOT be counted as dups; got %d" % result["dup_key_count"]
    )
    assert result["pass"] is True
    assert result["total_open"] == 5
    assert result["total_settled"] == 5


# ---------------------------------------------------------------------------
# Test 2: All-distinct status keys -> pass==True
# ---------------------------------------------------------------------------

def test_all_distinct_status_keys_pass():
    """A ledger where every (bet_id, status) pair is unique must pass."""
    rows = [_open("X%d" % i) for i in range(7)]
    result = run_audit(raw_rows=rows)

    assert result["pass"] is True
    assert result["dup_key_count"] == 0
    assert result["dup_keys"] == []
    assert result["status"] == "CLEAN"


# ---------------------------------------------------------------------------
# Test 3: Missing-tier open rows counted
# ---------------------------------------------------------------------------

def test_missing_tier_rows_counted():
    """Open rows without tier (inline or stamp) must appear in missing_tier."""
    rows = [
        _open("GOOD_1"),              # has tier="B"
        _open("GOOD_2", tier="A"),    # has tier="A"
        _open("BAD_1", tier=None),    # no tier (None excluded from row by helper)
        _open("BAD_2", tier=None),    # no tier
    ]
    # Ensure tier is genuinely absent (not just None-valued) for BAD rows
    for row in rows:
        if row.get("tier") is None and "tier" in row:
            del row["tier"]

    result = run_audit(raw_rows=rows)

    assert result["missing_tier"] == 2, (
        "Expected 2 missing-tier rows, got %d" % result["missing_tier"]
    )
    assert result["pass"] is False


def test_stamp_fills_missing_tier():
    """A policy_stamp sibling that provides tier must prevent the row being flagged."""
    open_row = _open("STAMP_BET", tier=None)
    if "tier" in open_row:
        del open_row["tier"]
    stamp = _stamp("STAMP_BET", tier="B")
    rows = [open_row, stamp]

    result = run_audit(raw_rows=rows)

    # Stamp fills the gap -- must not be flagged
    assert result["missing_tier"] == 0, (
        "Stamp-filled row should not be counted as missing_tier"
    )


# ---------------------------------------------------------------------------
# Test 4: Settled rows without clv_pct counted in missing_closing_line
# ---------------------------------------------------------------------------

def test_missing_closing_line_counted():
    """Settled rows without clv_pct must appear in missing_closing_line."""
    rows = [
        _open("S1"),
        _settled("S1", clv_pct=2.1),   # has clv_pct -> OK
        _open("S2"),
        _settled("S2", clv_pct=None),  # clv_pct absent -> missing
        _open("S3"),
        _settled("S3", clv_pct=None),  # clv_pct absent -> missing
    ]
    # Remove clv_pct key entirely when None
    for row in rows:
        if row.get("status") == "settled" and row.get("clv_pct") is None:
            row.pop("clv_pct", None)

    result = run_audit(raw_rows=rows)

    assert result["missing_closing_line"] == 2, (
        "Expected 2 missing_closing_line rows, got %d" % result["missing_closing_line"]
    )
    assert result["pass"] is False


def test_settled_with_clv_pct_not_counted():
    """Settled rows that have clv_pct must NOT appear in missing_closing_line."""
    rows = [
        _open("OK1"),
        _settled("OK1", clv_pct=0.5),
        _open("OK2"),
        _settled("OK2", clv_pct=-1.0),
    ]
    result = run_audit(raw_rows=rows)

    assert result["missing_closing_line"] == 0
    assert result["pass"] is True


# ---------------------------------------------------------------------------
# Test 5: Report written to sidecar; ledger file byte-identical after run
# ---------------------------------------------------------------------------

def test_report_written_to_sidecar(tmp_path: Path):
    """run_audit must write sidecar JSON without mutating the ledger file."""
    # Write a clean ledger
    row1 = _open("SIDECAR_001")
    row2 = _settled("SIDECAR_001", clv_pct=1.0)
    ledger = tmp_path / "clv_ledger.jsonl"
    ledger.write_text(
        json.dumps(row1) + "\n" + json.dumps(row2) + "\n",
        encoding="utf-8",
    )

    # Capture ledger bytes before audit
    before_bytes = ledger.read_bytes()

    report_out = tmp_path / "ops" / "clv_ledger_audit_report.json"
    result = run_audit(ledger_path=ledger, report_path=report_out)

    # Ledger must be byte-identical after the run
    after_bytes = ledger.read_bytes()
    assert before_bytes == after_bytes, (
        "Ledger file was mutated by run_audit (byte counts differ)"
    )

    # Sidecar must exist and be valid JSON
    assert report_out.exists(), "Sidecar report was not written"
    with report_out.open("r", encoding="utf-8") as fh:
        sidecar = json.load(fh)

    assert sidecar["pass"] is True, "Clean ledger must produce pass=True in sidecar"
    assert "dup_key_count" in sidecar
    assert "missing_tier" in sidecar
    assert "missing_closing_line" in sidecar


# ---------------------------------------------------------------------------
# Test 6: Missing ledger -> status=UNAVAILABLE, pass=False, never raises
# ---------------------------------------------------------------------------

def test_missing_ledger_unavailable(tmp_path: Path):
    """When the ledger file does not exist the audit must return UNAVAILABLE."""
    absent = tmp_path / "no_such_ledger.jsonl"
    result = run_audit(ledger_path=absent, report_path=tmp_path / "ops" / "report.json")

    assert result["status"] == "UNAVAILABLE"
    assert result["pass"] is False
    assert result["total_rows"] == 0


def test_missing_ledger_never_raises(tmp_path: Path):
    """run_audit must never raise, even for a completely absent ledger."""
    absent = tmp_path / "not_here.jsonl"
    # Should not raise
    result = run_audit(ledger_path=absent, report_path=tmp_path / "r.json")
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 7: No $ key in report dict or written JSON
# ---------------------------------------------------------------------------

def test_no_dollar_keys_in_report():
    """The audit report must never contain dollar/pnl/roi keys."""
    rows = [_open("MONEY_001"), _settled("MONEY_001", clv_pct=1.2)]
    result = run_audit(raw_rows=rows)

    result_json = json.dumps(result).lower()
    banned = ("dollar", "roi", "pnl", "profit", "bankroll", "revenue")
    for word in banned:
        assert word not in result_json, (
            "Banned word '%s' found in audit report: %s" % (word, result_json[:200])
        )


def test_no_dollar_keys_in_sidecar(tmp_path: Path):
    """The written sidecar JSON must have no banned $ keys at the top level."""
    row = _open("D001")
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    report_out = tmp_path / "ops" / "r.json"

    run_audit(ledger_path=ledger, report_path=report_out)

    with report_out.open("r", encoding="utf-8") as fh:
        sidecar = json.load(fh)

    # Check top-level keys (not file-path values which may contain words)
    sidecar_keys = " ".join(str(k).lower() for k in sidecar.keys())
    banned = ("dollar", "roi", "pnl", "profit", "bankroll", "revenue")
    for word in banned:
        assert word not in sidecar_keys, (
            "Banned key '%s' found in sidecar top-level keys: %s" % (word, sidecar_keys)
        )


# ---------------------------------------------------------------------------
# Test 8: CLI exits 0 on pass, 1 on fail
# ---------------------------------------------------------------------------

def test_cli_exit_pass(tmp_path: Path):
    """CLI must exit 0 for a ledger with no issues."""
    row_open = _open("CLI_OK")
    row_settled = _settled("CLI_OK", clv_pct=0.8)
    ledger = tmp_path / "clean.jsonl"
    ledger.write_text(
        json.dumps(row_open) + "\n" + json.dumps(row_settled) + "\n",
        encoding="utf-8",
    )
    code = _main([
        "--path", str(ledger),
        "--report", str(tmp_path / "ops" / "r.json"),
    ])
    assert code == 0, "CLI must exit 0 for a clean ledger"


def test_cli_exit_fail_dups(tmp_path: Path):
    """CLI must exit 1 when duplicate status keys are found."""
    row = _open("DUP_CLI")
    ledger = tmp_path / "dups.jsonl"
    # Two rows with the same bet_id AND same status = status-dup
    ledger.write_text(
        json.dumps(row) + "\n" + json.dumps(row) + "\n",
        encoding="utf-8",
    )
    code = _main([
        "--path", str(ledger),
        "--report", str(tmp_path / "ops" / "r.json"),
    ])
    assert code == 1, "CLI must exit 1 when dups are found"


def test_cli_exit_fail_missing_tier(tmp_path: Path):
    """CLI must exit 1 when open rows have missing tier."""
    row = _open("MT_CLI", tier=None)
    if "tier" in row:
        del row["tier"]
    ledger = tmp_path / "mt.jsonl"
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    code = _main([
        "--path", str(ledger),
        "--report", str(tmp_path / "ops" / "r.json"),
    ])
    assert code == 1, "CLI must exit 1 when missing_tier>0"


# ---------------------------------------------------------------------------
# Test 9: Read-only -- input list not mutated (raw_rows path)
# ---------------------------------------------------------------------------

def test_read_only_no_mutation():
    """run_audit must NOT mutate the raw_rows list passed to it."""
    rows: List[Dict[str, Any]] = [
        _open("MUT_001"),
        _settled("MUT_001", clv_pct=None),
    ]
    original = copy.deepcopy(rows)

    run_audit(raw_rows=rows)

    assert rows == original, "run_audit must not mutate the input rows list"


# ---------------------------------------------------------------------------
# Test 10: total_open and total_settled counts are accurate
# ---------------------------------------------------------------------------

def test_row_counts_accurate():
    """total_open, total_settled and total_rows must be exact."""
    rows = (
        [_open("T%d" % i) for i in range(3)]
        + [_settled("S%d" % i, clv_pct=1.0) for i in range(4)]
        + [_stamp("ST_001")]
    )
    result = run_audit(raw_rows=rows)

    assert result["total_rows"] == 8          # 3 open + 4 settled + 1 stamp
    assert result["total_open"] == 3
    assert result["total_settled"] == 4


# ---------------------------------------------------------------------------
# Test 11: status==DUPS_FOUND when dups present; CLEAN when not
# ---------------------------------------------------------------------------

def test_status_field_dups_found():
    """status field must be DUPS_FOUND when any dup key is present."""
    row = _open("SF_DUP")
    result = run_audit(raw_rows=[row, row])
    assert result["status"] == "DUPS_FOUND"


def test_status_field_clean():
    """status field must be CLEAN when no dups present."""
    result = run_audit(raw_rows=[_open("SF_CLN")])
    assert result["status"] == "CLEAN"
