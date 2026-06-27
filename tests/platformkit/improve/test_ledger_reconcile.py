"""Per-file test for scripts.platformkit.improve.ledger_reconcile.

Acceptance criteria (from BACKLOG.md SI-11):
  - SHIP row w/o graded row -> drift flag listed; n_drift >= 1; status "drift"
  - all SHIP rows matched -> clean=True; status "clean"
  - missing proposals file -> INSUFFICIENT_DATA, never green
  - empty proposals file -> INSUFFICIENT_DATA, never green
  - no SHIP rows -> INSUFFICIENT_DATA, never green
  - missing graded file -> INSUFFICIENT_DATA, never green
  - empty graded file -> INSUFFICIENT_DATA, never green
  - read-only: neither ledger is mutated
  - no $/roi/pnl/profit key in any output

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/improve/test_ledger_reconcile.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.improve.ledger_reconcile import (
    reconcile,
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


def _assert_no_banned_keys(obj: Any, ctx: str = "") -> None:
    for k in _all_keys(obj):
        assert not _BANNED_KEY_RE.search(k), (
            "Banned key '%s' found in output%s" % (k, (" (%s)" % ctx) if ctx else "")
        )


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _ship_proposal(name: str = "nba", ts: str = "2026-01-01T00:00:00",
                   version: int = 1) -> Dict[str, Any]:
    return {
        "ts": ts,
        "name": name,
        "decision": "SHIP",
        "reasons": ["oos_improves"],
        "shipped_version": version,
        "rolled_back_to": None,
        "n_new": 5,
        "n_corpora_replicated": 2,
        "note": "calibration, not edge",
    }


def _reject_proposal(name: str = "nba", ts: str = "2026-01-02T00:00:00") -> Dict[str, Any]:
    return {
        "ts": ts,
        "name": name,
        "decision": "REJECT",
        "reasons": ["gate failed"],
        "shipped_version": None,
        "rolled_back_to": None,
        "n_new": 3,
        "n_corpora_replicated": 1,
        "note": "calibration, not edge",
    }


def _graded_row(market: str = "nba:moneyline", ts: str = "2026-01-01T00:00:00",
                status: str = "SHIP") -> Dict[str, Any]:
    return {
        "ts": ts,
        "market": market,
        "status": status,
        "readout": {"n": 50, "raw_brier": 0.23},
        "note": "calibration != edge",
    }


# ---------------------------------------------------------------------------
# INSUFFICIENT_DATA guards (stale-never-green)
# ---------------------------------------------------------------------------


class TestInsufficientData:
    """Missing / empty / no-SHIP -> INSUFFICIENT_DATA, never green."""

    def test_missing_proposals_file(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row()])
        result = reconcile(proposals, graded)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["clean"] is False
        _assert_no_banned_keys(result, "missing proposals")

    def test_empty_proposals_file(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        proposals.write_text("")
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row()])
        result = reconcile(proposals, graded)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["clean"] is False
        _assert_no_banned_keys(result, "empty proposals")

    def test_no_ship_rows_in_proposals(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [
            _reject_proposal("nba"),
            _reject_proposal("mlb"),
        ])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row()])
        result = reconcile(proposals, graded)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n_ship_rows"] == 0
        assert result["clean"] is False
        _assert_no_banned_keys(result, "no ship rows")

    def test_missing_graded_file(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal()])
        graded = tmp_path / "graded.jsonl"  # not created
        result = reconcile(proposals, graded)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["clean"] is False
        _assert_no_banned_keys(result, "missing graded")

    def test_empty_graded_file(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal()])
        graded = tmp_path / "graded.jsonl"
        graded.write_text("")
        result = reconcile(proposals, graded)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["clean"] is False
        _assert_no_banned_keys(result, "empty graded")

    def test_both_files_missing(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        result = reconcile(proposals, graded)
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["clean"] is False
        _assert_no_banned_keys(result, "both missing")


# ---------------------------------------------------------------------------
# Drift detection: SHIP without a graded row
# ---------------------------------------------------------------------------


class TestDriftDetection:
    """SHIP row with no matching graded row -> drift flag."""

    def test_ship_without_graded_match_is_drift(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba", "2026-01-01T00:00:00")])
        graded = tmp_path / "graded.jsonl"
        # graded row for a DIFFERENT market name
        _write_jsonl(graded, [_graded_row("soccer:total", "2026-01-01T00:00:00")])
        result = reconcile(proposals, graded)
        assert result["status"] == "drift"
        assert result["n_drift"] >= 1
        assert result["clean"] is False
        assert len(result["drift_flags"]) >= 1
        drift = result["drift_flags"][0]
        assert "reason" in drift
        assert "ship_name" in drift
        _assert_no_banned_keys(result, "drift case")

    def test_two_ships_one_matched_one_drifted(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [
            _ship_proposal("nba", "2026-01-01T00:00:00", version=1),
            _ship_proposal("mlb", "2026-01-02T00:00:00", version=2),
        ])
        graded = tmp_path / "graded.jsonl"
        # only nba graded; mlb missing
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", "2026-01-01T00:00:00"),
        ])
        result = reconcile(proposals, graded)
        assert result["status"] == "drift"
        assert result["n_drift"] == 1
        assert result["n_matched"] == 1
        assert result["clean"] is False
        # Drift flag should reference mlb
        drift_names = [f["ship_name"] for f in result["drift_flags"]]
        assert "mlb" in drift_names
        _assert_no_banned_keys(result, "partial match")

    def test_all_ships_drifted(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [
            _ship_proposal("nba", "2026-01-01T00:00:00", version=1),
            _ship_proposal("mlb", "2026-01-01T00:00:00", version=2),
        ])
        graded = tmp_path / "graded.jsonl"
        # graded has tennis only -- no match for nba or mlb
        _write_jsonl(graded, [_graded_row("tennis:match", "2026-01-01T00:00:00")])
        result = reconcile(proposals, graded)
        assert result["status"] == "drift"
        assert result["n_drift"] == 2
        assert result["n_matched"] == 0
        assert result["clean"] is False
        _assert_no_banned_keys(result, "all drift")


# ---------------------------------------------------------------------------
# Clean path: all SHIP rows matched
# ---------------------------------------------------------------------------


class TestCleanPath:
    """All SHIP rows have a matching graded row -> clean=True."""

    def test_single_ship_matched(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba", "2026-01-01T00:00:00")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline", "2026-01-01T00:00:00")])
        result = reconcile(proposals, graded)
        assert result["status"] == "clean"
        assert result["clean"] is True
        assert result["n_drift"] == 0
        assert result["n_matched"] == 1
        _assert_no_banned_keys(result, "clean single")

    def test_two_ships_both_matched(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [
            _ship_proposal("nba", "2026-01-01T00:00:00", version=1),
            _ship_proposal("mlb", "2026-01-02T00:00:00", version=2),
        ])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", "2026-01-01T00:00:00"),
            _graded_row("mlb:moneyline", "2026-01-02T00:00:00"),
        ])
        result = reconcile(proposals, graded)
        assert result["status"] == "clean"
        assert result["clean"] is True
        assert result["n_drift"] == 0
        assert result["n_matched"] == 2
        assert result["n_ship_rows"] == 2
        _assert_no_banned_keys(result, "clean two ships")

    def test_reject_rows_ignored_clean(self, tmp_path: Path) -> None:
        """REJECT rows in proposals are not counted as SHIP rows."""
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [
            _ship_proposal("nba", "2026-01-01T00:00:00"),
            _reject_proposal("mlb", "2026-01-02T00:00:00"),
        ])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline", "2026-01-01T00:00:00")])
        result = reconcile(proposals, graded)
        assert result["status"] == "clean"
        assert result["clean"] is True
        assert result["n_ship_rows"] == 1  # only the SHIP row
        assert result["n_drift"] == 0
        _assert_no_banned_keys(result, "reject ignored")

    def test_extra_graded_rows_ok(self, tmp_path: Path) -> None:
        """Extra graded rows not referenced by any SHIP are allowed (no false drift)."""
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba", "2026-01-01T00:00:00")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", "2026-01-01T00:00:00"),
            _graded_row("soccer:total", "2026-01-01T00:00:00"),
            _graded_row("tennis:match", "2026-01-01T00:00:00"),
        ])
        result = reconcile(proposals, graded)
        assert result["status"] == "clean"
        assert result["clean"] is True
        assert result["n_drift"] == 0
        _assert_no_banned_keys(result, "extra graded ok")


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------


class TestReadOnly:
    """reconcile() must never mutate either file."""

    def test_proposals_not_modified(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba"), _reject_proposal("mlb")])
        original_proposals = proposals.read_text(encoding="utf-8")
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline")])
        reconcile(proposals, graded)
        assert proposals.read_text(encoding="utf-8") == original_proposals

    def test_graded_not_modified(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline")])
        original_graded = graded.read_text(encoding="utf-8")
        reconcile(proposals, graded)
        assert graded.read_text(encoding="utf-8") == original_graded

    def test_no_new_files_created(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline")])
        before = set(tmp_path.iterdir())
        reconcile(proposals, graded)
        after = set(tmp_path.iterdir())
        assert after == before, "reconcile() created unexpected files: %s" % (after - before)


# ---------------------------------------------------------------------------
# No banned keys
# ---------------------------------------------------------------------------


class TestNoBannedKeys:
    """No $/roi/pnl/profit key may appear in any output path."""

    def test_clean_result_no_banned_keys(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline")])
        result = reconcile(proposals, graded)
        _assert_no_banned_keys(result, "clean result")

    def test_drift_result_no_banned_keys(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("soccer:total")])
        result = reconcile(proposals, graded)
        _assert_no_banned_keys(result, "drift result")

    def test_insufficient_result_no_banned_keys(self, tmp_path: Path) -> None:
        result = reconcile(
            Path("/nonexistent/proposals.jsonl"),
            Path("/nonexistent/graded.jsonl"),
        )
        _assert_no_banned_keys(result, "insufficient result")


# ---------------------------------------------------------------------------
# Result shape contract
# ---------------------------------------------------------------------------


class TestResultShape:
    """Verify all required keys are present in every code path."""

    REQUIRED_KEYS = {
        "status", "n_ship_rows", "n_graded_rows",
        "n_matched", "n_drift", "drift_flags", "matched", "clean", "note",
    }

    def _check_shape(self, result: Dict[str, Any], ctx: str = "") -> None:
        for k in self.REQUIRED_KEYS:
            assert k in result, "Missing key '%s' in result%s" % (
                k, (" (%s)" % ctx) if ctx else "")

    def test_clean_result_shape(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline")])
        result = reconcile(proposals, graded)
        self._check_shape(result, "clean")

    def test_drift_result_shape(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("soccer:total")])
        result = reconcile(proposals, graded)
        self._check_shape(result, "drift")
        assert result["status"] == "drift"

    def test_insufficient_result_shape(self, tmp_path: Path) -> None:
        result = reconcile(
            Path("/nonexistent/proposals.jsonl"),
            Path("/nonexistent/graded.jsonl"),
        )
        self._check_shape(result, "insufficient")
        assert result["status"] == "INSUFFICIENT_DATA"
        assert "reason" in result

    def test_note_contains_calibration(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("nba:moneyline")])
        result = reconcile(proposals, graded)
        assert "calibration" in result["note"].lower()

    def test_drift_flags_contain_reason(self, tmp_path: Path) -> None:
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_proposal("nba")])
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row("soccer:total")])
        result = reconcile(proposals, graded)
        for flag in result["drift_flags"]:
            assert "reason" in flag
            assert "ship_name" in flag
