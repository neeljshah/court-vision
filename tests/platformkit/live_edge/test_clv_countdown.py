"""Focused tests for the S239 reader-only countdown metric."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.platformkit.live_edge.clv.clv_countdown import countdown


_ROOT = Path(__file__).resolve().parents[3]
_LEDGER = _ROOT / "data" / "frontend" / "clv_ledger.jsonl"
_STATUS = _ROOT / "data" / "frontend" / "analytics" / "execution_status.json"


class TestClvCountdown(unittest.TestCase):
    def test_real_store_is_undefined_with_named_blockers(self) -> None:
        result = countdown(str(_LEDGER), str(_STATUS))

        self.assertEqual(0, result["n_settled_today"])
        self.assertIsNone(result["settlement_rate_per_day"])
        self.assertEqual("UNDEFINED", result["days_to_first_reading"])
        self.assertIn("S20: week bar unmet", result["blockers"])
        self.assertIn("S18: blocked on S20", result["blockers"])

    def test_construct_history_returns_hand_computed_integer(self) -> None:
        rows = [
            {"status": "settled", "settled_at": "2026-09-01T12:00:00Z"},
            {"status": "settled", "settled_at": "2026-09-01T13:00:00Z"},
            {"status": "settled", "settled_at": "2026-09-02T12:00:00Z"},
            {"status": "settled", "settled_at": "2026-09-02T13:00:00Z"},
        ]
        status = {"n_settled": 4, "row_classes": {"settled": 4}}
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "ledger.jsonl"
            status_path = Path(temp_dir) / "status.json"
            ledger_path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            status_path.write_text(json.dumps(status), encoding="utf-8")
            result = countdown(str(ledger_path), str(status_path))

        self.assertEqual(4, result["n_settled_today"])
        self.assertEqual(2.0, result["settlement_rate_per_day"])
        self.assertEqual(98, result["days_to_first_reading"])
        self.assertEqual(
            ["S20: week bar unmet", "S18: blocked on S20"], result["blockers"]
        )
