"""test_graph_health.py — unit tests for graph_health.build_graph_health.

Uses tiny synthetic vault/Sports trees with:
  - a resolvable link, a dangling fixable link, a dangling intentional link
  - one note with a [[Players/X]] wikilink (person-bearing)
  - other notes containing common words (must NOT be flagged)

Single-process; safe for --timeout=120.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scripts.platformkit.atlas.graph_health import _is_intentional, build_graph_health


# -- helpers ------------------------------------------------------------------

def _write(base: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p

def _read(out: pathlib.Path) -> str:
    return out.read_text(encoding="utf-8")

def _dangling_instances(text: str) -> int:
    m = re.search(r"Dangling links \(instances\)\s*\|\s*(\d+)", text)
    assert m, f"Dangling instances row not found in:\n{text[:600]}"
    return int(m.group(1))

def _dangling_unique(text: str) -> int:
    m = re.search(r"Dangling targets \(unique\)\s*\|\s*(\d+)", text)
    assert m, f"Dangling unique row not found in:\n{text[:600]}"
    return int(m.group(1))

def _dangling_intentional(text: str) -> int:
    m = re.search(r"Dangling — intentional cross-vault\s*\|\s*(\d+)", text)
    assert m, f"Intentional cross-vault row not found in:\n{text[:600]}"
    return int(m.group(1))

def _dangling_fixable(text: str) -> int:
    m = re.search(r"Dangling — fixable\s*\|\s*(\d+)", text)
    assert m, f"Fixable dangling row not found in:\n{text[:600]}"
    return int(m.group(1))

def _person_count(text: str) -> int:
    m = re.search(r"Person-bearing notes\s*\|\s*\*\*(\d+)\*\*", text)
    assert m, f"Person-bearing notes row not found in:\n{text[:600]}"
    return int(m.group(1))

def _graph_integrity_verdict(text: str) -> str:
    m = re.search(r"GRAPH-INTEGRITY verdict\s*\|\s*\*\*([^*]+)\*\*", text)
    assert m, f"GRAPH-INTEGRITY verdict row not found in:\n{text[:600]}"
    return m.group(1).strip()


# -- fixtures -----------------------------------------------------------------

@pytest.fixture()
def tiny_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Minimal vault: one resolvable link, one fixable dangling, no persons."""
    _write(tmp_path, "Basketball_NBA/Teams/NYK.md",
           "---\ntags:\n  - sport/nba\n---\n# NYK\n\n[[_Index]] · [[GhostNote]]\n")
    _write(tmp_path, "Basketball_NBA/_Index.md",
           "---\ntags:\n  - sport/nba\n---\n# NBA Index\n\n[[Teams/NYK]]\n")
    _write(tmp_path, "Tennis/_Index.md",
           "---\ntags:\n  - sport/tennis\n---\n# Tennis\n\nBest-of-3 set format.\n")
    return tmp_path

@pytest.fixture()
def vault_with_intentional(tmp_path: pathlib.Path) -> pathlib.Path:
    """Vault with fixable dangling AND intentional cross-vault links."""
    _write(tmp_path, "Basketball_NBA/_Index.md",
           "---\ntags:\n  - sport/nba\n---\n# NBA Index\n\n[[Teams/NYK]] · [[Home]]\n")
    _write(tmp_path, "Basketball_NBA/Teams/NYK.md",
           "---\ntags:\n  - sport/nba\n---\n# NYK\n\n[[_Index]] · [[GhostNote]] · [[MOC-CV]]\n")
    return tmp_path

@pytest.fixture()
def vault_with_player(tmp_path: pathlib.Path) -> pathlib.Path:
    """Vault with a [[Players/SomeName]] wikilink — should be flagged."""
    _write(tmp_path, "Basketball_NBA/_Index.md",
           "---\ntags:\n  - sport/nba\n---\n# NBA Index\n\n[[Teams/NYK]]\n")
    _write(tmp_path, "Basketball_NBA/Teams/NYK.md",
           "---\ntags:\n  - sport/nba\n---\n# NYK\n\n[[_Index]] · [[Players/SomeStar]]\n")
    _write(tmp_path, "Tennis/_Index.md",
           "---\ntags:\n  - sport/tennis\n---\n# Tennis\nNo player info here.\n")
    return tmp_path


