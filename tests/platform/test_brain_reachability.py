"""
test_brain_reachability.py -- hermetic tests for the brain graph reachability
analyzer + the finalize entrypoint. All use a synthetic tmp_path vault; the live
vault is never touched.
"""
from __future__ import annotations
from pathlib import Path

from scripts.platformkit.brain_reachability import analyze, Resolver, extract_links
from scripts.platformkit.brain_graph_finalize import finalize


def _note(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _mini_vault(root: Path) -> None:
    """Master index -> NBA index -> one folder index -> two notes."""
    _note(root / "_Index.md",
          "# Home\n\n- [[_Organized/NBA/_Index|NBA]]\n")
    _note(root / "_Organized/NBA/_Index.md",
          "# NBA\n\n- [[_Organized/NBA/Drivers/_Drivers_Index|Drivers]]\n")
    _note(root / "_Organized/NBA/Drivers/_Drivers_Index.md",
          "# Drivers\n\n- [[_Organized/NBA/Drivers/pace|pace]]\n"
          "- [[_Organized/NBA/Drivers/spacing|spacing]]\n")
    _note(root / "_Organized/NBA/Drivers/pace.md", "# pace\n")
    _note(root / "_Organized/NBA/Drivers/spacing.md", "# spacing\n")


# -- analyzer -----------------------------------------------------------------

def test_all_reachable_when_fully_linked(tmp_path: Path):
    _mini_vault(tmp_path)
    r = analyze(tmp_path)
    assert r["total"] == 5
    assert r["reachable"] == 5
    assert r["unreachable"] == 0
    assert r["components"] == 1


def test_orphan_is_unreachable(tmp_path: Path):
    _mini_vault(tmp_path)
    _note(tmp_path / "_Organized/NBA/Drivers/orphan.md", "# orphan (nobody links me)\n")
    r = analyze(tmp_path, list_unreached=True)
    assert r["unreachable"] == 1
    assert "_Organized/NBA/Drivers/orphan" in r["unreachable_notes"]


def test_links_in_code_spans_and_fences_ignored(tmp_path: Path):
    _mini_vault(tmp_path)
    # 'pace' is linked ONLY from inside an inline-code span + a fenced block -> orphan.
    _note(tmp_path / "_Organized/NBA/Drivers/_Drivers_Index.md",
          "# Drivers\n\nInline `[[_Organized/NBA/Drivers/pace|pace]]` and:\n"
          "```\n[[_Organized/NBA/Drivers/pace|pace]]\n```\n"
          "- [[_Organized/NBA/Drivers/spacing|spacing]]\n")
    r = analyze(tmp_path, list_unreached=True)
    assert "_Organized/NBA/Drivers/pace" in r["unreachable_notes"]
    assert "_Organized/NBA/Drivers/spacing" not in r["unreachable_notes"]


def test_resolver_exact_suffix_and_basename(tmp_path: Path):
    _mini_vault(tmp_path)
    res = Resolver(tmp_path)
    src = "_Index"
    assert res.resolve("_Organized/NBA/Drivers/pace", src) == "_Organized/NBA/Drivers/pace"
    assert res.resolve("Drivers/pace", src) == "_Organized/NBA/Drivers/pace"   # suffix
    assert res.resolve("pace", src) == "_Organized/NBA/Drivers/pace"           # basename
    assert res.resolve("pace.md", src) == "_Organized/NBA/Drivers/pace"        # .md tolerated
    assert res.resolve("does_not_exist", src) is None


def test_extract_links_skips_code():
    raw = ("see [[A]] and `[[B]]`\n```\n[[C]]\n```\nplus [[D|alias]]\n")
    links = extract_links(raw)
    assert "A" in links and "D" in links
    assert "B" not in links and "C" not in links


# -- finalize entrypoint ------------------------------------------------------

def test_finalize_reaches_everything_incl_top_level_area(tmp_path: Path):
    # A realistic-ish tree: a sport folder + a top-level ops area + a journal note.
    (tmp_path / "_Organized/NBA/Drivers").mkdir(parents=True)
    (tmp_path / "_Organized/NBA/_Digest.md").write_text("# d\n", encoding="utf-8")
    (tmp_path / "_Organized/NBA/Drivers/pace.md").write_text(
        "# pace\n\n## Summary\nControlling tempo.\n", encoding="utf-8")
    # cross-sport hub dir so enrich_hubs has something to do
    (tmp_path / "_Organized/_Index").mkdir(parents=True)
    (tmp_path / "_Organized/_Index/_Brain.md").write_text("# brain\n", encoding="utf-8")
    # a top-level ops area + a dated journal note (the bucket-D shapes)
    (tmp_path / "_TrackRecord").mkdir()
    (tmp_path / "_TrackRecord/drift.md").write_text(
        "# drift\n\n## Summary\nCalibration drift report.\n", encoding="utf-8")
    (tmp_path / "2026-06-18.md").write_text("", encoding="utf-8")
    # a master index that links the sport home (folder/sport indexes are generated)
    (tmp_path / "_Index.md").write_text(
        "# Home\n\n- [[_Organized/NBA/_Index|NBA]]\n"
        "- [[_Organized/_Index/_Brain|Brain]]\n", encoding="utf-8")

    rep = finalize(tmp_path, write=True, do_assert=True)
    assert rep["fully_reachable"] is True
    assert rep["reachability"]["unreachable"] == 0
    assert rep["reachability"]["components"] == 1


def test_finalize_idempotent(tmp_path: Path):
    _mini_vault(tmp_path)
    (tmp_path / "_Organized/_Index").mkdir(parents=True)
    (tmp_path / "_Organized/_Index/_Brain.md").write_text("# brain\n", encoding="utf-8")
    finalize(tmp_path, write=True)
    snap = {p: p.read_bytes() for p in tmp_path.rglob("*.md")}
    finalize(tmp_path, write=True)
    for p, b in snap.items():
        assert p.read_bytes() == b, f"{p.name} changed on second finalize"
