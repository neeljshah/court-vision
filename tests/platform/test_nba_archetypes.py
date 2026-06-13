"""tests.platform.test_nba_archetypes — tests for NBA playstyle archetype notes.

Uses synthetic in-memory fixtures; no real parquets required.
Run with:
    python -m pytest tests/platform/test_nba_archetypes.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.basketball_nba.memory_atlas_archetypes import build_archetypes, ARCHETYPES

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_TAG_SPORT_RE = re.compile(r"sport/nba")
_TAG_ARCH_RE = re.compile(r"\barchetype\b")

# Known star surnames that must NOT appear in any archetype output
_PLAYER_SURNAMES = ["James", "Durant", "Curry", "Jokic", "Wembanyama", "Brunson"]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_POSITIONS = [
    "Guard", "Guard", "Guard", "Guard-Forward",       # guards
    "Forward", "Forward", "Forward-Guard",              # wings
    "Center", "Center", "Forward-Center",               # bigs
]

_N = len(_POSITIONS)


def _make_stats_df() -> pd.DataFrame:
    """Synthetic per-player season-average stats covering multiple archetypes."""
    return pd.DataFrame({
        "player_id": list(range(2001, 2001 + _N)),
        "position": _POSITIONS,
        # Usage spread: high (creator/scorer), mid, low
        "usage":        [0.28, 0.26, 0.23, 0.20, 0.18, 0.16, 0.15, 0.17, 0.19, 0.22],
        # TS% spread
        "ts":           [0.58, 0.55, 0.52, 0.60, 0.57, 0.56, 0.53, 0.65, 0.63, 0.61],
        # eFG%
        "efg":          [0.53, 0.50, 0.48, 0.56, 0.54, 0.52, 0.50, 0.61, 0.58, 0.57],
        # AST%: high for creators, low for bigs
        "ast_pct":      [0.25, 0.22, 0.18, 0.15, 0.12, 0.10, 0.09, 0.16, 0.10, 0.08],
        # DefRtg: lower = better
        "def_rtg":      [113, 114, 115, 112, 111, 113, 116, 108, 110, 112],
        # OffRtg
        "off_rtg":      [118, 115, 113, 116, 112, 110, 109, 115, 117, 119],
        # REB%
        "reb_pct":      [0.06, 0.07, 0.07, 0.08, 0.09, 0.10, 0.08, 0.13, 0.12, 0.11],
        # Minutes
        "minutes_avg":  [32, 28, 26, 24, 22, 18, 14, 20, 30, 28],
        "n_games":      [60] * _N,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_archetypes_returns_paths(tmp_path: pathlib.Path) -> None:
    """build_archetypes must return list[pathlib.Path] pointing to real files."""
    stats = _make_stats_df()
    written = build_archetypes(tmp_path / "vault", _stats_df=stats)
    assert isinstance(written, list)
    assert len(written) >= 1
    for p in written:
        assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"
        assert p.exists(), f"File was not written: {p}"


def test_archetype_notes_created(tmp_path: pathlib.Path) -> None:
    """An .md note must be written for every archetype in ARCHETYPES."""
    stats = _make_stats_df()
    written = build_archetypes(tmp_path / "vault", _stats_df=stats)
    written_names = {p.name for p in written}

    for arch in ARCHETYPES:
        slug = arch["label"].replace(" ", "_").replace("-", "_") + ".md"
        assert slug in written_names, (
            f"No note for archetype '{arch['label']}' (expected file: {slug})"
        )


def test_archetypes_index_exists(tmp_path: pathlib.Path) -> None:
    """_Archetypes_Index.md must be written."""
    stats = _make_stats_df()
    written = build_archetypes(tmp_path / "vault", _stats_df=stats)
    written_names = {p.name for p in written}
    assert "_Archetypes_Index.md" in written_names, "Missing _Archetypes_Index.md"


def test_no_player_names_in_output(tmp_path: pathlib.Path) -> None:
    """No player surnames must appear anywhere in the archetype output."""
    stats = _make_stats_df()
    out_dir = tmp_path / "vault"
    build_archetypes(out_dir, _stats_df=stats)

    arch_dir = out_dir / "Archetypes"
    for md_file in arch_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        for surname in _PLAYER_SURNAMES:
            assert surname not in text, (
                f"Player surname '{surname}' found in {md_file.name}"
            )


def test_archetype_note_has_frontmatter_and_tags(tmp_path: pathlib.Path) -> None:
    """Every archetype note must have YAML frontmatter, sport/nba tag, archetype tag."""
    stats = _make_stats_df()
    written = build_archetypes(tmp_path / "vault", _stats_df=stats)

    arch_notes = [p for p in written if p.name != "_Archetypes_Index.md"]
    assert len(arch_notes) >= 1

    for note in arch_notes:
        text = note.read_text(encoding="utf-8")
        assert _FRONTMATTER_RE.search(text), f"{note.name}: missing YAML frontmatter"
        assert _TAG_SPORT_RE.search(text), f"{note.name}: missing sport/nba tag"
        assert _TAG_ARCH_RE.search(text), f"{note.name}: missing archetype tag"


def test_archetype_note_has_uplink_to_index(tmp_path: pathlib.Path) -> None:
    """Every archetype note must contain [[_Index]] uplink."""
    stats = _make_stats_df()
    written = build_archetypes(tmp_path / "vault", _stats_df=stats)

    arch_notes = [p for p in written if p.name != "_Archetypes_Index.md"]
    for note in arch_notes:
        text = note.read_text(encoding="utf-8")
        links = _WIKILINK_RE.findall(text)
        assert any("_Index" in l for l in links), (
            f"{note.name}: missing [[_Index]] uplink; links found: {links}"
        )


def test_archetypes_index_has_population_table(tmp_path: pathlib.Path) -> None:
    """_Archetypes_Index.md must contain a markdown table and total player count."""
    stats = _make_stats_df()
    out_dir = tmp_path / "vault"
    build_archetypes(out_dir, _stats_df=stats)

    index_text = (out_dir / "Archetypes" / "_Archetypes_Index.md").read_text(encoding="utf-8")
    assert "|" in index_text, "_Archetypes_Index.md must contain a markdown table"
    assert "Total players classified" in index_text, (
        "_Archetypes_Index.md must report total player count"
    )


def test_archetypes_index_has_sport_tag(tmp_path: pathlib.Path) -> None:
    """_Archetypes_Index.md must have sport/nba tag."""
    stats = _make_stats_df()
    out_dir = tmp_path / "vault"
    build_archetypes(out_dir, _stats_df=stats)

    index_text = (out_dir / "Archetypes" / "_Archetypes_Index.md").read_text(encoding="utf-8")
    assert _TAG_SPORT_RE.search(index_text), "_Archetypes_Index.md missing sport/nba tag"


def test_population_counts_non_negative(tmp_path: pathlib.Path) -> None:
    """All archetype populations must be non-negative integers."""
    stats = _make_stats_df()
    out_dir = tmp_path / "vault"
    written = build_archetypes(out_dir, _stats_df=stats)

    arch_notes = [p for p in written if p.name != "_Archetypes_Index.md"]
    for note in arch_notes:
        text = note.read_text(encoding="utf-8")
        # Match "Players fitting this archetype: N"
        m = re.search(r"Players fitting this archetype:\*\* (\d+)", text)
        assert m is not None, f"{note.name}: missing population count line"
        count = int(m.group(1))
        assert count >= 0, f"{note.name}: negative population {count}"


def test_total_classified_equals_input(tmp_path: pathlib.Path) -> None:
    """Sum of all archetype populations must equal the number of input players."""
    stats = _make_stats_df()
    out_dir = tmp_path / "vault"
    build_archetypes(out_dir, _stats_df=stats)

    index_text = (out_dir / "Archetypes" / "_Archetypes_Index.md").read_text(encoding="utf-8")
    m = re.search(r"Total players classified:\*\* (\d+)", index_text)
    assert m is not None, "Could not find total count in _Archetypes_Index.md"
    total = int(m.group(1))
    assert total == _N, f"Expected {_N} players classified, got {total}"


def test_idempotent(tmp_path: pathlib.Path) -> None:
    """Running build_archetypes twice produces the same file count."""
    stats = _make_stats_df()
    out_dir = tmp_path / "vault"
    w1 = build_archetypes(out_dir, _stats_df=stats)
    w2 = build_archetypes(out_dir, _stats_df=stats)
    assert len(w1) == len(w2), "Idempotency violation: different file counts on rerun"
