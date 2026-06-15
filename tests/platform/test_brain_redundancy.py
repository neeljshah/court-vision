"""Tests for scripts.platformkit.brain_redundancy — brain density / redundancy audit.

Hermetic fixture with:
  - NBA/Archetypes/ : two near-identical notes (Jaccard >=0.85) + one thin note (<450B)
  - NBA/Drivers/   : one orphan (no inbound, no outbound wikilinks)
  - MLB/Drivers/   : minimal valid notes (no issues)

The tests assert:
  (a) thin nodes correctly counted (non-hub notes < 450 B)
  (b) near-duplicate pair detected at Jaccard >= 0.85
  (c) orphan detected (zero links in AND out)
  (d) _Redundancy_Report.md written under _Index/
  (e) report is person-free (no edge claims)
  (f) idempotent (second run produces identical file)
  (g) totals aggregate correctly across sports
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.platformkit.brain_redundancy import (
    build_redundancy,
    _tokens,
    _jaccard,
    _outlinks,
    _thin_nodes,
    _orphan_nodes,
    _dup_pairs,
)

# ---------------------------------------------------------------------------
# Helpers to build the tmp fixture tree
# ---------------------------------------------------------------------------

_LONG_BODY = " ".join([
    "The team deploys a high-pace transition attack built around perimeter spacing "
    "and pick-and-roll ball-screen actions. The primary engine is the drive-and-kick "
    "rotation creating open corner-three opportunities. Defensive identity emphasises "
    "switching on ball-screens to limit roll-man advantages. Turnover rate is below "
    "league average. Rebounding is assisted by strong boxing-out discipline."
] * 6)  # ~450+ characters to keep this note non-thin


def _make_tree(root: Path) -> Path:
    """Create a minimal vault/_Organized tree under root and return organized_root."""
    org = root / "vault" / "_Organized"

    # NBA/Archetypes — two near-duplicate notes + one thin note
    arch = org / "NBA" / "Archetypes"
    arch.mkdir(parents=True, exist_ok=True)

    note_a = arch / "Scoring_Guard_A.md"
    note_a.write_text(
        "---\ntags: [nba, archetype]\n---\n# Scoring Guard A\n\n"
        + _LONG_BODY, encoding="utf-8"
    )
    # Near-duplicate: same body with a trivial suffix -> Jaccard >= 0.85
    note_b = arch / "Scoring_Guard_B.md"
    note_b.write_text(
        "---\ntags: [nba, archetype]\n---\n# Scoring Guard B\n\n"
        + _LONG_BODY + " alternate.", encoding="utf-8"
    )
    # Thin note (< 450 B, non-hub): should be flagged
    thin = arch / "Empty_Stub.md"
    thin.write_text("# Stub\n\nTBD.", encoding="utf-8")

    # NBA/_Archetypes_Index.md — hub (_-prefixed): must NOT appear in thin list
    hub = arch / "_Archetypes_Index.md"
    hub.write_text("# Index\n\n- [[Scoring_Guard_A]]\n- [[Scoring_Guard_B]]\n",
                   encoding="utf-8")

    # NBA/Drivers — one orphan (no links in either direction, non-hub)
    drivers = org / "NBA" / "Drivers"
    drivers.mkdir(parents=True, exist_ok=True)
    orphan = drivers / "Isolated_Driver.md"
    orphan.write_text(
        "# Isolated Driver\n\nThis note mentions nothing and is mentioned by nobody.",
        encoding="utf-8"
    )

    # MLB/Drivers — healthy notes so the sport appears without errors
    mlb = org / "MLB" / "Drivers"
    mlb.mkdir(parents=True, exist_ok=True)
    (mlb / "Win_Rate_Driver.md").write_text(
        "# Win Rate Driver\n\n" + _LONG_BODY + " [[_Index]]", encoding="utf-8"
    )

    return org


# ---------------------------------------------------------------------------
# Unit tests for pure helpers
# ---------------------------------------------------------------------------

def test_tokens_returns_frozenset_of_lowercase_words():
    t = _tokens("Hello World 123")
    assert isinstance(t, frozenset)
    assert "hello" in t and "world" in t and "123" in t


def test_jaccard_identical_is_one():
    a = frozenset(["x", "y", "z"])
    assert _jaccard(a, a) == 1.0


def test_jaccard_disjoint_is_zero():
    a = frozenset(["x"])
    b = frozenset(["y"])
    assert _jaccard(a, b) == 0.0


def test_jaccard_partial_overlap():
    a = frozenset(["a", "b", "c"])
    b = frozenset(["b", "c", "d"])
    # inter=2 union=4 -> 0.5
    assert abs(_jaccard(a, b) - 0.5) < 1e-9


def test_outlinks_extracts_wikilink_targets():
    text = "See [[Foo]] and [[Bar|alias]] and [[Baz#section]]."
    links = _outlinks(text)
    assert "Foo" in links
    assert "Bar" in links
    assert "Baz" in links


def test_thin_nodes_excludes_hub_prefix(tmp_path):
    """_-prefixed notes must never appear in the thin list."""
    hub = tmp_path / "_Index.md"
    hub.write_text("x", encoding="utf-8")
    small = tmp_path / "Real.md"
    small.write_text("x", encoding="utf-8")
    notes = [
        {"path": hub, "name": "_Index.md", "size": 1, "tokens": frozenset(),
         "outlinks": [], "category": "."},
        {"path": small, "name": "Real.md", "size": 1, "tokens": frozenset(),
         "outlinks": [], "category": "."},
    ]
    thin = _thin_nodes(notes)
    assert all(not n["name"].startswith("_") for n in thin)
    assert any(n["name"] == "Real.md" for n in thin)


def test_orphan_nodes_excludes_hub_prefix(tmp_path):
    """_-prefixed notes must never appear in the orphan list."""
    hub_path = tmp_path / "_Hub.md"
    hub_path.write_text("x", encoding="utf-8")
    real_path = tmp_path / "Solo.md"
    real_path.write_text("x", encoding="utf-8")
    notes = [
        {"path": hub_path, "name": "_Hub.md", "size": 1, "tokens": frozenset(),
         "outlinks": [], "category": "."},
        {"path": real_path, "name": "Solo.md", "size": 1, "tokens": frozenset(),
         "outlinks": [], "category": "."},
    ]
    orphans = _orphan_nodes(notes, inlinks={})
    assert all(not n["name"].startswith("_") for n in orphans)
    assert any(n["name"] == "Solo.md" for n in orphans)


def test_dup_pairs_detects_near_identical():
    big_tok = frozenset(["a"] * 50 + list("bcdefghijklmnopqrstuvwxyz"))
    notes = [
        {"name": "A.md", "tokens": big_tok, "path": Path("A.md")},
        {"name": "B.md", "tokens": big_tok, "path": Path("B.md")},
        {"name": "C.md", "tokens": frozenset(["z"]), "path": Path("C.md")},
    ]
    pairs = _dup_pairs(notes)
    names = {(p[0]["name"], p[1]["name"]) for p in pairs}
    assert ("A.md", "B.md") in names


# ---------------------------------------------------------------------------
# Integration tests via build_redundancy
# ---------------------------------------------------------------------------

def test_build_redundancy_detects_thin_node(tmp_path):
    org = _make_tree(tmp_path)
    rep = build_redundancy(organized_root=org, write=False)
    nba = rep["by_sport"]["NBA"]
    thin_names = [t["name"] for t in nba["thin"]]
    assert "Empty_Stub.md" in thin_names, f"expected Empty_Stub.md in thin; got {thin_names}"


def test_build_redundancy_hub_not_in_thin(tmp_path):
    org = _make_tree(tmp_path)
    rep = build_redundancy(organized_root=org, write=False)
    nba = rep["by_sport"]["NBA"]
    thin_names = [t["name"] for t in nba["thin"]]
    assert "_Archetypes_Index.md" not in thin_names


def test_build_redundancy_detects_dup_pair(tmp_path):
    org = _make_tree(tmp_path)
    rep = build_redundancy(organized_root=org, write=False)
    nba = rep["by_sport"]["NBA"]
    assert len(nba["dup_pairs"]) >= 1, "expected at least one dup pair"
    pair_names = {(d["a"], d["b"]) for d in nba["dup_pairs"]}
    found = any("Scoring_Guard" in a and "Scoring_Guard" in b for a, b in pair_names)
    assert found, f"Scoring_Guard pair not found; got {pair_names}"
    for d in nba["dup_pairs"]:
        assert d["jaccard"] >= 0.85


def test_build_redundancy_detects_orphan(tmp_path):
    org = _make_tree(tmp_path)
    rep = build_redundancy(organized_root=org, write=False)
    nba = rep["by_sport"]["NBA"]
    orphan_names = [o["name"] for o in nba["orphans"]]
    assert "Isolated_Driver.md" in orphan_names, (
        f"expected Isolated_Driver.md in orphans; got {orphan_names}"
    )


def test_build_redundancy_writes_report_under_index(tmp_path):
    org = _make_tree(tmp_path)
    build_redundancy(organized_root=org, write=True)
    report = org / "_Index" / "_Redundancy_Report.md"
    assert report.is_file(), f"report not found at {report}"
    text = report.read_text(encoding="utf-8")
    assert len(text) > 100


def test_report_contains_sport_summary_table(tmp_path):
    org = _make_tree(tmp_path)
    build_redundancy(organized_root=org, write=True)
    text = (org / "_Index" / "_Redundancy_Report.md").read_text(encoding="utf-8")
    assert "NBA" in text
    assert "MLB" in text
    # table header
    assert "Thin" in text or "thin" in text.lower()
    assert "Dup" in text or "dup" in text.lower()
    assert "Orphan" in text or "orphan" in text.lower()


def test_report_is_person_free_no_edge_claim(tmp_path):
    org = _make_tree(tmp_path)
    build_redundancy(organized_root=org, write=True)
    text = (org / "_Index" / "_Redundancy_Report.md").read_text(encoding="utf-8")
    assert "no edge claimed" in text.lower()
    assert "markets efficient" in text.lower()
    # no edge-claim patterns
    forbidden = [r"\+\d+\.?\d*\s*%\s*(ROI|edge|profit)",
                 r"beats\s+the\s+market", r"guaranteed"]
    for pat in forbidden:
        assert not re.search(pat, text, re.IGNORECASE), f"forbidden pattern found: {pat}"


def test_build_redundancy_idempotent(tmp_path):
    org = _make_tree(tmp_path)
    build_redundancy(organized_root=org, write=True)
    first = (org / "_Index" / "_Redundancy_Report.md").read_text(encoding="utf-8")
    build_redundancy(organized_root=org, write=True)
    second = (org / "_Index" / "_Redundancy_Report.md").read_text(encoding="utf-8")
    assert first == second


def test_totals_aggregate_across_sports(tmp_path):
    org = _make_tree(tmp_path)
    rep = build_redundancy(organized_root=org, write=False)
    t = rep["totals"]
    expected_notes = sum(
        v.get("n_notes", 0) for v in rep["by_sport"].values()
    )
    assert t["n_notes"] == expected_notes
    assert t["n_notes"] > 0


def test_note_key_present(tmp_path):
    org = _make_tree(tmp_path)
    rep = build_redundancy(organized_root=org, write=False)
    assert "no edge claimed" in rep["_note"].lower()


def test_missing_organized_root_returns_empty(tmp_path):
    """Graceful handling when organized_root doesn't exist."""
    absent = tmp_path / "nonexistent"
    rep = build_redundancy(organized_root=absent, write=False)
    assert rep["totals"]["n_notes"] == 0
    assert "no edge claimed" in rep["_note"].lower()
