"""Tests for scripts.platformkit.brain_consolidate — stub-family consolidation.

Hermetic fixture: n near-identical stub .md files + index hubs.
Tests: (a-g) existing; (h) link repair; (i) fact-cell cleanliness.
"""
from __future__ import annotations
import re
from pathlib import Path
from scripts.platformkit.brain_consolidate import (
    consolidate, _tokenize, _jaccard, _facts, _title, _clean_fact,
)

# ---------------------------------------------------------------------------
# Shared stub builders
# ---------------------------------------------------------------------------

def _make_stubs(cat_dir: Path, n: int = 10):
    cat_dir.mkdir(parents=True, exist_ok=True)
    stubs = []
    for i in range(n):
        content = (
            f"---\neditions: {i+1}\nspan: \"200{i}-2025\"\ntags:\n  - sport/test\n---\n\n"
            f"# Venue{i:02d}\n\n[[_Index|Test Index]]\n\n## Overview\n"
            f"- **Level:** ATP 500\n- **Surface:** Hard\n"
            f"- **Editions in corpus:** {i+1}\n"
            f"- **Corpus matches:** {(i+1)*100} (unique-fact-{i})\n"
            f"| All-court | 100% | ██████████ |\n---\n#sport/test\n"
        )
        p = cat_dir / f"Venue{i:02d}.md"; p.write_text(content, encoding="utf-8")
        stubs.append(p)
    idx = cat_dir / "_Index.md"
    idx.write_text("# Test Index\n\nHub note — must not be removed.\n", encoding="utf-8")
    return stubs, idx


def _run(tmp_path: Path, n: int = 10):
    cat_dir = tmp_path / "TestSport" / "Reference"
    stubs, idx = _make_stubs(cat_dir, n=n)
    rep = consolidate(organized_root=tmp_path, write=True,
                      injected_families=[{"sport": "TestSport", "category": "Reference",
                                          "name": "Venues", "members": stubs,
                                          "description": "Test venue stubs"}])
    return rep, cat_dir, stubs, idx


def _make_link_fixture(tmp_path: Path):
    cat_dir = tmp_path / "LinkSport" / "Places"; cat_dir.mkdir(parents=True, exist_ok=True)
    names = [f"Venue{i:02d}" for i in range(10)]
    stubs = []
    for name in names:
        p = cat_dir / f"{name}.md"
        p.write_text(f"---\neditions: 5\ntags: [stub]\n---\n# {name}\n"
                     f"- **Editions:** 5\n- **Corpus matches:** 100\n", encoding="utf-8")
        stubs.append(p)
    # Four wikilink forms + one non-stub link + remaining stubs
    lines = (
        "# Sport Index\n\n"
        "- [[Places/Venue00.md|Venue00]]\n"   # form 1: path + .md + alias
        "- [[Places/Venue01|Venue01]]\n"       # form 2: path + alias
        "- [[Venue02]]\n"                      # form 3: bare stem
        "- [[Venue03.md]]\n"                   # form 4: stem.md
        "- [[_Catalog|Catalog]]\n"             # non-stub — must survive
        + "".join(f"- [[{n}]]\n" for n in names[4:])
    )
    idx = tmp_path / "LinkSport" / "_Index.md"
    idx.write_text(lines, encoding="utf-8")
    return tmp_path / "LinkSport", cat_dir, stubs, idx


def _make_dirty_stubs(cat_dir: Path, n: int = 10):
    cat_dir.mkdir(parents=True, exist_ok=True)
    stubs = []
    for i in range(n):
        content = (
            f"---\nlevel_label: ATP 500\neditions: {i+1}\nbest_of: 3\ntags:[stub]\n---\n\n"
            f"# Dirty{i:02d}\n\n- **Level:** ATP 500 (A)\n"
            f"- **Editions in corpus:** {i+1} (201{i}-2025)\n"
            f"- **Typical format:** Best of 3\n"
            f"- **Total corpus matches:** {(i+1)*50}\n"
            f"| Surface-specialist | 0% | ░░░░░░░░░░ |\n"
            f"| All-court | 100% | ██████████ |\n"
            f"- unique-dirty-{i}\n"
        )
        p = cat_dir / f"Dirty{i:02d}.md"; p.write_text(content, encoding="utf-8")
        stubs.append(p)
    return stubs

# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def test_tokenize_returns_frozenset():
    t = _tokenize("Hello World 2025")
    assert isinstance(t, frozenset) and "hello" in t and "2025" in t

def test_jaccard_identical():
    a = frozenset(["x","y","z"]); assert _jaccard(a, a) == 1.0

def test_jaccard_disjoint():
    assert _jaccard(frozenset(["a"]), frozenset(["b"])) == 0.0

def test_jaccard_partial():
    j = _jaccard(frozenset(["a","b","c"]), frozenset(["a","b","d"]))
    assert 0.0 < j < 1.0

