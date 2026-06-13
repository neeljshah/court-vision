"""test_clv_baseline_report.py — Acceptance tests for clv_baseline_report.py (N-CLV-006).

Done-criteria coverage
-----------------------
1. Disclaimer string is present in the output (required by spec).
2. Zero instances of "edge" used as a claim in the output.
3. Empty ledger is handled honestly ("no forward rows yet").
4. Single open+close pair produces a non-empty report with distributions.
5. Graded pair (opener has 'prediction' field) surfaces CLV grading section.
6. Pairs with non-numeric prices are skipped without crashing.
7. Module-level MANDATORY_DISCLAIMER constant contains no edge-claim language.

All disk I/O uses pytest's ``tmp_path`` fixture — the real
``data/lines/forward/`` directory is NEVER touched.
Python 3.9 compatible. No network. No torch.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pytest

# ---------------------------------------------------------------------------
# Path wiring
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "platformkit" / "capture"
sys.path.insert(0, str(CAPTURE_DIR))
sys.path.insert(0, str(ROOT))

import ledger_writer as writer  # noqa: E402
from clv_baseline_report import (  # noqa: E402
    MANDATORY_DISCLAIMER,
    generate_report,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Substrings that would constitute a claim of systematic betting advantage.
# The word "edge" is permitted in a purely descriptive or *negating* context
# (e.g., "no edge is asserted", "no betting edge") but NOT as a positive
# affirmation.  We check only for patterns that could only appear as positive
# claims; they should never match the legitimate disclaimer text.
_EDGE_CLAIM_PATTERNS: List[str] = [
    "has edge",
    "proven edge",
    "real edge",
    "there is an edge",
    "demonstrates edge",
    "positive edge",
    "confirms edge",
    "we have edge",
    "model edge",
]


def _make_record(
    sport: str = "nba",
    event_id: str = "0042500404",
    market: str = "player_points",
    book: str = "draftkings",
    price: float = -115.0,
    side: str = "over:Brunson:25.5",
    kind: str = "open",
    ts_utc_observed: str = "2026-06-11T18:00:00Z",
    source: str = "test",
    **extra,
) -> dict:
    rec: dict = {
        "sport": sport,
        "event_id": event_id,
        "market": market,
        "book": book,
        "price": price,
        "side": side,
        "kind": kind,
        "ts_utc_observed": ts_utc_observed,
        "source": source,
    }
    rec.update(extra)
    return rec


# ---------------------------------------------------------------------------
# Mandatory done-criteria tests
# ---------------------------------------------------------------------------

class TestDisclaimerPresent:
    """Done-criteria #1: disclaimer string is in the report output."""

    def test_disclaimer_in_empty_ledger_report(self, tmp_path: Path) -> None:
        """Disclaimer must appear even when the ledger is empty."""
        report = generate_report(root=tmp_path)
        assert MANDATORY_DISCLAIMER in report, (
            "MANDATORY_DISCLAIMER not found in report output (empty ledger case)."
        )

    def test_disclaimer_in_populated_report(self, tmp_path: Path) -> None:
        """Disclaimer must appear in a report that has data."""
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-120.0), root=tmp_path)
        report = generate_report(root=tmp_path)
        assert MANDATORY_DISCLAIMER in report, (
            "MANDATORY_DISCLAIMER not found in report output (populated ledger case)."
        )

    def test_disclaimer_constant_non_empty(self) -> None:
        """MANDATORY_DISCLAIMER constant must be a non-empty string."""
        assert isinstance(MANDATORY_DISCLAIMER, str)
        assert len(MANDATORY_DISCLAIMER) > 50, "Disclaimer looks too short to be meaningful."

    def test_disclaimer_mentions_market_follow(self) -> None:
        """Disclaimer must include 'market-follow by construction' language."""
        assert "market-follow by construction" in MANDATORY_DISCLAIMER, (
            "Disclaimer must state open-vs-close is 'market-follow by construction'."
        )

    def test_disclaimer_appears_twice_in_populated_report(self, tmp_path: Path) -> None:
        """Populated report should print the disclaimer at top AND bottom."""
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-120.0), root=tmp_path)
        report = generate_report(root=tmp_path)
        count = report.count(MANDATORY_DISCLAIMER)
        assert count >= 2, (
            f"Expected disclaimer at least twice (header+footer), found {count} time(s)."
        )


