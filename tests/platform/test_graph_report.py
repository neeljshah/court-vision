"""test_graph_report.py — scoped unit tests for graph_report.build_graph_report.

Uses a synthetic vault/Sports tree in tmp_path so no real vault is touched.
Single-process; safe for --timeout=120.
"""

from __future__ import annotations

import pathlib
import re
import textwrap

import pytest

from scripts.platform.atlas.graph_report import build_graph_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_sport(base: pathlib.Path, sport: str, notes: dict) -> None:
    """Create sport subdirectory with notes described by {rel_path: content}."""
    sport_dir = base / sport
    sport_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in notes.items():
        p = sport_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


TENNIS_NOTES = {
    "_Index.md": textwrap.dedent("""\
        ---
        tags:
          - sport/tennis
          - index
        ---
        # Tennis Index
        [[Players/Ana_Ivanovic|Ana Ivanovic]] · [[Players/Boris_Becker|Boris Becker]]
    """),
    "Players/Ana_Ivanovic.md": textwrap.dedent("""\
        ---
        tags:
          - sport/tennis
          - player
        ---
        # Ana Ivanovic
        [[_Index|Back]] · [[Surfaces/Clay|Clay]]
    """),
    "Players/Boris_Becker.md": textwrap.dedent("""\
        ---
        tags:
          - sport/tennis
          - player
        ---
        # Boris Becker
        [[_Index|Back]]
    """),
    "Matchups/Ana_Ivanovic vs Boris_Becker.md": textwrap.dedent("""\
        ---
        tags:
          - sport/tennis
          - matchup
        ---
        # H2H
        [[Players/Ana_Ivanovic|Ana]] · [[Players/Boris_Becker|Boris]] · [[Players/GHOST|Ghost]]
    """),
    "Surfaces/Clay.md": textwrap.dedent("""\
        ---
        tags:
          - sport/tennis
          - surface
        ---
        # Clay
        [[_Index]]
    """),
}

SOCCER_NOTES = {
    "_Index.md": textwrap.dedent("""\
        ---
        tags:
          - sport/soccer
          - index
        ---
        # Soccer Index
        [[Teams/Arsenal|Arsenal]]
    """),
    "Teams/Arsenal.md": textwrap.dedent("""\
        ---
        tags:
          - sport/soccer
          - atlas/team
        ---
        # Arsenal
        [[_Index]] · [[Leagues/Premier_League|PL]]
    """),
    "Leagues/Premier_League.md": textwrap.dedent("""\
        ---
        tags:
          - sport/soccer
          - league
        ---
        # Premier League
        [[_Index]]
    """),
}


@pytest.fixture()
def synthetic_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build a tiny synthetic vault/Sports tree and return its path."""
    _make_sport(tmp_path, "Tennis", TENNIS_NOTES)
    _make_sport(tmp_path, "Soccer", SOCCER_NOTES)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildGraphReport:

    def test_output_file_created(self, synthetic_vault: pathlib.Path) -> None:
        out = build_graph_report(synthetic_vault)
        assert out.exists(), "_GraphStats.md was not created"
        assert out.name == "_GraphStats.md"
        assert out.parent == synthetic_vault

    def test_note_counts_correct(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")

        # Grand total: 5 Tennis + 3 Soccer = 8
        assert "**8**" in text, f"Expected grand total 8, got:\n{text[:600]}"

        # Per-sport rows should contain the sport names
        assert "Tennis" in text
        assert "Soccer" in text

        # Tennis has 5 notes, Soccer has 3 — check the "Total" column
        lines = text.splitlines()
        counts_start = next(
            i for i, l in enumerate(lines) if l.startswith("## Per-Sport Note Counts")
        )
        header = lines[counts_start + 2]  # "| Sport | Total | ..."
        col_names = [c.strip() for c in header.split("|") if c.strip()]
        total_idx = col_names.index("Total")

        tennis_row = next(l for l in lines[counts_start:] if l.startswith("| Tennis"))
        soccer_row = next(l for l in lines[counts_start:] if l.startswith("| Soccer"))

        tennis_cells = [c.strip() for c in tennis_row.split("|") if c.strip()]
        soccer_cells = [c.strip() for c in soccer_row.split("|") if c.strip()]

        assert tennis_cells[total_idx] == "5", f"Tennis count wrong: {tennis_row}"
        assert soccer_cells[total_idx] == "3", f"Soccer count wrong: {soccer_row}"

    def test_dangling_link_detected(self, synthetic_vault: pathlib.Path) -> None:
        """The Tennis Matchup links [[Players/GHOST]] which has no matching note."""
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")

        # Locate Link Density table header to find correct "Dangling" column index
        lines = text.splitlines()
        density_start = next(
            i for i, l in enumerate(lines) if l.startswith("## Link Density")
        )
        header = lines[density_start + 2]
        col_names = [c.strip() for c in header.split("|") if c.strip()]
        dangling_idx = col_names.index("Dangling")

        tennis_row = next(
            l for l in lines[density_start:] if l.startswith("| Tennis")
        )
        cells = [c.strip() for c in tennis_row.split("|") if c.strip()]
        dangling = int(cells[dangling_idx])
        assert dangling >= 1, f"Expected >=1 dangling for Tennis, got {dangling}: {tennis_row}"

    def test_soccer_no_dangling(self, synthetic_vault: pathlib.Path) -> None:
        """Soccer notes only link to each other — no dangling expected."""
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")

        # Find the Link Density table; parse header to locate "Dangling" column index
        lines = text.splitlines()
        density_start = next(
            i for i, l in enumerate(lines) if l.startswith("## Link Density")
        )
        header = lines[density_start + 2]   # "| Sport | Total Links | ..."
        col_names = [c.strip() for c in header.split("|") if c.strip()]
        dangling_idx = col_names.index("Dangling")

        soccer_row = next(
            l for l in lines[density_start:] if l.startswith("| Soccer")
        )
        cells = [c.strip() for c in soccer_row.split("|") if c.strip()]
        dangling = int(cells[dangling_idx])
        assert dangling == 0, f"Soccer should have 0 dangling, got {dangling}"

    def test_frontmatter_tags(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")
        assert "memory-graph" in text
        assert "stats" in text
        assert "meta" in text

    def test_hub_uplink(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")
        assert "[[_Hub]]" in text

    def test_idempotent(self, synthetic_vault: pathlib.Path) -> None:
        """Running twice should produce the same file without error."""
        out1 = build_graph_report(synthetic_vault)
        out2 = build_graph_report(synthetic_vault)
        assert out1 == out2
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")
        # Still exactly one Overview section
        assert text.count("## Overview") == 1

    def test_type_breakdown_columns(self, synthetic_vault: pathlib.Path) -> None:
        """Subfolder types (Players, Matchups, Surfaces, Teams, Leagues) appear as columns."""
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")
        for t in ("Players", "Matchups", "Surfaces", "Teams", "Leagues"):
            assert t in text, f"Type column '{t}' missing from report"

    def test_tags_histogram_present(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")
        assert "## Top Tags" in text
        # sport/tennis appears in 5 notes
        assert "sport/tennis" in text

    def test_link_density_section(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")
        assert "## Link Density" in text
        assert "Avg Links/Note" in text

    def test_freshness_section(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = (synthetic_vault / "_GraphStats.md").read_text(encoding="utf-8")
        assert "## Freshness" in text

    def test_missing_dir_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_graph_report(tmp_path / "does_not_exist")
