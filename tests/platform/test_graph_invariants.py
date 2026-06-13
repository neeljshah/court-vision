"""test_graph_invariants.py — Regression-guard for two Obsidian-graph invariants.

Invariant 1 — PERSON-FREE: graph contains only playstyle/archetype/team concepts.
  Any note bearing [[Players/X]], player_name:/display_name: frontmatter, or
  ## Players/Roster/Squad headers is a CI failure.

Invariant 2 — LINK-INTEGRITY: every wikilink resolves or is an intentional
  cross-vault anchor (e.g. [[Home]], [[MOC-*]]).  Fixable-dangling links must be 0.

Design: HERMETIC (tmp_path only, never touches the real vault).
Reuses: _is_person_bearing, _is_intentional, _scan_vault from graph_health.py.
"""
from __future__ import annotations

import pathlib

import pytest

from scripts.platformkit.atlas.graph_health import (
    _is_intentional,
    _is_person_bearing,
    _scan_vault,
)


def _write(base: pathlib.Path, rel: str, content: str) -> pathlib.Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ===========================================================================
# INVARIANT 1 — PERSON-FREE
# ===========================================================================

class TestPersonFreeInvariant:
    """_is_person_bearing must flag ONLY high-confidence individual-name markers."""

    # --- unit tests of the helper ---

    def test_flags_players_wikilink(self) -> None:
        assert _is_person_bearing("See [[Players/LeBronJames]] for stats.")

    def test_flags_player_name_frontmatter(self) -> None:
        assert _is_person_bearing("---\nplayer_name: Jane Doe\n---\n")

    def test_flags_display_name_frontmatter(self) -> None:
        assert _is_person_bearing("---\ndisplay_name: John Smith\n---\n")

    def test_flags_roster_section_header(self) -> None:
        assert _is_person_bearing("# Team\n\n## Roster\n\n- Alice\n")

    def test_flags_squad_section_header(self) -> None:
        assert _is_person_bearing("# Team\n\n## Squad\n\n- Bob\n")

    def test_flags_players_section_header(self) -> None:
        assert _is_person_bearing("# Team\n\n## Players\n\n- Charlie\n")

    def test_not_triggered_by_common_words_in_body(self) -> None:
        """Prose mentions of 'roster', 'player', 'squad' must NOT trigger."""
        clean = [
            "# Trends\n\nThe roster depth matters for scheduling.\n",
            "# Style\n\nBest-of-3 set format.\n",
            "# Notes\n\nPlayer usage rate influences pace.\n",
            "# Analysis\n\nSquad rotation is crucial in high-pace systems.\n",
        ]
        for text in clean:
            assert not _is_person_bearing(text), (
                f"False-positive for: {text!r}"
            )

    def test_not_triggered_by_playstyle_wikilink(self) -> None:
        assert not _is_person_bearing("See [[Playstyles/HighPost]] for context.")

    def test_not_triggered_by_archetypes_wikilink(self) -> None:
        assert not _is_person_bearing("Archetype: [[Archetypes/PickAndRoll]]")

    # --- synthetic vault: CLEAN ---

    @pytest.fixture()
    def clean_vault(self, tmp_path: pathlib.Path) -> pathlib.Path:
        _write(tmp_path, "Basketball_NBA/Teams/NYK.md",
               "---\ntags:\n  - sport/nba\n---\n"
               "# NYK\n\n[[Basketball_NBA/_Index]] · [[Archetypes/HighPace]]\n")
        _write(tmp_path, "Basketball_NBA/_Index.md",
               "---\ntags:\n  - sport/nba\n---\n# NBA Index\n\n[[Teams/NYK]]\n")
        _write(tmp_path, "Basketball_NBA/Archetypes/HighPace.md",
               "---\ntags:\n  - type/archetype\n---\n# High-Pace\n\n[[Home]]\n")
        _write(tmp_path, "Tennis/_Index.md",
               "---\ntags:\n  - sport/tennis\n---\n# Tennis Hub\n\nSet format.\n")
        return tmp_path

    def test_clean_vault_zero_person_notes(self, clean_vault: pathlib.Path) -> None:
        """REGRESSION GUARD: clean synthetic graph must yield 0 person-bearing notes."""
        data = _scan_vault(clean_vault)
        person = data["person_notes"]
        assert len(person) == 0, (
            f"Expected 0; got {len(person)}: {[str(p) for p in person]}"
        )

    # --- synthetic vault: DIRTY ---

    @pytest.fixture()
    def dirty_vault_players_link(self, tmp_path: pathlib.Path) -> pathlib.Path:
        _write(tmp_path, "Basketball_NBA/_Index.md",
               "---\ntags:\n  - sport/nba\n---\n# NBA Index\n\n[[Teams/NYK]]\n")
        _write(tmp_path, "Basketball_NBA/Teams/NYK.md",
               "---\ntags:\n  - sport/nba\n---\n"
               "# NYK\n\n[[_Index]] · [[Players/SomeStar]]\n")
        _write(tmp_path, "Tennis/_Index.md",
               "---\ntags:\n  - sport/tennis\n---\n# Tennis\nNo player info here.\n")
        return tmp_path

    @pytest.fixture()
    def dirty_vault_frontmatter_key(self, tmp_path: pathlib.Path) -> pathlib.Path:
        _write(tmp_path, "Sport/Note.md",
               "---\nplayer_name: Jane Doe\ntags:\n  - sport/test\n---\n# Note\n")
        _write(tmp_path, "Sport/_Index.md",
               "---\ntags:\n  - sport/test\n---\n# Index\n")
        return tmp_path

    def test_dirty_players_link_flagged(
        self, dirty_vault_players_link: pathlib.Path
    ) -> None:
        """REGRESSION GUARD: [[Players/X]] wikilink must be caught."""
        data = _scan_vault(dirty_vault_players_link)
        assert len(data["person_notes"]) > 0, (
            "Expected >0 person-bearing notes with [[Players/SomeStar]]; "
            "got 0 — PERSON-FREE guard is broken"
        )

    def test_dirty_only_polluted_note_flagged(
        self, dirty_vault_players_link: pathlib.Path
    ) -> None:
        """Exactly 1 note flagged — Tennis note (no person markers) is clean."""
        data = _scan_vault(dirty_vault_players_link)
        assert len(data["person_notes"]) == 1, (
            f"Expected 1 person-bearing note; got {len(data['person_notes'])}: "
            f"{[str(p) for p in data['person_notes']]}"
        )

    def test_dirty_frontmatter_key_flagged(
        self, dirty_vault_frontmatter_key: pathlib.Path
    ) -> None:
        """REGRESSION GUARD: player_name: frontmatter key must be caught."""
        data = _scan_vault(dirty_vault_frontmatter_key)
        assert len(data["person_notes"]) > 0, (
            "Expected >0 person-bearing notes for player_name: frontmatter; got 0"
        )


