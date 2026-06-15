"""Tests for brain_concept_map — per-sport concept-map hubs + sport-index patch."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.brain_concept_map import build_concept_map  # noqa: E402


def _concept_family(root: Path, sport: str, family: str, slugs):
    """Write a concept-family dir: an _Index.md tagged 'concept' + node files."""
    fam = root / sport / family
    fam.mkdir(parents=True, exist_ok=True)
    lines = [f"- [[{s}|{s.title()}]]" for s in slugs]
    (fam / "_Index.md").write_text(
        f"---\ntags: [organized, {sport.lower()}, {family.lower()}, concept, person-free]\n---\n"
        f"# {sport} - {family}\n\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    for s in slugs:
        (fam / f"{s}.md").write_text(
            f"---\ntags: [concept]\n---\n# {s.title()}\nbody\n", encoding="utf-8")


def _legacy_category(root: Path, sport: str, name: str):
    """A NON-concept category index (no 'concept' tag) — must be ignored."""
    d = root / sport / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "_Index.md").write_text(
        f"---\ntags: [organized, {sport.lower()}, index]\n---\n# {name}\n- [[x|X]]\n",
        encoding="utf-8")


def _sport_index(root: Path, sport: str):
    (root / sport).mkdir(parents=True, exist_ok=True)
    (root / sport / "_Index.md").write_text(
        f"---\ntags: [organized, index]\n---\n# {sport} — Index\n\n## Teams\n- [[a|A]]\n",
        encoding="utf-8")


def _build_tree(root: Path):
    _sport_index(root, "NBA")
    _concept_family(root, "NBA", "Situational", ["rest_advantage", "back_to_back", "clutch"])
    _concept_family(root, "NBA", "Tactics", ["drop_coverage", "switch_everything"])
    _legacy_category(root, "NBA", "Archetypes")
    _sport_index(root, "MLB")
    _concept_family(root, "MLB", "Mechanisms", ["run_prevention"])


def test_writes_concept_map_per_sport(tmp_path):
    _build_tree(tmp_path)
    rep = build_concept_map(organized_root=tmp_path, write=True)
    assert rep["n_maps"] == 2                       # NBA + MLB
    assert (tmp_path / "NBA" / "_Concept_Map.md").is_file()
    assert (tmp_path / "MLB" / "_Concept_Map.md").is_file()


def test_map_links_only_concept_families(tmp_path):
    _build_tree(tmp_path)
    build_concept_map(organized_root=tmp_path, write=True)
    nba_map = (tmp_path / "NBA" / "_Concept_Map.md").read_text(encoding="utf-8")
    assert "[[Situational/_Index|Situational]]" in nba_map
    assert "[[Tactics/_Index|Tactics]]" in nba_map
    assert "Archetypes" not in nba_map              # legacy category ignored


def test_node_counts_in_map(tmp_path):
    _build_tree(tmp_path)
    rep = build_concept_map(organized_root=tmp_path, write=True)
    assert rep["by_sport"]["NBA"] == 5              # 3 situational + 2 tactics
    assert rep["by_sport"]["MLB"] == 1
    nba_map = (tmp_path / "NBA" / "_Concept_Map.md").read_text(encoding="utf-8")
    assert "3 node(s)" in nba_map and "2 node(s)" in nba_map


def test_patches_sport_index_with_link(tmp_path):
    _build_tree(tmp_path)
    rep = build_concept_map(organized_root=tmp_path, write=True)
    assert "NBA" in rep["patched"]
    idx = (tmp_path / "NBA" / "_Index.md").read_text(encoding="utf-8")
    assert "## Concept Graph" in idx
    assert "[[_Concept_Map|Concept Map]]" in idx
    assert "## Teams" in idx                        # original content preserved


def test_idempotent_patch(tmp_path):
    _build_tree(tmp_path)
    build_concept_map(organized_root=tmp_path, write=True)
    first = (tmp_path / "NBA" / "_Index.md").read_text(encoding="utf-8")
    rep2 = build_concept_map(organized_root=tmp_path, write=True)
    second = (tmp_path / "NBA" / "_Index.md").read_text(encoding="utf-8")
    assert first == second                          # no double-patch
    assert "NBA" not in rep2["patched"]             # already patched -> not re-reported
    assert first.count("## Concept Graph") == 1


def test_banner_and_person_free(tmp_path):
    _build_tree(tmp_path)
    build_concept_map(organized_root=tmp_path, write=True)
    txt = (tmp_path / "NBA" / "_Concept_Map.md").read_text(encoding="utf-8")
    assert "markets efficient" in txt and "no edge" in txt.lower()
    assert " vs " not in txt


def test_no_organized_root(tmp_path):
    missing = tmp_path / "nope"
    rep = build_concept_map(organized_root=missing, write=True)
    assert rep["n_maps"] == 0


def test_write_false_writes_nothing(tmp_path):
    _build_tree(tmp_path)
    build_concept_map(organized_root=tmp_path, write=False)
    assert not (tmp_path / "NBA" / "_Concept_Map.md").exists()
    idx = (tmp_path / "NBA" / "_Index.md").read_text(encoding="utf-8")
    assert "## Concept Graph" not in idx
