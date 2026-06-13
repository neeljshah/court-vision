"""test_graph_report.py — scoped unit tests for graph_report.build_graph_report.

Uses a synthetic vault/Sports tree in tmp_path so no real vault is touched.
Single-process; safe for --timeout=120.
"""
from __future__ import annotations

import pathlib

import pytest

from scripts.platformkit.atlas.graph_report import build_graph_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _note(tags: list, title: str, body: str = "") -> str:
    tag_lines = "".join(f"  - {t}\n" for t in tags)
    return f"---\ntags:\n{tag_lines}---\n# {title}\n{body}\n"


def _make_sport(base: pathlib.Path, sport: str, notes: dict) -> None:
    sport_dir = base / sport
    sport_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in notes.items():
        p = sport_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def _get_cell(text: str, section_prefix: str, row_prefix: str, col_name: str) -> str:
    """Extract a cell value from a markdown table by section/row/column name."""
    lines = text.splitlines()
    sec = next(i for i, l in enumerate(lines) if l.startswith(section_prefix))
    col_names = [c.strip() for c in lines[sec + 2].split("|") if c.strip()]
    row = next(l for l in lines[sec:] if l.startswith(row_prefix))
    return [c.strip() for c in row.split("|") if c.strip()][col_names.index(col_name)]


