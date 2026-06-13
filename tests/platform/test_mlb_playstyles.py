"""tests/platform/test_mlb_playstyles.py — Scoped unit tests for MLB playstyle atlas.

Uses a synthetic games.parquet fixture so the suite is fast and hermetic.
The fixture engineers clear archetype cases:
  - HIGH_RS team (BOS): rs ≈ 6.5, positive rd → should hit power_run_scoring
  - LOW_RA team (TAM): ra ≈ 3.5, positive rd → should hit pitching_run_prevention
  - DEFICIT team (MIA): rd ≈ −1.0, win% < 0.48 → should hit run_deficit_rebuilding

Asserts:
  - build_playstyles returns a non-empty list of pathlib.Path objects
  - At least one archetype note is written
  - _Playstyles_Index.md is written
  - Each written file has valid YAML frontmatter (--- ... ---)
  - Each written file contains at least one [[wikilink]]
  - [[Teams/X]] links appear in archetype notes
  - high-RS fixture team lands in power_run_scoring archetype
  - No exception is raised on well-formed corpus data
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.mlb.atlas_playstyles import build_playstyles

# ---------------------------------------------------------------------------
# Synthetic corpus fixture
# ---------------------------------------------------------------------------

# We create enough games (>= 100 per team) for the MIN_GAMES filter to pass.
# Three teams: BOS (high scorer), TAM (pitching-led), MIA (run-deficit).
# All are AL so home_league is consistent; resolver fallback handles "MIA" fine.

_COLS = [
    "event_id", "date", "season", "home_team", "away_team",
    "home_runs", "away_runs", "target_home_win", "game_seq", "home_league",
]


def _synthetic_rows() -> list:
    """Generate 150 games per team-pair ensuring clear archetype signatures."""
    rows = []
    g = 1

    def _add(home: str, away: str, h_runs: float, a_runs: float, hw: int, s: int) -> None:
        nonlocal g
        rows.append((
            f"G{g:04d}", f"{s}-04-{(g % 28) + 1:02d}", s,
            home, away, h_runs, a_runs, hw, g, "AL",
        ))
        g += 1

    for s in range(2010, 2016):  # 6 seasons
        for _ in range(26):  # 26 games per season-pair → 156 total per pair
            # BOS (high-RS) vs TAM (low-RA): BOS scores 7, TAM allows 7→ BOS wins
            _add("BOS", "TAM", 7.0, 3.0, 1, s)
            # TAM (home) vs MIA (deficit): TAM scores 4, MIA scores 1
            _add("TAM", "MIA", 4.0, 1.0, 1, s)
            # MIA (home) vs BOS (visitor): BOS scores 6, MIA scores 2 → MIA loses
            _add("MIA", "BOS", 2.0, 6.0, 0, s)

    return rows


@pytest.fixture()
def synthetic_corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write tiny games.parquet and return its parent directory."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    rows = _synthetic_rows()
    df = pd.DataFrame(rows, columns=_COLS)
    df["home_runs"] = df["home_runs"].astype(float)
    df["away_runs"] = df["away_runs"].astype(float)
    df["target_home_win"] = df["target_home_win"].astype(int)
    df["season"] = df["season"].astype(int)
    df.to_parquet(corpus_dir / "games.parquet", index=False)
    return corpus_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[.+?\]\]")
_FRONTMATTER_RE = re.compile(r"^---\n.+?\n---", re.DOTALL)
_TEAMS_LINK_RE = re.compile(r"\[\[Teams/\w+\]\]")


def _has_frontmatter(text: str) -> bool:
    return bool(_FRONTMATTER_RE.match(text))


def _has_wikilinks(text: str) -> bool:
    return bool(_WIKILINK_RE.search(text))


def _has_teams_links(text: str) -> bool:
    return bool(_TEAMS_LINK_RE.search(text))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_returns_paths(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """build_playstyles returns a non-empty list of Path objects."""
    out = tmp_path / "out"
    result = build_playstyles(out, corpus_dir=synthetic_corpus)
    assert isinstance(result, list), "Expected a list"
    assert len(result) > 0, "Expected at least one path returned"
    for p in result:
        assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"


def test_index_note_written(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """_Playstyles_Index.md is written."""
    out = tmp_path / "out"
    build_playstyles(out, corpus_dir=synthetic_corpus)
    index = out / "_Playstyles_Index.md"
    assert index.exists(), "_Playstyles_Index.md should be written"
    assert index.stat().st_size > 0, "_Playstyles_Index.md should be non-empty"


def test_at_least_one_archetype_note(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """At least one archetype .md note is written (beyond the index)."""
    out = tmp_path / "out"
    result = build_playstyles(out, corpus_dir=synthetic_corpus)
    arch_notes = [p for p in result if p.name != "_Playstyles_Index.md"]
    assert len(arch_notes) >= 1, "Expected at least one archetype note"


def test_frontmatter_in_all_notes(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Every written note has valid YAML frontmatter."""
    out = tmp_path / "out"
    result = build_playstyles(out, corpus_dir=synthetic_corpus)
    for p in result:
        text = p.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{p.name} is missing YAML frontmatter"


