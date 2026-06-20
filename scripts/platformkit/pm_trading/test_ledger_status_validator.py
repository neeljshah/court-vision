"""test_ledger_status_validator.py -- per-file tests for ledger_status_validator.

Acceptance criteria (BE-R4-4):
  1. Clean ledger (open + settled twins) -> pass_=True, no collisions, no orphans
  2. Same-status duplicate (two "open" rows, same bet_id) -> collision flagged,
     pass_=False, collision_keys lists the offending (bet_id, status)
  3. Settled row with no open twin -> orphan flagged, pass_=False,
     orphan_ids lists the offender
  4. Multiple bet_ids -- only the bad ones are flagged, clean ones pass
  5. Empty ledger -> pass_=True, zero counts
  6. READ-ONLY: validator never mutates the input list
  7. No $/dollar/pnl/roi field in StatusValidationResult
  8. CLI exits 0 on pass, 1 on fail
  9. policy_stamp collision still detected (covers all status values)
  10. Settled + open twin present -> orphan check does NOT fire

Run ONLY this file (full suite freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    scripts/platformkit/pm_trading/test_ledger_status_validator.py -q
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

from scripts.platformkit.pm_trading.ledger_status_validator import (
    INSUFFICIENT_DATA,
    StatusValidationResult,
    _main,
    validate_ledger_status,
)


# ---------------------------------------------------------------------------
# Row-builder helpers
# ---------------------------------------------------------------------------

def _open(bet_id: str, sport: str = "nba", matchup: str = "BOS@NYK") -> Dict[str, Any]:
    return {
        "status": "open",
        "bet_id": bet_id,
        "sport": sport,
        "matchup": matchup,
        "side": "home",
        "taken_decimal": 1.95,
        "stake_units": 1.0,
        "tier": "B",
        "flat_unit": 1.0,
        "quarter_kelly": 0.05,
        "executed": False,
    }


def _settled(bet_id: str, sport: str = "nba", matchup: str = "BOS@NYK") -> Dict[str, Any]:
    return {
        "status": "settled",
        "bet_id": bet_id,
        "sport": sport,
        "matchup": matchup,
        "side": "home",
        "taken_decimal": 1.95,
        "stake_units": 1.0,
        "clv_pct": 1.5,
        "beat_close": True,
    }


def _stamp(bet_id: str, tier: str = "B") -> Dict[str, Any]:
    return {
        "status": "policy_stamp",
        "bet_id": bet_id,
        "tier": tier,
        "flat_unit": 1.0,
        "quarter_kelly": 0.05,
    }


# ---------------------------------------------------------------------------
# Test 1: clean ledger (open + settled twins) -> pass_=True
# ---------------------------------------------------------------------------

def test_clean_open_and_settled_twins_pass():
    """A well-formed ledger with matching open/settled pairs must pass."""
    rows = [
        _open("BET_001"),
        _settled("BET_001"),
        _open("BET_002"),
        _settled("BET_002"),
    ]
    result = validate_ledger_status(raw_rows=rows)

    assert result.pass_ is True, "Clean open+settled twins should pass"
    assert result.collision_keys == [], "No collisions expected"
    assert result.orphan_ids == [], "No orphans expected"
    assert result.total_rows == 4
    assert result.total_bets == 2


# ---------------------------------------------------------------------------
# Test 2: two "open" rows with same bet_id -> collision flagged, pass_=False
# ---------------------------------------------------------------------------

def test_duplicate_open_rows_collision():
    """Two open rows with the same bet_id must be flagged as a collision."""
    rows = [
        _open("DUP_OPEN"),
        _open("DUP_OPEN"),  # second open for same bet_id = collision
    ]
    result = validate_ledger_status(raw_rows=rows)

    assert result.pass_ is False, "Duplicate open rows must fail"
    assert len(result.collision_keys) == 1
    assert ("DUP_OPEN", "open") in result.collision_keys, (
        "collision_keys must list the offending (bet_id, status)"
    )


# ---------------------------------------------------------------------------
# Test 3: settled row with no open twin -> orphan flagged, pass_=False
# ---------------------------------------------------------------------------

def test_settled_without_open_twin_is_orphan():
    """A settled row that has no matching open twin must be flagged as an orphan."""
    rows = [
        _settled("ORPHAN_001"),  # no open row with this bet_id
    ]
    result = validate_ledger_status(raw_rows=rows)

    assert result.pass_ is False, "Orphan settled row must fail"
    assert "ORPHAN_001" in result.orphan_ids, (
        "orphan_ids must list bet_ids with settled but no open row"
    )
    assert result.collision_keys == [], "No collision, only an orphan"


# ---------------------------------------------------------------------------
# Test 4: mixed ledger -- only bad bet_ids flagged
# ---------------------------------------------------------------------------

def test_mixed_ledger_only_bad_flagged():
    """With clean and dirty rows, only the dirty bet_ids appear in results."""
    rows = [
        # clean twin
        _open("CLEAN_001"),
        _settled("CLEAN_001"),
        # collision (two settled rows for same bet_id)
        _open("BAD_DUP"),
        _settled("BAD_DUP"),
        _settled("BAD_DUP"),  # second settled = collision
        # orphan (settled with no open)
        _settled("BAD_ORPHAN"),
    ]
    result = validate_ledger_status(raw_rows=rows)

    assert result.pass_ is False
    # Only the collision bet_id (settled twice) should appear
    assert ("BAD_DUP", "settled") in result.collision_keys, (
        "BAD_DUP settled collision must be in collision_keys"
    )
    # Clean bet_id must NOT appear
    assert ("CLEAN_001", "open") not in result.collision_keys
    assert ("CLEAN_001", "settled") not in result.collision_keys
    # Orphan check
    assert "BAD_ORPHAN" in result.orphan_ids
    assert "CLEAN_001" not in result.orphan_ids


# ---------------------------------------------------------------------------
# Test 5: empty ledger -> pass_=True, zeros
# ---------------------------------------------------------------------------

def test_empty_ledger_passes():
    """An empty ledger is vacuously valid."""
    result = validate_ledger_status(raw_rows=[])

    assert result.pass_ is True
    assert result.collision_keys == []
    assert result.orphan_ids == []
    assert result.total_rows == 0
    assert result.total_bets == 0


# ---------------------------------------------------------------------------
# Test 6: read-only invariant
# ---------------------------------------------------------------------------

def test_read_only_does_not_mutate_input():
    """validate_ledger_status must NOT mutate the input list."""
    rows: List[Dict[str, Any]] = [
        _open("MUT_001"),
        _settled("ORPHAN_MUT"),
    ]
    original = copy.deepcopy(rows)

    validate_ledger_status(raw_rows=rows)

    assert rows == original, "validate_ledger_status must not mutate input rows"


# ---------------------------------------------------------------------------
# Test 7: no $/dollar/pnl/roi field in StatusValidationResult
# ---------------------------------------------------------------------------

def test_no_dollar_fields_in_result():
    """StatusValidationResult must never contain money/ROI fields."""
    rows = [_open("MONEY_001"), _settled("MONEY_001")]
    result = validate_ledger_status(raw_rows=rows)

    result_str = str(result).lower()
    banned = ("dollar", "roi", "pnl", "profit", "revenue", "bankroll")
    for bad_word in banned:
        assert bad_word not in result_str, (
            "Banned field %r found in StatusValidationResult: %s" % (bad_word, result_str)
        )


# ---------------------------------------------------------------------------
# Test 8: CLI exits 0 on pass, 1 on fail
# ---------------------------------------------------------------------------

def test_cli_exit_code_pass(tmp_path: Path):
    """CLI must exit 0 for a clean ledger."""
    row_open = _open("CLI_CLEAN")
    row_settled = _settled("CLI_CLEAN")
    ledger = tmp_path / "clean.jsonl"
    ledger.write_text(
        json.dumps(row_open) + "\n" + json.dumps(row_settled) + "\n",
        encoding="utf-8",
    )
    code = _main(["--path", str(ledger)])
    assert code == 0, "CLI must exit 0 for a clean ledger"


def test_cli_exit_code_fail_collision(tmp_path: Path):
    """CLI must exit 1 when there is a collision."""
    row1 = _open("CLI_DUP")
    row2 = _open("CLI_DUP")  # duplicate open
    ledger = tmp_path / "collision.jsonl"
    ledger.write_text(
        json.dumps(row1) + "\n" + json.dumps(row2) + "\n",
        encoding="utf-8",
    )
    code = _main(["--path", str(ledger)])
    assert code == 1, "CLI must exit 1 on collision"


def test_cli_exit_code_fail_orphan(tmp_path: Path):
    """CLI must exit 1 when there is an orphan."""
    row_settled = _settled("CLI_ORPHAN")
    ledger = tmp_path / "orphan.jsonl"
    ledger.write_text(json.dumps(row_settled) + "\n", encoding="utf-8")
    code = _main(["--path", str(ledger)])
    assert code == 1, "CLI must exit 1 on orphan"


# ---------------------------------------------------------------------------
# Test 9: policy_stamp collision is detected (covers all statuses)
# ---------------------------------------------------------------------------

def test_policy_stamp_collision_detected():
    """Two policy_stamp rows with the same bet_id must also be flagged."""
    rows = [
        _open("STAMP_DUP"),
        _stamp("STAMP_DUP", tier="A"),
        _stamp("STAMP_DUP", tier="B"),  # duplicate policy_stamp
    ]
    result = validate_ledger_status(raw_rows=rows)

    assert result.pass_ is False, "Duplicate policy_stamp must fail"
    assert ("STAMP_DUP", "policy_stamp") in result.collision_keys


# ---------------------------------------------------------------------------
# Test 10: settled + open twin present -> orphan check does NOT fire
# ---------------------------------------------------------------------------

def test_settled_with_open_twin_not_orphan():
    """A settled row with a corresponding open twin must NOT be an orphan."""
    rows = [
        _open("TWIN_001"),
        _settled("TWIN_001"),
    ]
    result = validate_ledger_status(raw_rows=rows)

    assert result.pass_ is True
    assert result.orphan_ids == [], (
        "TWIN_001 has an open twin -- must not appear in orphan_ids"
    )


# ---------------------------------------------------------------------------
# Test 11: detail list structure for collisions
# ---------------------------------------------------------------------------

def test_detail_structure_collision():
    """Each collision detail entry must have finding, bet_id, status, count."""
    rows = [_open("DETAIL_COL"), _open("DETAIL_COL")]
    result = validate_ledger_status(raw_rows=rows)

    collision_details = [d for d in result.detail if d.get("finding") == "collision"]
    assert len(collision_details) == 1
    entry = collision_details[0]
    assert entry["bet_id"] == "DETAIL_COL"
    assert entry["status"] == "open"
    assert entry["count"] == 2


# ---------------------------------------------------------------------------
# Test 12: detail list structure for orphans
# ---------------------------------------------------------------------------

def test_detail_structure_orphan():
    """Each orphan detail entry must have finding and bet_id."""
    rows = [_settled("DETAIL_ORP")]
    result = validate_ledger_status(raw_rows=rows)

    orphan_details = [d for d in result.detail if d.get("finding") == "orphan"]
    assert len(orphan_details) == 1
    entry = orphan_details[0]
    assert entry["bet_id"] == "DETAIL_ORP"
    assert "settled" in str(entry.get("reason", "")).lower()