class TestNoEdgeClaims:
    """Done-criteria #2: zero 'edge' claim substrings in the output."""

    def test_no_edge_claim_in_empty_ledger_report(self, tmp_path: Path) -> None:
        """No positive edge-claim language when ledger is empty."""
        report = generate_report(root=tmp_path).lower()
        for pattern in _EDGE_CLAIM_PATTERNS:
            assert pattern not in report, (
                f"Edge-claim pattern {pattern!r} found in empty-ledger report."
            )

    def test_no_edge_claim_in_populated_report(self, tmp_path: Path) -> None:
        """No positive edge-claim language when pairs exist."""
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-120.0), root=tmp_path)
        report = generate_report(root=tmp_path).lower()
        for pattern in _EDGE_CLAIM_PATTERNS:
            assert pattern not in report, (
                f"Edge-claim pattern {pattern!r} found in populated report."
            )

    def test_no_edge_claim_in_disclaimer_constant(self) -> None:
        """MANDATORY_DISCLAIMER constant itself must not assert edge."""
        disc_lower = MANDATORY_DISCLAIMER.lower()
        for pattern in _EDGE_CLAIM_PATTERNS:
            assert pattern not in disc_lower, (
                f"Edge-claim pattern {pattern!r} found in MANDATORY_DISCLAIMER constant."
            )


# ---------------------------------------------------------------------------
# Empty-ledger honest reporting
# ---------------------------------------------------------------------------

class TestEmptyLedger:
    """Done-criteria #3: empty ledger is reported honestly."""

    def test_empty_ledger_returns_string(self, tmp_path: Path) -> None:
        report = generate_report(root=tmp_path)
        assert isinstance(report, str)
        assert len(report) > 0

    def test_empty_ledger_says_no_forward_rows(self, tmp_path: Path) -> None:
        report = generate_report(root=tmp_path)
        assert "no forward rows yet" in report.lower(), (
            "Empty-ledger report must say 'no forward rows yet'."
        )

    def test_missing_ledger_root_does_not_crash(self, tmp_path: Path) -> None:
        """Non-existent root path must not raise — return honest empty message."""
        nonexistent = tmp_path / "does_not_exist"
        report = generate_report(root=nonexistent)
        assert "no forward rows yet" in report.lower()

    def test_reconstructed_only_rows_treated_as_empty(self, tmp_path: Path) -> None:
        """Rows with ts_quality=reconstructed must be excluded (treated as no forward rows)."""
        import json
        import os

        sport_dir = tmp_path / "nba"
        sport_dir.mkdir(parents=True)
        jf = sport_dir / "2026-06-11.jsonl"
        rec = _make_record(kind="open")
        rec["ts_quality"] = "reconstructed"
        with open(jf, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

        report = generate_report(root=tmp_path)
        assert "no forward rows yet" in report.lower(), (
            "Report should treat reconstructed-only rows as an empty ledger."
        )


# ---------------------------------------------------------------------------
# Populated ledger — distribution section
# ---------------------------------------------------------------------------

class TestPopulatedReport:
    """Done-criteria #4: single open+close pair produces distribution output."""

    def test_report_contains_market_header(self, tmp_path: Path) -> None:
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-115.0), root=tmp_path)
        report = generate_report(root=tmp_path)
        assert "PER-MARKET" in report, (
            "Expected 'PER-MARKET' distribution header in populated report."
        )

    def test_report_contains_coverage_section(self, tmp_path: Path) -> None:
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-115.0), root=tmp_path)
        report = generate_report(root=tmp_path)
        assert "CAPTURE COVERAGE" in report, (
            "Expected 'CAPTURE COVERAGE' section in populated report."
        )

    def test_pair_count_correct(self, tmp_path: Path) -> None:
        """One open + one close for the same key → 1 completed pair reported."""
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-120.0), root=tmp_path)
        report = generate_report(root=tmp_path)
        assert "Completed open->close pairs     : 1" in report, (
            "Expected exactly 1 completed pair in report."
        )

    def test_movement_delta_reflected(self, tmp_path: Path) -> None:
        """Price delta -120 - (-110) = -10 should appear in distribution row."""
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-120.0), root=tmp_path)
        report = generate_report(root=tmp_path)
        # The mean delta for this single pair should be -10.00
        assert "-10.00" in report, (
            "Expected mean movement of -10.00 in distribution (open=-110, close=-120)."
        )

    def test_multiple_markets_all_appear(self, tmp_path: Path) -> None:
        """Two markets should both appear as rows in the distribution table."""
        for mkt in ("player_points", "player_assists"):
            writer.append(
                _make_record(market=mkt, side=f"over:player:{mkt}", kind="open", price=-110.0),
                root=tmp_path,
            )
            writer.append(
                _make_record(market=mkt, side=f"over:player:{mkt}", kind="close", price=-115.0),
                root=tmp_path,
            )
        report = generate_report(root=tmp_path)
        assert "player_points" in report
        assert "player_assists" in report