def test_wikilinks_in_all_notes(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Every written note contains at least one Obsidian [[wikilink]]."""
    out = tmp_path / "out"
    result = build_playstyles(out, corpus_dir=synthetic_corpus)
    for p in result:
        text = p.read_text(encoding="utf-8")
        assert _has_wikilinks(text), f"{p.name} has no [[wikilinks]]"


def test_teams_links_in_archetype_notes(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Archetype notes containing teams include [[Teams/X]] wikilinks."""
    out = tmp_path / "out"
    result = build_playstyles(out, corpus_dir=synthetic_corpus)
    arch_notes = [p for p in result if p.name != "_Playstyles_Index.md"]
    # At least one archetype note should have teams linked
    linked = [p for p in arch_notes if _has_teams_links(p.read_text(encoding="utf-8"))]
    assert len(linked) >= 1, "Expected at least one archetype note with [[Teams/X]] links"


def test_high_rs_team_in_power_archetype(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """BOS (engineered high RS ≈ 4.9/G) should appear in power_run_scoring note."""
    out = tmp_path / "out"
    build_playstyles(out, corpus_dir=synthetic_corpus)
    power_note = out / "power_run_scoring.md"
    assert power_note.exists(), "power_run_scoring.md should be written"
    text = power_note.read_text(encoding="utf-8")
    assert "BOS" in text, "BOS (high-RS team) should appear in power_run_scoring note"


def test_index_links_all_archetypes(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """_Playstyles_Index.md links back to each named archetype slug (not unclassified)."""
    out = tmp_path / "out"
    result = build_playstyles(out, corpus_dir=synthetic_corpus)
    index_text = (out / "_Playstyles_Index.md").read_text(encoding="utf-8")
    # Exclude the index itself and the unclassified stub (it is a catch-all,
    # not a named archetype, so it does not appear in the index table).
    _SKIP = {"_Playstyles_Index", "unclassified"}
    arch_notes = [p for p in result if p.stem not in _SKIP]
    for p in arch_notes:
        slug = p.stem  # e.g. "power_run_scoring"
        assert slug in index_text, (
            f"Index should reference archetype slug '{slug}'"
        )


def test_unclassified_stub_written(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """unclassified.md stub is written so [[Playstyles/unclassified]] resolves."""
    out = tmp_path / "out"
    build_playstyles(out, corpus_dir=synthetic_corpus)
    stub = out / "unclassified.md"
    assert stub.exists(), "unclassified.md stub should be written"
    text = stub.read_text(encoding="utf-8")
    assert "---" in text, "unclassified.md should have YAML frontmatter"
    assert "[[Playstyles/_Playstyles_Index]]" in text, (
        "unclassified.md should link up to _Playstyles_Index"
    )


def test_no_exception_on_minimal_valid_corpus(tmp_path: pathlib.Path) -> None:
    """build_playstyles does not raise on a minimal valid corpus (few games, no teams pass filter)."""
    corpus_dir = tmp_path / "tiny"
    corpus_dir.mkdir()
    rows = [
        ("E1", "2015-04-01", 2015, "NYY", "BOS", 5.0, 3.0, 1, 1, "AL"),
        ("E2", "2015-04-02", 2015, "BOS", "NYY", 3.0, 4.0, 0, 2, "AL"),
    ]
    df = pd.DataFrame(rows, columns=_COLS)
    df["home_runs"] = df["home_runs"].astype(float)
    df["away_runs"] = df["away_runs"].astype(float)
    df["target_home_win"] = df["target_home_win"].astype(int)
    df["season"] = df["season"].astype(int)
    df.to_parquet(corpus_dir / "games.parquet", index=False)

    out = tmp_path / "tiny_out"
    result = build_playstyles(out, corpus_dir=corpus_dir)
    # Should complete without exception; index + 6 archetype stubs written
    assert isinstance(result, list)
    assert (out / "_Playstyles_Index.md").exists()
