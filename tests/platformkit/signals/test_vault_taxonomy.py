"""tests.platformkit.signals.test_vault_taxonomy -- LANE C person-free loader contract.

Asserts:
  (1) the loader returns ONLY Archetype/DefensiveScheme NAMES, never a person token and
      never a KMeans cluster-id (the RAILS: the graph is PERSON-FREE + name-stable).
  (2) assert_person_free() is a real tripwire: it RAISES on a planted person token and on
      a planted KMeans cluster-id, and PASSES on clean concept names.
  (3) cold start: a missing vault / unknown sport yields EMPTY name lists (never raises).
  (4) names are deterministic + deduped (same call -> same tuple).

Per-file test only (full pytest freezes the box). ASCII; stdlib deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.signals import vault_taxonomy as VT  # noqa: E402


# ----------------------------------------------------------------- (2) tripwire
def test_assert_person_free_raises_on_person_token():
    with pytest.raises(ValueError):
        VT.assert_person_free(["3-and-D Wing", "player_name field"])
    with pytest.raises(ValueError):
        VT.assert_person_free(["something firstName here"])


def test_assert_person_free_raises_on_cluster_id():
    # a KMeans cluster-id re-numbers on refit -> a name keyed on it is not name-stable.
    for bad in ["cluster_07", "kmeans3 wing", "grp 4", "k_5 archetype", "c12"]:
        with pytest.raises(ValueError):
            VT.assert_person_free([bad])


def test_assert_person_free_passes_on_clean_names():
    VT.assert_person_free(["3-and-D Wing", "No-Middle Funnel Philosophy",
                           "Rim Running Big", "Help Rotation Shell System"])


# ----------------------------------------------------------------- (1) name-only
def test_load_taxonomy_is_person_free_and_name_only():
    tax = VT.load_taxonomy("nba")
    # The real vault is person-free; the loader's own tripwire already ran, but assert it.
    VT.assert_person_free(tax.archetypes)
    VT.assert_person_free(tax.schemes)
    for nm in list(tax.archetypes) + list(tax.schemes):
        assert isinstance(nm, str) and nm
        # no underscore-id residue / no leading index scaffolding leaked through
        assert not nm.startswith("_")


def test_load_taxonomy_synthetic_vault(tmp_path):
    # Build a tiny synthetic, person-free vault and assert names come back as expected.
    root = tmp_path / "_Organized"
    arch = root / "NBA" / "Archetypes"
    sch = root / "NBA" / "DefensiveSchemes"
    arch.mkdir(parents=True)
    sch.mkdir(parents=True)
    (arch / "stretch_big.md").write_text("# Stretch Big\n", encoding="ascii")
    (arch / "_Archetypes_Index.md").write_text("# index\n", encoding="ascii")  # skipped
    (sch / "drop_coverage_system.md").write_text("# Drop\n", encoding="ascii")
    tax = VT.load_taxonomy("nba", vault_root=root)
    assert "stretch big" in [a.lower() for a in tax.archetypes]
    assert not any(a.lower().startswith("_") for a in tax.archetypes)  # index skipped
    assert "drop coverage system" in [s.lower() for s in tax.schemes]


def test_cluster_id_stem_filtered_at_load(tmp_path):
    root = tmp_path / "_Organized"
    arch = root / "NBA" / "Archetypes"
    arch.mkdir(parents=True)
    (arch / "kmeans_3.md").write_text("# k3\n", encoding="ascii")  # cluster-id -> dropped
    (arch / "movement_shooter.md").write_text("# ms\n", encoding="ascii")
    tax = VT.load_taxonomy("nba", vault_root=root)
    names = [a.lower() for a in tax.archetypes]
    assert "movement shooter" in names
    assert not any("kmean" in n or "cluster" in n for n in names)


# ----------------------------------------------------------------- (3) cold start
def test_cold_start_unknown_sport_is_empty():
    tax = VT.load_taxonomy("quidditch")
    assert tax.archetypes == ()
    assert tax.schemes == ()
    assert tax.is_empty()


def test_cold_start_missing_vault_is_empty(tmp_path):
    tax = VT.load_taxonomy("nba", vault_root=tmp_path / "does_not_exist")
    assert tax.is_empty()


# ----------------------------------------------------------------- (4) deterministic
def test_load_taxonomy_is_deterministic():
    a = VT.load_taxonomy("nba")
    b = VT.load_taxonomy("nba")
    assert a.archetypes == b.archetypes
    assert a.schemes == b.schemes
