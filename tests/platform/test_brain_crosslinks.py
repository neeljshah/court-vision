"""
test_brain_crosslinks.py — Hermetic tests for brain_crosslinks.build_crosslinks.
All tests use a synthetic tmp_path tree; the live vault is never touched.
"""
from __future__ import annotations
import re
from pathlib import Path

import pytest

from scripts.platformkit.brain_crosslinks import (
    _RELATED_HDR as RELATED_HEADER,
    build_crosslinks,
)

_DISCLAIMER = "NOT a market edge; no edge claimed."


# ── tree builder ─────────────────────────────────────────────────────────────

def _note(path: Path, heading: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntags: [organized, test, person-free]\n---\n"
        f"# {heading}\n\n> **Intelligence only, {_DISCLAIMER}**\n\n{body}\n",
        encoding="utf-8",
    )


def _tree(root: Path) -> dict[str, Path]:
    """Build a minimal synthetic _Organized/ tree and return a path map."""
    n: dict[str, Path] = {}
    nba = root / "NBA"

    p = nba / "_Index.md";           _note(p, "NBA Index"); n["nba_idx"] = p
    p = nba / "_WhatWins.md";        _note(p, "NBA — What Wins"); n["nba_ww"] = p
    p = nba / "Drivers/shooting.md"; _note(p, "NBA Driver — SHOOTING",
        "## Mechanism\neFG.\n## Links\n"); n["nba_dr"] = p
    p = nba / "Mechanisms/_Mechanisms.md"; _note(p, "NBA Mechanisms Index",
        "## Summary\nCore mechanisms.\n"); n["nba_mech"] = p
    p = nba / "Archetypes/3_and_D_Wing.md"; _note(p, "NBA Archetype — 3-and-D Wing",
        "## Role\nSpacing + defense.\n"); n["nba_arch"] = p
    p = nba / "Schemes/drop_coverage.md"; _note(p, "NBA Scheme — Drop Coverage",
        "## Desc\nDrop into paint.\n"); n["nba_scheme"] = p
    p = nba / "Trends/_Trends_Overview.md"; _note(p, "NBA Trends Overview",
        "## Summary\nSeason trends.\n"); n["nba_trend"] = p
    p = nba / "Teams/BOS/_Identity.md"; _note(p, "BOS — Team Identity",
        "## Archetype\nSwitching defense.\n"); n["nba_id"] = p

    soccer = root / "Soccer"
    p = soccer / "_Index.md";           _note(p, "Soccer Index"); n["soc_idx"] = p
    p = soccer / "_WhatWins.md";        _note(p, "Soccer — What Wins"); n["soc_ww"] = p
    p = soccer / "Drivers/finishing.md";_note(p, "Soccer Driver — FINISHING"); n["soc_dr"] = p
    p = soccer / "Archetypes/high_press.md"; _note(p, "Soccer Archetype — High Press"); n["soc_arch"] = p

    return n


@pytest.fixture()
def org(tmp_path: Path):
    root = tmp_path / "_Organized"
    return root, _tree(root)


# ── return dict ──────────────────────────────────────────────────────────────

def test_return_keys(org):
    root, _ = org
    r = build_crosslinks(root, write=False)
    assert {"n_files_scanned", "n_linked", "by_sport", "note"} <= r.keys()


def test_scanned_counts(org):
    root, _ = org
    r = build_crosslinks(root, write=False)
    assert r["by_sport"]["NBA"]["scanned"] == 8
    assert r["by_sport"]["Soccer"]["scanned"] == 4
    assert r["n_files_scanned"] == 12


def test_missing_sports_absent(org):
    root, _ = org
    r = build_crosslinks(root, write=False)
    assert "MLB" not in r["by_sport"]
    assert "Tennis" not in r["by_sport"]


def test_note_field_no_fabricated_edge(org):
    root, _ = org
    r = build_crosslinks(root, write=False)
    # If "edge" appears it must be in the denial phrase.
    low = r["note"].lower()
    assert "edge" not in low or "not a market edge" in low


# ── write mode: structure ────────────────────────────────────────────────────

def test_related_section_added(org):
    root, paths = org
    build_crosslinks(root, write=True)
    for p in paths.values():
        assert RELATED_HEADER in p.read_text(encoding="utf-8"), \
            f"{p.name} missing '## Related'"


