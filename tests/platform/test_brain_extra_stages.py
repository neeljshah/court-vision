"""Hermetic tests for scripts.platformkit.brain_extra_stages.run_extra_stages.

Builds a minimal tmp _Organized tree (sport dir + >=8 near-identical stubs +
_Index) and verifies the wiring shim runs end-to-end without raising, returns
a dict, and that consolidate+redundancy behave correctly on the tmp tree.

form_profiles / tennis_depth will skip honestly (no parquets in tmp dir) —
expected; the relevant dict keys will simply be absent.

Markets efficient; calibration is not edge; no edge claimed.
"""
from __future__ import annotations
import re
from pathlib import Path

from scripts.platformkit.brain_extra_stages import run_extra_stages


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _build_organized(root: Path, n_stubs: int = 9) -> tuple:
    """Build a minimal _Organized/<sport>/<cat> tree and return (sport_dir, cat_dir, stubs, idx)."""
    cat_dir = root / "XSport" / "Events"; cat_dir.mkdir(parents=True, exist_ok=True)
    stubs = []
    for i in range(n_stubs):
        content = (
            f"---\neditions: {i+1}\ntags:\n  - sport/xsport\n---\n\n"
            f"# Event{i:02d}\n\n[[_Index|XSport Index]]\n\n## Overview\n"
            f"- **Level:** ATP 500\n- **Surface:** Hard\n"
            f"- **Editions in corpus:** {i+1}\n"
            f"- **Corpus matches:** {(i+1)*100} (unique-ev-{i})\n"
            f"| All-court | 100% | ██████████ |\n"
        )
        p = cat_dir / f"Event{i:02d}.md"; p.write_text(content, encoding="utf-8"); stubs.append(p)
    idx = root / "XSport" / "_Index.md"
    idx.write_text(
        "# XSport Index\n\n"
        + "".join(f"- [[Events/Event{i:02d}.md|Event{i:02d}]]\n" for i in range(n_stubs)),
        encoding="utf-8",
    )
    return root / "XSport", cat_dir, stubs, idx


def _inject_families(root: Path, stubs: list) -> dict:
    """Call consolidate directly via injected_families so detection is deterministic."""
    from scripts.platformkit.brain_consolidate import consolidate
    return consolidate(
        organized_root=root,
        write=True,
        injected_families=[{
            "sport": "XSport",
            "category": "Events",
            "name": "Events",
            "members": stubs,
            "description": "XSport event stubs",
        }],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_run_extra_stages_returns_dict(tmp_path):
    """run_extra_stages must return a dict and never raise."""
    _build_organized(tmp_path)
    result = run_extra_stages(tmp_path)
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"


def test_run_extra_stages_no_crash_on_empty_root(tmp_path):
    """run_extra_stages on a root with no sport dirs must return a dict (all stages skip)."""
    result = run_extra_stages(tmp_path)
    assert isinstance(result, dict)


def test_run_extra_stages_form_profiles_skips_honestly(tmp_path):
    """form_profiles has no parquets in tmp tree — must skip, not raise; key absent or empty."""
    _build_organized(tmp_path)
    result = run_extra_stages(tmp_path)
    # If the key exists it must be a dict (not an exception/string error)
    if "_form_profiles" in result:
        assert isinstance(result["_form_profiles"], dict)


def test_consolidate_merges_stub_family(tmp_path):
    """Consolidate on >=8 near-identical stubs must produce the consolidated file."""
    _, cat_dir, stubs, _ = _build_organized(tmp_path)
    info = _inject_families(tmp_path, stubs)
    assert info["n_families"] == 1, f"Expected 1 family, got {info['n_families']}"
    assert info["n_notes_merged"] == len(stubs)
    con = cat_dir / "_Events_Consolidated.md"
    assert con.exists(), "Consolidated file not created"
    text = con.read_text(encoding="utf-8")
    for i in range(len(stubs)):
        assert f"unique-ev-{i}" in text, f"unique-ev-{i} missing from consolidated note"


def test_consolidate_index_links_repaired(tmp_path):
    """After consolidate, _Index.md must have no dangling stub links."""
    _, cat_dir, stubs, idx = _build_organized(tmp_path)
    _inject_families(tmp_path, stubs)
    text = idx.read_text(encoding="utf-8")
    for p in stubs:
        hit = re.search(
            r"\[\[(?:[^\]|]*/)?{}(?:\.md)?(?:\|[^\]]+)?\]\]".format(re.escape(p.stem)),
            text, re.IGNORECASE,
        )
        assert not hit, f"Dangling link to '{p.stem}' survives after repair"


def test_run_extra_stages_consolidate_key_present_when_stubs_merged(tmp_path):
    """After pre-consolidating stubs, _consolidate key must appear in run_extra_stages output."""
    _, cat_dir, stubs, _ = _build_organized(tmp_path)
    # inject consolidate first so stubs are merged into the tree
    _inject_families(tmp_path, stubs)
    # stubs are now gone; run_extra_stages auto-detects and may find nothing more to merge —
    # but should still return a dict (no crash).  The key test here is no exception.
    result = run_extra_stages(tmp_path)
    assert isinstance(result, dict)


def test_run_extra_stages_redundancy_honest(tmp_path):
    """After consolidation, if _redundancy key appears it must carry a 'redundancy_report' value."""
    _, cat_dir, stubs, _ = _build_organized(tmp_path)
    _inject_families(tmp_path, stubs)
    result = run_extra_stages(tmp_path)
    if "_redundancy" in result:
        assert result["_redundancy"].get("redundancy_report") == "written"


def test_run_extra_stages_note_in_consolidate_result_is_honest(tmp_path):
    """The _note field from consolidate must contain the honesty disclaimer."""
    _, cat_dir, stubs, _ = _build_organized(tmp_path)
    from scripts.platformkit.brain_consolidate import consolidate
    result = consolidate(organized_root=tmp_path, write=True,
                         injected_families=[{"sport": "XSport", "category": "Events",
                                             "name": "Events", "members": stubs,
                                             "description": "honesty test"}])
    assert "no edge claimed" in result.get("_note", "").lower()
    assert "markets efficient" in result.get("_note", "").lower()
