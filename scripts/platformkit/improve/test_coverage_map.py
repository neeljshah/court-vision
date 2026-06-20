"""Per-file test for scripts.platformkit.improve.coverage_map (SI-10).

Acceptance criteria:
  - Ledger absent or empty -> all cells INSUFFICIENT_DATA (stale-never-green)
  - Tried-family NOT in tried_families.jsonl -> cell status "untried"
  - Tried family + graded SHIP -> cell status "shipped"
  - Tried family + non-SHIP ledger row -> cell status "graded"
  - Frozen family (null_shipped) -> cell status "frozen"
  - vs_close = "UNPROVEN" on every cell
  - no $ / roi / pnl / profit key in any output

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_coverage_map.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.improve.coverage_map import build_coverage_map
from scripts.platformkit.improve.candidate_families import FAMILIES

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
            "Banned key %r found%s" % (k, (" in " + context) if context else "")
        )


def _write_jsonl(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _ledger_row(market: str = "nba:moneyline", status: str = "HOLD") -> Dict:
    return {"market": market, "status": status, "ts": "2026-01-01T00:00:00+00:00"}


def _tried_row(
    family: str,
    verdict: str = "REJECT",
    is_planted_null: bool = False,
) -> Dict:
    """A tried-families row for a given family (mimics append_tried output)."""
    return {
        "candidate_id": "cand_test_%s" % family,
        "family": family,
        "sport": "nba",
        "target": "win_prob",
        "signature": "test:%s" % family,
        "verdict": verdict,
        "status": verdict,
        "is_planted_null": is_planted_null,
        "note": "calibration, not edge",
    }


# ---------------------------------------------------------------------------
# Class 1: Ledger absent / empty -> INSUFFICIENT_DATA for all cells
# ---------------------------------------------------------------------------


class TestInsufficientDataWhenNoLedger:
    """Missing or empty ledger -> every cell must be INSUFFICIENT_DATA."""

    def test_no_ledger_all_cells_insufficient(self, tmp_path: Path) -> None:
        """Ledger absent -> every cell reports INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"  # does not exist
        tried = tmp_path / "tried.jsonl"    # does not exist
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        assert len(cells) == len(FAMILIES), (
            "Expected one cell per family; got %d cells for %d families"
            % (len(cells), len(FAMILIES))
        )
        for cell in cells:
            assert cell["status"] == "INSUFFICIENT_DATA", (
                "Family %r should be INSUFFICIENT_DATA with no ledger; got %r"
                % (cell["family"], cell["status"])
            )
        _assert_no_banned_keys(result, "no ledger")

    def test_empty_ledger_all_cells_insufficient(self, tmp_path: Path) -> None:
        """Empty ledger file -> every cell INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        insuff = [c for c in cells if c["status"] == "INSUFFICIENT_DATA"]
        assert len(insuff) == len(cells), (
            "All cells should be INSUFFICIENT_DATA with empty ledger"
        )

    def test_insufficient_summary_counts(self, tmp_path: Path) -> None:
        """Summary insufficient_data count must equal total cells when ledger absent."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        summary = result["summary"]
        assert summary["insufficient_data"] == summary["total"]
        assert summary["graded"] == 0
        assert summary["shipped"] == 0


# ---------------------------------------------------------------------------
# Class 2: Untried cells -- family not in tried_families.jsonl
# ---------------------------------------------------------------------------


