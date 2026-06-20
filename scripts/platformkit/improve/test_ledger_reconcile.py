"""Per-file test for scripts.platformkit.improve.ledger_reconcile (SI-11).

Acceptance criteria (per workstream spec BE-R5-5-si-ledger-reconcile-parity):
  (a) daemon SHIP with matching graded row -> 0 orphans, verdict CLEAN
  (b) daemon SHIP with NO graded row -> orphan_ship reported, verdict NO_CANDIDATE
  (c) graded row with no daemon entry -> orphan_grade reported, verdict NO_CANDIDATE
  (d) empty ledgers -> INSUFFICIENT_DATA, never raises, no $ field

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_ledger_reconcile.py -q
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
    VERDICT_CLEAN,
    VERDICT_NO_CANDIDATE,
    VERDICT_INSUFFICIENT,
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
            "Banned key %r found%s" % (k, (" in " + context) if context else "")
        )


def _write_jsonl(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _ship_row(name: str = "nba", ts: str = "2026-01-01T00:00:00+00:00") -> Dict:
    return {"decision": "SHIP", "name": name, "ts": ts, "shipped_version": "v1"}


def _graded_row(market: str = "nba:moneyline", ts: str = "2026-01-01T00:00:00+00:00") -> Dict:
    return {"market": market, "ts": ts, "status": "SHIP"}


# ---------------------------------------------------------------------------
# (a) Acceptance criterion A: SHIP with matching graded row -> CLEAN, 0 orphans
# ---------------------------------------------------------------------------


class TestAcceptanceCriterionA:
    """(a) A daemon SHIP with a matching graded row reconciles clean (0 orphans)."""

    def test_matched_ship_is_clean(self, tmp_path: Path) -> None:
        """Single SHIP row with a matching graded row -> verdict CLEAN, clean=True."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-01-15T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [_graded_row("nba:moneyline", ts)])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_CLEAN, result
        assert result["clean"] is True
        assert result["n_orphan_ship"] == 0
        assert result["n_orphan_grade"] == 0
        assert result["n_matched"] == 1
        _assert_no_banned_keys(result, "clean reconciliation")

    def test_two_ships_both_matched(self, tmp_path: Path) -> None:
        """Two SHIP rows, both with graded matches -> CLEAN, n_matched=2, 0 orphans."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-02-10T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts), _ship_row("mlb", ts)])
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", ts),
            _graded_row("mlb:moneyline", ts),
        ])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_CLEAN
        assert result["clean"] is True
        assert result["n_matched"] == 2
        assert result["n_orphan_ship"] == 0
        assert result["n_orphan_grade"] == 0
        _assert_no_banned_keys(result, "two matched")

    def test_matched_records_names_and_markets(self, tmp_path: Path) -> None:
        """Matched list must carry ship_name and graded_market."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-01-20T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [_graded_row("nba:pts", ts)])
        result = reconcile(proposals, graded)
        assert len(result["matched"]) == 1
        m = result["matched"][0]
        assert m["ship_name"] == "nba"
        assert "nba" in m["graded_market"]

    def test_carries_calibration_note(self, tmp_path: Path) -> None:
        """Every result must carry the calibration note (no edge claim)."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-01-01T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [_graded_row("nba:moneyline", ts)])
        result = reconcile(proposals, graded)
        assert "note" in result
        assert "calibration" in result["note"].lower()


# ---------------------------------------------------------------------------
# (b) Acceptance criterion B: SHIP with NO graded row -> orphan_ship, NO_CANDIDATE
# ---------------------------------------------------------------------------


class TestAcceptanceCriterionB:
    """(b) A daemon SHIP with no graded row is reported as orphan_ship, NO_CANDIDATE."""

    def test_unmatched_ship_is_orphan_ship(self, tmp_path: Path) -> None:
        """SHIP 'nba' with no graded 'nba:*' -> orphan_ship in result."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(proposals, [_ship_row("nba", "2026-01-01T00:00:00+00:00")])
        # Graded row for tennis, not nba
        _write_jsonl(graded, [{"market": "tennis:moneyline",
                                "ts": "2026-01-01T00:00:00+00:00", "status": "SHIP"}])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_NO_CANDIDATE, result
        assert result["n_orphan_ship"] == 1
        assert result["clean"] is False
        assert len(result["orphan_ships"]) == 1
        _assert_no_banned_keys(result, "orphan ship")

    def test_orphan_ship_verdict_is_no_candidate(self, tmp_path: Path) -> None:
        """Orphan SHIP must block auto-promotion: verdict must be NO_CANDIDATE."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(proposals, [_ship_row("mlb", "2026-02-01T00:00:00+00:00")])
        _write_jsonl(graded, [{"market": "tennis:moneyline",
                                "ts": "2026-02-01T00:00:00+00:00"}])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_NO_CANDIDATE
        # clean must be False when there are orphans
        assert result["clean"] is False

    def test_orphan_ship_flag_contains_name(self, tmp_path: Path) -> None:
        """orphan_ships entries must record ship_name."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(proposals, [_ship_row("soccer")])
        _write_jsonl(graded, [{"market": "tennis:moneyline",
                                "ts": "2026-01-01T00:00:00+00:00"}])
        result = reconcile(proposals, graded)
        assert len(result["orphan_ships"]) >= 1
        flag = result["orphan_ships"][0]
        assert flag["ship_name"] == "soccer"
        assert isinstance(flag.get("reason"), str) and len(flag["reason"]) > 5

    def test_partial_match_produces_orphan_ship(self, tmp_path: Path) -> None:
        """Two SHIP rows, one matched -> n_orphan_ship=1, verdict NO_CANDIDATE."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-03-01T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts), _ship_row("mlb", ts)])
        _write_jsonl(graded, [_graded_row("nba:moneyline", ts)])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_NO_CANDIDATE
        assert result["n_orphan_ship"] == 1
        assert result["n_matched"] == 1
        _assert_no_banned_keys(result, "partial match")


# ---------------------------------------------------------------------------
# (c) Acceptance criterion C: graded row with no daemon entry -> orphan_grade
# ---------------------------------------------------------------------------


class TestAcceptanceCriterionC:
    """(c) A graded row with no daemon entry is reported as orphan_grade, NO_CANDIDATE."""

    def test_graded_without_daemon_is_orphan_grade(self, tmp_path: Path) -> None:
        """Graded row with no matching SHIP row -> orphan_grade, NO_CANDIDATE."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-01-01T00:00:00+00:00"
        # Daemon only has 'nba' SHIP
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        # Graded has 'nba' and an extra 'soccer' that the daemon never proposed
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", ts),
            _graded_row("soccer:total", ts),
        ])
        result = reconcile(proposals, graded)
        # nba matches; soccer is an orphan_grade
        assert result["n_orphan_grade"] == 1
        assert result["verdict"] == VERDICT_NO_CANDIDATE
        assert result["clean"] is False
        assert len(result["orphan_grades"]) == 1
        _assert_no_banned_keys(result, "orphan grade")

    def test_orphan_grade_carries_market_info(self, tmp_path: Path) -> None:
        """orphan_grades entries must record graded_market."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-04-01T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", ts),
            _graded_row("tennis:moneyline", ts),
        ])
        result = reconcile(proposals, graded)
        og = result["orphan_grades"]
        assert len(og) == 1
        assert og[0]["graded_market"] == "tennis:moneyline"
        assert isinstance(og[0].get("reason"), str) and len(og[0]["reason"]) > 5

    def test_all_graded_orphan_is_no_candidate(self, tmp_path: Path) -> None:
        """If ALL graded rows are orphans (no daemon SHIP matches) -> NO_CANDIDATE."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-05-01T00:00:00+00:00"
        # Daemon SHIPped 'nba', graded has only 'tennis'
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [_graded_row("tennis:moneyline", ts)])
        result = reconcile(proposals, graded)
        # nba is orphan_ship; tennis is orphan_grade
        assert result["verdict"] == VERDICT_NO_CANDIDATE
        assert result["n_orphan_ship"] >= 1
        assert result["n_orphan_grade"] >= 1
        _assert_no_banned_keys(result, "all orphan")

    def test_multiple_orphan_grades(self, tmp_path: Path) -> None:
        """Multiple extra graded rows each become orphan_grade entries."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-06-01T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", ts),   # matches
            _graded_row("mlb:moneyline", ts),    # orphan
            _graded_row("tennis:atp", ts),       # orphan
        ])
        result = reconcile(proposals, graded)
        assert result["n_orphan_grade"] == 2
        assert result["verdict"] == VERDICT_NO_CANDIDATE


# ---------------------------------------------------------------------------
# (d) Acceptance criterion D: empty ledgers -> INSUFFICIENT_DATA, never raises
# ---------------------------------------------------------------------------


class TestAcceptanceCriterionD:
    """(d) Empty or missing ledgers -> INSUFFICIENT_DATA, never raises, no $ field."""

    def test_both_missing_is_insufficient(self, tmp_path: Path) -> None:
        """Both files absent -> INSUFFICIENT_DATA, never raises."""
        result = reconcile(tmp_path / "nope.jsonl", tmp_path / "nope2.jsonl")
        assert result["verdict"] == VERDICT_INSUFFICIENT
        assert result["clean"] is False
        _assert_no_banned_keys(result, "both missing")

    def test_proposals_missing_is_insufficient(self, tmp_path: Path) -> None:
        """Missing proposals file -> INSUFFICIENT_DATA."""
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(graded, [_graded_row()])
        result = reconcile(tmp_path / "proposals.jsonl", graded)
        assert result["verdict"] == VERDICT_INSUFFICIENT
        assert result["clean"] is False
        _assert_no_banned_keys(result, "missing proposals")

    def test_proposals_empty_is_insufficient(self, tmp_path: Path) -> None:
        """Empty proposals file -> INSUFFICIENT_DATA."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(proposals, [])
        _write_jsonl(graded, [_graded_row()])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_INSUFFICIENT
        assert result["clean"] is False
        _assert_no_banned_keys(result, "empty proposals")

    def test_no_ship_rows_is_insufficient(self, tmp_path: Path) -> None:
        """Proposals with only REJECT rows -> INSUFFICIENT_DATA."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(proposals, [{"decision": "REJECT", "name": "nba",
                                   "ts": "2026-01-01T00:00:00+00:00"}])
        _write_jsonl(graded, [_graded_row()])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_INSUFFICIENT
        assert result["clean"] is False
        assert "no SHIP rows" in result.get("reason", "")
        _assert_no_banned_keys(result, "no SHIP rows")

    def test_graded_missing_is_insufficient(self, tmp_path: Path) -> None:
        """Proposals present, graded absent -> INSUFFICIENT_DATA."""
        proposals = tmp_path / "proposals.jsonl"
        _write_jsonl(proposals, [_ship_row()])
        result = reconcile(proposals, tmp_path / "graded.jsonl")
        assert result["verdict"] == VERDICT_INSUFFICIENT
        assert result["clean"] is False
        _assert_no_banned_keys(result, "missing graded")

    def test_graded_empty_is_insufficient(self, tmp_path: Path) -> None:
        """Proposals present, graded empty -> INSUFFICIENT_DATA."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        _write_jsonl(proposals, [_ship_row()])
        _write_jsonl(graded, [])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_INSUFFICIENT
        assert result["clean"] is False
        _assert_no_banned_keys(result, "empty graded")

    def test_insufficient_has_calibration_note(self, tmp_path: Path) -> None:
        """INSUFFICIENT_DATA result must carry the calibration note."""
        result = reconcile(tmp_path / "a.jsonl", tmp_path / "b.jsonl")
        assert "note" in result
        assert "calibration" in result["note"].lower()

    def test_no_dollar_field_in_any_output(self, tmp_path: Path) -> None:
        """No $/roi/pnl/profit key in any output -- all three result shapes."""
        # INSUFFICIENT_DATA
        r1 = reconcile(tmp_path / "a.jsonl", tmp_path / "b.jsonl")
        _assert_no_banned_keys(r1, "INSUFFICIENT_DATA shape")

        # CLEAN
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-01-01T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [_graded_row("nba:moneyline", ts)])
        r2 = reconcile(proposals, graded)
        _assert_no_banned_keys(r2, "CLEAN shape")

        # NO_CANDIDATE (orphan_ship)
        proposals2 = tmp_path / "proposals2.jsonl"
        graded2 = tmp_path / "graded2.jsonl"
        _write_jsonl(proposals2, [_ship_row("nba", ts)])
        _write_jsonl(graded2, [_graded_row("tennis:ml", ts)])
        r3 = reconcile(proposals2, graded2)
        _assert_no_banned_keys(r3, "NO_CANDIDATE shape")

    def test_malformed_jsonl_lines_skipped(self, tmp_path: Path) -> None:
        """Malformed JSON lines are silently skipped, not raised."""
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        proposals.write_text(
            '{"decision": "SHIP", "name": "nba", "ts": "2026-01-01T00:00:00+00:00"}\n'
            "not-json-at-all\n"
            '{"decision": "SHIP", "name": "mlb", "ts": "2026-01-01T00:00:00+00:00"}\n',
            encoding="utf-8",
        )
        _write_jsonl(graded, [_graded_row("nba:ml", "2026-01-01T00:00:00+00:00")])
        result = reconcile(proposals, graded)
        # Must not raise; at least 1 valid SHIP row was parsed
        assert result["n_ship_rows"] >= 1
        _assert_no_banned_keys(result, "malformed lines skipped")

    def test_never_raises_on_arbitrary_inputs(self, tmp_path: Path) -> None:
        """reconcile() must never raise regardless of file state."""
        # Call with no arguments (default paths may not exist)
        try:
            result = reconcile(tmp_path / "x.jsonl", tmp_path / "y.jsonl")
            assert "verdict" in result
        except Exception as exc:
            pytest.fail("reconcile() raised unexpectedly: %s" % exc)