def _read(vault: pathlib.Path) -> str:
    return (vault / "_GraphStats.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Note fixture data
# ---------------------------------------------------------------------------

TENNIS_NOTES = {
    "_Index.md": _note(["sport/tennis", "index"], "Tennis Index",
        "[[Playstyles/Clay_Court_Specialist|Clay]] · [[Surfaces/Clay|Clay Surface]]"),
    "Playstyles/Clay_Court_Specialist.md": _note(["sport/tennis", "playstyle"],
        "Clay Court Specialist", "[[_Index|Back]] · [[Surfaces/Clay|Clay]]"),
    "Playstyles/Fast_Court_Big_Server.md": _note(["sport/tennis", "playstyle"],
        "Fast Court Big Server", "[[_Index|Back]]"),
    "Matchups/Clay_vs_Hard.md": _note(["sport/tennis", "matchup"], "Clay vs Hard",
        "[[Playstyles/Clay_Court_Specialist]] · [[Playstyles/Fast_Court_Big_Server]]"
        "\n· [[Playstyles/GHOST_PLAYSTYLE|Ghost]]"),
    "Surfaces/Clay.md": _note(["sport/tennis", "surface"], "Clay", "[[_Index]]"),
    "Signals/_Catalog.md": _note(["sport/tennis", "signal-catalog"], "Signals Catalog",
        "| Signal | Verdict |\n|--------|----------|\n| elo_diff | REJECT |"),
}

SOCCER_NOTES = {
    "_Index.md": _note(["sport/soccer", "index"], "Soccer Index", "[[Teams/Arsenal|Arsenal]]"),
    "Teams/Arsenal.md": _note(["sport/soccer", "atlas/team"], "Arsenal",
        "[[_Index]] · [[Leagues/Premier_League|PL]]"),
    "Leagues/Premier_League.md": _note(["sport/soccer", "league"], "Premier League", "[[_Index]]"),
    "Playstyles/High_Pressing.md": _note(["sport/soccer", "playstyle"], "High Pressing", "[[_Index]]"),
}

NBA_NOTES = {
    "_Index.md": _note(["sport/nba", "index"], "NBA Index",
        "[[Teams/NYK|Knicks]] · [[Archetypes/High_Usage_Creator|Creator]]"),
    "Teams/NYK.md": _note(["sport/nba", "atlas/team"], "New York Knicks", "[[_Index]]"),
    "Archetypes/High_Usage_Creator.md": _note(["sport/nba", "archetype"],
        "High-Usage Creator", "[[_Index]]"),
    "Archetypes/Defensive_Anchor.md": _note(["sport/nba", "archetype"],
        "Defensive Anchor", "[[_Index]]"),
    "Signals/_Catalog.md": _note(["sport/nba", "signal-catalog"], "NBA Signals Catalog",
        "| Signal | Verdict |\n|--------|----------|\n| ast_pct | PASS |"),
}

TENNIS_WITH_PLAYERS = {
    **TENNIS_NOTES,
    "Players/Ana_Ivanovic.md": _note(["sport/tennis", "player"], "Ana Ivanovic", "[[_Index|Back]]"),
    "Players/Boris_Becker.md": _note(["sport/tennis", "player"], "Boris Becker", "[[_Index|Back]]"),
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Person-free synthetic vault/Sports tree."""
    _make_sport(tmp_path, "Tennis", TENNIS_NOTES)
    _make_sport(tmp_path, "Soccer", SOCCER_NOTES)
    _make_sport(tmp_path, "Basketball_NBA", NBA_NOTES)
    return tmp_path


@pytest.fixture()
def vault_with_players(tmp_path: pathlib.Path) -> pathlib.Path:
    """Vault with Players/ notes — PERSON-FREE check should FAIL."""
    _make_sport(tmp_path, "Tennis", TENNIS_WITH_PLAYERS)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests — existing behaviour
# ---------------------------------------------------------------------------

class TestBuildGraphReport:

    def test_output_file_created(self, synthetic_vault: pathlib.Path) -> None:
        out = build_graph_report(synthetic_vault)
        assert out.exists() and out.name == "_GraphStats.md"
        assert out.parent == synthetic_vault

    def test_note_counts_correct(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        assert "**15**" in text, f"Expected grand total 15:\n{text[:800]}"
        assert _get_cell(text, "## Per-Sport Note Counts", "| Tennis", "Total") == "6"
        assert _get_cell(text, "## Per-Sport Note Counts", "| Soccer", "Total") == "4"
        assert _get_cell(text, "## Per-Sport Note Counts", "| Basketball_NBA", "Total") == "5"

    def test_dangling_link_detected(self, synthetic_vault: pathlib.Path) -> None:
        """Tennis Matchup links [[Playstyles/GHOST_PLAYSTYLE]] which has no note."""
        build_graph_report(synthetic_vault)
        dangling = int(_get_cell(_read(synthetic_vault), "## Link Density", "| Tennis", "Dangling"))
        assert dangling >= 1, f"Expected >=1 dangling for Tennis, got {dangling}"

    def test_soccer_no_dangling(self, synthetic_vault: pathlib.Path) -> None:
        """Soccer notes only link to each other — no dangling expected."""
        build_graph_report(synthetic_vault)
        dangling = int(_get_cell(_read(synthetic_vault), "## Link Density", "| Soccer", "Dangling"))
        assert dangling == 0, f"Soccer should have 0 dangling, got {dangling}"

    def test_frontmatter_tags(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        assert "memory-graph" in text and "stats" in text and "meta" in text

    def test_hub_uplink(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        assert "[[_Hub]]" in _read(synthetic_vault)

    def test_idempotent(self, synthetic_vault: pathlib.Path) -> None:
        """Running twice produces the same file without error."""
        build_graph_report(synthetic_vault)
        build_graph_report(synthetic_vault)
        assert _read(synthetic_vault).count("## Overview") == 1

    def test_tags_histogram_present(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        assert "## Top Tags" in text and "sport/tennis" in text

    def test_link_density_section(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        assert "## Link Density" in text and "Avg Links/Note" in text

    def test_freshness_section(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        assert "## Freshness" in _read(synthetic_vault)

    def test_missing_dir_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_graph_report(tmp_path / "does_not_exist")


# ---------------------------------------------------------------------------
# Tests — new type columns (Archetypes, Playstyles, Signals)
# ---------------------------------------------------------------------------

class TestNewNoteTypes:

    def test_type_columns_include_new_types(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        for col in ("Archetypes", "Playstyles", "Signals"):
            assert col in text, f"Column '{col}' missing from report"

    def test_legacy_type_columns_still_present(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        for col in ("Teams", "Matchups", "Surfaces", "Leagues"):
            assert col in text, f"Legacy column '{col}' missing from report"

    def test_archetype_count_for_nba(self, synthetic_vault: pathlib.Path) -> None:
        """Basketball_NBA has 2 Archetype notes."""
        build_graph_report(synthetic_vault)
        val = _get_cell(_read(synthetic_vault), "## Per-Sport Note Counts",
                        "| Basketball_NBA", "Archetypes")
        assert val == "2", f"Expected 2 NBA Archetypes, got {val!r}"

    def test_playstyle_count_for_tennis(self, synthetic_vault: pathlib.Path) -> None:
        """Tennis has 2 Playstyle notes."""
        build_graph_report(synthetic_vault)
        val = _get_cell(_read(synthetic_vault), "## Per-Sport Note Counts",
                        "| Tennis", "Playstyles")
        assert val == "2", f"Expected 2 Tennis Playstyles, got {val!r}"

    def test_signal_catalog_counted(self, synthetic_vault: pathlib.Path) -> None:
        """Signals/_Catalog.md notes in Tennis and NBA should each count as 1."""
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        for row_pfx, label in [("| Tennis", "Tennis"), ("| Basketball_NBA", "NBA")]:
            val = _get_cell(text, "## Per-Sport Note Counts", row_pfx, "Signals")
            assert val == "1", f"{label} Signals wrong: {val!r}"

    def test_graph_composition_section_present(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        assert "## Graph Composition" in text
        assert "Style layer?" in text and "yes" in text

    def test_style_layer_callout(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        assert "Style-layer notes (Archetypes + Playstyles + Signals)" in _read(synthetic_vault)


# ---------------------------------------------------------------------------
# Tests — PERSON-FREE data-quality metric
# ---------------------------------------------------------------------------

class TestPersonFreeMetric:

    def test_person_free_pass_when_no_players(self, synthetic_vault: pathlib.Path) -> None:
        """Vault with no Players/ subfolders must report PERSON-FREE: PASS."""
        build_graph_report(synthetic_vault)
        text = _read(synthetic_vault)
        assert "PERSON-FREE" in text and "PASS" in text

    def test_person_free_fail_when_players_present(
        self, vault_with_players: pathlib.Path
    ) -> None:
        """Vault with Players/ notes must report PERSON-FREE: FAIL."""
        build_graph_report(vault_with_players)
        text = (vault_with_players / "_GraphStats.md").read_text(encoding="utf-8")
        assert "FAIL" in text and "2 person notes found" in text

    def test_person_free_section_present(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        assert "## PERSON-FREE Data-Quality Check" in _read(synthetic_vault)

    def test_person_count_in_overview(self, synthetic_vault: pathlib.Path) -> None:
        """Overview table must contain the PERSON-FREE check row."""
        build_graph_report(synthetic_vault)
        lines = _read(synthetic_vault).splitlines()
        ov_start = next(i for i, l in enumerate(lines) if l.startswith("## Overview"))
        assert any("PERSON-FREE" in l for l in lines[ov_start:ov_start + 15]), \
            "PERSON-FREE row missing from Overview table"

    def test_footer_includes_person_count(self, synthetic_vault: pathlib.Path) -> None:
        build_graph_report(synthetic_vault)
        assert "person notes: 0" in _read(synthetic_vault)
