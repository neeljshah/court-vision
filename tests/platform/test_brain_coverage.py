"""Tests for scripts.platformkit.brain_coverage — fixture tree, no real vault."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.brain_coverage import build_coverage, render_markdown, write_artifact


def _mk(root: Path) -> None:
    # NBA: fully covered (dirs + all artifacts)
    for d in ("Teams", "Archetypes", "Schemes", "Trends", "Reference"):
        (root / "NBA" / d).mkdir(parents=True, exist_ok=True)
        (root / "NBA" / d / "x.md").write_text("x", encoding="utf-8")
    for f in ("_Digest.md", "_Read.md", "_Model_Card.md", "_Team_Base_Rates_EB.md"):
        (root / "NBA" / f).write_text("x", encoding="utf-8")
    # Tennis: player-level — Teams/BaseRates/Schemes absent BY DESIGN (structural)
    (root / "Tennis" / "Archetypes").mkdir(parents=True, exist_ok=True)
    (root / "Tennis" / "Archetypes" / "a.md").write_text("a", encoding="utf-8")
    for f in ("_Digest.md", "_Read.md", "_Model_Card.md"):
        (root / "Tennis" / f).write_text("x", encoding="utf-8")
    (root / "Tennis" / "Trends").mkdir(exist_ok=True)
    (root / "Tennis" / "Reference").mkdir(exist_ok=True)


def test_full_nba_is_complete(tmp_path):
    _mk(tmp_path)
    rep = build_coverage(tmp_path)
    assert rep["sports"]["NBA"]["complete"] is True
    assert rep["sports"]["NBA"]["cells"]["ModelCard"]["present"] is True


def test_structural_absences_not_counted_as_gaps(tmp_path):
    _mk(tmp_path)
    rep = build_coverage(tmp_path)
    # tennis lacks Teams/BaseRates/Schemes by design -> NOT real gaps
    for g in ("Tennis/Teams", "Tennis/BaseRates", "Tennis/Schemes"):
        assert g not in rep["real_gaps"]
    assert rep["sports"]["Tennis"]["complete"] is True


def test_real_gap_detected(tmp_path):
    _mk(tmp_path)
    # remove NBA model card -> a REAL gap (NBA ModelCard is expected)
    (tmp_path / "NBA" / "_Model_Card.md").unlink()
    rep = build_coverage(tmp_path)
    assert "NBA/ModelCard" in rep["real_gaps"]
    assert rep["sports"]["NBA"]["complete"] is False


def test_render_and_write(tmp_path):
    _mk(tmp_path)
    rep = build_coverage(tmp_path)
    md = render_markdown(rep)
    assert "Brain Coverage Map" in md and "NOT a betting edge" in md
    assert "roi" not in md.lower()
    path = write_artifact(rep, organized_root=tmp_path)
    assert (tmp_path / "_Index" / "_Coverage.md").is_file()
    assert path.endswith("_Coverage.md")
