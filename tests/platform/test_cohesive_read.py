"""tests/platform/test_cohesive_read.py — Tests for scripts.platformkit.cohesive_read.

Invariants checked:
  (1) build_cohesive_read('nba', use_llm=False) returns edge_claimed=False,
      has 'read' (with critique.edge_claim_detected=False) and 'concept_landscape'
      (n_nodes may be 0 against tmp fixture, but key present).
  (2) render_markdown contains 'Cohesive Read', per-sport read section, concept graph
      section, and 'calibration' / 'no edge'.
  (3) brain_audit.scan_text over rendered markdown is empty for all four sports.
  (4) write_reads(sports=['tennis'], root=<tmp>) writes a _Cohesive_Read.md that
      exists, ends with that filename, and is person-free (scan_text clean).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.cohesive_read import (
    build_cohesive_read,
    render_markdown,
    render_index,
    write_index,
    write_reads,
)
from scripts.platformkit.brain_audit import scan_text

_ALL_SPORTS = ("nba", "mlb", "soccer", "tennis")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_minimal_brain(tmp_path: Path, sport_dir: str = "NBA") -> Path:
    """Minimal _Organized tree sufficient to exercise both cohesive_read layers."""
    root = tmp_path / "brain"

    # Sport/Archetypes/ — for sport_read scout
    arch = root / sport_dir / "Archetypes"
    arch.mkdir(parents=True)
    (arch / "fast_break_initiator.md").write_text(
        "---\narchetype: Fast Break Initiator\nsport: nba\n---\n"
        "# Fast Break Initiator\n\n## STYLE\n"
        "Pushes transition before defense sets. Calibration is not edge.\n"
        "**Usage rate:** 22%\n"
        "#sport/nba #archetype\n",
        encoding="utf-8",
    )

    # Sport/Schemes/ — for sport_read scout
    scm = root / sport_dir / "Schemes"
    scm.mkdir(parents=True)
    (scm / "zone_defense.md").write_text(
        "---\nscheme: Zone Defense\n---\n"
        "# Zone Defense\n\nDescriptive scheme. No edge claimed. Markets efficient.\n"
        "#sport/nba #scheme\n",
        encoding="utf-8",
    )

    # Sport/Situational/ — concept family dir, for concept_landscape
    sit = root / sport_dir / "Situational"
    sit.mkdir(parents=True)
    for i in range(2):
        (sit / f"sit_{i}.md").write_text(
            f"# Situational Concept {i}\n\nDescriptive only. No edge.\n#situational\n",
            encoding="utf-8",
        )

    # _Index world model
    idx = root / "_Index"
    idx.mkdir(parents=True)
    (idx / "_World_Model.md").write_text(
        "# World Model\n\nMarkets efficient; all signals REJECT.\n"
        "No edge claimed. edge_claimed: False\n",
        encoding="utf-8",
    )

    return root


def _make_tennis_brain(tmp_path: Path) -> Path:
    """Minimal tree for write_reads tennis test."""
    root = tmp_path / "brain"
    # Tennis/ dir must exist so write_reads will write to it
    ten = root / "Tennis"
    ten.mkdir(parents=True)
    (ten / "stub.md").write_text(
        "# Tennis Stub\n\nPlaceholder. Calibration is not edge.\n",
        encoding="utf-8",
    )
    idx = root / "_Index"
    idx.mkdir(parents=True)
    (idx / "_World_Model.md").write_text(
        "# World Model\n\nMarkets efficient. No edge claimed.\n",
        encoding="utf-8",
    )
    return root


# ---------------------------------------------------------------------------
# Tests: build_cohesive_read
# ---------------------------------------------------------------------------

class TestBuildCohesiveRead:

    def test_edge_claimed_false(self, tmp_path):
        """(1) edge_claimed is always False."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        assert cr["edge_claimed"] is False

    def test_required_top_level_keys(self, tmp_path):
        """(1) Required keys present in result."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        for key in ("sport", "banner", "read", "concept_landscape",
                    "knowledge_layers", "scoreboards", "edge_claimed"):
            assert key in cr, f"Missing required key: {key!r}"

    def test_knowledge_layers_link_real_artifacts(self):
        """knowledge_layers links the per-sport + cross-sport hubs the rebuild wrote."""
        cr = build_cohesive_read("nba", use_llm=False)
        layers = cr["knowledge_layers"]
        assert isinstance(layers, list)
        if not layers:
            pytest.skip("real vault/_Organized hubs not populated")
        for k in layers:
            assert k["provenance"].startswith("brain:")
            assert set(k) >= {"label", "provenance", "excerpt"}

    def test_sport_key_lowercase(self, tmp_path):
        """sport is returned as lowercase."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("NBA", root=root, use_llm=False)
        assert cr["sport"] == "nba"

    def test_read_has_critique_no_edge_claim(self, tmp_path):
        """(1) read['critique']['edge_claim_detected'] is False."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        assert "critique" in cr["read"], "read dict missing 'critique'"
        assert cr["read"]["critique"]["edge_claim_detected"] is False

    def test_concept_landscape_key_present(self, tmp_path):
        """(1) concept_landscape sub-dict has n_nodes key (may be 0 in fixture)."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        cl = cr["concept_landscape"]
        assert "n_nodes" in cl
        assert isinstance(cl["n_nodes"], int)

    def test_banner_no_edge(self, tmp_path):
        """banner contains 'no edge' or 'efficient'."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        banner_lower = cr["banner"].lower()
        assert "no edge" in banner_lower or "efficient" in banner_lower

    def test_real_vault_nba(self):
        """(1) Against real vault (skip if absent): n_nodes>0 in concept_landscape."""
        cr = build_cohesive_read("nba", use_llm=False)
        assert cr["edge_claimed"] is False
        cl = cr["concept_landscape"]
        if cl["n_nodes"] == 0:
            pytest.skip("real vault/_Organized NBA concept nodes not found")
        assert cl["n_nodes"] > 0

    def test_missing_root_degrades_gracefully(self, tmp_path):
        """Nonexistent root returns valid dict with edge_claimed=False."""
        cr = build_cohesive_read("nba", root=tmp_path / "absent", use_llm=False)
        assert cr["edge_claimed"] is False
        assert "read" in cr
        assert "concept_landscape" in cr


# ---------------------------------------------------------------------------
# Tests: render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:

    def test_contains_cohesive_read_heading(self, tmp_path):
        """(2) render_markdown output contains 'Cohesive Read'."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        md = render_markdown(cr)
        assert "Cohesive Read" in md

    def test_contains_per_sport_read_section(self, tmp_path):
        """(2) Includes the per-sport read section (## Per-Sport Intelligence Read)."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        md = render_markdown(cr)
        assert "Per-Sport Intelligence Read" in md

    def test_contains_concept_graph_section(self, tmp_path):
        """(2) Includes the concept graph section."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        md = render_markdown(cr)
        assert "Concept Graph" in md

    def test_contains_calibration_and_no_edge(self, tmp_path):
        """(2) Rendered markdown contains 'calibration' and 'no edge' / 'not edge'."""
        root = _make_minimal_brain(tmp_path)
        cr = build_cohesive_read("nba", root=root, use_llm=False)
        md = render_markdown(cr).lower()
        assert "calibration" in md
        assert "no edge" in md or "not edge" in md or "no un-gated" in md

    def test_audit_clean_fixture_all_sports(self, tmp_path):
        """(3) brain_audit.scan_text is clean for all four sports over fixture brain."""
        for sport in _ALL_SPORTS:
            sport_dir = {"nba": "NBA", "mlb": "MLB", "soccer": "Soccer", "tennis": "Tennis"}[sport]
            root = _make_minimal_brain(tmp_path / sport, sport_dir=sport_dir)
            cr = build_cohesive_read(sport, root=root, use_llm=False)
            md = render_markdown(cr)
            flags = scan_text(md)
            assert flags == [], (
                f"brain_audit flagged {sport} rendered cohesive read: {flags}"
            )

    def test_audit_clean_real_vault(self):
        """(3) scan_text clean over real vault for all four sports (skip if absent)."""
        any_present = False
        for sport in _ALL_SPORTS:
            cr = build_cohesive_read(sport, use_llm=False)
            md = render_markdown(cr)
            flags = scan_text(md)
            assert flags == [], f"brain_audit flagged {sport}: {flags}"
            if cr["concept_landscape"]["n_nodes"] > 0:
                any_present = True
        if not any_present:
            pytest.skip("real vault/_Organized not populated with concept nodes")


