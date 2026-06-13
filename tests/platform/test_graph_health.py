"""test_graph_health.py — unit tests for graph_health.build_graph_health.

Uses a tiny synthetic vault/Sports tree with:
  - a resolvable link
  - a dangling link
  - one note with a [[Players/X]] wikilink (person-bearing)
  - other notes that contain common words (must NOT be flagged)

Single-process; safe for --timeout=120.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scripts.platform.atlas.graph_health import build_graph_health


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(base: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _read(out: pathlib.Path) -> str:
    return out.read_text(encoding="utf-8")


def _dangling_instances(text: str) -> int:
    """Extract 'Dangling links (instances)' value from the Overview table."""
    m = re.search(r"Dangling links \(instances\)\s*\|\s*(\d+)", text)
    assert m, f"Dangling instances row not found in:\n{text[:600]}"
    return int(m.group(1))


def _dangling_unique(text: str) -> int:
    m = re.search(r"Dangling targets \(unique\)\s*\|\s*(\d+)", text)
    assert m, f"Dangling unique row not found in:\n{text[:600]}"
    return int(m.group(1))


def _person_count(text: str) -> int:
    m = re.search(r"Person-bearing notes\s*\|\s*\*\*(\d+)\*\*", text)
    assert m, f"Person-bearing notes row not found in:\n{text[:600]}"
    return int(m.group(1))


# ---------------------------------------------------------------------------
# Synthetic vault fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tiny_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Minimal vault/Sports with one resolvable link, one dangling, no persons."""
    base = tmp_path

    # Basketball_NBA/Teams/NYK.md — links to _Index (resolvable) and GhostNote (dangling)
    _write(base, "Basketball_NBA/Teams/NYK.md",
           "---\ntags:\n  - sport/nba\n---\n"
           "# NYK\n\n[[_Index]] · [[GhostNote]]\n")

    # Basketball_NBA/_Index.md — exists so [[_Index]] resolves
    _write(base, "Basketball_NBA/_Index.md",
           "---\ntags:\n  - sport/nba\n---\n# NBA Index\n\n[[Teams/NYK]]\n")

    # Tennis/_Index.md — contains a common word ('set') but no person patterns
    _write(base, "Tennis/_Index.md",
           "---\ntags:\n  - sport/tennis\n---\n"
           "# Tennis\n\nBest-of-3 set format.\n")

    return base


