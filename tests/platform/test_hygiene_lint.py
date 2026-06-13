"""test_hygiene_lint.py — Acceptance tests for scripts/platformkit/hygiene_lint.py.

Python 3.9 compatible.  No network required.  Runs in < 30 s.

Test matrix
-----------
1. Planted retracted numbers are flagged.
2. Retracted numbers in retraction-context lines are NOT flagged (false-positive guard).
3. Edge-claim phrases are flagged.
4. Edge-claim phrases within retraction context lines ARE still flagged
   (edge claims have no exemption).
5. A clean fixture directory produces zero hits.
6. Binary / skipped-extension files are silently ignored.
7. ``run_lint`` honours a monkeypatched file list (integration seam test).
8. Each LintHit.__str__ produces the expected ``path:line:category: text`` format.
9. Real repo scan: ``run_lint`` against the actual git-tracked file set completes
   without error and returns a list (content reported, not asserted clean, so the
   test suite never chases moving-target docs).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))

from hygiene_lint import (  # noqa: E402
    LintHit,
    _scan_file,
    _scan_line,
    run_lint,
    list_tracked_files,
    _RETRACTION_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> str:
    """Write *content* to *tmp_path/name* and return the absolute path string."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# 1. Retracted numbers ARE flagged outside retraction context
# ---------------------------------------------------------------------------

class TestRetractedNumbers:
    def test_18_38_percent_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "a.md", "We achieved +18.38% ROI!\n")
        hits = _scan_file(path)
        assert len(hits) == 1, f"Expected 1 hit, got {hits}"
        assert "18.38%" in hits[0].category or "18.38" in hits[0].matched_text

    def test_18_38_percent_no_plus_flagged(self, tmp_path: Path) -> None:
        """Variant without leading + is also caught."""
        path = _write(tmp_path, "b.md", "ROI of 18.38% was measured\n")
        hits = _scan_file(path)
        assert any("18.38" in h.matched_text for h in hits)

    def test_0119_brier_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "c.md", "endQ3 Brier score: 0.119\n")
        hits = _scan_file(path)
        assert any("0.119" in h.matched_text for h in hits)

    def test_01191_brier_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "d.md", "inside Pinnacle's range (0.1191)\n")
        hits = _scan_file(path)
        assert any("0.1191" in h.matched_text for h in hits)

    def test_54_percent_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "e.md", "in-play hit rate +54% ROI\n")
        hits = _scan_file(path)
        assert any("54" in h.matched_text for h in hits)

    def test_5457_percent_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "f.md", "achieved +54.57% ROI\n")
        hits = _scan_file(path)
        assert any("54.57" in h.matched_text for h in hits)

    def test_multiple_violations_in_one_file(self, tmp_path: Path) -> None:
        content = (
            "ROI: +18.38%\n"
            "endQ3 Brier: 0.1191\n"
            "in-play: +54%\n"
        )
        path = _write(tmp_path, "multi.md", content)
        hits = _scan_file(path)
        assert len(hits) >= 3, f"Expected >=3 hits, got {hits}"


# ---------------------------------------------------------------------------
# 2. Retraction-context lines do NOT false-positive (key requirement)
# ---------------------------------------------------------------------------

class TestRetractionContextNoFalsePositive:
    """Lines mentioning retracted numbers alongside retraction keywords must pass."""

    @pytest.mark.parametrize("keyword", _RETRACTION_KEYWORDS)
    def test_retracted_number_in_retraction_context(
        self, tmp_path: Path, keyword: str
    ) -> None:
        line = f"The +18.38% figure is {keyword} — do not use.\n"
        path = _write(tmp_path, f"ctx_{keyword.replace(' ', '_')}.md", line)
        hits = _scan_file(path)
        retracted_hits = [h for h in hits if "RETRACTED" in h.category]
        assert retracted_hits == [], (
            f"False positive with keyword={keyword!r}: {retracted_hits}"
        )

    def test_0119_in_retraction_context(self, tmp_path: Path) -> None:
        line = "endQ3 0.1191 is retracted due to Q4 leak.\n"
        path = _write(tmp_path, "ctx_0119.md", line)
        hits = [h for h in _scan_file(path) if "RETRACTED" in h.category]
        assert hits == [], f"False positive: {hits}"

    def test_54pct_in_retraction_context(self, tmp_path: Path) -> None:
        line = "+54% is an artifact of grading against L5 proxy (do-not-claim).\n"
        path = _write(tmp_path, "ctx_54.md", line)
        hits = [h for h in _scan_file(path) if "RETRACTED" in h.category]
        assert hits == [], f"False positive: {hits}"

    def test_do_not_claim_with_hyphen(self, tmp_path: Path) -> None:
        line = "do-not-claim: +18.38% ROI\n"
        path = _write(tmp_path, "dnc_hyphen.md", line)
        hits = [h for h in _scan_file(path) if "RETRACTED" in h.category]
        assert hits == [], f"False positive: {hits}"

    def test_case_insensitive_retraction_keyword(self, tmp_path: Path) -> None:
        line = "The +18.38% number is RETRACTED.\n"
        path = _write(tmp_path, "upper.md", line)
        # keyword match is on line.lower(), so RETRACTED should still exempt
        hits = [h for h in _scan_file(path) if "RETRACTED" in h.category]
        assert hits == [], f"False positive on uppercase keyword: {hits}"

    def test_inflated_keyword_suppresses_retracted_number(self, tmp_path: Path) -> None:
        line = "The +18.38% figure is inflated due to grader bug.\n"
        path = _write(tmp_path, "inflated.md", line)
        hits = [h for h in _scan_file(path) if "RETRACTED" in h.category]
        assert hits == [], f"False positive: {hits}"


