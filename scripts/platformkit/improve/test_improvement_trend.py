"""Per-file test for scripts.platformkit.improve.improvement_trend.

Acceptance criteria (from BACKLOG.md SI-03):
  - monotone-improving cycles -> monotone_improving True
  - worsening cycles -> monotone_improving False + regression_flag set
  - < 2 cycles -> INSUFFICIENT_DATA
  - INSUFFICIENT_DATA ledger rows excluded from the series
  - no $ key in any output

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_improvement_trend.py -q
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from scripts.platformkit.improve.improvement_trend import (
    compute_trend,
    compute_trends,
    MIN_CYCLES,
    REGRESSION_TOL,
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
            "Banned key '%s' found in output%s" % (k, (" (%s)" % context) if context else "")
        )


def _write_ledger(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _make_data_row(
    market: str,
    raw_brier: float,
    ts: str = "2026-01-01T00:00:00+00:00",
    status: str = "HOLD",
) -> Dict[str, Any]:
    """Build a ledger row with a readout (i.e. a data-bearing row)."""
    return {
        "ts": ts,
        "market": market,
        "status": status,
        "readout": {
            "n": 50,
            "raw_brier": raw_brier,
            "raw_ece": 0.05,
            "base_rate": 0.5,
            "sharpness": 0.25,
            "n_with_close": 0,
            "bss_vs_close": None,
            "pct_beat_close": None,
        },
        "note": "calibration != edge",
    }


def _make_insufficient_row(market: str, ts: str = "2026-01-01T00:00:00+00:00") -> Dict[str, Any]:
    """Build an INSUFFICIENT_DATA ledger row (no readout)."""
    return {
        "ts": ts,
        "market": market,
        "status": "INSUFFICIENT_DATA",
        "n": 3,
        "min_n": 30,
        "note": "calibration != edge",
        "reason": "only 3 settled rows",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInsufficientData:
    """Fewer than 2 data cycles -> INSUFFICIENT_DATA status."""

    def test_empty_ledger(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text("")
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(result, "empty ledger")

    def test_no_rows_for_market(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [_make_data_row("mlb:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00")]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(result)

    def test_one_data_row(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [_make_data_row("nba:moneyline", 0.24, ts="2026-01-01T00:00:00+00:00")]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n_data_cycles"] == 1
        _assert_no_banned_keys(result)

    def test_only_insufficient_rows(self, tmp_path: Path) -> None:
        """All rows are INSUFFICIENT_DATA -> excluded from series -> INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_insufficient_row("nba:moneyline", ts="2026-01-01T00:00:00+00:00"),
            _make_insufficient_row("nba:moneyline", ts="2026-01-02T00:00:00+00:00"),
            _make_insufficient_row("nba:moneyline", ts="2026-01-03T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n_data_cycles"] == 0
        assert result["n_excluded"] == 3
        _assert_no_banned_keys(result)