# -- _is_intentional ----------------------------------------------------------

@pytest.mark.parametrize("target", [
    "Home", "MOC-CV", "MOC-Models", "MOC-Betting", "MOC-Strategy",
    "Intelligence/_Scout_Index", "Bundesliga_2021", "Premier_League_2020", "La_Liga_2023",
])
def test_is_intentional_true(target: str) -> None:
    assert _is_intentional(target), f"Expected {target!r} to be intentional"

@pytest.mark.parametrize("target", ["GhostNote", "Playstyles/unclassified", "SomeRandomNote"])
def test_is_intentional_false(target: str) -> None:
    assert not _is_intentional(target), f"Expected {target!r} to NOT be intentional"


# -- output file --------------------------------------------------------------

class TestOutputFile:
    def test_output_file_created(self, tiny_vault: pathlib.Path) -> None:
        out = build_graph_health(tiny_vault)
        assert out.exists() and out.name == "_Graph_Health.md" and out.parent == tiny_vault

    def test_missing_dir_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_graph_health(tmp_path / "does_not_exist")

    def test_idempotent(self, tiny_vault: pathlib.Path) -> None:
        build_graph_health(tiny_vault)
        build_graph_health(tiny_vault)
        assert _read(build_graph_health(tiny_vault)).count("## Overview") == 1


# -- frontmatter & structure --------------------------------------------------

class TestFrontmatterAndStructure:
    def test_frontmatter_tags(self, tiny_vault: pathlib.Path) -> None:
        text = _read(build_graph_health(tiny_vault))
        assert "graph-health" in text and "meta" in text

    def test_hub_uplink(self, tiny_vault: pathlib.Path) -> None:
        assert "[[_Hub]]" in _read(build_graph_health(tiny_vault))

    def test_sections_present(self, tiny_vault: pathlib.Path) -> None:
        text = _read(build_graph_health(tiny_vault))
        for s in ["## Overview", "## Dangling-Link Audit", "### Intentional Cross-Vault Links",
                  "### Fixable Dangling Links", "## Note-Type Coverage per Sport",
                  "## Conservative Person-Free Check"]:
            assert s in text, f"Missing section: {s}"

    def test_graph_integrity_verdict_present(self, tiny_vault: pathlib.Path) -> None:
        assert "GRAPH-INTEGRITY verdict" in _read(build_graph_health(tiny_vault))


# -- dangling link split ------------------------------------------------------

