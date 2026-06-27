r"""tests/platformkit/improve/test_coverage_map.py -- SI-10 coverage map acceptance tests.

Acceptance contract (from BACKLOG.md SI-10):
  A. 1-of-4 families graded -> the other 3 have at least 3 cells with "untried".
  B. A shipped cell shows latest_delta (non-None Brier delta).
  C. A frozen family is flagged (cell.frozen == True).
  D. Missing ledger -> all cells emit status INSUFFICIENT_DATA.
  E. No key matching /(\$|roi|pnl|profit)/ in any cell or summary.
  F. Read-only: no file mutations; no flag flips.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/improve/test_coverage_map.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from scripts.platformkit.improve.coverage_map import build_coverage_map
from scripts.platformkit.improve.candidate_families import FAMILIES

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

BANNED_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)
ALL_FAMILIES = list(FAMILIES)  # 7 families as of 2026-06-20

_CALIBRATION_NOTE_FRAGMENT = "calibration != edge"

# Minimum settled rows per market to trigger a non-INSUFFICIENT_DATA cell.
# Must match per_market_ledger.MIN_MARKET_N = 30.
_MIN_MARKET_N = 30


def _all_keys(obj: Any) -> List[str]:
    """Recursively collect all dict keys (for banned-key scan)."""
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _no_banned_keys(obj: Any) -> bool:
    for k in _all_keys(obj):
        if BANNED_RE.search(k):
            return False
    return True


def _write_ledger(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _write_tried(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _make_ledger_row(
    market: str,
    status: str = "HOLD",
    raw_brier: Optional[float] = 0.23,
) -> Dict[str, Any]:
    """Build a minimal ledger row as PerMarketLedger would write it."""
    row: Dict[str, Any] = {
        "ts": "2026-06-19T10:00:00+00:00",
        "market": market,
        "note": "calibration != edge: ...",
        "status": status,
    }
    if status != "INSUFFICIENT_DATA" and raw_brier is not None:
        row["readout"] = {
            "n": _MIN_MARKET_N + 5,
            "n_with_close": _MIN_MARKET_N + 5,
            "raw_brier": raw_brier,
            "bss_vs_close": 0.01 if status == "SHIP" else 0.0,
        }
    elif status == "INSUFFICIENT_DATA":
        row["n"] = 5
        row["min_n"] = _MIN_MARKET_N
    return row


def _make_tried_row(
    family: str,
    candidate_id: str = "cand_abc123",
    verdict: str = "REJECT",
) -> Dict[str, Any]:
    """Build a minimal tried-families row as candidate_enum.append_tried would write."""
    return {
        "candidate_id": candidate_id,
        "family": family,
        "sport": "nba",
        "target": "win_prob",
        "signature": "recal=platt",
        "note": "calibration, not edge",
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# D: Missing ledger -> all cells INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestMissingLedger:
    """D: When the ledger file does not exist -> every cell emits INSUFFICIENT_DATA."""

    def test_no_ledger_all_cells_insufficient(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "nonexistent.jsonl"
        tried_path = tmp_path / "tried.jsonl"
        result = build_coverage_map(ledger_path=ledger_path, tried_path=tried_path)
        cells = result["cells"]
        assert len(cells) > 0, "expected at least one cell even with missing ledger"
        for cell in cells:
            assert cell["status"] == "INSUFFICIENT_DATA", (
                "expected INSUFFICIENT_DATA when ledger absent, got %r for cell %r"
                % (cell["status"], cell)
            )

    def test_no_ledger_ledger_present_false(self, tmp_path: Path) -> None:
        result = build_coverage_map(
            ledger_path=tmp_path / "missing.jsonl",
            tried_path=tmp_path / "tried.jsonl",
        )
        assert result["ledger_present"] is False

    def test_no_ledger_no_banned_keys(self, tmp_path: Path) -> None:
        result = build_coverage_map(
            ledger_path=tmp_path / "missing.jsonl",
            tried_path=tmp_path / "tried.jsonl",
        )
        assert _no_banned_keys(result), "banned $ key found in result with missing ledger"

    def test_empty_ledger_all_cells_insufficient(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        ledger_path.write_text("", encoding="utf-8")
        result = build_coverage_map(
            ledger_path=ledger_path,
            tried_path=tmp_path / "tried.jsonl",
        )
        for cell in result["cells"]:
            assert cell["status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# A: 1-of-4 families graded -> 3 cells "untried" (per the 4-family view)
# ---------------------------------------------------------------------------

class TestOneOfFourGraded:
    """A: 1-of-4 families graded -> the other 3 produce untried cells for that aspect.

    We use 4 families from ALL_FAMILIES. One is marked tried, three are not.
    With a single market aspect in the ledger, each family produces exactly one
    cell for that aspect. The tried family -> graded, the three untried -> untried.
    """

    def _setup(self, tmp_path: Path):
        """Return (ledger_path, tried_path) for a scenario with 4 families, 1 tried."""
        ledger_path = tmp_path / "ledger.jsonl"
        tried_path = tmp_path / "tried.jsonl"

        # One market aspect with a real readout (above MIN_MARKET_N).
        _write_ledger(ledger_path, [_make_ledger_row("nba:moneyline", status="HOLD")])

        # Only ONE family is marked tried (the first family in FAMILIES list).
        tried_fam = ALL_FAMILIES[0]
        _write_tried(tried_path, [_make_tried_row(tried_fam, verdict="REJECT")])

        return ledger_path, tried_path, tried_fam

    def test_one_graded_three_untried(self, tmp_path: Path) -> None:
        lp, tp, tried_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        cells = result["cells"]

        # Filter to the 4 families we care about (first 4 from the list).
        families_4 = ALL_FAMILIES[:4]
        cells_4 = [c for c in cells if c["family"] in families_4
                   and c["aspect"] == "nba:moneyline"]

        # Exactly 4 cells for 4 families x 1 aspect.
        assert len(cells_4) == 4, (
            "expected 4 cells for 4 families x 1 aspect, got %d" % len(cells_4)
        )

        # The tried family is graded; the other 3 are untried.
        untried = [c for c in cells_4 if c["status"] == "untried"]
        graded_or_shipped = [
            c for c in cells_4 if c["status"] in ("graded", "shipped", "INSUFFICIENT_DATA")
        ]
        tried_cells = [c for c in cells_4 if c["family"] == tried_fam]
        assert len(tried_cells) == 1
        assert tried_cells[0]["status"] != "untried", (
            "tried family should not be untried; got %r" % tried_cells[0]["status"]
        )
        assert len(untried) == 3, (
            "expected 3 untried cells for 3 un-tried families, got %d: %r"
            % (len(untried), [c["family"] for c in untried])
        )

    def test_summary_untried_count(self, tmp_path: Path) -> None:
        lp, tp, tried_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        # Summary untried must be >= 3 (there are 7 families, only 1 tried).
        assert result["summary"]["untried"] >= 3, (
            "expected >= 3 untried in summary, got %d" % result["summary"]["untried"]
        )

    def test_tried_family_cell_not_untried(self, tmp_path: Path) -> None:
        lp, tp, tried_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        tried_cells = [c for c in result["cells"]
                       if c["family"] == tried_fam and c["aspect"] == "nba:moneyline"]
        assert tried_cells, "expected at least one cell for the tried family"
        for cell in tried_cells:
            assert cell["status"] != "untried", (
                "tried family should not have status 'untried'; got %r" % cell["status"]
            )


# ---------------------------------------------------------------------------
# B: Shipped cell shows latest_delta
# ---------------------------------------------------------------------------

class TestShippedCellLatestDelta:
    """B: A cell from a shipped ledger row must carry a non-None latest_delta."""

    def _setup(self, tmp_path: Path):
        ledger_path = tmp_path / "ledger.jsonl"
        tried_path = tmp_path / "tried.jsonl"

        # One market with SHIP status and a known raw_brier.
        _write_ledger(ledger_path, [
            _make_ledger_row("nba:moneyline", status="SHIP", raw_brier=0.215)
        ])
        tried_fam = ALL_FAMILIES[0]
        _write_tried(tried_path, [_make_tried_row(tried_fam, verdict="SHIP")])

        return ledger_path, tried_path, tried_fam

    def test_shipped_cell_has_latest_delta(self, tmp_path: Path) -> None:
        lp, tp, tried_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        shipped_cells = [c for c in result["cells"]
                         if c["status"] == "shipped"
                         and c["family"] == tried_fam]
        assert shipped_cells, "expected at least one shipped cell for tried family"
        for cell in shipped_cells:
            assert cell["latest_delta"] is not None, (
                "shipped cell must carry latest_delta; got None for %r" % cell
            )

    def test_shipped_cell_latest_delta_is_float(self, tmp_path: Path) -> None:
        lp, tp, tried_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        shipped = [c for c in result["cells"] if c["status"] == "shipped"]
        for cell in shipped:
            assert isinstance(cell["latest_delta"], float), (
                "latest_delta must be float, got %r" % type(cell["latest_delta"])
            )

    def test_untried_cells_latest_delta_none(self, tmp_path: Path) -> None:
        lp, tp, _ = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        untried_cells = [c for c in result["cells"] if c["status"] == "untried"]
        for cell in untried_cells:
            assert cell["latest_delta"] is None, (
                "untried cell should have latest_delta=None; got %r" % cell["latest_delta"]
            )

    def test_summary_shipped_count(self, tmp_path: Path) -> None:
        lp, tp, tried_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        assert result["summary"]["shipped"] >= 1, "expected >= 1 shipped cell in summary"


# ---------------------------------------------------------------------------
# C: Frozen family is flagged
# ---------------------------------------------------------------------------

class TestFrozenFamily:
    """C: A family whose planted null shipped must be flagged as frozen in the map."""

    def _setup(self, tmp_path: Path):
        ledger_path = tmp_path / "ledger.jsonl"
        tried_path = tmp_path / "tried.jsonl"

        _write_ledger(ledger_path, [
            _make_ledger_row("nba:moneyline", status="HOLD")
        ])

        # Mark the first family as having its planted null shipped (frozen trigger).
        frozen_fam = ALL_FAMILIES[0]
        _write_tried(tried_path, [
            {
                "candidate_id": "cand_null_001",
                "family": frozen_fam,
                "sport": "nba",
                "target": "win_prob",
                "signature": "planted_null",
                "note": "calibration, not edge",
                "verdict": "SHIP",
                "is_planted_null": True,  # triggers frozen_families()
                "null_ships": 1,
            }
        ])
        return ledger_path, tried_path, frozen_fam

    def test_frozen_family_flagged(self, tmp_path: Path) -> None:
        lp, tp, frozen_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        frozen_cells = [c for c in result["cells"] if c["family"] == frozen_fam]
        assert frozen_cells, "expected cells for frozen family"
        for cell in frozen_cells:
            assert cell["frozen"] is True, (
                "family %r should be flagged frozen; cell.frozen=%r" % (frozen_fam, cell["frozen"])
            )

    def test_frozen_cell_status(self, tmp_path: Path) -> None:
        lp, tp, frozen_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        frozen_cells = [c for c in result["cells"] if c["family"] == frozen_fam]
        for cell in frozen_cells:
            assert cell["status"] == "frozen", (
                "frozen family cells should have status 'frozen'; got %r" % cell["status"]
            )

    def test_non_frozen_family_not_flagged(self, tmp_path: Path) -> None:
        lp, tp, frozen_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        other_cells = [c for c in result["cells"] if c["family"] != frozen_fam]
        # Not all non-frozen families should be flagged frozen.
        any_wrongly_frozen = any(c["frozen"] for c in other_cells)
        assert not any_wrongly_frozen, (
            "non-frozen families should not be flagged; found frozen=True in: %r"
            % [c["family"] for c in other_cells if c["frozen"]]
        )

    def test_frozen_count_in_summary(self, tmp_path: Path) -> None:
        lp, tp, frozen_fam = self._setup(tmp_path)
        result = build_coverage_map(ledger_path=lp, tried_path=tp)
        assert result["summary"]["frozen"] >= 1, (
            "expected >= 1 frozen cell in summary"
        )


# ---------------------------------------------------------------------------
# E: No banned $ / roi / pnl / profit key anywhere
# ---------------------------------------------------------------------------

class TestNoBannedKeys:
    """E: No key matching dollar/roi/pnl/profit in any output field."""

    def test_no_banned_keys_full_result(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        tried_path = tmp_path / "tried.jsonl"
        _write_ledger(ledger_path, [
            _make_ledger_row("nba:moneyline", status="SHIP", raw_brier=0.21),
            _make_ledger_row("mlb:totals", status="REJECT", raw_brier=0.28),
            _make_ledger_row("prop:pts", status="INSUFFICIENT_DATA"),
        ])
        _write_tried(tried_path, [_make_tried_row(ALL_FAMILIES[0], verdict="SHIP")])
        result = build_coverage_map(ledger_path=ledger_path, tried_path=tried_path)
        assert _no_banned_keys(result), "banned key found in full result"

    def test_no_banned_keys_missing_ledger(self, tmp_path: Path) -> None:
        result = build_coverage_map(
            ledger_path=tmp_path / "none.jsonl",
            tried_path=tmp_path / "tried.jsonl",
        )
        assert _no_banned_keys(result)

    def test_no_banned_keys_each_cell(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        _write_ledger(ledger_path, [_make_ledger_row("nba:moneyline", status="HOLD")])
        result = build_coverage_map(ledger_path=ledger_path,
                                    tried_path=tmp_path / "tried.jsonl")
        for cell in result["cells"]:
            assert _no_banned_keys(cell), (
                "banned key found in cell: %r" % cell
            )


# ---------------------------------------------------------------------------
# F: Read-only -- no file mutations
# ---------------------------------------------------------------------------

class TestReadOnly:
    """F: build_coverage_map must not write or modify any file."""

    def test_does_not_write_ledger(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        tried_path = tmp_path / "tried.jsonl"
        _write_ledger(ledger_path, [_make_ledger_row("nba:moneyline")])
        mtime_before = ledger_path.stat().st_mtime
        build_coverage_map(ledger_path=ledger_path, tried_path=tried_path)
        mtime_after = ledger_path.stat().st_mtime
        assert mtime_after == mtime_before, "build_coverage_map modified the ledger file"

    def test_does_not_create_extra_files(self, tmp_path: Path) -> None:
        before = set(tmp_path.iterdir())
        build_coverage_map(
            ledger_path=tmp_path / "nope.jsonl",
            tried_path=tmp_path / "tried.jsonl",
        )
        after = set(tmp_path.iterdir())
        assert after == before, "build_coverage_map created unexpected files: %r" % (after - before)


# ---------------------------------------------------------------------------
# G: Structural / contract checks
# ---------------------------------------------------------------------------

class TestStructural:
    """Structural contract: vs_close UNPROVEN, note present, cells keyed by family+aspect."""

    def test_vs_close_unproven_on_each_cell(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        _write_ledger(ledger_path, [_make_ledger_row("nba:moneyline", status="SHIP")])
        result = build_coverage_map(ledger_path=ledger_path,
                                    tried_path=tmp_path / "tried.jsonl")
        for cell in result["cells"]:
            assert cell.get("vs_close") == "UNPROVEN", (
                "expected vs_close=UNPROVEN; got %r" % cell.get("vs_close")
            )

    def test_calibration_note_in_each_cell(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        _write_ledger(ledger_path, [_make_ledger_row("nba:moneyline")])
        result = build_coverage_map(ledger_path=ledger_path,
                                    tried_path=tmp_path / "tried.jsonl")
        for cell in result["cells"]:
            assert _CALIBRATION_NOTE_FRAGMENT in cell.get("note", ""), (
                "calibration note missing from cell: %r" % cell
            )

    def test_all_known_families_present(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        _write_ledger(ledger_path, [_make_ledger_row("nba:moneyline")])
        result = build_coverage_map(ledger_path=ledger_path,
                                    tried_path=tmp_path / "tried.jsonl")
        families_in_cells = {c["family"] for c in result["cells"]}
        for fam in ALL_FAMILIES:
            assert fam in families_in_cells, (
                "family %r not found in coverage map cells" % fam
            )

    def test_summary_has_required_keys(self, tmp_path: Path) -> None:
        result = build_coverage_map(
            ledger_path=tmp_path / "none.jsonl",
            tried_path=tmp_path / "tried.jsonl",
        )
        for key in ("total", "graded", "untried", "shipped", "frozen",
                    "insufficient_data"):
            assert key in result["summary"], "missing summary key: %r" % key

    def test_multiple_markets_multiple_aspects(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        tried_path = tmp_path / "tried.jsonl"
        _write_ledger(ledger_path, [
            _make_ledger_row("nba:moneyline", status="HOLD"),
            _make_ledger_row("mlb:totals", status="REJECT"),
        ])
        result = build_coverage_map(ledger_path=ledger_path, tried_path=tried_path)
        aspects = {c["aspect"] for c in result["cells"]}
        assert "nba:moneyline" in aspects
        assert "mlb:totals" in aspects

    def test_total_equals_families_times_aspects(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "ledger.jsonl"
        _write_ledger(ledger_path, [
            _make_ledger_row("nba:moneyline"),
            _make_ledger_row("mlb:totals"),
        ])
        result = build_coverage_map(ledger_path=ledger_path,
                                    tried_path=tmp_path / "tried.jsonl")
        n_families = len(ALL_FAMILIES)
        n_aspects = 2
        assert result["summary"]["total"] == n_families * n_aspects, (
            "expected total=%d, got %d" % (n_families * n_aspects,
                                           result["summary"]["total"])
        )
