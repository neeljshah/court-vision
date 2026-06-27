"""
test_brain_graph_fixes.py -- hermetic tests for the Obsidian graph-navigability
generators: brain_fix_relative_links, brain_system_map, brain_folder_indexes.
All use a synthetic tmp_path vault; the live vault is never touched.
"""
from __future__ import annotations
from pathlib import Path

from scripts.platformkit.brain_fix_relative_links import normalize_vault
from scripts.platformkit.brain_system_map import build_system_map
from scripts.platformkit.brain_folder_indexes import build_folder_indexes


# -- brain_fix_relative_links -------------------------------------------------

def test_relative_link_rewritten_to_vault_relative(tmp_path: Path):
    (tmp_path / "_Organized/NBA/Schemes").mkdir(parents=True)
    (tmp_path / "_Organized/NBA/Schemes/balanced.md").write_text("# balanced\n", encoding="utf-8")
    arch = tmp_path / "_Organized/NBA/Archetypes"
    arch.mkdir(parents=True)
    f = arch / "wing.md"
    f.write_text("see [[../Schemes/balanced.md|balanced]]\n", encoding="utf-8")
    normalize_vault(tmp_path, write=True)
    txt = f.read_text(encoding="utf-8")
    assert "../" not in txt
    assert "[[_Organized/NBA/Schemes/balanced|balanced]]" in txt


def test_stale_index_remaps_to_digest(tmp_path: Path):
    nba = tmp_path / "_Organized/NBA"
    (nba / "Archetypes").mkdir(parents=True)
    (nba / "_Digest.md").write_text("# digest\n", encoding="utf-8")
    f = nba / "Archetypes/w.md"
    f.write_text("[[../_Index.md|_Index]]\n", encoding="utf-8")
    normalize_vault(tmp_path, write=True)
    assert "_Organized/NBA/_Digest" in f.read_text(encoding="utf-8")


def test_clean_link_untouched(tmp_path: Path):
    (tmp_path / "_Organized/NBA").mkdir(parents=True)
    f = tmp_path / "_Organized/NBA/a.md"
    f.write_text("[[_WhatWins]] and `[[../keep/me.md]]`\n", encoding="utf-8")
    normalize_vault(tmp_path, write=True)
    txt = f.read_text(encoding="utf-8")
    assert "[[_WhatWins]]" in txt          # already valid, untouched
    assert "`[[../keep/me.md]]`" in txt    # inside code span, untouched


# -- brain_system_map ---------------------------------------------------------

def test_system_map_emits_all_notes(tmp_path: Path):
    r = build_system_map(tmp_path, write=True)
    assert r["written"] == r["notes"] >= 30
    idx = (tmp_path / "_System/_System_Index.md").read_text(encoding="utf-8")
    assert "_System/01_Data" in idx and "_System/05_Predictions" in idx


def test_system_component_links_to_stage_and_flows(tmp_path: Path):
    build_system_map(tmp_path, write=True)
    fe = tmp_path / "_System/02_Signals/feature_engineering.md"
    assert fe.exists()
    txt = fe.read_text(encoding="utf-8")
    assert "_System/02_Signals" in txt                      # back to stage
    assert "_System/03_Models/win_probability" in txt       # flows downstream


def test_system_map_no_edge_claim(tmp_path: Path):
    build_system_map(tmp_path, write=True)
    txt = (tmp_path / "_System/06_Execution/betting_portfolio.md").read_text(encoding="utf-8").lower()
    # "edge" may appear only in a denial.
    assert "edge" not in txt or "not" in txt


# -- brain_folder_indexes -----------------------------------------------------

def test_folder_index_links_notes_and_hub(tmp_path: Path):
    cf = tmp_path / "_Organized/NBA/ClosingExecution"
    cf.mkdir(parents=True)
    (tmp_path / "_Organized/NBA/_Digest.md").write_text("# d\n", encoding="utf-8")
    (cf / "a.md").write_text("# a\n", encoding="utf-8")
    (cf / "b.md").write_text("# b\n", encoding="utf-8")
    build_folder_indexes(tmp_path, write=True)
    idx = cf / "_ClosingExecution_Index.md"
    assert idx.exists()
    txt = idx.read_text(encoding="utf-8")
    assert "_Organized/NBA/ClosingExecution/a" in txt   # links folder notes
    assert "_Organized/NBA/_Digest" in txt              # links UP to sport hub
    assert (tmp_path / "_Organized/NBA/_Index.md").exists()  # sport home created


def test_folder_index_idempotent(tmp_path: Path):
    cf = tmp_path / "_Organized/MLB/Drivers"
    cf.mkdir(parents=True)
    (tmp_path / "_Organized/MLB/_Digest.md").write_text("# d\n", encoding="utf-8")
    (cf / "x.md").write_text("# x\n", encoding="utf-8")
    build_folder_indexes(tmp_path, write=True)
    first = (cf / "_Drivers_Index.md").read_bytes()
    build_folder_indexes(tmp_path, write=True)
    assert (cf / "_Drivers_Index.md").read_bytes() == first
