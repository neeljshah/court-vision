"""tests/platform/test_concept_landscape.py — Tests for scripts.platformkit.concept_landscape.

Invariants checked:
  (1) Real vault: n_nodes>0, n_families>0 for 'nba'; every top_hit family is a true
      concept-expansion family (member of _CONCEPT_FAMILIES, case-insensitive).
  (2) families list is sorted by count descending.
  (3) render_markdown contains sport name and 'Concept Graph'.
  (4) HONEST/NO-EDGE: brain_audit.scan_text over rendered markdown is empty;
      dict 'note' mentions calibration/edge disclaimer.
  (5) Graceful degradation on missing root (n_nodes=0, families=[], valid shape).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.concept_landscape import build_concept_landscape, render_markdown
from scripts.platformkit.brain_vault import _CONCEPT_FAMILIES
from scripts.platformkit.brain_audit import scan_text

# Canonical set of concept-expansion family names (case-folded for membership tests).
_FAMILY_SET_LOWER = frozenset(f.lower() for f in _CONCEPT_FAMILIES)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_concept_brain(tmp_path: Path) -> Path:
    """Minimal _Organized tree with two concept-family dirs under NBA/."""
    root = tmp_path / "brain"
    # NBA/Situational/ — a real concept family
    sit = root / "NBA" / "Situational"
    sit.mkdir(parents=True)
    for i in range(3):
        (sit / f"concept_{i}.md").write_text(
            f"---\ntags:\n  - sport/nba\n  - situational\n---\n"
            f"# Situational Concept {i}\n\nDescriptive prose only; no edge claimed.\n"
            f"Calibration is not edge.\n#situational\n",
            encoding="utf-8",
        )
    # NBA/Tactics/ — a second real concept family
    tac = root / "NBA" / "Tactics"
    tac.mkdir(parents=True)
    for i in range(2):
        (tac / f"tactic_{i}.md").write_text(
            f"---\ntags:\n  - sport/nba\n  - tactics\n---\n"
            f"# Tactic {i}\n\nDescriptive; markets efficient; no edge.\n#tactics\n",
            encoding="utf-8",
        )
    # _Index world model note
    idx = root / "_Index"
    idx.mkdir(parents=True)
    (idx / "_World_Model.md").write_text(
        "# World Model\n\nMarkets efficient; all signals REJECT.\n"
        "No edge claimed. edge_claimed: False\n",
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# Tests: build_concept_landscape over REAL vault
# ---------------------------------------------------------------------------

class TestRealVault:
    """Tests that use the real vault/_Organized (skip gracefully if absent)."""

    def test_nba_has_nodes_and_families(self):
        """(1a) Real vault: n_nodes>0 and n_families>0 for 'nba'."""
        land = build_concept_landscape("nba")
        if land["n_nodes"] == 0:
            pytest.skip("real vault/_Organized not present or NBA concept nodes absent")
        assert land["n_nodes"] > 0
        assert land["n_families"] > 0

    def test_top_hits_families_are_concept_families(self):
        """(1b) Every top_hit['family'] is a member of _CONCEPT_FAMILIES (case-insensitive)."""
        land = build_concept_landscape("nba")
        if land["n_nodes"] == 0:
            pytest.skip("real vault/_Organized not present or NBA concept nodes absent")
        for hit in land["top_hits"]:
            fam = hit["family"].lower()
            assert fam in _FAMILY_SET_LOWER, (
                f"top_hit family '{hit['family']}' not in _CONCEPT_FAMILIES: {hit['title']}"
            )

    def test_families_sorted_desc(self):
        """(2) families list is sorted by count descending."""
        land = build_concept_landscape("nba")
        if land["n_nodes"] == 0:
            pytest.skip("real vault/_Organized not present or NBA concept nodes absent")
        counts = [f["count"] for f in land["families"]]
        assert counts == sorted(counts, reverse=True), "families not sorted by count desc"


# ---------------------------------------------------------------------------
# Tests: build_concept_landscape over minimal fixture
# ---------------------------------------------------------------------------

class TestFixtureBrain:

    def test_fixture_n_nodes_and_families(self, tmp_path):
        """Fixture brain returns correct node + family counts."""
        root = _make_concept_brain(tmp_path)
        land = build_concept_landscape("nba", root=root)
        assert land["n_nodes"] == 5   # 3 Situational + 2 Tactics
        assert land["n_families"] == 2

    def test_fixture_families_sorted_desc(self, tmp_path):
        """(2) families sorted descending by count in fixture."""
        root = _make_concept_brain(tmp_path)
        land = build_concept_landscape("nba", root=root)
        counts = [f["count"] for f in land["families"]]
        assert counts == sorted(counts, reverse=True)

    def test_missing_root_degrades_gracefully(self, tmp_path):
        """(5) Nonexistent root returns n_nodes=0, n_families=0, valid dict shape."""
        land = build_concept_landscape("nba", root=tmp_path / "nonexistent")
        assert land["n_nodes"] == 0
        assert land["n_families"] == 0
        assert land["families"] == []
        assert isinstance(land["top_hits"], list)
        assert "note" in land

    def test_note_is_honest_disclaimer(self, tmp_path):
        """(4b) 'note' mentions probability/edge disclaimer."""
        root = _make_concept_brain(tmp_path)
        land = build_concept_landscape("nba", root=root)
        note_lower = land["note"].lower()
        assert "not a probability" in note_lower or "edge" in note_lower or "calibration" in note_lower, (
            f"'note' does not contain an honest disclaimer: {land['note']!r}"
        )

    def test_sport_key_is_lowercase(self, tmp_path):
        """sport key in result is lowercase."""
        root = _make_concept_brain(tmp_path)
        land = build_concept_landscape("NBA", root=root)
        assert land["sport"] == "nba"


# ---------------------------------------------------------------------------
# Tests: render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:

    def test_render_contains_sport_and_concept_graph(self, tmp_path):
        """(3) render_markdown output contains the sport name and 'Concept Graph'."""
        root = _make_concept_brain(tmp_path)
        land = build_concept_landscape("nba", root=root)
        md = render_markdown(land)
        assert isinstance(md, str)
        assert "NBA" in md
        assert "Concept Graph" in md

    def test_render_audit_clean(self, tmp_path):
        """(4a) HONEST/NO-EDGE: scan_text finds no forbidden edge-claim tokens."""
        root = _make_concept_brain(tmp_path)
        land = build_concept_landscape("nba", root=root)
        md = render_markdown(land)
        flags = scan_text(md)
        assert flags == [], f"brain_audit flagged rendered markdown: {flags}"

    def test_render_audit_clean_real_vault(self):
        """(4a) scan_text is clean over the REAL vault render too (skip if absent)."""
        land = build_concept_landscape("nba")
        if land["n_nodes"] == 0:
            pytest.skip("real vault/_Organized not present")
        md = render_markdown(land)
        flags = scan_text(md)
        assert flags == [], f"brain_audit flagged real-vault render: {flags}"

    def test_render_shows_families_line(self, tmp_path):
        """Rendered markdown includes a Families line when families are present."""
        root = _make_concept_brain(tmp_path)
        land = build_concept_landscape("nba", root=root)
        md = render_markdown(land)
        assert "Families" in md or "Situational" in md

    def test_render_empty_root_graceful(self, tmp_path):
        """render_markdown handles n_nodes=0 without crashing."""
        land = build_concept_landscape("nba", root=tmp_path / "absent")
        md = render_markdown(land)
        assert isinstance(md, str)
        assert "Concept Graph" in md
