"""test_brain_vault — _Organized as a clean standalone Obsidian vault (hermetic)."""
from __future__ import annotations

import json

from scripts.platformkit.brain_vault import ensure_brain_graph_config


def test_seeds_valid_obsidian_vault(tmp_path):
    rep = ensure_brain_graph_config(tmp_path)
    obs = tmp_path / ".obsidian"
    assert obs.is_dir()
    for name in ("app.json", "appearance.json", "core-plugins.json", "graph.json"):
        assert (obs / name).exists()
        json.loads((obs / name).read_text(encoding="utf-8"))  # valid JSON
    assert "graph" in json.loads((obs / "core-plugins.json").read_text())


def test_graph_colorgroups_by_family_no_search_filter(tmp_path):
    ensure_brain_graph_config(tmp_path)
    g = json.loads((tmp_path / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
    # all content in _Organized is brain -> no scope filter needed
    assert g["search"] == ""
    queries = " ".join(cg["query"] for cg in g["colorGroups"])
    # coloured BY FAMILY via exact tags (collision-free) + legacy paths + hub/identity
    assert len(g["colorGroups"]) >= 20
    for token in ("tag:#tactics", "tag:#situational", "tag:#shotprofiles",
                  "path:Drivers", "file:_Identity", "_Concept_Map"):
        assert token in queries
    # exact tags avoid the substring clash a bare path: query would hit
    assert "tag:#defensiveschemes" in queries and "tag:#subarchetypes" in queries


def test_idempotent(tmp_path):
    ensure_brain_graph_config(tmp_path)
    first = (tmp_path / ".obsidian" / "graph.json").read_text(encoding="utf-8")
    ensure_brain_graph_config(tmp_path)
    second = (tmp_path / ".obsidian" / "graph.json").read_text(encoding="utf-8")
    assert first == second


def test_no_edge_or_person_tokens(tmp_path):
    ensure_brain_graph_config(tmp_path)
    blob = "".join((tmp_path / ".obsidian" / n).read_text(encoding="utf-8")
                   for n in ("graph.json", "app.json", "appearance.json", "core-plugins.json"))
    low = blob.lower()
    for bad in ("roi", "edge", "profit", "guaranteed", "lebron", "vs "):
        assert bad not in low