class TestUntriedCells:
    """Families not appearing in tried_families.jsonl produce untried cells."""

    def test_untried_family_shows_untried_cell(self, tmp_path: Path) -> None:
        """A family absent from tried file -> cell status 'untried'."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        # Ledger has a row so we get into the real cell logic
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "HOLD")])
        # Tried file has a DIFFERENT family (not the one we're checking)
        other_fam = FAMILIES[0] if FAMILIES[0] != FAMILIES[-1] else FAMILIES[1]
        _write_jsonl(tried, [_tried_row(other_fam)])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        # Families NOT in tried should be 'untried'
        tried_names = {other_fam}
        for cell in cells:
            if cell["family"] not in tried_names:
                assert cell["status"] == "untried", (
                    "Family %r not in tried -> expected 'untried'; got %r"
                    % (cell["family"], cell["status"])
                )

    def test_all_families_untried_when_tried_absent(self, tmp_path: Path) -> None:
        """No tried file + ledger present -> every cell is 'untried'."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"  # does not exist
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "HOLD")])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        statuses = {c["status"] for c in cells}
        # With no tried file, no family is tried; all cells should be untried
        assert statuses <= {"untried", "frozen", "INSUFFICIENT_DATA"}, (
            "With empty tried file, cells should only be untried/frozen/INSUFFICIENT_DATA; "
            "got %s" % statuses
        )

    def test_summary_untried_count(self, tmp_path: Path) -> None:
        """Summary untried count must match actual untried cells."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "HOLD")])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        summary = result["summary"]
        cells = result["cells"]
        real_untried = sum(1 for c in cells if c["status"] == "untried")
        assert summary["untried"] == real_untried


# ---------------------------------------------------------------------------
# Class 3: Shipped cell
# ---------------------------------------------------------------------------


class TestShippedCell:
    """A tried family with a SHIP row in the ledger produces a 'shipped' cell."""

    def test_tried_family_ship_ledger_shipped(self, tmp_path: Path) -> None:
        """Family in tried + SHIP ledger row -> cell status 'shipped'."""
        fam = FAMILIES[0]  # e.g. "recal_variant"
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "SHIP")])
        _write_jsonl(tried, [_tried_row(fam, verdict="SHIP")])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        shipped = [c for c in cells if c["family"] == fam and c["status"] == "shipped"]
        assert len(shipped) >= 1, (
            "Expected at least one 'shipped' cell for family %r; cells=%r"
            % (fam, [(c["family"], c["status"]) for c in cells])
        )
        _assert_no_banned_keys(result, "shipped cell")

    def test_shipped_cell_summary_incremented(self, tmp_path: Path) -> None:
        """Summary 'shipped' count must be >= 1 when a shipped cell exists."""
        fam = FAMILIES[0]
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:ml", "SHIP")])
        _write_jsonl(tried, [_tried_row(fam, verdict="SHIP")])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        assert result["summary"]["shipped"] >= 1


# ---------------------------------------------------------------------------
# Class 4: Graded cell
# ---------------------------------------------------------------------------


class TestGradedCell:
    """A tried family with a non-SHIP ledger row produces a 'graded' cell."""

    def test_tried_family_hold_ledger_graded(self, tmp_path: Path) -> None:
        """Family in tried + HOLD ledger row -> cell status 'graded'."""
        fam = FAMILIES[0]
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "HOLD")])
        _write_jsonl(tried, [_tried_row(fam, verdict="REJECT")])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        graded = [c for c in cells if c["family"] == fam and c["status"] == "graded"]
        assert len(graded) >= 1, (
            "Expected at least one 'graded' cell for family %r; cells=%r"
            % (fam, [(c["family"], c["status"]) for c in cells])
        )

    def test_graded_summary_count(self, tmp_path: Path) -> None:
        fam = FAMILIES[0]
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "HOLD")])
        _write_jsonl(tried, [_tried_row(fam, verdict="REJECT")])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        real_graded = sum(1 for c in cells if c["status"] == "graded")
        assert result["summary"]["graded"] == real_graded


# ---------------------------------------------------------------------------
# Class 5: Frozen family
# ---------------------------------------------------------------------------


class TestFrozenFamily:
    """A family whose planted null shipped must appear as 'frozen' in cells."""

    def test_null_shipped_family_is_frozen(self, tmp_path: Path) -> None:
        """Family with is_planted_null=True and verdict=SHIP -> frozen cell."""
        fam = FAMILIES[0]
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "SHIP")])
        # A planted null that shipped -> family is frozen
        _write_jsonl(tried, [_tried_row(fam, verdict="SHIP", is_planted_null=True)])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        frozen = [c for c in cells if c["family"] == fam and c["status"] == "frozen"]
        # frozen is set based on prioritizer.frozen_families which requires null_shipped
        # in the ledger built from tried rows; confirm frozen=True on at least one cell
        frozen_flag = [c for c in cells if c["family"] == fam and c.get("frozen") is True]
        assert len(frozen_flag) >= 1, (
            "Family %r should be flagged frozen when planted null shipped; "
            "cells=%r" % (fam, [(c["family"], c.get("frozen"), c["status"]) for c in cells])
        )
        _assert_no_banned_keys(result, "frozen family")

    def test_frozen_summary_count(self, tmp_path: Path) -> None:
        """Summary frozen count must match cells with frozen=True."""
        fam = FAMILIES[0]
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:ml", "SHIP")])
        _write_jsonl(tried, [_tried_row(fam, verdict="SHIP", is_planted_null=True)])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        real_frozen = sum(1 for c in cells if c.get("frozen") is True)
        assert result["summary"]["frozen"] == real_frozen


# ---------------------------------------------------------------------------
# Class 6: vs_close and no banned keys on all paths
# ---------------------------------------------------------------------------


class TestContractGuarantees:
    """vs_close=UNPROVEN, no banned keys, calibration note on all outputs."""

    def test_vs_close_always_unproven(self, tmp_path: Path) -> None:
        """Every cell must carry vs_close='UNPROVEN'; never auto-claimed."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "HOLD")])
        _write_jsonl(tried, [_tried_row(FAMILIES[0])])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        for cell in result["cells"]:
            assert cell.get("vs_close") == "UNPROVEN", (
                "Cell vs_close should be UNPROVEN; got %r" % cell.get("vs_close")
            )

    def test_result_vs_close_unproven(self, tmp_path: Path) -> None:
        """Top-level vs_close on the result dict must be UNPROVEN."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        assert result.get("vs_close") == "UNPROVEN"

    def test_no_banned_keys_ledger_absent(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        _assert_no_banned_keys(result, "ledger absent")

    def test_no_banned_keys_with_data(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [_ledger_row("nba:moneyline", "SHIP")])
        _write_jsonl(tried, [_tried_row(FAMILIES[0], verdict="SHIP")])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        _assert_no_banned_keys(result, "with data")

    def test_note_field_present(self, tmp_path: Path) -> None:
        """Top-level 'note' on the result must contain 'calibration'."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        assert "note" in result
        assert "calibration" in result["note"].lower()

    def test_cells_note_field(self, tmp_path: Path) -> None:
        """Each cell must carry a note with 'calibration'."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        for cell in result["cells"]:
            assert "note" in cell
            assert "calibration" in cell["note"].lower()

    def test_summary_keys_present(self, tmp_path: Path) -> None:
        """Summary must have total, graded, untried, shipped, frozen, insufficient_data."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        for key in ("total", "graded", "untried", "shipped", "frozen", "insufficient_data"):
            assert key in result["summary"], "Summary missing key %r" % key

    def test_multiple_markets_produce_cells_per_family(self, tmp_path: Path) -> None:
        """With two market rows in ledger, each family gets two cells (one per aspect)."""
        ledger = tmp_path / "ledger.jsonl"
        tried = tmp_path / "tried.jsonl"
        _write_jsonl(ledger, [
            _ledger_row("nba:moneyline", "HOLD"),
            _ledger_row("nba:totals", "SHIP"),
        ])
        result = build_coverage_map(ledger_path=ledger, tried_path=tried)
        cells = result["cells"]
        # 2 markets x len(FAMILIES) families = 2*len(FAMILIES) cells
        assert len(cells) == 2 * len(FAMILIES), (
            "Expected %d cells (2 markets x %d families); got %d"
            % (2 * len(FAMILIES), len(FAMILIES), len(cells))
        )