class TestMonotoneImproving:
    """Strictly improving Brier series -> monotone_improving True, no regression."""

    def test_two_cycles_improving(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["monotone_improving"] is True
        assert result["regression_flag"] is False
        assert len(result["deltas"]) == 1
        assert result["deltas"][0] < 0  # Brier decreased = improvement
        _assert_no_banned_keys(result)

    def test_three_cycles_monotone_improving(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        briers = [0.30, 0.27, 0.24]
        rows = [
            _make_data_row("nba:moneyline", b, ts="2026-01-0%dT00:00:00+00:00" % (i + 1))
            for i, b in enumerate(briers)
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["monotone_improving"] is True
        assert result["regression_flag"] is False
        assert result["n_data_cycles"] == 3
        assert len(result["deltas"]) == 2
        for d in result["deltas"]:
            assert d < 0, "Expected negative delta (improvement), got %s" % d
        _assert_no_banned_keys(result)

    def test_flat_within_tolerance_is_not_regression(self, tmp_path: Path) -> None:
        """A flat Brier (delta=0) should not trigger regression_flag."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["regression_flag"] is False
        assert result["monotone_improving"] is True
        _assert_no_banned_keys(result)


class TestWorsening:
    """Worsening cycles -> monotone_improving False + regression_flag set."""

    def test_two_cycles_worsening(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.27, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["monotone_improving"] is False
        assert result["regression_flag"] is True
        assert result["deltas"][0] > 0  # Brier increased = regression
        _assert_no_banned_keys(result)

    def test_mixed_cycles_regression_detected(self, tmp_path: Path) -> None:
        """Improving then worsening -> regression_flag True, monotone_improving False."""
        ledger = tmp_path / "ledger.jsonl"
        briers = [0.30, 0.27, 0.29]  # improved then worsened
        rows = [
            _make_data_row("nba:moneyline", b, ts="2026-01-0%dT00:00:00+00:00" % (i + 1))
            for i, b in enumerate(briers)
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["regression_flag"] is True
        assert result["monotone_improving"] is False
        assert len(result["deltas"]) == 2
        assert result["deltas"][0] < 0  # first step: improvement
        assert result["deltas"][1] > 0  # second step: regression
        _assert_no_banned_keys(result)

    def test_small_regression_beyond_tolerance(self, tmp_path: Path) -> None:
        """A Brier increase just above REGRESSION_TOL must set regression_flag."""
        ledger = tmp_path / "ledger.jsonl"
        delta = REGRESSION_TOL + 0.0001
        rows = [
            _make_data_row("nba:moneyline", 0.250000, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.250000 + delta, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["regression_flag"] is True
        assert result["monotone_improving"] is False
        _assert_no_banned_keys(result)

    def test_small_regression_within_tolerance(self, tmp_path: Path) -> None:
        """A Brier increase <= REGRESSION_TOL must NOT set regression_flag."""
        ledger = tmp_path / "ledger.jsonl"
        delta = REGRESSION_TOL * 0.5
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.25 + delta, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["regression_flag"] is False
        assert result["monotone_improving"] is True
        _assert_no_banned_keys(result)


class TestInsufficientDataExclusion:
    """INSUFFICIENT_DATA rows are excluded from the series but counted."""

    def test_insufficient_rows_excluded(self, tmp_path: Path) -> None:
        """3 INSUFFICIENT rows + 2 data rows -> only 2 data rows in series."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_insufficient_row("nba:moneyline", ts="2026-01-01T00:00:00+00:00"),
            _make_insufficient_row("nba:moneyline", ts="2026-01-02T00:00:00+00:00"),
            _make_insufficient_row("nba:moneyline", ts="2026-01-03T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-04T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-05T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["n_data_cycles"] == 2
        assert result["n_excluded"] == 3
        assert len(result["deltas"]) == 1
        _assert_no_banned_keys(result)

    def test_mixed_order_insufficient_rows_excluded(self, tmp_path: Path) -> None:
        """INSUFFICIENT_DATA rows interspersed with data rows; all excluded."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.28, ts="2026-01-01T00:00:00+00:00"),
            _make_insufficient_row("nba:moneyline", ts="2026-01-02T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-03T00:00:00+00:00"),
            _make_insufficient_row("nba:moneyline", ts="2026-01-04T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.22, ts="2026-01-05T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["n_data_cycles"] == 3
        assert result["n_excluded"] == 2
        assert result["monotone_improving"] is True
        # 0.25-0.28=-0.03 and 0.22-0.25=-0.03
        for d in result["deltas"]:
            assert d < 0
        _assert_no_banned_keys(result)

    def test_one_insufficient_brings_below_min_cycles(self, tmp_path: Path) -> None:
        """One data row + two INSUFFICIENT rows -> INSUFFICIENT_DATA (only 1 usable)."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_insufficient_row("nba:moneyline", ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.24, ts="2026-01-02T00:00:00+00:00"),
            _make_insufficient_row("nba:moneyline", ts="2026-01-03T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n_data_cycles"] == 1
        _assert_no_banned_keys(result)


class TestNoBannedKeys:
    """No output dict may contain a $ / roi / pnl / profit key."""

    def test_ok_result_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        _assert_no_banned_keys(result, "ok result")

    def test_insufficient_result_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text("")
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        _assert_no_banned_keys(result, "insufficient result")

    def test_compute_trends_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-02T00:00:00+00:00"),
            _make_data_row("mlb:moneyline", 0.24, ts="2026-01-01T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        results = compute_trends(ledger_path=ledger)
        _assert_no_banned_keys(results, "compute_trends")


class TestMultiMarket:
    """compute_trends returns a per-market dict with correct per-market results."""

    def test_two_markets_independent(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-02T00:00:00+00:00"),
            _make_data_row("mlb:moneyline", 0.20, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("mlb:moneyline", 0.22, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        results = compute_trends(ledger_path=ledger)
        assert "nba:moneyline" in results
        assert "mlb:moneyline" in results
        nba = results["nba:moneyline"]
        mlb = results["mlb:moneyline"]
        assert nba["status"] == "ok"
        assert nba["monotone_improving"] is True  # 0.25->0.23, improving
        assert mlb["status"] == "ok"
        assert mlb["monotone_improving"] is False  # 0.20->0.22, worsening
        assert mlb["regression_flag"] is True
        _assert_no_banned_keys(results)

    def test_one_market_sufficient_one_not(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-02T00:00:00+00:00"),
            _make_data_row("soccer:total", 0.20, ts="2026-01-01T00:00:00+00:00"),
            # only one soccer row -> INSUFFICIENT_DATA
        ]
        _write_ledger(rows, ledger)
        results = compute_trends(ledger_path=ledger)
        assert results["nba:moneyline"]["status"] == "ok"
        assert results["soccer:total"]["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(results)


class TestEdgeCases:
    """Edge-case / robustness tests."""

    def test_missing_ledger_file(self, tmp_path: Path) -> None:
        absent = tmp_path / "nonexistent.jsonl"
        result = compute_trend("nba:moneyline", ledger_path=absent)
        assert result["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(result)

    def test_market_key_case_insensitive(self, tmp_path: Path) -> None:
        """Market key matching is case-insensitive."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("NBA:Moneyline", 0.25, ts="2026-01-01T00:00:00+00:00"),
            _make_data_row("NBA:Moneyline", 0.23, ts="2026-01-02T00:00:00+00:00"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["n_data_cycles"] == 2
        _assert_no_banned_keys(result)

    def test_briers_list_correct_length(self, tmp_path: Path) -> None:
        """briers has one element per data cycle, deltas has one fewer."""
        ledger = tmp_path / "ledger.jsonl"
        brier_vals = [0.30, 0.28, 0.26, 0.24]
        rows = [
            _make_data_row("nba:moneyline", b, ts="2026-01-0%dT00:00:00+00:00" % (i + 1))
            for i, b in enumerate(brier_vals)
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert len(result["briers"]) == 4
        assert len(result["deltas"]) == 3
        _assert_no_banned_keys(result)

    def test_ship_status_rows_included(self, tmp_path: Path) -> None:
        """SHIP-status rows are data-bearing and must be included in the series."""
        ledger = tmp_path / "ledger.jsonl"
        rows = [
            _make_data_row("nba:moneyline", 0.25, ts="2026-01-01T00:00:00+00:00", status="SHIP"),
            _make_data_row("nba:moneyline", 0.23, ts="2026-01-02T00:00:00+00:00", status="SHIP"),
        ]
        _write_ledger(rows, ledger)
        result = compute_trend("nba:moneyline", ledger_path=ledger)
        assert result["status"] == "ok"
        assert result["n_data_cycles"] == 2
        assert result["cycle_statuses"] == ["SHIP", "SHIP"]
        _assert_no_banned_keys(result)