def test_title_extraction():
    assert _title("---\ntags:[t]\n---\n\n# My Venue\n\nBody.\n", "fb") == "My Venue"

def test_title_fallback():
    assert _title("no heading", "fallback_stem") == "fallback_stem"

def test_facts_extracts_numeric_lines():
    txt = "---\neditions:7\ntags:[t]\n---\n\n- **Corpus matches:** 500\n- Rate: 55%\n"
    assert any("500" in f or "55" in f for f in _facts(txt, "Venue"))

def test_clean_fact_strips_bullets_and_bold():
    assert _clean_fact("- **Level:** ATP 500") == "Level: ATP 500"

def test_clean_fact_drops_parenthetical_code():
    assert _clean_fact("- **Level:** ATP 500 (A)") == "Level: ATP 500"

def test_clean_fact_drops_histogram_only():
    assert _clean_fact("/ Surface-specialist / 0% / ░░░░░░░░░░ /") is None

def test_facts_deduplicates_same_key():
    txt = ("---\nlevel_label: ATP 500\neditions: 5\ntags:[t]\n---\n\n"
           "- **Level:** ATP 500 (A)\n- **Editions in corpus:** 5 (2020-2025)\n")
    count = sum(1 for f in _facts(txt, "Venue") if f.lower().startswith("level"))
    assert count <= 1, f"Duplicate 'Level' key: {_facts(txt, 'Venue')}"

def test_facts_no_histogram_glyphs():
    txt = ("---\neditions:3\ntags:[t]\n---\n\n| All-court | 100% | ██████████ |\n"
           "| Surface-specialist | 0% | ░░░░░░░░░░ |\n- **Editions:** 3 (2022-2025)\n")
    joined = " ".join(_facts(txt, "Venue"))
    assert "░" not in joined and "█" not in joined

def test_facts_retains_distinct_values():
    txt = ("---\neditions:11\nspan:\"2015-2025\"\nbest_of:3\ntags:[t]\n---\n\n"
           "- **Level:** ATP 500 (A)\n- **Editions in corpus:** 11 (2015-2025)\n"
           "- **Typical format:** Best of 3\n- **Total corpus matches:** 341\n")
    joined = " ".join(_facts(txt, "Venue"))
    assert "341" in joined and "11" in joined

# ---------------------------------------------------------------------------
# Integration: basic consolidation
# ---------------------------------------------------------------------------

def test_consolidated_file_created(tmp_path):
    rep, cat_dir, _, _ = _run(tmp_path)
    assert rep["n_families"] == 1 and rep["n_notes_merged"] == 10
    assert (cat_dir / "_Venues_Consolidated.md").exists()

def test_consolidated_contains_every_unique_fact(tmp_path):
    _, cat_dir, _, _ = _run(tmp_path)
    text = (cat_dir / "_Venues_Consolidated.md").read_text(encoding="utf-8")
    for i in range(10):
        assert f"unique-fact-{i}" in text

def test_stub_files_removed(tmp_path):
    _, cat_dir, stubs, _ = _run(tmp_path)
    assert not any(p.exists() for p in stubs)

def test_index_not_touched(tmp_path):
    _, cat_dir, _, idx = _run(tmp_path)
    assert idx.exists() and "Hub note" in idx.read_text(encoding="utf-8")

def test_output_person_free(tmp_path):
    _, cat_dir, _, _ = _run(tmp_path)
    text = (cat_dir / "_Venues_Consolidated.md").read_text(encoding="utf-8")
    allowed = {"Distinguishing Facts", "Fact Table", "See Also", "Intelligence Map",
               "Entry Distinguishing", "All Court", "Venues Consolidated",
               "Test Index", "Sport Index"}
    flagged = [n for n in re.findall(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text)
               if n not in allowed]
    assert not flagged, f"Person-like names: {flagged}"

def test_honest_banner_present(tmp_path):
    _, cat_dir, _, _ = _run(tmp_path)
    text = (cat_dir / "_Venues_Consolidated.md").read_text(encoding="utf-8").lower()
    assert "no edge claimed" in text and "markets efficient" in text

def test_idempotent_second_run_stable(tmp_path):
    rep, cat_dir, stubs, idx = _run(tmp_path)
    con = cat_dir / "_Venues_Consolidated.md"
    first_text = con.read_text(encoding="utf-8")
    rep2 = consolidate(organized_root=tmp_path, write=True,
                       injected_families=[{"sport": "TestSport", "category": "Reference",
                                           "name": "Venues", "members": [],
                                           "description": "Test venue stubs"}])
    assert rep2["n_notes_merged"] == 0 and rep2["n_files_removed"] == 0
    assert con.read_text(encoding="utf-8") == first_text and idx.exists()

