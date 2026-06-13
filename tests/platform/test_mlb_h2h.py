"""tests/platform/test_mlb_h2h.py — scoped unit tests for the MLB H2H atlas generator.

Uses a synthetic fixture (no real parquet required) so the suite runs fast
and hermetically.  Asserts:
  - _Matchups_Index.md is written
  - At least one matchup note is written
  - The NYY-vs-BOS matchup note exists (since the fixture includes repeated games)
  - Notes contain valid [[wikilinks]] linking to BOTH team notes
  - Notes contain valid YAML frontmatter
  - Correct game counts (cross-checked against fixture)
  - build_h2h returns a list of pathlib.Path objects with no exceptions
  - Idempotent: second run produces identical output
"""
from __future__ import annotations

import pathlib
import re
from typing import List

import pandas as pd
import pytest

from domains.mlb.atlas_h2h import build_h2h

# ---------------------------------------------------------------------------
# Synthetic corpus
# ---------------------------------------------------------------------------

# Repeated pairings: NYY-BOS appears 6 times, LAD-ATL 4 times, NYY-LAD 2 times.
_SYNTHETIC_GAMES = [
    # event_id, date, season, home_team, away_team,
    # home_runs, away_runs, target_home_win, game_seq, home_league
    ("20100404-NYY-BOS-1", "2010-04-04", 2010, "NYY", "BOS", 5, 3, 1, 1, "AL"),
    ("20100405-NYY-BOS-2", "2010-04-05", 2010, "NYY", "BOS", 2, 4, 0, 1, "AL"),
    ("20100406-BOS-NYY-1", "2010-04-06", 2010, "BOS", "NYY", 3, 3, 0, 1, "AL"),
    ("20100407-LAD-ATL-1", "2010-04-07", 2010, "LAD", "ATL", 6, 2, 1, 1, "NL"),
    ("20100408-ATL-LAD-1", "2010-04-08", 2010, "ATL", "LAD", 1, 4, 0, 1, "NL"),
    ("20110404-NYY-BOS-1", "2011-04-04", 2011, "NYY", "BOS", 4, 2, 1, 1, "AL"),
    ("20110405-LAD-ATL-1", "2011-04-05", 2011, "LAD", "ATL", 3, 5, 0, 1, "NL"),
    ("20110406-BOS-NYY-1", "2011-04-06", 2011, "BOS", "NYY", 5, 1, 1, 1, "AL"),
    ("20110407-ATL-LAD-1", "2011-04-07", 2011, "ATL", "LAD", 4, 4, 0, 1, "NL"),
    ("20110408-NYY-LAD-1", "2011-04-08", 2011, "NYY", "LAD", 6, 2, 1, 1, "AL"),
    ("20110409-BOS-NYY-2", "2011-04-09", 2011, "BOS", "NYY", 2, 7, 0, 2, "AL"),
    ("20110410-NYY-LAD-2", "2011-04-10", 2011, "NYY", "LAD", 3, 4, 0, 2, "AL"),
]

# Expected counts:
# NYY vs BOS (canonical: BOS < NYY): 6 games
# ATL vs LAD (canonical: ATL < LAD): 4 games
# LAD vs NYY (canonical: LAD < NYY): 2 games
_NYY_BOS_PAIR = ("BOS", "NYY")
_ATL_LAD_PAIR = ("ATL", "LAD")
_LAD_NYY_PAIR = ("LAD", "NYY")


@pytest.fixture()
def synthetic_corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a tiny games.parquet and return its parent dir."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    cols = [
        "event_id", "date", "season", "home_team", "away_team",
        "home_runs", "away_runs", "target_home_win", "game_seq", "home_league",
    ]
    df = pd.DataFrame(_SYNTHETIC_GAMES, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    df["home_runs"] = df["home_runs"].astype(float)
    df["away_runs"] = df["away_runs"].astype(float)
    df["target_home_win"] = df["target_home_win"].astype(int)
    df.to_parquet(corpus_dir / "games.parquet", index=False)
    return corpus_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[.+?\]\]")
_FRONTMATTER_RE = re.compile(r"^---\n.+?\n---", re.DOTALL)


def _has_wikilinks(text: str) -> bool:
    return bool(_WIKILINK_RE.search(text))


def _has_frontmatter(text: str) -> bool:
    return bool(_FRONTMATTER_RE.match(text))


