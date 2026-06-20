"""Per-file test for scripts.platformkit.improve.per_market_ledger.

Acceptance criteria (SI-01):
  (1) 3-market batch -> 3 segmented rows, each with its own market key.
  (2) Under-N cycles -> INSUFFICIENT_DATA status (never a fabricated readout).
  (3) n_promoted=0 surfaced honestly (banner in honest_note, not suppressed).
  (4) No $/pnl/roi key in any output row or batch_summary dict.
  (5) segment_by_market groups correctly by market key.
  (6) grade_market_segment emits INSUFFICIENT_DATA below MIN_MARKET_N.
  (7) rows_for_market / latest_row_per_market are correct on the JSONL.
  (8) count_promoted counts only SHIP status rows.
  (9) batch_summary n_promoted=0 banner is present when no SHIPs.
  (10) batch_summary fields never contain a banned money key.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_per_market_ledger.py -q
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from scripts.platformkit.improve.per_market_ledger import (
    PerMarketLedger,
    batch_summary,
    count_promoted,
    grade_market_segment,
    record_per_market,
    segment_by_market,
    MIN_MARKET_N,
    CALIBRATION_NOTE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(obj: Any, context: str = "") -> None:
    for k in _all_keys(obj):
        assert not _BANNED_KEY_RE.search(k), (
            "Banned key '%s' in output%s" % (k, (" (%s)" % context) if context else "")
        )


def _make_settled_rows(market: str, n: int, p_raw: float = 0.6, y: float = 1.0) -> List[Dict[str, Any]]:
    """Build n minimal settled rows for a given market."""
    return [
        {"market": market, "p_raw": p_raw, "y": y, "sport": market.split(":")[0]}
        for _ in range(n)
    ]


def _make_ship_row(market: str, ts: str = "2026-01-01T00:00:00+00:00") -> Dict[str, Any]:
    return {"ts": ts, "market": market, "status": "SHIP",
            "readout": {"n": 50, "raw_brier": 0.20},
            "note": "calibration != edge"}


def _make_hold_row(market: str, ts: str = "2026-01-01T00:00:00+00:00") -> Dict[str, Any]:
    return {"ts": ts, "market": market, "status": "HOLD",
            "readout": {"n": 50, "raw_brier": 0.24},
            "note": "calibration != edge"}


def _make_insufficient_row(market: str, ts: str = "2026-01-01T00:00:00+00:00") -> Dict[str, Any]:
    return {"ts": ts, "market": market, "status": "INSUFFICIENT_DATA",
            "n": 5, "min_n": MIN_MARKET_N, "note": "calibration != edge"}


def _write_ledger(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Tests: segment_by_market
# ---------------------------------------------------------------------------


class TestSegmentByMarket:
    """segment_by_market groups settled rows by their market key."""

    def test_three_markets_segmented(self) -> None:
        rows = (
            _make_settled_rows("nba:moneyline", 5)
            + _make_settled_rows("mlb:moneyline", 3)
            + _make_settled_rows("soccer:total", 7)
        )
        groups = segment_by_market(rows)
        assert set(groups.keys()) == {"nba:moneyline", "mlb:moneyline", "soccer:total"}
        assert len(groups["nba:moneyline"]) == 5
        assert len(groups["mlb:moneyline"]) == 3
        assert len(groups["soccer:total"]) == 7

    def test_empty_input_returns_empty(self) -> None:
        assert segment_by_market([]) == {}

    def test_single_market(self) -> None:
        rows = _make_settled_rows("nba:moneyline", 10)
        groups = segment_by_market(rows)
        assert list(groups.keys()) == ["nba:moneyline"]
        assert len(groups["nba:moneyline"]) == 10

    def test_market_key_lowercased(self) -> None:
        rows = [{"market": "NBA:Moneyline", "p_raw": 0.6, "y": 1.0}]
        groups = segment_by_market(rows)
        assert "nba:moneyline" in groups

    def test_fallback_when_no_market_field(self) -> None:
        rows = [{"sport": "nba", "bet_type": "spread", "p_raw": 0.6, "y": 1.0}]
        groups = segment_by_market(rows)
        assert "nba:spread" in groups


# ---------------------------------------------------------------------------
# Tests: grade_market_segment
# ---------------------------------------------------------------------------


class TestGradeMarketSegment:
    """grade_market_segment emits INSUFFICIENT_DATA below MIN_MARKET_N."""

    def test_empty_rows_insufficient(self) -> None:
        row = grade_market_segment("nba:moneyline", [])
        assert row["status"] == "INSUFFICIENT_DATA"
        assert row["n"] == 0
        _assert_no_banned_keys(row)

    def test_below_min_n_insufficient(self) -> None:
        rows = _make_settled_rows("nba:moneyline", MIN_MARKET_N - 1)
        row = grade_market_segment("nba:moneyline", rows)
        assert row["status"] == "INSUFFICIENT_DATA"
        assert row["n"] == MIN_MARKET_N - 1
        assert row["min_n"] == MIN_MARKET_N
        assert "reason" in row
        _assert_no_banned_keys(row)

    def test_exactly_min_n_computes_readout(self) -> None:
        rows = _make_settled_rows("nba:moneyline", MIN_MARKET_N)
        row = grade_market_segment("nba:moneyline", rows)
        assert row["status"] in {"SHIP", "HOLD", "REJECT"}
        assert "readout" in row
        assert row["readout"]["n"] == MIN_MARKET_N
        _assert_no_banned_keys(row)

    def test_market_key_preserved(self) -> None:
        rows = _make_settled_rows("soccer:total", MIN_MARKET_N)
        row = grade_market_segment("soccer:total", rows)
        assert row["market"] == "soccer:total"

    def test_ts_injected_when_provided(self) -> None:
        fixed_ts = "2026-01-15T12:00:00+00:00"
        rows = _make_settled_rows("nba:moneyline", 2)
        row = grade_market_segment("nba:moneyline", rows, ts=fixed_ts)
        assert row["ts"] == fixed_ts

    def test_calibration_note_always_present(self) -> None:
        rows = _make_settled_rows("nba:moneyline", 1)
        row = grade_market_segment("nba:moneyline", rows)
        assert "note" in row
        assert "calibration" in row["note"].lower()

    def test_no_banned_keys_in_readout(self) -> None:
        rows = _make_settled_rows("nba:moneyline", MIN_MARKET_N + 5)
        row = grade_market_segment("nba:moneyline", rows)
        _assert_no_banned_keys(row, "grade_market_segment readout")


# ---------------------------------------------------------------------------
# Tests: PerMarketLedger.record_batch -- 3-market segmentation
# ---------------------------------------------------------------------------


class TestRecordBatch:
    """record_batch -> 3 segmented rows for 3-market input."""

    def test_three_market_batch_produces_three_rows(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        settled = (
            _make_settled_rows("nba:moneyline", 5)
            + _make_settled_rows("mlb:moneyline", 3)
            + _make_settled_rows("soccer:total", 7)
        )
        rows = ledger.record_batch(settled, ts="2026-01-01T00:00:00+00:00")
        assert len(rows) == 3, "Expected 3 rows for 3 markets, got %d" % len(rows)
        markets = {r["market"] for r in rows}
        assert markets == {"nba:moneyline", "mlb:moneyline", "soccer:total"}

    def test_three_markets_all_insufficient_below_min_n(self, tmp_path: Path) -> None:
        """All markets have < MIN_MARKET_N rows -> all INSUFFICIENT_DATA."""
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        settled = (
            _make_settled_rows("nba:moneyline", 5)
            + _make_settled_rows("mlb:moneyline", 3)
            + _make_settled_rows("soccer:total", 7)
        )
        rows = ledger.record_batch(settled)
        for row in rows:
            assert row["status"] == "INSUFFICIENT_DATA", (
                "market '%s' has %d rows but got status '%s' instead of INSUFFICIENT_DATA"
                % (row.get("market"), row.get("n", "?"), row["status"])
            )

    def test_batch_appended_to_jsonl(self, tmp_path: Path) -> None:
        """record_batch appends all rows to the JSONL file."""
        path = tmp_path / "ledger.jsonl"
        ledger = PerMarketLedger(path)
        settled = (
            _make_settled_rows("nba:moneyline", 5)
            + _make_settled_rows("mlb:moneyline", 3)
        )
        ledger.record_batch(settled)
        lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_batch_no_banned_keys_in_any_row(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "ledger.jsonl")
        settled = (
            _make_settled_rows("nba:moneyline", 5)
            + _make_settled_rows("mlb:moneyline", 40)
        )
        rows = ledger.record_batch(settled)
        _assert_no_banned_keys(rows, "record_batch rows")


# ---------------------------------------------------------------------------
# Tests: INSUFFICIENT_DATA under MIN_MARKET_N
# ---------------------------------------------------------------------------


class TestInsufficientData:
    """Markets with fewer than MIN_MARKET_N rows must emit INSUFFICIENT_DATA."""

    def test_zero_rows_insufficient(self, tmp_path: Path) -> None:
        row = grade_market_segment("nba:moneyline", [])
        assert row["status"] == "INSUFFICIENT_DATA"
        assert row["n"] == 0

    def test_one_row_insufficient(self, tmp_path: Path) -> None:
        rows = _make_settled_rows("nba:moneyline", 1)
        row = grade_market_segment("nba:moneyline", rows)
        assert row["status"] == "INSUFFICIENT_DATA"
        assert row["n"] == 1

    def test_min_n_minus_one_insufficient(self, tmp_path: Path) -> None:
        rows = _make_settled_rows("nba:moneyline", MIN_MARKET_N - 1)
        row = grade_market_segment("nba:moneyline", rows)
        assert row["status"] == "INSUFFICIENT_DATA"

    def test_insufficient_has_no_fabricated_readout(self) -> None:
        """INSUFFICIENT_DATA rows must NOT have a readout field."""
        rows = _make_settled_rows("nba:moneyline", 5)
        row = grade_market_segment("nba:moneyline", rows)
        assert "readout" not in row, (
            "INSUFFICIENT_DATA row must not contain a readout (no fabricated calibration)"
        )


# ---------------------------------------------------------------------------
# Tests: n_promoted=0 surfaced honestly
# ---------------------------------------------------------------------------


class TestNPromoted:
    """n_promoted=0 must be surfaced with an honest banner; never suppressed."""

    def test_count_promoted_absent_ledger_returns_zero(self, tmp_path: Path) -> None:
        absent = tmp_path / "no_such_file.jsonl"
        assert count_promoted(absent) == 0

    def test_count_promoted_no_ship_rows_returns_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        rows = [
            _make_hold_row("nba:moneyline"),
            _make_insufficient_row("mlb:moneyline"),
        ]
        _write_ledger(rows, path)
        assert count_promoted(path) == 0

    def test_count_promoted_counts_only_ship_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        rows = [
            _make_ship_row("nba:moneyline"),
            _make_hold_row("nba:spread"),
            _make_ship_row("mlb:moneyline"),
            _make_insufficient_row("soccer:total"),
        ]
        _write_ledger(rows, path)
        assert count_promoted(path) == 2

    def test_batch_summary_zero_promoted_banner(self, tmp_path: Path) -> None:
        """batch_summary honest_note contains the ratchet-zero banner when n_promoted=0."""
        path = tmp_path / "ledger.jsonl"
        # Write only HOLD rows -> n_promoted=0
        _write_ledger([_make_hold_row("nba:moneyline")], path)
        ledger_rows = [_make_hold_row("nba:moneyline"), _make_insufficient_row("mlb:moneyline")]
        summary = batch_summary(ledger_rows, ledger_path=path)
        assert summary["n_promoted"] == 0
        assert "ratchet has not promoted" in summary["honest_note"].lower(), (
            "n_promoted=0 must produce an honest banner; got: %s" % summary["honest_note"]
        )

    def test_batch_summary_nonzero_promoted_no_banner(self, tmp_path: Path) -> None:
        """When n_promoted > 0 the honest_note does NOT say 'ratchet has not promoted'."""
        path = tmp_path / "ledger.jsonl"
        _write_ledger([_make_ship_row("nba:moneyline")], path)
        ledger_rows = [_make_ship_row("nba:moneyline")]
        summary = batch_summary(ledger_rows, ledger_path=path)
        assert summary["n_promoted"] == 1
        assert "ratchet has not promoted" not in summary["honest_note"].lower()

    def test_batch_summary_counts_correct(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        _write_ledger([], path)
        ledger_rows = [
            {**_make_ship_row("nba:moneyline"), "status": "SHIP"},
            {**_make_hold_row("nba:spread"), "status": "HOLD"},
            {**_make_hold_row("mlb:moneyline"), "status": "REJECT"},
            {**_make_insufficient_row("soccer:total"), "status": "INSUFFICIENT_DATA"},
        ]
        summary = batch_summary(ledger_rows, ledger_path=path)
        assert summary["n_markets"] == 4
        assert summary["n_ship"] == 1
        assert summary["n_hold"] == 1
        assert summary["n_reject"] == 1
        assert summary["n_insufficient"] == 1


# ---------------------------------------------------------------------------
# Tests: no banned keys
# ---------------------------------------------------------------------------


class TestNoBannedKeys:
    """No output row or summary may contain a $/roi/pnl/profit key."""

    def test_insufficient_row_no_banned_keys(self) -> None:
        row = grade_market_segment("nba:moneyline", [])
        _assert_no_banned_keys(row, "empty INSUFFICIENT_DATA row")

    def test_sufficient_row_no_banned_keys(self) -> None:
        rows = _make_settled_rows("nba:moneyline", MIN_MARKET_N)
        row = grade_market_segment("nba:moneyline", rows)
        _assert_no_banned_keys(row, "sufficient row")

    def test_record_per_market_no_banned_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        settled = (
            _make_settled_rows("nba:moneyline", 5)
            + _make_settled_rows("mlb:moneyline", 40)
            + _make_settled_rows("soccer:total", 50)
        )
        rows = record_per_market(settled, ledger_path=path)
        _assert_no_banned_keys(rows, "record_per_market")

    def test_batch_summary_no_banned_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        _write_ledger([], path)
        ledger_rows = [_make_hold_row("nba:moneyline"), _make_insufficient_row("mlb:moneyline")]
        summary = batch_summary(ledger_rows, ledger_path=path)
        _assert_no_banned_keys(summary, "batch_summary")


# ---------------------------------------------------------------------------
# Tests: PerMarketLedger query methods
# ---------------------------------------------------------------------------


class TestLedgerQueries:
    """rows_for_market, latest_row_per_market work correctly on JSONL."""

    def test_rows_for_market_filters_correctly(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        rows = [
            _make_hold_row("nba:moneyline", ts="2026-01-01T00:00:00+00:00"),
            _make_hold_row("mlb:moneyline", ts="2026-01-01T00:00:00+00:00"),
            _make_hold_row("nba:moneyline", ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, path)
        ledger = PerMarketLedger(path)
        nba_rows = ledger.rows_for_market("nba:moneyline")
        assert len(nba_rows) == 2
        mlb_rows = ledger.rows_for_market("mlb:moneyline")
        assert len(mlb_rows) == 1

    def test_latest_row_per_market_last_wins(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        rows = [
            {**_make_hold_row("nba:moneyline", ts="2026-01-01T00:00:00+00:00"), "cycle": 1},
            {**_make_ship_row("nba:moneyline", ts="2026-01-02T00:00:00+00:00"), "cycle": 2},
        ]
        _write_ledger(rows, path)
        ledger = PerMarketLedger(path)
        latest = ledger.latest_row_per_market()
        assert latest["nba:moneyline"]["status"] == "SHIP"
        assert latest["nba:moneyline"].get("cycle") == 2

    def test_all_rows_returns_full_chronological_list(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        rows = [
            _make_hold_row("nba:moneyline", ts="2026-01-01T00:00:00+00:00"),
            _make_insufficient_row("mlb:moneyline", ts="2026-01-02T00:00:00+00:00"),
            _make_ship_row("soccer:total", ts="2026-01-03T00:00:00+00:00"),
        ]
        _write_ledger(rows, path)
        ledger = PerMarketLedger(path)
        all_rows = ledger.all_rows()
        assert len(all_rows) == 3
        assert all_rows[0]["market"] == "nba:moneyline"
        assert all_rows[2]["market"] == "soccer:total"

    def test_absent_ledger_returns_empty(self, tmp_path: Path) -> None:
        ledger = PerMarketLedger(tmp_path / "no_such_ledger.jsonl")
        assert ledger.all_rows() == []
        assert ledger.rows_for_market("nba:moneyline") == []
        assert ledger.latest_row_per_market() == {}
