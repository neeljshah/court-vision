"""test_ledger_hygiene_report.py -- per-file tests for ledger_hygiene_report (WS7).

Acceptance criteria:
  1. Flat-prior-polluted rows (model_prob 0.4655 / 0.5345) are counted correctly.
  2. Synthetic rows (test_ prefix, short game_id) are counted correctly.
  3. Malformed rows (missing required field or unknown status) are counted.
  4. Duplicate (bet_id, status) rows are counted.
  5. Settled rows without clv_pct are counted.
  6. Orphan-ship count is surfaced from fixture data (via mock).
  7. Returns a structured HygieneReport with correct fields.
  8. NO ledger file is mutated (read-only invariant).
  9. No dollar / pnl / roi key appears anywhere in the report output.
  10. Clean ledger -> status "OK"; polluted ledger -> status "POLLUTED".
  11. Empty ledger -> all counts == 0, status "OK".
  12. to_dict() returns a JSON-serializable dict with no banned keys.

Run ONLY this file (full-suite pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    scripts/platformkit/pm_trading/test_ledger_hygiene_report.py -q
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Hermetic import: prefer package path, fall back to inserting repo root
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.pm_trading.ledger_hygiene_report import (
    FLAT_PRIOR_PROBS,
    INSUFFICIENT_DATA,
    HygieneReport,
    _find_duplicates,
    _is_flat_prior,
    _is_malformed,
    _is_synthetic,
    build_report,
    to_dict,
)

# ---------------------------------------------------------------------------
# Fixture row builders
# ---------------------------------------------------------------------------

def _open_row(
    bet_id: str = "BET_001",
    sport: str = "nba",
    model_prob: Optional[float] = 0.62,
    status: str = "open",
    taken_decimal: float = 1.95,
) -> Dict[str, Any]:
    """Build a clean open CLV ledger row."""
    return {
        "bet_id": bet_id,
        "status": status,
        "sport": sport,
        "matchup": "BOS@NYK",
        "side": "home",
        "taken_book": "kalshi",
        "taken_decimal": taken_decimal,
        "model_prob": model_prob,
        "stake_units": 1.0,
        "executed": False,
        "channel": "paper",
    }


def _settled_row(
    bet_id: str = "BET_001",
    sport: str = "nba",
    clv_pct: Optional[float] = 1.5,
) -> Dict[str, Any]:
    """Build a clean settled CLV ledger row."""
    row = _open_row(bet_id=bet_id, sport=sport, status="settled")
    if clv_pct is not None:
        row["clv_pct"] = clv_pct
    else:
        row.pop("clv_pct", None)
    return row


def _flat_prior_row(prob: float = 0.4655, bet_id: str = "FLAT_001") -> Dict[str, Any]:
    """Build a row with a known flat-prior sentinel model_prob."""
    row = _open_row(bet_id=bet_id, model_prob=prob)
    return row


def _synthetic_test_prefix(bet_id: str = "test_abc") -> Dict[str, Any]:
    """Build a synthetic row identified by 'test_' in bet_id."""
    return _open_row(bet_id=bet_id, sport="test_none_path_no_raise")


def _synthetic_short_game_id(game_id: str = "gg") -> Dict[str, Any]:
    """Build a synthetic row identified by a short/unstructured game_id."""
    row = _open_row(bet_id="GAME_SHORT")
    row["game_id"] = game_id
    return row


def _malformed_missing_field(field: str = "bet_id") -> Dict[str, Any]:
    """Build a row that is missing one required field."""
    row = _open_row()
    row.pop(field, None)
    row[field] = None
    return row


def _malformed_bad_status() -> Dict[str, Any]:
    """Build a row with an unknown status value."""
    row = _open_row()
    row["status"] = "ZOMBIE"
    return row


# ---------------------------------------------------------------------------
# Test 1: flat-prior sentinel detection
# ---------------------------------------------------------------------------
class TestFlatPriorDetection:
    def test_0_4655_is_flat_prior(self):
        assert _is_flat_prior(_flat_prior_row(0.4655))

    def test_0_5345_is_flat_prior(self):
        assert _is_flat_prior(_flat_prior_row(0.5345))

    def test_normal_prob_not_flat_prior(self):
        assert not _is_flat_prior(_open_row(model_prob=0.62))

    def test_none_model_prob_not_flat_prior(self):
        assert not _is_flat_prior(_open_row(model_prob=None))

    def test_build_report_counts_flat_prior_rows(self):
        rows = [
            _flat_prior_row(0.4655, "FP_001"),
            _flat_prior_row(0.5345, "FP_002"),
            _open_row(bet_id="CLEAN_001", model_prob=0.65),
        ]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.flat_prior_count == 2
        assert "FP_001" in report.flat_prior_bet_ids
        assert "FP_002" in report.flat_prior_bet_ids
        assert report.status == "POLLUTED"

    def test_flat_prior_ids_truncated_at_50(self):
        # Produce 60 flat-prior rows; report must cap at 50 entries
        rows = [_flat_prior_row(0.4655, "FP_%03d" % i) for i in range(60)]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.flat_prior_count == 60
        assert len(report.flat_prior_bet_ids) == 50


# ---------------------------------------------------------------------------
# Test 2: synthetic row detection
# ---------------------------------------------------------------------------
class TestSyntheticDetection:
    def test_test_prefix_in_bet_id(self):
        assert _is_synthetic(_synthetic_test_prefix("test_abc"))

    def test_test_prefix_in_sport(self):
        row = _open_row(sport="test_nba_sport")
        assert _is_synthetic(row)

    def test_short_game_id(self):
        assert _is_synthetic(_synthetic_short_game_id("gg"))

    def test_clean_row_not_synthetic(self):
        assert not _is_synthetic(_open_row())

    def test_build_report_counts_synthetic(self):
        rows = [
            _synthetic_test_prefix("test_001"),
            _synthetic_short_game_id("ab"),
            _open_row(bet_id="CLEAN_001"),
        ]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.synthetic_count == 2
        assert report.status == "POLLUTED"


# ---------------------------------------------------------------------------
# Test 3: malformed row detection
# ---------------------------------------------------------------------------
class TestMalformedDetection:
    def test_missing_bet_id_is_malformed(self):
        assert _is_malformed(_malformed_missing_field("bet_id"))

    def test_missing_status_is_malformed(self):
        assert _is_malformed(_malformed_missing_field("status"))

    def test_missing_sport_is_malformed(self):
        assert _is_malformed(_malformed_missing_field("sport"))

    def test_missing_taken_decimal_is_malformed(self):
        assert _is_malformed(_malformed_missing_field("taken_decimal"))

    def test_unknown_status_is_malformed(self):
        assert _is_malformed(_malformed_bad_status())

    def test_clean_row_not_malformed(self):
        assert not _is_malformed(_open_row())

    def test_build_report_counts_malformed(self):
        rows = [
            _malformed_missing_field("bet_id"),
            _malformed_missing_field("sport"),
            _open_row(bet_id="OK_001"),
        ]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.malformed_count == 2
        assert report.status == "POLLUTED"


# ---------------------------------------------------------------------------
# Test 4: duplicate (bet_id, status) detection
# ---------------------------------------------------------------------------
class TestDuplicateDetection:
    def test_identical_rows_counted_as_dup(self):
        row = _open_row(bet_id="DUP_001")
        rows = [row, dict(row)]
        assert _find_duplicates(rows) == 1

    def test_open_plus_settled_twin_not_a_dup(self):
        open_row = _open_row(bet_id="TWIN_001")
        settled = _settled_row(bet_id="TWIN_001")
        assert _find_duplicates([open_row, settled]) == 0

    def test_build_report_counts_duplicates(self):
        row = _open_row(bet_id="DUP_REPORT")
        rows = [row, dict(row), _open_row(bet_id="UNIQUE_001")]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.duplicate_count == 1
        assert report.status == "POLLUTED"


# ---------------------------------------------------------------------------
# Test 5: settled-without-CLV detection
# ---------------------------------------------------------------------------
class TestSettledWithoutCLV:
    def test_settled_no_clv_pct_counted(self):
        rows = [
            _settled_row(bet_id="S001", clv_pct=1.5),   # has CLV
            _settled_row(bet_id="S002", clv_pct=None),  # missing CLV
        ]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.settled_without_clv_count == 1
        assert report.status == "POLLUTED"

    def test_settled_with_clv_not_counted(self):
        rows = [_settled_row(bet_id="S001", clv_pct=0.8)]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.settled_without_clv_count == 0


# ---------------------------------------------------------------------------
# Test 6: orphan-ship count surfaced via mock
# ---------------------------------------------------------------------------
class TestOrphanShips:
    def test_orphan_ships_surfaced(self):
        _mock_detail = [
            {"ship_name": "nba", "ship_ts": "2026-06-01T00:00:00Z",
             "reason": "no matching graded row"}
        ]
        with mock.patch(
            "scripts.platformkit.pm_trading.ledger_hygiene_report._orphan_ships",
            return_value=(1, _mock_detail),
        ):
            rows = [_open_row()]
            report = build_report(raw_rows=rows, check_orphan_ships=True)
        assert report.orphan_ship_count == 1
        assert len(report.orphan_ship_details) == 1
        assert report.orphan_ship_details[0]["ship_name"] == "nba"
        assert report.status == "POLLUTED"

    def test_no_orphan_ships_when_skip(self):
        rows = [_open_row()]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.orphan_ship_count == 0
        assert report.orphan_ship_details == []


# ---------------------------------------------------------------------------
# Test 7: structured HygieneReport fields
# ---------------------------------------------------------------------------
class TestHygieneReportStructure:
    def test_report_has_all_fields(self):
        report = build_report(raw_rows=[], check_orphan_ships=False)
        assert hasattr(report, "total_rows")
        assert hasattr(report, "flat_prior_count")
        assert hasattr(report, "flat_prior_bet_ids")
        assert hasattr(report, "synthetic_count")
        assert hasattr(report, "malformed_count")
        assert hasattr(report, "duplicate_count")
        assert hasattr(report, "settled_without_clv_count")
        assert hasattr(report, "orphan_ship_count")
        assert hasattr(report, "orphan_ship_details")
        assert hasattr(report, "status")
        assert hasattr(report, "note")
        assert hasattr(report, "audited_at")

    def test_to_dict_is_json_serializable(self):
        rows = [_open_row(), _flat_prior_row()]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        d = to_dict(report)
        # Must be JSON-round-trippable
        s = json.dumps(d)
        parsed = json.loads(s)
        assert parsed["flat_prior_count"] == 1

    def test_to_dict_no_banned_keys(self):
        report = build_report(raw_rows=[_open_row()], check_orphan_ships=False)
        d = to_dict(report)
        _BANNED = {"dollar", "dollars", "pnl", "roi", "profit",
                   "dollar_stake", "bankroll", "revenue"}
        for k in d:
            assert k.lower() not in _BANNED, "Banned key '%s' in to_dict output" % k


# ---------------------------------------------------------------------------
# Test 8: read-only invariant
# ---------------------------------------------------------------------------
class TestReadOnly:
    def test_build_report_does_not_mutate_rows(self):
        rows = [
            _flat_prior_row(0.4655, "FP_001"),
            _open_row(bet_id="CLEAN"),
        ]
        original = copy.deepcopy(rows)
        build_report(raw_rows=rows, check_orphan_ships=False)
        assert rows == original, "build_report must not mutate input rows"

    def test_build_report_does_not_write_files(self, tmp_path):
        ledger = tmp_path / "test_clv_ledger.jsonl"
        row = _open_row()
        ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
        before = ledger.read_bytes()
        build_report(ledger_path=ledger, check_orphan_ships=False)
        after = ledger.read_bytes()
        assert before == after, "build_report must not modify the ledger file"


# ---------------------------------------------------------------------------
# Test 9: no dollar / pnl / roi keys in report output
# ---------------------------------------------------------------------------
class TestNoBannedKeys:
    def test_report_note_contains_no_dollar_wording(self):
        report = build_report(raw_rows=[], check_orphan_ships=False)
        # The note should not mention dollar amounts
        note_lower = report.note.lower()
        for banned in ("$", "roi", "profit", "pnl", "bankroll"):
            assert banned not in note_lower, (
                "Banned term '%s' in report note" % banned
            )

    def test_hygiene_report_dataclass_has_no_banned_fields(self):
        report = HygieneReport()
        _BANNED = {"dollar", "pnl", "roi", "profit", "bankroll", "revenue"}
        for attr in vars(report):
            assert attr.lower() not in _BANNED, (
                "Banned field '%s' in HygieneReport" % attr
            )


# ---------------------------------------------------------------------------
# Test 10: clean vs polluted status
# ---------------------------------------------------------------------------
class TestStatusLabel:
    def test_clean_ledger_status_ok(self):
        rows = [_open_row(model_prob=0.62), _open_row(bet_id="BET_002", model_prob=0.55)]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.status == "OK"

    def test_polluted_ledger_status_polluted(self):
        rows = [_flat_prior_row(), _open_row(model_prob=0.62)]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.status == "POLLUTED"


# ---------------------------------------------------------------------------
# Test 11: empty ledger
# ---------------------------------------------------------------------------
class TestEmptyLedger:
    def test_empty_rows_all_zero(self):
        report = build_report(raw_rows=[], check_orphan_ships=False)
        assert report.total_rows == 0
        assert report.flat_prior_count == 0
        assert report.synthetic_count == 0
        assert report.malformed_count == 0
        assert report.duplicate_count == 0
        assert report.settled_without_clv_count == 0
        assert report.status == "OK"


# ---------------------------------------------------------------------------
# Test 12: missing ledger file -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------
class TestMissingLedger:
    def test_missing_file_returns_insufficient_data(self, tmp_path):
        missing = tmp_path / "nonexistent_ledger.jsonl"
        report = build_report(ledger_path=missing, check_orphan_ships=False)
        assert report.status == INSUFFICIENT_DATA
        assert report.total_rows == 0

    def test_missing_file_never_raises(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        # Must not raise
        report = build_report(ledger_path=missing, check_orphan_ships=False)
        assert isinstance(report, HygieneReport)


# ---------------------------------------------------------------------------
# Test 13: combined fixture (all pollution types in one ledger)
# ---------------------------------------------------------------------------
class TestCombinedFixture:
    def test_all_pollution_types_detected(self):
        """Fixture with all six pollution categories; verify each count >= 1."""
        rows = [
            # flat-prior
            _flat_prior_row(0.4655, "FP_001"),
            _flat_prior_row(0.5345, "FP_002"),
            # synthetic
            _synthetic_test_prefix("test_bet_001"),
            # malformed
            _malformed_missing_field("sport"),
            # duplicate (open BET_A appears twice)
            _open_row(bet_id="BET_A", model_prob=0.62),
            _open_row(bet_id="BET_A", model_prob=0.62),
            # settled without CLV
            _settled_row(bet_id="S_NO_CLV", clv_pct=None),
            # one clean row
            _open_row(bet_id="CLEAN_001", model_prob=0.58),
        ]
        report = build_report(raw_rows=rows, check_orphan_ships=False)
        assert report.flat_prior_count == 2, "Expected 2 flat-prior rows"
        assert report.synthetic_count >= 1, "Expected >= 1 synthetic row"
        assert report.malformed_count >= 1, "Expected >= 1 malformed row"
        assert report.duplicate_count >= 1, "Expected >= 1 duplicate row"
        assert report.settled_without_clv_count == 1, "Expected 1 settled-no-CLV row"
        assert report.status == "POLLUTED"
        assert report.total_rows == len(rows)
