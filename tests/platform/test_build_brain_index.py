"""tests.platform.test_build_brain_index — Brain MOC generator tests.

Synthetic tmp vault with a few person-free notes across 2 sports + named files
to confirm they are skipped.  Fast: pure stdlib, no real vault, no network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.platformkit.atlas.build_brain_index import (
    build_brain_index,
    _is_person_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write(p: Path, text: str = "x\n") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    """A synthetic vault with 2 sports, intel families, meta notes, person files."""
    v = tmp_path / "vault"
    # --- Tennis (person-free playstyles + style matchups) ---
    _write(v / "Sports" / "Tennis" / "Playstyles" / "All_Court_Baseliner.md")
    _write(v / "Sports" / "Tennis" / "Playstyles" / "Clay_Court_Specialist.md")
    _write(v / "Sports" / "Tennis" / "StyleMatchups" / "Baseliner_vs_Server.md")
    # --- Basketball (archetypes incl. digit-prefixed + a meta index) ---
    _write(v / "Sports" / "Basketball_NBA" / "Archetypes" / "3_and_D_Wing.md")
    _write(v / "Sports" / "Basketball_NBA" / "Archetypes" / "Defensive_Anchor.md")
    _write(v / "Sports" / "Basketball_NBA" / "Archetypes" / "_Archetypes_Index.md")
    # PERSON FILES that must be skipped:
    _write(v / "Sports" / "Basketball_NBA" / "Archetypes" / "101108_chris_paul.md")  # id-prefixed
    _write(v / "Sports" / "Basketball_NBA" / "Trends" / "damian_lillard.md")        # lowercase name
    _write(v / "Sports" / "Basketball_NBA" / "Trends" / "_2025-26_Matchup_Meta.md")  # meta kept
    # --- Cross-sport intelligence families ---
    _write(v / "Intelligence" / "Schemes" / "drop_coverage.md")   # lowercase single-token? no -> two tokens
    _write(v / "Intelligence" / "Positions" / "center.md")        # single token -> kept
    # --- Meta notes ---
    _write(v / "_Index" / "_World_Model.md")
    _write(v / "Sports" / "_Base_Rates.md")
    return v


# ---------------------------------------------------------------------------
# Person-file detection unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stem", [
    "101108_chris_paul",   # id-prefixed
    "1626145_tyus_jones",
    "aaron_holiday",       # lowercase first_last
    "damian_lillard",
    "shai_gilgeous-alexander",  # hyphenated lastname
])
def test_person_files_detected(stem: str) -> None:
    assert _is_person_file(stem) is True


@pytest.mark.parametrize("stem", [
    "All_Court_Baseliner",   # Title_Case style
    "3_and_D_Wing",          # digit archetype (single digit, not id)
    "2015",                  # year file
    "Balanced",              # single token
    "center",                # single lowercase token (a position)
    "Defensive_Low-Block",   # mixed case scheme
])
def test_style_files_not_persons(stem: str) -> None:
    assert _is_person_file(stem) is False


# ---------------------------------------------------------------------------
# MOC generation tests
# ---------------------------------------------------------------------------

def test_emits_moc_with_wikilinks(vault: Path, tmp_path: Path) -> None:
    out = tmp_path / "out" / "_Brain.md"
    p = build_brain_index(vault_dir=vault, out_path=out)
    assert p == out and p.is_file()
    text = p.read_text(encoding="utf-8")
    # person-free notes are linked as [[basename]]
    assert "[[All_Court_Baseliner]]" in text
    assert "[[Clay_Court_Specialist]]" in text
    assert "[[3_and_D_Wing]]" in text
    assert "[[Defensive_Anchor]]" in text
    assert "[[drop_coverage]]" in text
    assert "[[center]]" in text


def test_groups_by_sport_and_section(vault: Path, tmp_path: Path) -> None:
    out = tmp_path / "_Brain.md"
    text = build_brain_index(vault_dir=vault, out_path=out).read_text(encoding="utf-8")
    assert "## Sports" in text
    assert "## Cross-sport intelligence" in text
    assert "## Cross-sport meta" in text
    # sport headings present
    assert "### Tennis" in text
    assert "### Basketball NBA" in text
    # family labels present
    assert "**Playstyles**" in text
    assert "**Archetypes**" in text
    assert "**Schemes**" in text
    # per-family count: Tennis Playstyles has 2 person-free notes
    assert "**Playstyles** (2):" in text


def test_skips_person_named_files(vault: Path, tmp_path: Path) -> None:
    out = tmp_path / "_Brain.md"
    text = build_brain_index(vault_dir=vault, out_path=out).read_text(encoding="utf-8")
    # id-prefixed + lowercase-name person files are NOT linked
    assert "chris_paul" not in text
    assert "101108" not in text
    assert "damian_lillard" not in text
    # but they ARE counted as skipped (2 person files: chris_paul + damian_lillard)
    assert "2 skipped (non-person-free)" in text
    # meta note inside a person dir is kept (not a person)
    assert "[[_2025-26_Matchup_Meta]]" in text


def test_counts_in_header(vault: Path, tmp_path: Path) -> None:
    out = tmp_path / "_Brain.md"
    text = build_brain_index(vault_dir=vault, out_path=out).read_text(encoding="utf-8")
    # Sport person-free notes:
    #   Tennis: Playstyles 2 + StyleMatchups 1 = 3
    #   NBA Archetypes: 3_and_D_Wing, Defensive_Anchor, _Archetypes_Index = 3 (chris_paul skipped)
    #   NBA Trends: _2025-26_Matchup_Meta = 1 (damian_lillard skipped)
    # = 7 sport notes ; Intel: drop_coverage + center = 2 ; total = 9.
    assert "9 person-free notes linked across 4 sport families" in text
    assert "2 cross-sport intelligence notes" in text
    # meta: _World_Model + _Base_Rates present = 2
    assert "2 meta note(s)" in text


def test_meta_section_links_present_notes(vault: Path, tmp_path: Path) -> None:
    out = tmp_path / "_Brain.md"
    text = build_brain_index(vault_dir=vault, out_path=out).read_text(encoding="utf-8")
    assert "[[_World_Model]]" in text
    assert "[[_Base_Rates]]" in text
    # a meta note that is absent must NOT be linked
    assert "[[_Signals_Hub]]" not in text


def test_deterministic_identical_bytes(vault: Path, tmp_path: Path) -> None:
    out1 = tmp_path / "a" / "_Brain.md"
    out2 = tmp_path / "b" / "_Brain.md"
    b1 = build_brain_index(vault_dir=vault, out_path=out1).read_bytes()
    b2 = build_brain_index(vault_dir=vault, out_path=out2).read_bytes()
    assert b1 == b2


def test_missing_dirs_no_crash(tmp_path: Path) -> None:
    empty = tmp_path / "empty_vault"
    empty.mkdir()
    out = tmp_path / "_Brain.md"
    p = build_brain_index(vault_dir=empty, out_path=out)
    text = p.read_text(encoding="utf-8")
    # empty sections render placeholders, header still present
    assert "## Sports" in text
    assert "_(none found)_" in text
    assert "0 person-free notes linked" in text


def test_header_has_person_free_and_calibration_note(vault: Path, tmp_path: Path) -> None:
    out = tmp_path / "_Brain.md"
    text = build_brain_index(vault_dir=vault, out_path=out).read_text(encoding="utf-8")
    low = text.lower()
    assert "person-free" in low
    assert "calibration is not edge" in low
    # honest framing: not a betting claim
    assert "never" in low and "name" in low


def test_default_out_path(vault: Path) -> None:
    # default out_path = vault/_Index/_Brain.md
    p = build_brain_index(vault_dir=vault)
    assert p == vault / "_Index" / "_Brain.md"
    assert p.is_file()