def test_return_dict_keys(tmp_path):
    rep, _, _, _ = _run(tmp_path)
    assert set(rep) >= {"n_families","n_notes_merged","n_files_removed","by_sport","_note"}
    assert "no edge claimed" in rep["_note"].lower()

# ---------------------------------------------------------------------------
# NEW — link repair
# ---------------------------------------------------------------------------

def test_link_repair_no_dangling_stubs(tmp_path):
    sport_dir, cat_dir, stubs, idx = _make_link_fixture(tmp_path)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "LinkSport", "category": "Places",
                                    "name": "Venues", "members": stubs,
                                    "description": "Link repair stubs"}])
    text = idx.read_text(encoding="utf-8")
    for stem in {p.stem for p in stubs}:
        hit = re.search(
            r"\[\[(?:[^\]|]*/)?{}\b(?:\.md)?(?:\|[^\]]+)?\]\]".format(re.escape(stem)),
            text, re.IGNORECASE)
        assert not hit, f"Dangling link to '{stem}': {hit.group()!r}"

def test_link_repair_consolidated_linked(tmp_path):
    sport_dir, cat_dir, stubs, idx = _make_link_fixture(tmp_path)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "LinkSport", "category": "Places",
                                    "name": "Venues", "members": stubs,
                                    "description": "Link repair stubs"}])
    assert re.search(r"Venues.Consolidated", idx.read_text(encoding="utf-8"), re.IGNORECASE)

def test_link_repair_deduplicates_consecutive(tmp_path):
    sport_dir, cat_dir, stubs, idx = _make_link_fixture(tmp_path)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "LinkSport", "category": "Places",
                                    "name": "Venues", "members": stubs,
                                    "description": "Link repair stubs"}])
    hits = re.findall(r"Venues.Consolidated", idx.read_text(encoding="utf-8"), re.IGNORECASE)
    assert len(hits) < len(stubs), f"Dedup failed: {len(hits)} links for {len(stubs)} stubs"

def test_link_repair_preserves_non_stub_links(tmp_path):
    sport_dir, cat_dir, stubs, idx = _make_link_fixture(tmp_path)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "LinkSport", "category": "Places",
                                    "name": "Venues", "members": stubs,
                                    "description": "Link repair stubs"}])
    assert "[[_Catalog|Catalog]]" in idx.read_text(encoding="utf-8")

def test_link_repair_idempotent(tmp_path):
    sport_dir, cat_dir, stubs, idx = _make_link_fixture(tmp_path)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "LinkSport", "category": "Places",
                                    "name": "Venues", "members": stubs,
                                    "description": "Link repair stubs"}])
    after_first = idx.read_text(encoding="utf-8")
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "LinkSport", "category": "Places",
                                    "name": "Venues", "members": [], "description": ""}])
    assert idx.read_text(encoding="utf-8") == after_first

# ---------------------------------------------------------------------------
# NEW — fact-cell cleanliness
# ---------------------------------------------------------------------------

def test_fact_cell_no_histogram_glyphs(tmp_path):
    cat_dir = tmp_path / "CleanSport" / "Reference"
    stubs = _make_dirty_stubs(cat_dir)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "CleanSport", "category": "Reference",
                                    "name": "Dirty", "members": stubs,
                                    "description": "Glyph test"}])
    text = (cat_dir / "_Dirty_Consolidated.md").read_text(encoding="utf-8")
    assert "░" not in text and "█" not in text

def test_fact_cell_no_duplicate_key(tmp_path):
    cat_dir = tmp_path / "CleanSport2" / "Reference"
    stubs = _make_dirty_stubs(cat_dir)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "CleanSport2", "category": "Reference",
                                    "name": "Dirty", "members": stubs,
                                    "description": "Dedup test"}])
    text = (cat_dir / "_Dirty_Consolidated.md").read_text(encoding="utf-8")
    for row in [ln for ln in text.splitlines() if ln.startswith("| Dirty")]:
        cell = row.split("|")[2] if row.count("|") >= 2 else ""
        keys = [f[:f.find(":")].strip().lower() for f in cell.split(";")
                if f.find(":") != -1]
        dupes = [k for k in keys if keys.count(k) > 1]
        assert not dupes, f"Duplicate keys {dupes} in: {row}"

def test_fact_cell_retains_distinct_values(tmp_path):
    cat_dir = tmp_path / "CleanSport3" / "Reference"
    stubs = _make_dirty_stubs(cat_dir)
    consolidate(organized_root=tmp_path, write=True,
                injected_families=[{"sport": "CleanSport3", "category": "Reference",
                                    "name": "Dirty", "members": stubs,
                                    "description": "Retain test"}])
    text = (cat_dir / "_Dirty_Consolidated.md").read_text(encoding="utf-8")
    for i in range(len(stubs)):
        assert f"unique-dirty-{i}" in text, f"unique-dirty-{i} lost"
