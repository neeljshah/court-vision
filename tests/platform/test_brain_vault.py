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


def test_graph_has_brain_colorgroups_no_search_filter(tmp_path):
    ensure_brain_graph_config(tmp_path)
    g = json.loads((tmp_path / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
    # all content in _Organized is brain -> no scope filter needed
    assert g["search"] == ""
    queries = " ".join(cg["query"] for cg in g["colorGroups"])
    for token in ("NBA", "MLB", "Soccer", "Tennis", "Drivers", "Mechanisms", "_Identity"):
        assert token in queries


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
