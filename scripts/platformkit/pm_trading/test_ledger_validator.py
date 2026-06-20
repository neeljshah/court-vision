"""test_ledger_validator.py -- per-file tests for ledger_validator (PT-10).

Acceptance criteria:
  1. 5 clean + 2 missing-tier rows -> missing_tier==2, pass_==False
  2. All-clean rows -> pass_==True
  3. Validator never mutates the input list (read-only invariant)
  4. Empty ledger -> pass_==True, missing_tier==0
  5. Rows with policy_stamp siblings get their tier filled -> not flagged
  6. No $ / dollar / roi / pnl field in result
  7. CLI: exit code 1 on fail, 0 on pass

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/pm_trading/test_ledger_validator.py -q
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import under test (hermetic: prefer package import; fall back to sibling)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.pm_trading.ledger_validator import (
    INSUFFICIENT_DATA,
    REQUIRED_POLICY_FIELDS,
    ValidationResult,
    _collect_stamps,
    _apply_stamps,
    _main,
    validate_ledger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_row(
    bet_id: str,
    tier: object = "B",
    flat_unit: float = 1.0,
    quarter_kelly: float = 0.05,
    sport: str = "nba",
    matchup: str = "BOS@NYK",
) -> dict:
    """Build a synthetic "open" CLV row."""
    row: dict = {
        "status": "open",
        "bet_id": bet_id,
        "sport": sport,
        "matchup": matchup,
        "side": "home",
        "taken_book": "kalshi",
        "taken_decimal": 1.95,
        "stake_units": 1.0,
        "executed": False,
    }
    if tier is not None:
        row["tier"] = tier
    if flat_unit is not None:
        row["flat_unit"] = flat_unit
    if quarter_kelly is not None:
        row["quarter_kelly"] = quarter_kelly
    return row


def _missing_tier_row(bet_id: str) -> dict:
    """An "open" row with tier explicitly absent (never stamped)."""
    return {
        "status": "open",
        "bet_id": bet_id,
        "sport": "nba",
        "matchup": "LAL@GSW",
        "side": "away",
        "taken_book": "polymarket",
        "taken_decimal": 2.10,
        "stake_units": 1.0,
        "executed": False,
        # tier, flat_unit, quarter_kelly deliberately absent
    }


def _stamp_row(bet_id: str, tier: str = "A") -> dict:
    """A policy_stamp sibling for the given bet_id."""
    return {
        "status": "policy_stamp",
        "bet_id": bet_id,
        "tier": tier,
        "flat_unit": 1.0,
        "quarter_kelly": 0.06,
        "ev": 0.09,
        "clv_is_proxy": False,
    }


# ---------------------------------------------------------------------------
# Test 1: 5 clean + 2 missing-tier -> missing_tier==2, pass_==False
# ---------------------------------------------------------------------------
def test_five_clean_two_missing():
    """Core acceptance criterion: mixed ledger correctly flags exactly 2 rows."""
    clean_rows = [_open_row(f"BET_{i:03d}") for i in range(5)]
    bad_rows = [_missing_tier_row(f"BAD_{i:03d}") for i in range(2)]
    rows = clean_rows + bad_rows

    result = validate_ledger(raw_rows=rows)

    assert result.missing_tier == 2, (
        f"Expected 2 missing-tier rows, got {result.missing_tier}"
    )
    assert result.pass_ is False, "Expected pass_=False when missing_tier>0"
    assert result.total_open == 7
    assert len(result.flagged_ids) == 2
    # Check flagged ids match the bad rows
    assert set(result.flagged_ids) == {"BAD_000", "BAD_001"}


# ---------------------------------------------------------------------------
# Test 2: All-clean rows -> pass_==True
# ---------------------------------------------------------------------------
def test_all_clean_pass():
    """All-stamped rows -> pass_=True, missing_tier=0."""
    rows = [_open_row(f"CLEAN_{i:03d}") for i in range(5)]
    result = validate_ledger(raw_rows=rows)

    assert result.pass_ is True
    assert result.missing_tier == 0
    assert result.total_open == 5
    assert result.flagged_ids == []


# ---------------------------------------------------------------------------
# Test 3: Validator never mutates the input list (read-only invariant)
# ---------------------------------------------------------------------------
def test_read_only_no_mutation():
    """validate_ledger must NOT mutate the rows passed to it."""
    rows = [_missing_tier_row("X001"), _open_row("X002")]
    original = copy.deepcopy(rows)

    validate_ledger(raw_rows=rows)

    assert rows == original, "validate_ledger must not mutate input rows"


# ---------------------------------------------------------------------------
# Test 4: Empty ledger -> pass_==True
# ---------------------------------------------------------------------------
def test_empty_ledger():
    """Empty ledger is vacuously complete."""
    result = validate_ledger(raw_rows=[])

    assert result.pass_ is True
    assert result.missing_tier == 0
    assert result.total_open == 0


# ---------------------------------------------------------------------------
# Test 5: Missing-tier row that has a policy_stamp sibling -> NOT flagged
# ---------------------------------------------------------------------------
def test_stamp_sibling_fills_tier():
    """A row missing tier inline but with a policy_stamp sibling should pass."""
    open_row = _missing_tier_row("STAMPED_001")
    stamp = _stamp_row("STAMPED_001", tier="B")
    rows = [open_row, stamp]

    result = validate_ledger(raw_rows=rows)

    # The stamp provides tier="B", so the row should NOT be flagged.
    assert result.missing_tier == 0, (
        f"Row with stamp sibling should not be flagged; missing_tier={result.missing_tier}"
    )
    assert result.pass_ is True
    assert "STAMPED_001" not in result.flagged_ids


# ---------------------------------------------------------------------------
# Test 6: No $ / dollar / roi / pnl field in ValidationResult
# ---------------------------------------------------------------------------
def test_no_dollar_fields_in_result():
    """ValidationResult must never contain money / ROI fields."""
    rows = [_open_row("MONEY_001")]
    result = validate_ledger(raw_rows=rows)

    # Flatten all values in the result to a string for easy scanning.
    result_str = str(result).lower()
    banned = ("dollar", "roi", "pnl", "profit", "revenue", "bankroll")
    for bad_word in banned:
        assert bad_word not in result_str, (
            f"Banned field '{bad_word}' found in ValidationResult output"
        )


# ---------------------------------------------------------------------------
# Test 7: detail list contains expected fields for flagged rows
# ---------------------------------------------------------------------------
def test_detail_structure():
    """Each detail entry has bet_id and missing_fields."""
    rows = [_missing_tier_row("DETAIL_001")]
    result = validate_ledger(raw_rows=rows)

    assert len(result.detail) == 1
    entry = result.detail[0]
    assert entry["bet_id"] == "DETAIL_001"
    assert "tier" in entry["missing_fields"]


# ---------------------------------------------------------------------------
# Test 8: non-open rows (settled, policy_stamp) are not counted as open rows
# ---------------------------------------------------------------------------
def test_non_open_rows_ignored():
    """Settled and policy_stamp rows are not counted in total_open."""
    settled = {
        "status": "settled",
        "bet_id": "S001",
        "sport": "mlb",
        "clv_pct": 1.2,
        "tier": None,  # Even with missing tier, settled rows don't count
    }
    stamp_only = _stamp_row("S001", tier="C")
    open_clean = _open_row("OPEN_001")

    rows = [settled, stamp_only, open_clean]
    result = validate_ledger(raw_rows=rows)

    # Only the one open row is examined.
    assert result.total_open == 1
    assert result.pass_ is True


# ---------------------------------------------------------------------------
# Test 9: CLI exits 1 on fail, 0 on pass (via _main helper)
# ---------------------------------------------------------------------------
def test_cli_exit_codes(tmp_path):
    """CLI must exit 1 when there are missing-tier rows, 0 when clean."""
    # Write a ledger with one bad row.
    bad_row = _missing_tier_row("CLI_BAD")
    ledger_fail = tmp_path / "fail_ledger.jsonl"
    import json
    ledger_fail.write_text(json.dumps(bad_row) + "\n", encoding="utf-8")

    exit_code = _main(["--path", str(ledger_fail)])
    assert exit_code == 1, "Expected exit code 1 for failing ledger"

    # Write a ledger with one clean row.
    good_row = _open_row("CLI_GOOD")
    ledger_pass = tmp_path / "pass_ledger.jsonl"
    ledger_pass.write_text(json.dumps(good_row) + "\n", encoding="utf-8")

    exit_code = _main(["--path", str(ledger_pass)])
    assert exit_code == 0, "Expected exit code 0 for passing ledger"


# ---------------------------------------------------------------------------
# Test 10: _collect_stamps and _apply_stamps internal helpers
# ---------------------------------------------------------------------------
def test_collect_stamps_first_wins():
    """_collect_stamps keeps first stamp per bet_id (idempotency contract)."""
    first = _stamp_row("BET_ABC", tier="A")
    second = _stamp_row("BET_ABC", tier="C")
    rows = [first, second]
    stamps = _collect_stamps(rows)

    assert len(stamps) == 1
    assert stamps["BET_ABC"]["tier"] == "A"


def test_apply_stamps_fills_only_missing():
    """_apply_stamps fills None fields from stamp but preserves existing values."""
    row = {"status": "open", "bet_id": "BET_Z", "tier": "C", "flat_unit": None}
    stamp = {"status": "policy_stamp", "bet_id": "BET_Z", "tier": "A", "flat_unit": 1.0}
    stamps = {"BET_Z": stamp}

    merged = _apply_stamps(row, stamps)
    # tier was already "C" -- must not be overwritten.
    assert merged["tier"] == "C"
    # flat_unit was None -- should be filled from stamp.
    assert merged["flat_unit"] == 1.0
    # original must not be mutated.
    assert row["flat_unit"] is None


# ---------------------------------------------------------------------------
# Test 11: Dup (bet_id|status) keys -> dup_keys > 0, pass_=False
# ---------------------------------------------------------------------------
def test_dup_key_causes_fail():
    """Two identical open rows (same bet_id AND same status) -> dup_keys=1, pass_=False."""
    row = _open_row("DUP_001")
    rows = [row, dict(row)]  # exact copy = same (bet_id|status) key

    result = validate_ledger(raw_rows=rows)

    assert result.dup_keys == 1, (
        "Expected 1 dup (bet_id|status) key, got %d" % result.dup_keys
    )
    assert result.pass_ is False, "Expected pass_=False when dup_keys>0"
    assert len(result.dup_key_list) == 1


# ---------------------------------------------------------------------------
# Test 12: open + settled twin -> NOT a dup key (both kept, dup_keys==0)
# ---------------------------------------------------------------------------
def test_open_settled_twin_not_a_dup():
    """Open row + settled twin have DISTINCT (bet_id|status) keys -> not a dup."""
    open_row = _open_row("TWIN_001")
    settled_row = dict(open_row)
    settled_row["status"] = "settled"
    settled_row["clv_pct"] = 0.8

    rows = [open_row, settled_row]
    result = validate_ledger(raw_rows=rows)

    assert result.dup_keys == 0, (
        "open+settled twin must NOT be flagged as a dup; dup_keys=%d" % result.dup_keys
    )
    # settled row is not examined for tier; only the open row is -> pass depends on tier
    assert result.missing_tier == 0, "open row has tier -> no missing_tier"
    assert result.pass_ is True


# ---------------------------------------------------------------------------
# Test 13: both dup_keys AND missing_tier -> pass_=False, both counts populated
# ---------------------------------------------------------------------------
def test_dup_and_missing_tier_both_flagged():
    """Combined failure: dup rows + missing tier -> both counts > 0, pass_=False."""
    dup_row = _open_row("DUP_ALSO_CLEAN")
    missing_row = _missing_tier_row("ALSO_MISSING")
    rows = [dup_row, dict(dup_row), missing_row]

    result = validate_ledger(raw_rows=rows)

    assert result.dup_keys >= 1
    assert result.missing_tier >= 1
    assert result.pass_ is False


# ---------------------------------------------------------------------------
# Test 14: ValidationResult has dup_keys attribute (schema check)
# ---------------------------------------------------------------------------
def test_validation_result_has_dup_keys_field():
    """ValidationResult must expose dup_keys and dup_key_list attributes."""
    result = validate_ledger(raw_rows=[])
    assert hasattr(result, "dup_keys"), "ValidationResult must have dup_keys"
    assert hasattr(result, "dup_key_list"), "ValidationResult must have dup_key_list"
    assert result.dup_keys == 0
    assert result.dup_key_list == []