# ---------------------------------------------------------------------------
# Tests: write_reads
# ---------------------------------------------------------------------------

class TestWriteReads:

    def test_write_reads_tennis(self, tmp_path):
        """(4) write_reads(['tennis'], root) writes a valid _Cohesive_Read.md for Tennis."""
        root = _make_tennis_brain(tmp_path)
        paths = write_reads(sports=["tennis"], root=root)
        # Tennis dir exists, so exactly one path should be written
        assert len(paths) == 1, f"Expected 1 path, got: {paths}"
        p = Path(paths[0])
        assert p.name == "_Cohesive_Read.md", f"Unexpected filename: {p.name}"
        assert "Tennis" in p.parts or "tennis" in p.parts, (
            f"Path does not include Tennis dir: {p}"
        )
        assert p.exists(), f"Written path does not exist: {p}"

    def test_write_reads_file_content_audit_clean(self, tmp_path):
        """(4) Written _Cohesive_Read.md is person-free (scan_text returns empty)."""
        root = _make_tennis_brain(tmp_path)
        paths = write_reads(sports=["tennis"], root=root)
        if not paths:
            pytest.skip("write_reads returned no paths (Tennis dir missing?)")
        text = Path(paths[0]).read_text(encoding="utf-8")
        flags = scan_text(text)
        assert flags == [], f"Written file has audit flags: {flags}"

    def test_write_reads_returns_list(self, tmp_path):
        """write_reads always returns a list (even when no sport dirs exist)."""
        root = tmp_path / "empty_brain"
        root.mkdir()
        result = write_reads(sports=["nba"], root=root)
        assert isinstance(result, list)

    def test_write_reads_absent_root_returns_empty(self, tmp_path):
        """write_reads on absent root returns []."""
        result = write_reads(sports=["tennis"], root=tmp_path / "no_such_dir")
        assert result == []


# ---------------------------------------------------------------------------
# Tests: cross-sport index
# ---------------------------------------------------------------------------

class TestCohesiveIndex:

    def test_render_index_audit_clean_and_headed(self):
        """The cross-sport index is person-free/no-edge and has the system heading."""
        md = render_index()
        assert "Cohesive Brain — System Index" in md
        assert scan_text(md) == [], f"index has audit flags: {scan_text(md)}"

    def test_write_index_writes_under_index_dir(self, tmp_path):
        """write_index writes _Cohesive_Index.md when an _Index dir exists; else None."""
        assert write_index(root=tmp_path / "no_such") is None
        root = tmp_path / "brain"
        (root / "_Index").mkdir(parents=True)
        out = write_index(root=root)
        assert out is not None and out.endswith("_Cohesive_Index.md")
        assert Path(out).exists()
        assert scan_text(Path(out).read_text(encoding="utf-8")) == []