@pytest.fixture()
def vault_with_player(tmp_path: pathlib.Path) -> pathlib.Path:
    """Vault where one note links to [[Players/SomeName]] — should be flagged."""
    base = tmp_path

    _write(base, "Basketball_NBA/_Index.md",
           "---\ntags:\n  - sport/nba\n---\n# NBA Index\n\n[[Teams/NYK]]\n")

    _write(base, "Basketball_NBA/Teams/NYK.md",
           "---\ntags:\n  - sport/nba\n---\n"
           "# NYK\n\n[[_Index]] · [[Players/SomeStar]]\n")

    _write(base, "Tennis/_Index.md",
           "---\ntags:\n  - sport/tennis\n---\n# Tennis\nNo player info here.\n")

    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOutputFile:

    def test_output_file_created(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        assert out.exists()
        assert out.name == "_Graph_Health.md"
        assert out.parent == tiny_vault

    def test_missing_dir_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_graph_health(tmp_path / "does_not_exist")

    def test_idempotent(self, tiny_vault: pathlib.Path) -> None:
        build_graph_health(tiny_vault)
        build_graph_health(tiny_vault)
        text = _read(build_graph_health(tiny_vault))
        assert text.count("## Overview") == 1


class TestFrontmatterAndStructure:

    def test_frontmatter_tags(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        text = _read(out)
        assert "graph-health" in text
        assert "meta" in text

    def test_hub_uplink(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        assert "[[_Hub]]" in _read(out)

    def test_sections_present(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        text = _read(out)
        assert "## Overview" in text
        assert "## Dangling-Link Audit" in text
        assert "## Note-Type Coverage per Sport" in text
        assert "## Conservative Person-Free Check" in text


class TestDanglingLinks:

    def test_dangling_count_correct(self, tiny_vault: pathlib.Path) -> None:
        """GhostNote has no corresponding .md — must appear as dangling."""
        out = build_graph_health(tiny_vault)
        text = _read(out)
        assert _dangling_instances(text) >= 1, \
            f"Expected >=1 dangling instance, got {_dangling_instances(text)}"

    def test_resolvable_link_not_counted_dangling(self, tiny_vault: pathlib.Path) -> None:
        """[[_Index]] resolves against Basketball_NBA/_Index.md — must not inflate dangling."""
        out = build_graph_health(tiny_vault)
        text = _read(out)
        # Total links = NYK links [[_Index]]+[[GhostNote]] + _Index links [[Teams/NYK]] + Tennis = 3
        # Dangling = only GhostNote = 1
        assert _dangling_instances(text) == 1, \
            f"Only GhostNote should be dangling; got {_dangling_instances(text)}"
        assert _dangling_unique(text) == 1

    def test_ghost_note_listed_in_top_dangling(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        text = _read(out)
        assert "GhostNote" in text

    def test_zero_dangling_when_all_resolve(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/_Index.md",
               "# Index\n\n[[Teams/Alpha]]\n")
        _write(tmp_path, "Sport/Teams/Alpha.md",
               "# Alpha\n\n[[_Index]]\n")
        out = build_graph_health(tmp_path)
        text = _read(out)
        assert _dangling_instances(text) == 0


class TestNoteTypeCoverage:

    def test_coverage_table_present(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        assert "## Note-Type Coverage per Sport" in _read(out)

    def test_sport_names_in_table(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        text = _read(out)
        assert "Basketball_NBA" in text
        assert "Tennis" in text

    def test_total_column_correct(self, tiny_vault: pathlib.Path) -> None:
        """Basketball_NBA has 2 notes (Teams/NYK.md + _Index.md)."""
        out = build_graph_health(tiny_vault)
        text = _read(out)
        lines = text.splitlines()
        nba_row = next(l for l in lines if l.startswith("| Basketball_NBA"))
        cols = [c.strip() for c in nba_row.split("|") if c.strip()]
        total = int(cols[1])  # second column = Total
        assert total == 2


class TestPersonFreeCheck:

    def test_person_free_pass_when_no_players(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        text = _read(out)
        assert _person_count(text) == 0
        assert "PASS" in text

    def test_person_flag_catches_players_wikilink(
        self, vault_with_player: pathlib.Path
    ) -> None:
        """Only the note with [[Players/SomeStar]] must be flagged, not tennis note."""
        out = build_graph_health(vault_with_player)
        text = _read(out)
        assert _person_count(text) == 1, \
            f"Expected exactly 1 person-bearing note, got {_person_count(text)}"
        assert "FAIL" in text

    def test_common_word_note_not_flagged(self, tiny_vault: pathlib.Path) -> None:
        """Tennis/_Index.md contains 'set' — must NOT be flagged as person-bearing."""
        out = build_graph_health(tiny_vault)
        text = _read(out)
        assert _person_count(text) == 0

    def test_player_name_frontmatter_key_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md",
               "---\nplayer_name: Jane Doe\ntags:\n  - sport/test\n---\n# Note\n")
        out = build_graph_health(tmp_path)
        assert _person_count(_read(out)) == 1

    def test_display_name_key_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md",
               "---\ndisplay_name: John Smith\n---\n# Note\n")
        out = build_graph_health(tmp_path)
        assert _person_count(_read(out)) == 1

    def test_roster_section_header_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md",
               "# Team\n\n## Roster\n\n- Alice\n")
        out = build_graph_health(tmp_path)
        assert _person_count(_read(out)) == 1

    def test_squad_section_header_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md",
               "# Team\n\n## Squad\n\n- Bob\n")
        out = build_graph_health(tmp_path)
        assert _person_count(_read(out)) == 1

    def test_only_players_wikilink_triggers_not_random_text(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A note mentioning 'roster' in body text must NOT be flagged."""
        _write(tmp_path, "Sport/Note.md",
               "# Trends\n\nThe roster depth matters for scheduling.\n")
        out = build_graph_health(tmp_path)
        assert _person_count(_read(out)) == 0