def test_at_least_one_resolving_link(org):
    root, paths = org
    build_crosslinks(root, write=True)
    link_re = re.compile(r"\[\[([^\]|]+)\|")
    for p in paths.values():
        txt = p.read_text(encoding="utf-8")
        rel_txt = txt[txt.find(RELATED_HEADER):]
        targets = link_re.findall(rel_txt)
        assert any(
            (p.parent / Path(t)).resolve().exists() for t in targets
        ), f"{p.name}: no resolving wikilink — targets={targets}"


def test_no_self_links(org):
    root, paths = org
    build_crosslinks(root, write=True)
    link_re = re.compile(r"\[\[([^\]|]+)\|")
    for p in paths.values():
        txt = p.read_text(encoding="utf-8")
        rel_txt = txt[txt.find(RELATED_HEADER):]
        for t in link_re.findall(rel_txt):
            resolved = (p.parent / Path(t)).resolve()
            assert resolved != p.resolve(), f"{p.name} self-links via {t}"


def test_no_edge_tokens_in_links(org):
    root, paths = org
    build_crosslinks(root, write=True)
    forbidden = re.compile(
        r"\b(bet|wager|roi|clv|kelly|sharp|odds|vig|pick|arb)\b", re.IGNORECASE
    )
    for p in paths.values():
        txt = p.read_text(encoding="utf-8")
        rel_txt = txt[txt.find(RELATED_HEADER):]
        assert not forbidden.search(rel_txt), \
            f"{p.name} Related section has edge token"


# ── idempotency ───────────────────────────────────────────────────────────────

def test_byte_identical_on_second_run(org):
    root, paths = org
    build_crosslinks(root, write=True)
    after_first = {p: p.read_bytes() for p in paths.values()}
    build_crosslinks(root, write=True)
    for p, b in after_first.items():
        assert p.read_bytes() == b, f"{p.name} changed on second run"


def test_scanned_stable_across_runs(org):
    root, _ = org
    r1 = build_crosslinks(root, write=True)
    r2 = build_crosslinks(root, write=True)
    assert r1["n_files_scanned"] == r2["n_files_scanned"]


# ── dry-run ───────────────────────────────────────────────────────────────────

def test_dry_run_no_file_changes(org):
    root, paths = org
    originals = {p: p.read_bytes() for p in paths.values()}
    build_crosslinks(root, write=False)
    for p, b in originals.items():
        assert p.read_bytes() == b, f"{p.name} modified despite write=False"


# ── sport isolation ───────────────────────────────────────────────────────────

def test_nba_notes_not_linked_to_soccer(org):
    root, paths = org
    build_crosslinks(root, write=True)
    txt = paths["nba_dr"].read_text(encoding="utf-8")
    rel = txt[txt.find(RELATED_HEADER):]
    assert "Soccer" not in rel and "finishing" not in rel


def test_soccer_not_linked_to_nba(org):
    root, paths = org
    build_crosslinks(root, write=True)
    txt = paths["soc_dr"].read_text(encoding="utf-8")
    rel = txt[txt.find(RELATED_HEADER):]
    assert "NBA" not in rel and "shooting" not in rel


# ── affinity ──────────────────────────────────────────────────────────────────

def test_driver_links_to_whatwins(org):
    root, paths = org
    build_crosslinks(root, write=True)
    txt = paths["nba_dr"].read_text(encoding="utf-8")
    rel = txt[txt.find(RELATED_HEADER):]
    assert "_WhatWins" in rel or "WhatWins" in rel


def test_archetype_links_to_whatwins_or_scheme(org):
    root, paths = org
    build_crosslinks(root, write=True)
    txt = paths["nba_arch"].read_text(encoding="utf-8")
    rel = txt[txt.find(RELATED_HEADER):]
    assert "_WhatWins" in rel or "drop_coverage" in rel


def test_identity_links_to_archetype_or_whatwins(org):
    root, paths = org
    build_crosslinks(root, write=True)
    txt = paths["nba_id"].read_text(encoding="utf-8")
    rel = txt[txt.find(RELATED_HEADER):]
    assert "3_and_D_Wing" in rel or "_WhatWins" in rel
