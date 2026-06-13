"""tests.platform.test_atlas_person_free — PERSON-FREE gate selection logic.

Asserts the platform's atlas build is PERSON-FREE by default: the NAMED-entity
generators (base atlas → Teams, H2H → Matchups, Seasons, Tournaments, Scouting)
are gated OFF, while the person-free archetype families (Playstyles, StyleMatchups,
StyleTrends, SchemeTransitions, HomeEnvironment, Trends) still run.

Tests the PURE selection helper hub_data.selected_generators(person_free) WITHOUT
running any generation (no corpus reads, no file writes).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.atlas.hub_data import (  # noqa: E402
    NAMED_GENERATORS,
    PERSON_FREE,
    PERSON_FREE_GENERATORS,
    EXTRA_SUBDIR_KEY,
    selected_generators,
)

# Logical keys the platform must NEVER emit under the person-free discipline.
_NAMED_KEYS = {"base_atlas", "h2h", "tournaments", "seasons", "scouting"}
# Archetype/style families that must ALWAYS run.
_PERSON_FREE_KEYS = {
    "playstyles", "style_matchups", "style_trends",
    "scheme_transitions", "home_environment", "trends",
}


def test_person_free_default_is_true() -> None:
    """The platform ships PERSON-FREE by default."""
    assert PERSON_FREE is True


def test_named_and_person_free_sets_are_disjoint() -> None:
    """No generator key is classified as both NAMED and PERSON-FREE."""
    assert set(NAMED_GENERATORS).isdisjoint(set(PERSON_FREE_GENERATORS))


def test_named_set_matches_expected() -> None:
    assert set(NAMED_GENERATORS) == _NAMED_KEYS


def test_person_free_set_matches_expected() -> None:
    assert set(PERSON_FREE_GENERATORS) == _PERSON_FREE_KEYS


def test_selected_person_free_excludes_named() -> None:
    """Under PERSON_FREE=True, none of the named (Teams/Matchups/Seasons/
    Tournaments/Scouting) generators are selected."""
    selected = set(selected_generators(True))
    leaked = selected & _NAMED_KEYS
    assert not leaked, f"NAMED generators leaked into person-free build: {leaked}"


def test_selected_person_free_includes_archetype_families() -> None:
    """Under PERSON_FREE=True, every Style*/Playstyles family still runs."""
    selected = set(selected_generators(True))
    missing = _PERSON_FREE_KEYS - selected
    assert not missing, f"Person-free families dropped from build: {missing}"


def test_selected_person_free_equals_person_free_set() -> None:
    """Person-free selection is EXACTLY the person-free generator set."""
    assert set(selected_generators(True)) == set(PERSON_FREE_GENERATORS)


def test_selected_with_named_includes_everything() -> None:
    """PERSON_FREE=False restores the full build (gate, not deletion)."""
    selected = set(selected_generators(False))
    assert _NAMED_KEYS <= selected, "Named generators missing from full build"
    assert _PERSON_FREE_KEYS <= selected, "Person-free families missing from full build"
    assert selected == _NAMED_KEYS | _PERSON_FREE_KEYS


def test_selected_returns_fresh_list() -> None:
    """Helper returns a new list each call (mutating it must not corrupt state)."""
    a = selected_generators(True)
    a.append("__mutated__")
    b = selected_generators(True)
    assert "__mutated__" not in b


def test_extra_subdir_named_dirs_map_to_named_keys() -> None:
    """Scouting (per-named-entity) maps to a NAMED key so _build_extras gates it,
    while the style/environment subdirs map to person-free keys."""
    assert EXTRA_SUBDIR_KEY["Scouting"] in _NAMED_KEYS
    for sub in ("StyleMatchups", "StyleTrends", "SchemeTransitions",
                "HomeEnvironment", "Trends"):
        assert EXTRA_SUBDIR_KEY[sub] in _PERSON_FREE_KEYS, sub
