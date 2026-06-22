"""test_brain_vault — _Organized as a clean standalone Obsidian vault (hermetic)."""
from __future__ import annotations

import json

from scripts.platformkit.brain_vault import ensure_brain_graph_config


def test_seeds_valid_obsidian_vault(tmp_path):
    rep = ensure_brain_graph_config(tmp_path)
    obs = tmp_path / ".obsidian"
    assert obs.is_dir()
    for name in ("app.json", "appearance.json", "core-plugins.json", "graph.json",
                 "workspace.json"):
        assert (obs / name).exists()
        json.loads((obs / name).read_text(encoding="utf-8"))  # valid JSON
    assert "graph" in json.loads((obs / "core-plugins.json").read_text())


def test_workspace_lands_on_real_hub_no_graph(tmp_path):
    """Opens fast: the vault lands on the REAL in-vault hub (_Index/_Brain.md) as
    markdown with NO graph pane -- so a ~5k-node brain opens instantly. The graph is
    the slow part and stays OFF until explicitly opened."""
    ensure_brain_graph_config(tmp_path)
    ws = json.loads((tmp_path / ".obsidian" / "workspace.json").read_text(encoding="utf-8"))
    # main area opens a markdown leaf on the real hub that exists INSIDE _Organized
    # (NOT the parent vault/_Index.md, which is outside this vault).
    md = ws["main"]["children"][0]["children"][0]
    assert md["state"]["type"] == "markdown"
    assert md["state"]["state"]["file"] == "_Index/_Brain.md"
    assert ws["lastOpenFiles"] == ["_Index/_Brain.md"]
    # NO graph of any kind auto-opens (global OR local) -> guaranteed fast open.
    blob = json.dumps(ws)
    assert '"type": "graph"' not in blob
    assert '"type": "localgraph"' not in blob
    # preview-mode landing so it renders read-only + instant.
    assert json.loads((tmp_path / ".obsidian" / "app.json").read_text())[
        "defaultViewMode"] == "preview"


def test_graph_colorgroups_by_family_no_search_filter(tmp_path):
    ensure_brain_graph_config(tmp_path)
    g = json.loads((tmp_path / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
    # PERF: the global graph defaults to the HUB BACKBONE (root _Index MOCs + per-sport top
    # hubs) so it opens instantly instead of rendering ~5k nodes. Nothing is removed -- every
    # note is still reachable by link; clearing the search box restores the full graph.
    assert g["search"], "expected a default backbone scope filter, not empty"
    for token in ("_Index/", "NBA/_", "MLB/_", "Soccer/_", "Tennis/_"):
        assert token in g["search"]
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