# ---------------------------------------------------------------------------
# Graded pair (CLV vs pregame number)
# ---------------------------------------------------------------------------

class TestGradedPairs:
    """Done-criteria #5: opener with 'prediction' field surfaces CLV grading."""

    def test_grading_section_present_when_prediction_field_exists(
        self, tmp_path: Path
    ) -> None:
        """When opener has a 'prediction' field, grading section should appear."""
        open_rec = _make_record(kind="open", price=-110.0, prediction=-105.0)
        close_rec = _make_record(kind="close", price=-115.0)
        writer.append(open_rec, root=tmp_path)
        writer.append(close_rec, root=tmp_path)
        report = generate_report(root=tmp_path)
        assert "CLV VS PRE-GAME" in report, (
            "Expected 'CLV VS PRE-GAME NUMBER GRADING' header when prediction field present."
        )
        assert "graded pair" in report.lower(), (
            "Expected 'graded pair' mention in report."
        )

    def test_grading_section_honest_when_no_prediction(self, tmp_path: Path) -> None:
        """When no opener has a prediction field, grading section says so."""
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-115.0), root=tmp_path)
        report = generate_report(root=tmp_path)
        # Should still show the section heading but say no graded pairs found.
        assert "CLV VS PRE-GAME" in report
        assert "no graded pairs found" in report.lower()

    def test_clv_grading_descriptive_not_claim(self, tmp_path: Path) -> None:
        """CLV grading section must describe movement, not claim an advantage."""
        open_rec = _make_record(kind="open", price=-110.0, prediction=-105.0)
        close_rec = _make_record(kind="close", price=-115.0)
        writer.append(open_rec, root=tmp_path)
        writer.append(close_rec, root=tmp_path)
        report = generate_report(root=tmp_path).lower()
        for pattern in _EDGE_CLAIM_PATTERNS:
            assert pattern not in report, (
                f"Edge-claim pattern {pattern!r} in grading section."
            )


# ---------------------------------------------------------------------------
# Non-numeric price robustness
# ---------------------------------------------------------------------------

class TestNonNumericPrice:
    """Done-criteria #6: non-numeric prices skipped without crashing."""

    def test_non_numeric_price_does_not_crash(self, tmp_path: Path) -> None:
        """A pair whose price cannot be parsed to float must be skipped, not crash."""
        # Write one clean pair plus one bad-price pair.
        writer.append(_make_record(kind="open", price=-110.0), root=tmp_path)
        writer.append(_make_record(kind="close", price=-115.0), root=tmp_path)

        # Manually inject a malformed record.
        import json, os
        sport_dir = tmp_path / "nba"
        bad_open = _make_record(
            side="over:BadPlayer:30.0",
            kind="open",
            price="N/A",
            ts_utc_observed="2026-06-11T18:00:00Z",
        )
        bad_close = _make_record(
            side="over:BadPlayer:30.0",
            kind="close",
            price="N/A",
            ts_utc_observed="2026-06-11T18:00:00Z",
        )
        jf = sport_dir / "2026-06-11.jsonl"
        with open(jf, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(bad_open) + "\n")
            fh.write(json.dumps(bad_close) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

        # Should not raise.
        report = generate_report(root=tmp_path)
        assert isinstance(report, str)
        assert "PER-MARKET" in report, "Good pair should still produce distribution section."