# ---------------------------------------------------------------------------
# 3. Edge-claim phrases ARE flagged
# ---------------------------------------------------------------------------

class TestEdgeClaims:
    def test_our_edge_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "edge1.md", "This is our edge over the books.\n")
        hits = _scan_file(path)
        assert any("EDGE_CLAIM" in h.category for h in hits)

    def test_profitable_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "edge2.md", "The strategy is profitable long-term.\n")
        hits = _scan_file(path)
        assert any("profitable" in h.category.lower() for h in hits)

    def test_beats_the_market_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "edge3.md", "Our model beats the market consistently.\n")
        hits = _scan_file(path)
        assert any("EDGE_CLAIM" in h.category for h in hits)

    def test_guaranteed_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "edge4.md", "Guaranteed returns on all picks.\n")
        hits = _scan_file(path)
        assert any("EDGE_CLAIM" in h.category for h in hits)

    def test_ev_proven_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "edge5.md", "This selection is +EV proven.\n")
        hits = _scan_file(path)
        assert any("EDGE_CLAIM" in h.category for h in hits)

    def test_proven_edge_flagged(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "edge6.md", "We have a proven edge on totals.\n")
        hits = _scan_file(path)
        assert any("EDGE_CLAIM" in h.category for h in hits)

    def test_edge_claims_case_insensitive(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "edge_case.md", "PROFITABLE strategy.\n")
        hits = _scan_file(path)
        assert any("EDGE_CLAIM" in h.category for h in hits)


# ---------------------------------------------------------------------------
# 4. Edge claims in retraction-context lines ARE still flagged (no exemption)
# ---------------------------------------------------------------------------

class TestEdgeClaimsNotExempted:
    def test_edge_claim_with_retraction_keyword_still_flagged(
        self, tmp_path: Path
    ) -> None:
        # Even in a "retracted" sentence, an edge-claim phrase must be caught
        line = "This was profitable (retracted)\n"
        path = _write(tmp_path, "edge_retracted.md", line)
        hits = _scan_file(path)
        edge_hits = [h for h in hits if "EDGE_CLAIM" in h.category]
        assert edge_hits, f"Edge claim should still fire in retraction context: {hits}"


# ---------------------------------------------------------------------------
# 5. Clean fixture — zero hits
# ---------------------------------------------------------------------------