class TestDanglingLinkSplit:
    def test_fixable_dangling_counted(self, tiny_vault: pathlib.Path) -> None:
        text = _read(build_graph_health(tiny_vault))
        assert _dangling_fixable(text) == 1, \
            f"Expected 1 fixable dangling, got {_dangling_fixable(text)}"

    def test_no_intentional_in_tiny_vault(self, tiny_vault: pathlib.Path) -> None:
        assert _dangling_intentional(_read(build_graph_health(tiny_vault))) == 0

    def test_intentional_and_fixable_split(self, vault_with_intentional: pathlib.Path) -> None:
        text = _read(build_graph_health(vault_with_intentional))
        assert _dangling_intentional(text) == 2, \
            f"Expected 2 intentional (Home + MOC-CV), got {_dangling_intentional(text)}"
        assert _dangling_fixable(text) == 1, \
            f"Expected 1 fixable (GhostNote), got {_dangling_fixable(text)}"

    def test_dangling_instances_equals_intentional_plus_fixable(
            self, vault_with_intentional: pathlib.Path) -> None:
        text = _read(build_graph_health(vault_with_intentional))
        total, intentional, fixable = (_dangling_instances(text),
                                       _dangling_intentional(text), _dangling_fixable(text))
        assert total == intentional + fixable, \
            f"total={total} != intentional={intentional} + fixable={fixable}"

    def test_graph_integrity_fail_when_fixable(self, vault_with_intentional: pathlib.Path) -> None:
        verdict = _graph_integrity_verdict(_read(build_graph_health(vault_with_intentional)))
        assert "FAIL" in verdict, f"Expected FAIL verdict, got: {verdict}"

    def test_graph_integrity_pass_when_no_fixable(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/_Index.md", "# Index\n\n[[Teams/Alpha]] · [[Home]]\n")
        _write(tmp_path, "Sport/Teams/Alpha.md", "# Alpha\n\n[[_Index]]\n")
        text = _read(build_graph_health(tmp_path))
        assert _dangling_fixable(text) == 0
        assert _graph_integrity_verdict(text) == "PASS"

    def test_resolvable_link_not_counted_dangling(self, tiny_vault: pathlib.Path) -> None:
        text = _read(build_graph_health(tiny_vault))
        assert _dangling_instances(text) == 1, \
            f"Only GhostNote should be dangling; got {_dangling_instances(text)}"
        assert _dangling_unique(text) == 1

    def test_ghost_note_listed_in_fixable_section(self, tiny_vault: pathlib.Path) -> None:
        text = _read(build_graph_health(tiny_vault))
        in_fixable = found = False
        for line in text.splitlines():
            if "### Fixable Dangling Links" in line:
                in_fixable = True
            if in_fixable and "GhostNote" in line:
                found = True
                break
        assert found, "GhostNote not found in Fixable section"

    def test_zero_dangling_when_all_resolve(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/_Index.md", "# Index\n\n[[Teams/Alpha]]\n")
        _write(tmp_path, "Sport/Teams/Alpha.md", "# Alpha\n\n[[_Index]]\n")
        text = _read(build_graph_health(tmp_path))
        assert _dangling_instances(text) == 0
        assert _dangling_fixable(text) == 0
        assert _dangling_intentional(text) == 0
        assert _graph_integrity_verdict(text) == "PASS"


# -- note type coverage -------------------------------------------------------

class TestNoteTypeCoverage:
    def test_coverage_table_present(self, tiny_vault: pathlib.Path) -> None:
        assert "## Note-Type Coverage per Sport" in _read(build_graph_health(tiny_vault))

    def test_sport_names_in_table(self, tiny_vault: pathlib.Path) -> None:
        text = _read(build_graph_health(tiny_vault))
        assert "Basketball_NBA" in text and "Tennis" in text

    def test_total_column_correct(self, tiny_vault: pathlib.Path) -> None:
        """Basketball_NBA has 2 notes."""
        text = _read(build_graph_health(tiny_vault))
        nba_row = next(l for l in text.splitlines() if l.startswith("| Basketball_NBA"))
        assert int([c.strip() for c in nba_row.split("|") if c.strip()][1]) == 2


# -- person-free check --------------------------------------------------------

class TestPersonFreeCheck:
    def test_person_free_pass_when_no_players(self, tiny_vault: pathlib.Path) -> None:
        text = _read(build_graph_health(tiny_vault))
        assert _person_count(text) == 0 and "PASS" in text

    def test_person_flag_catches_players_wikilink(self, vault_with_player: pathlib.Path) -> None:
        text = _read(build_graph_health(vault_with_player))
        assert _person_count(text) == 1, \
            f"Expected exactly 1 person-bearing note, got {_person_count(text)}"
        assert "FAIL" in text

    def test_common_word_note_not_flagged(self, tiny_vault: pathlib.Path) -> None:
        assert _person_count(_read(build_graph_health(tiny_vault))) == 0

    def test_player_name_frontmatter_key_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md",
               "---\nplayer_name: Jane Doe\ntags:\n  - sport/test\n---\n# Note\n")
        assert _person_count(_read(build_graph_health(tmp_path))) == 1

    def test_display_name_key_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md", "---\ndisplay_name: John Smith\n---\n# Note\n")
        assert _person_count(_read(build_graph_health(tmp_path))) == 1

    def test_roster_section_header_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md", "# Team\n\n## Roster\n\n- Alice\n")
        assert _person_count(_read(build_graph_health(tmp_path))) == 1

    def test_squad_section_header_flagged(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md", "# Team\n\n## Squad\n\n- Bob\n")
        assert _person_count(_read(build_graph_health(tmp_path))) == 1

    def test_only_players_wikilink_triggers_not_random_text(self, tmp_path: pathlib.Path) -> None:
        _write(tmp_path, "Sport/Note.md",
               "# Trends\n\nThe roster depth matters for scheduling.\n")
        assert _person_count(_read(build_graph_health(tmp_path))) == 0
