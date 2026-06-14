"""tests/platform/test_sport_read.py — Tests for scripts.platformkit.sport_read.

Fixture: a minimal organized brain in a tmp directory with:
  - NBA/Archetypes/High_Usage_Creator.md
  - NBA/Schemes/switch_heavy.md
  - _Index/_World_Model.md  (contains "markets efficient", "REJECT", "no edge")

Invariants checked:
  (1) banner present & contains "no edge" (case-insensitive)
  (2) edge_claimed is False
  (3) narrative is non-empty str and critique.edge_claim_detected is False
  (4) no top-level key is a numeric pick
  (5) surface is a dict with moneyline when jd given; None when jd=None
  (6) missing/empty root degrades gracefully
  (7) render_markdown returns str containing banner text
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure repo root on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.sim_framework import JointDistribution
from scripts.platformkit.sport_read import build_sport_read, render_markdown


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_fixture_brain(tmp_path: Path) -> Path:
    """Build a minimal organized brain under tmp_path."""
    root = tmp_path / "brain"

    # NBA/Archetypes
    arch_dir = root / "NBA" / "Archetypes"
    arch_dir.mkdir(parents=True)
    (arch_dir / "High_Usage_Creator.md").write_text(
        "---\ntags:\n  - sport/nba\n  - archetype\n---\n"
        "# High Usage Creator\n\n"
        "## STYLE\n"
        "Elite shot-creators who dominate the ball — isolation scoring and "
        "off-screen sets.\n\n"
        "## SIGNATURE\n**usage%**: >= 0.28\n**ast%**: >= 0.20\n"
        "#sport/nba #archetype #archetype/high_usage_creator\n",
        encoding="utf-8",
    )

    # NBA/Schemes
    scheme_dir = root / "NBA" / "Schemes"
    scheme_dir.mkdir(parents=True)
    (scheme_dir / "switch_heavy.md").write_text(
        "---\ntags:\n  - sport/nba\n  - scheme\n---\n"
        "# Switch-Heavy Defense\n\n"
        "## OVERVIEW\n"
        "All ball-screens switched; prioritises preventing open threes over "
        "paint protection.\n\n"
        "#sport/nba #scheme\n",
        encoding="utf-8",
    )

    # _Index/_World_Model.md — honest priors
    idx_dir = root / "_Index"
    idx_dir.mkdir(parents=True)
    (idx_dir / "_World_Model.md").write_text(
        "# World Model\n\n"
        "markets efficient; no edge claimed; edge_claimed False\n"
        "nba signals: REJECT\n"
        "tennis signals: REJECT\n"
        "soccer signals: REJECT\n"
        "mlb signals: REJECT\n",
        encoding="utf-8",
    )

    return root


def _small_jd(n: int = 500, seed: int = 7) -> JointDistribution:
    rng = np.random.default_rng(seed)
    home = np.clip(rng.normal(112.0, 12.0, n), 0, None)
    away = np.clip(rng.normal(109.0, 12.0, n), 0, None)
    return JointDistribution(
        samples=np.stack([home, away], axis=1),
        joint_quality="simulated",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildSportRead:
    def test_banner_present_and_no_edge(self, tmp_path):
        """(1) banner is present and contains 'no edge' (case-insensitive)."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        assert "banner" in read
        assert isinstance(read["banner"], str)
        assert "no edge" in read["banner"].lower()

    def test_edge_claimed_false(self, tmp_path):
        """(2) edge_claimed is always False."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        assert read["edge_claimed"] is False

    def test_narrative_non_empty_and_no_edge_claim(self, tmp_path):
        """(3) narrative is a non-empty str; critique.edge_claim_detected is False."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        assert isinstance(read["narrative"], str)
        assert len(read["narrative"].strip()) > 0
        assert read["critique"]["edge_claim_detected"] is False

    def test_no_numeric_pick_key(self, tmp_path):
        """(4) no top-level key is an un-gated numeric pick."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        forbidden = {"pick", "bet", "wager", "stake", "recommended_bet"}
        for key in read:
            assert key not in forbidden, f"Forbidden key found: {key!r}"
        # surface may contain numbers but must not be itself a bare float/int at top level
        for key, val in read.items():
            if key not in ("surface", "scout", "priors", "critique", "provenance"):
                assert not isinstance(val, (int, float)) or isinstance(val, bool), \
                    f"Unexpected numeric at top-level key {key!r}: {val}"

    def test_surface_present_with_jd(self, tmp_path):
        """(5a) with jd given, surface is a dict containing moneyline."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        assert read["surface"] is not None
        assert isinstance(read["surface"], dict)
        assert "moneyline" in read["surface"]

    def test_surface_none_without_jd(self, tmp_path):
        """(5b) with jd=None, surface is None."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=None, root=root, use_llm=False)
        assert read["surface"] is None

    def test_missing_root_degrades_gracefully(self, tmp_path):
        """(6) missing/empty root returns a valid read with empty scout lists."""
        empty_root = tmp_path / "nonexistent_brain"
        read = build_sport_read("nba", jd=None, root=empty_root, use_llm=False)
        assert "banner" in read
        assert read["edge_claimed"] is False
        assert isinstance(read["scout"]["archetypes"], list)
        assert isinstance(read["scout"]["schemes"], list)
        assert isinstance(read["scout"]["trends"], list)
        assert isinstance(read["narrative"], str)
        assert len(read["narrative"].strip()) > 0

    def test_none_root_uses_default_vault(self):
        """(6b) root=None degrades gracefully whether or not vault exists."""
        read = build_sport_read("nba", jd=None, root=None, use_llm=False)
        assert "banner" in read
        assert read["edge_claimed"] is False

    def test_scout_classifies_archetypes(self, tmp_path):
        """Scout finds the archetype note from fixture."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=None, root=root, use_llm=False)
        titles = [a["title"] for a in read["scout"]["archetypes"]]
        assert any("High" in t or "Creator" in t for t in titles), \
            f"Expected archetype not found; got: {titles}"

    def test_use_llm_false_uses_template(self, tmp_path):
        """use_llm=False uses deterministic template (no network call)."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=None, root=root, use_llm=False)
        # Template always contains "calibration not edge" or "REJECT"
        assert ("calibration" in read["narrative"].lower()
                or "reject" in read["narrative"].lower()
                or "efficient" in read["narrative"].lower())

    def test_critique_shape(self, tmp_path):
        """critique dict has required keys."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        crit = read["critique"]
        assert "passes" in crit
        assert "edge_claim_detected" in crit
        assert "citation_coverage" in crit

    def test_provenance_non_empty(self, tmp_path):
        """provenance list is non-empty."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=None, root=root, use_llm=False)
        assert isinstance(read["provenance"], list)
        assert len(read["provenance"]) > 0


class TestRenderMarkdown:
    def test_render_returns_str_with_banner(self, tmp_path):
        """render_markdown returns a str containing banner text."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        md = render_markdown(read)
        assert isinstance(md, str)
        # Banner must appear in the output
        assert "no edge" in md.lower() or "honest" in md.lower()

    def test_render_contains_sections(self, tmp_path):
        """render_markdown contains expected section headers."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=None, root=root, use_llm=False)
        md = render_markdown(read)
        assert "## Per-Sport Intelligence Read" in md
        assert "Archetypes" in md
        assert "Honest Market Verdict" in md
        assert "Intelligence Narrative" in md

    def test_render_no_surface_note(self, tmp_path):
        """When jd=None, surface section says no numbers fabricated."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=None, root=root, use_llm=False)
        md = render_markdown(read)
        assert "no numbers fabricated" in md.lower() or "no joint" in md.lower()

    def test_render_surface_present(self, tmp_path):
        """When jd given, markdown includes moneyline line."""
        root = _make_fixture_brain(tmp_path)
        read = build_sport_read("nba", jd=_small_jd(), root=root, use_llm=False)
        md = render_markdown(read)
        assert "oneyline" in md  # "Moneyline"