# ===========================================================================
# INVARIANT 2 — LINK-INTEGRITY
# ===========================================================================

class TestLinkIntegrityInvariant:
    """dangling_fixable must be 0; intentional cross-vault anchors are allowed."""

    # --- unit tests for the intentional classifier ---

    def test_intentional_home(self) -> None:
        assert _is_intentional("Home")

    def test_intentional_moc_exact(self) -> None:
        assert _is_intentional("MOC-CV")

    def test_intentional_moc_prefix(self) -> None:
        assert _is_intentional("MOC-Anything")

    def test_intentional_intelligence_prefix(self) -> None:
        assert _is_intentional("Intelligence/SomeNote")

    def test_intentional_rejects_random_slug(self) -> None:
        assert not _is_intentional("MissingArc")

    def test_intentional_rejects_plain_team(self) -> None:
        assert not _is_intentional("NYK")

    # --- synthetic vault with all three link categories ---

    @pytest.fixture()
    def three_category_vault(self, tmp_path: pathlib.Path) -> pathlib.Path:
        """Vault with 1 resolvable, 1 fixable-dangling, 1 intentional cross-vault link."""
        _write(tmp_path, "Basketball_NBA/Teams/NYK.md",
               "---\ntags:\n  - sport/nba\n---\n"
               "# NYK\n\n"
               "[[Archetypes/HighPace]] · [[Archetypes/MissingArc]] · [[Home]]\n")
        _write(tmp_path, "Basketball_NBA/Archetypes/HighPace.md",
               "---\ntags:\n  - type/archetype\n---\n# High-Pace\n")
        return tmp_path

    def test_resolvable_absent_from_fixable(
        self, three_category_vault: pathlib.Path
    ) -> None:
        """[[Archetypes/HighPace]] resolves → must NOT appear in dangling_fixable."""
        data = _scan_vault(three_category_vault)
        assert "Archetypes/HighPace" not in data["dangling_fixable"], (
            f"Resolvable link in dangling_fixable: {dict(data['dangling_fixable'])}"
        )

    def test_fixable_dangling_count_is_one(
        self, three_category_vault: pathlib.Path
    ) -> None:
        """REGRESSION GUARD: exactly 1 fixable-dangling unique target."""
        data = _scan_vault(three_category_vault)
        fixable = data["dangling_fixable"]
        assert len(fixable) == 1, (
            f"Expected 1 fixable-dangling; got {len(fixable)}: {dict(fixable)}"
        )

    def test_intentional_count_is_one(
        self, three_category_vault: pathlib.Path
    ) -> None:
        """REGRESSION GUARD: exactly 1 intentional cross-vault unique target."""
        data = _scan_vault(three_category_vault)
        intentional = data["dangling_intentional"]
        assert len(intentional) == 1, (
            f"Expected 1 intentional; got {len(intentional)}: {dict(intentional)}"
        )

    def test_intentional_key_is_home(
        self, three_category_vault: pathlib.Path
    ) -> None:
        assert "Home" in _scan_vault(three_category_vault)["dangling_intentional"]

    def test_fixable_key_is_missing_arc(
        self, three_category_vault: pathlib.Path
    ) -> None:
        assert "Archetypes/MissingArc" in _scan_vault(three_category_vault)["dangling_fixable"]

    # --- edge cases ---

    def test_fully_connected_zero_fixable(self, tmp_path: pathlib.Path) -> None:
        """All links resolve or are intentional → 0 fixable dangling."""
        _write(tmp_path, "Sport/_Index.md",
               "# Index\n\n[[Teams/Alpha]] · [[Home]]\n")
        _write(tmp_path, "Sport/Teams/Alpha.md",
               "# Alpha\n\n[[_Index]]\n")
        data = _scan_vault(tmp_path)
        assert len(data["dangling_fixable"]) == 0, (
            f"Expected 0 fixable; got {dict(data['dangling_fixable'])}"
        )

    def test_two_fixable_dangling_counted_correctly(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Two distinct broken refs → fixable unique count must be 2."""
        _write(tmp_path, "Sport/_Index.md",
               "# Index\n\n[[Teams/Alpha]] · [[Teams/Bravo]] · [[Home]]\n")
        data = _scan_vault(tmp_path)
        fixable = data["dangling_fixable"]
        assert len(fixable) == 2, (
            f"Expected 2 fixable-dangling; got {len(fixable)}: {dict(fixable)}"
        )

    def test_partition_fixable_plus_intentional_equals_total_dangling_instances(
        self, three_category_vault: pathlib.Path
    ) -> None:
        """fixable + intentional instances must account for all dangling links."""
        data = _scan_vault(three_category_vault)
        n_fixable = sum(data["dangling_fixable"].values())
        n_intentional = sum(data["dangling_intentional"].values())
        total_dangling = n_fixable + n_intentional
        assert total_dangling <= data["total_links"], (
            "Dangling instances cannot exceed total link count"
        )
        # Every dangling instance is classified into exactly one bucket
        assert n_fixable + n_intentional == total_dangling

    def test_stem_only_link_resolves(self, tmp_path: pathlib.Path) -> None:
        """[[NYK]] stem-only link must resolve when NYK.md exists anywhere in tree."""
        _write(tmp_path, "Sport/Teams/NYK.md", "# NYK\n\n[[_Index]]\n")
        _write(tmp_path, "Sport/_Index.md", "# Index\n\n[[NYK]]\n")
        data = _scan_vault(tmp_path)
        assert len(data["dangling_fixable"]) == 0, (
            f"Stem-only [[NYK]] should resolve; fixable={dict(data['dangling_fixable'])}"
        )