def _extract_wikilinks(text: str) -> List[str]:
    return _WIKILINK_RE.findall(text)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_h2h_returns_paths(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """build_h2h must return a non-empty list of pathlib.Path objects."""
    out_dir = tmp_path / "h2h_out"
    result = build_h2h(out_dir, corpus_dir=synthetic_corpus)
    assert isinstance(result, list)
    assert len(result) > 0
    for p in result:
        assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"


def test_matchups_index_exists(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Matchups_Index.md must be written to the output directory."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    index = out_dir / "_Matchups_Index.md"
    assert index.exists(), "_Matchups_Index.md not found in output directory"


def test_at_least_one_matchup_note(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """At least one individual matchup note must be written."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    notes = [p for p in out_dir.glob("*.md") if p.name != "_Matchups_Index.md"]
    assert len(notes) >= 1, "No matchup notes written"


def test_bos_nyx_note_exists(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """BOS vs NYY note must exist (canonical alphabetical ordering)."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    note = out_dir / "BOS vs NYY.md"
    assert note.exists(), "BOS vs NYY.md not found — canonical ordering wrong"


def test_bos_nyx_correct_game_count(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """BOS vs NYY note must report exactly 6 games from the synthetic fixture."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    note = out_dir / "BOS vs NYY.md"
    text = note.read_text(encoding="utf-8")
    # The frontmatter should have total_games: 6
    assert "total_games: 6" in text, (
        f"BOS vs NYY should have 6 total games; frontmatter excerpt:\n{text[:500]}"
    )


def test_matchup_note_links_to_both_teams(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """BOS vs NYY note must contain [[wikilinks]] to both Teams/BOS and Teams/NYY."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    note = out_dir / "BOS vs NYY.md"
    text = note.read_text(encoding="utf-8")
    assert "[[Teams/BOS]]" in text, "Missing [[Teams/BOS]] wikilink"
    assert "[[Teams/NYY]]" in text, "Missing [[Teams/NYY]] wikilink"


def test_matchup_index_has_frontmatter(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Matchups_Index.md must open with valid YAML frontmatter."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    text = (out_dir / "_Matchups_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "_Matchups_Index.md missing YAML frontmatter"


def test_matchup_index_has_wikilinks(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Matchups_Index.md must contain [[wikilinks]] for team notes."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    text = (out_dir / "_Matchups_Index.md").read_text(encoding="utf-8")
    assert _has_wikilinks(text), "_Matchups_Index.md contains no [[wikilinks]]"


def test_matchup_index_links_to_index(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Matchups_Index.md must link up to [[_Index]] for graph connectivity."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    text = (out_dir / "_Matchups_Index.md").read_text(encoding="utf-8")
    assert "[[_Index]]" in text, "_Matchups_Index.md missing [[_Index]] link"


def test_matchup_note_has_frontmatter_and_wikilinks(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """All individual matchup notes must have frontmatter and wikilinks."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    notes = [p for p in out_dir.glob("*.md") if p.name != "_Matchups_Index.md"]
    for note in notes:
        text = note.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{note.name} missing YAML frontmatter"
        assert _has_wikilinks(text), f"{note.name} missing [[wikilinks]]"


def test_three_distinct_matchup_notes(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Exactly 3 distinct matchup notes should be generated from the fixture."""
    out_dir = tmp_path / "h2h_out"
    build_h2h(out_dir, corpus_dir=synthetic_corpus)
    notes = [p for p in out_dir.glob("*.md") if p.name != "_Matchups_Index.md"]
    assert len(notes) == 3, (
        f"Expected 3 matchup notes, got {len(notes)}: {[n.name for n in notes]}"
    )


def test_idempotent(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Running build_h2h twice must produce identical output (idempotent)."""
    out_dir = tmp_path / "h2h_out"
    paths1 = build_h2h(out_dir, corpus_dir=synthetic_corpus)
    contents1 = {p.name: p.read_text(encoding="utf-8") for p in paths1}
    paths2 = build_h2h(out_dir, corpus_dir=synthetic_corpus)
    contents2 = {p.name: p.read_text(encoding="utf-8") for p in paths2}
    assert set(contents1.keys()) == set(contents2.keys()), "File set differs on second run"
    for name in contents1:
        assert contents1[name] == contents2[name], f"{name} content differs on second run"


def test_missing_corpus_raises(tmp_path: pathlib.Path) -> None:
    """build_h2h must raise FileNotFoundError for a missing corpus dir."""
    out_dir = tmp_path / "h2h_out"
    empty_corpus = tmp_path / "empty_corpus"
    empty_corpus.mkdir()
    with pytest.raises(FileNotFoundError):
        build_h2h(out_dir, corpus_dir=empty_corpus)