# ---------------------------------------------------------------------------
# (e) Bug regression: same-sport-prefix collision at same ts -> NO_CANDIDATE
# ---------------------------------------------------------------------------


class TestSamePrefixCollisionRegression:
    """Regression: two graded rows with the same sport prefix + ts must not collide.

    Original bug (BE-R5-5-si-ledger-reconcile-parity): graded_by_key used
    sport_prefix:ts as its key, so 'nba:moneyline' and 'nba:pts' at the same ts
    both mapped to 'nba:<ts>', causing the second row to overwrite the first.
    The second was then never iterated in the orphan_grade loop (its key was
    already in consumed_graded_keys from the first match), producing a false CLEAN.
    """

    def test_one_ship_two_same_prefix_graded_is_no_candidate(
        self, tmp_path: Path
    ) -> None:
        """One SHIP 'nba' + graded [nba:moneyline, nba:pts] same ts -> NO_CANDIDATE.

        The daemon matches one graded row (first in file order).  The second graded
        row has no daemon entry and must be reported as an orphan_grade.
        Result: n_orphan_grade == 1, verdict == NO_CANDIDATE, clean == False.
        """
        proposals = tmp_path / "proposals.jsonl"
        graded = tmp_path / "graded.jsonl"
        ts = "2026-06-20T00:00:00+00:00"
        _write_jsonl(proposals, [_ship_row("nba", ts)])
        _write_jsonl(graded, [
            _graded_row("nba:moneyline", ts),
            _graded_row("nba:pts", ts),
        ])
        result = reconcile(proposals, graded)
        assert result["verdict"] == VERDICT_NO_CANDIDATE, (
            "Expected NO_CANDIDATE: two same-prefix graded rows at one ts with "
            "only one daemon SHIP must produce an orphan_grade. Got: %s" % result
        )
        assert result["n_orphan_grade"] == 1, (
            "Expected exactly 1 orphan_grade (the second nba:* row). Got: %s"
            % result["n_orphan_grade"]
        )
        assert result["n_matched"] == 1, result
        assert result["n_orphan_ship"] == 0, result
        assert result["clean"] is False
        _assert_no_banned_keys(result, "same-prefix collision regression")