class TestCleanFixture:
    def test_no_hits_on_neutral_text(self, tmp_path: Path) -> None:
        content = (
            "This system uses walk-forward validation.\n"
            "MAE ~4.58 on held-out player-games.\n"
            "Brier 0.193 (5-fold walk-forward).\n"
            "The model is roughly break-even minus vig.\n"
        )
        path = _write(tmp_path, "clean.md", content)
        hits = _scan_file(path)
        assert hits == [], f"Expected clean, got: {hits}"

    def test_0119_adjacent_digits_no_hit(self, tmp_path: Path) -> None:
        """0.11912 should not match the \\b0.1191?\\b pattern."""
        path = _write(tmp_path, "digits.md", "value=0.11912 other=0.11904\n")
        hits = [h for h in _scan_file(path) if "RETRACTED" in h.category]
        assert hits == [], f"False positive on adjacent digits: {hits}"

    def test_empty_file_no_hits(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "empty.txt", "")
        hits = _scan_file(path)
        assert hits == []

    def test_run_lint_on_clean_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_lint returns [] for a directory of clean files."""
        _write(tmp_path, "a.md", "No problems here.\n")
        _write(tmp_path, "b.py", '"""Pure module."""\nx = 1\n')
        # Monkeypatch list_tracked_files to return our tmp files
        import hygiene_lint as hl
        monkeypatch.setattr(
            hl,
            "list_tracked_files",
            lambda _root: [
                str(tmp_path / "a.md"),
                str(tmp_path / "b.py"),
            ],
        )
        hits = run_lint(str(tmp_path))
        assert hits == [], f"Expected clean, got: {hits}"


# ---------------------------------------------------------------------------
# 6. Binary / skipped extensions are silently ignored
# ---------------------------------------------------------------------------

class TestSkippedExtensions:
    def test_binary_extension_skipped(self, tmp_path: Path) -> None:
        # Write a file with a binary extension but with text that would otherwise hit
        path = _write(tmp_path, "weights.pkl", "+18.38% proven edge\n")
        hits = _scan_file(path)
        assert hits == [], f"Binary extension should be skipped: {hits}"

    def test_pyc_skipped(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "module.pyc", "+18.38% proven edge\n")
        hits = _scan_file(path)
        assert hits == []


# ---------------------------------------------------------------------------
# 7. run_lint honours a monkeypatched file list
# ---------------------------------------------------------------------------

class TestRunLintIntegration:
    def test_planted_violations_detected_via_run_lint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run_lint flags violations when file list is monkeypatched."""
        viol_path = _write(
            tmp_path,
            "bad.md",
            "We achieved +18.38% ROI and have a proven edge.\n",
        )
        import hygiene_lint as hl
        monkeypatch.setattr(hl, "list_tracked_files", lambda _root: [viol_path])
        hits = run_lint(str(tmp_path))
        assert len(hits) >= 2, f"Expected >=2 hits, got {hits}"

    def test_multiple_files_scanned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Violations in multiple files are all reported."""
        p1 = _write(tmp_path, "f1.md", "ROI: +18.38%\n")
        p2 = _write(tmp_path, "f2.md", "beats the market\n")
        p3 = _write(tmp_path, "f3.md", "clean file\n")
        import hygiene_lint as hl
        monkeypatch.setattr(hl, "list_tracked_files", lambda _root: [p1, p2, p3])
        hits = run_lint(str(tmp_path))
        paths_with_hits = {h.path for h in hits}
        assert str(p1) in paths_with_hits
        assert str(p2) in paths_with_hits
        assert str(p3) not in paths_with_hits


# ---------------------------------------------------------------------------
# 8. LintHit string formatting
# ---------------------------------------------------------------------------

class TestLintHitFormat:
    def test_str_format(self) -> None:
        hit = LintHit(
            path="docs/README.md",
            line_number=42,
            category="RETRACTED_NUMBER(+18.38%)",
            matched_text="18.38%",
        )
        s = str(hit)
        assert "docs/README.md" in s
        assert "42" in s
        assert "RETRACTED_NUMBER" in s
        assert "18.38%" in s

    def test_str_format_edge_claim(self) -> None:
        hit = LintHit(
            path="src/foo.py",
            line_number=7,
            category="EDGE_CLAIM(proven edge)",
            matched_text="proven edge",
        )
        s = str(hit)
        assert "src/foo.py:7:" in s
        assert "EDGE_CLAIM" in s


# ---------------------------------------------------------------------------
# 9. _scan_line unit tests
# ---------------------------------------------------------------------------

class TestScanLine:
    def test_clean_line_no_hits(self) -> None:
        assert list(_scan_line("f.md", 1, "MAE 4.58 clean line")) == []

    def test_retracted_flagged_without_context(self) -> None:
        hits = list(_scan_line("f.md", 1, "ROI +18.38% is impressive"))
        assert len(hits) == 1

    def test_retracted_suppressed_with_context(self) -> None:
        hits = list(_scan_line("f.md", 1, "ROI +18.38% is retracted"))
        retracted = [h for h in hits if "RETRACTED" in h.category]
        assert retracted == []

    def test_edge_claim_always_flagged(self) -> None:
        hits = list(_scan_line("f.md", 1, "this is profitable retracted"))
        edge = [h for h in hits if "EDGE_CLAIM" in h.category]
        assert len(edge) == 1, "Edge claims must not be suppressed by retraction context"


# ---------------------------------------------------------------------------
# 10. Real-repo scan (informational — reports hits but does not assert zero)
# ---------------------------------------------------------------------------

class TestRealRepoScan:
    def test_real_repo_scan_completes(self, capsys: pytest.CaptureFixture) -> None:
        """Scan the actual live repo; report any hits to stdout.

        This test never FAILS on the presence of hits — it is informational.
        The orchestrator reads the captured output to decide follow-up actions.
        """
        import hygiene_lint as hl

        try:
            hits = run_lint(str(ROOT))
        except RuntimeError as exc:
            pytest.skip(f"git ls-files unavailable: {exc}")

        if hits:
            print(f"\n[hygiene_lint] {len(hits)} real-repo hit(s):")
            for h in hits:
                print(f"  {h}")
        else:
            print("\n[hygiene_lint] real-repo scan: CLEAN")

        # Test passes regardless — the important thing is it completed without exception.
        assert isinstance(hits, list)
