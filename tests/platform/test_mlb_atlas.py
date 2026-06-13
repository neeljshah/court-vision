"""tests/platform/test_mlb_atlas.py — scoped unit tests for the MLB atlas generator.

Uses a synthetic fixture (no real parquet required) so the suite runs fast
and hermetically.  Asserts:
  - _Index.md is written
  - At least one Team note is written
  - At least one League note is written
  - Notes contain valid [[wikilinks]]
  - Notes contain valid YAML frontmatter (--- ... ---)
  - build_atlas returns a list of pathlib.Path objects with no exceptions
"""
from __future__ import annotations

import pathlib
import re
from typing import List

import pandas as pd
import pytest

from domains.mlb.atlas import build_atlas

# ---------------------------------------------------------------------------
# Synthetic corpus fixture
# ---------------------------------------------------------------------------

_SYNTHETIC_GAMES = [
    # event_id, date, season, home, away, home_runs, away_runs, target_home_win,
    # game_seq, home_league
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
]


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_atlas_returns_paths(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """build_atlas must return a non-empty list of pathlib.Path objects."""
    out_dir = tmp_path / "atlas_out"
    result = build_atlas(out_dir, corpus_dir=synthetic_corpus)
    assert isinstance(result, list)
    assert len(result) > 0
    for p in result:
        assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"


def test_index_note_exists(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Index.md must be written to the output directory."""
    out_dir = tmp_path / "atlas_out"
    build_atlas(out_dir, corpus_dir=synthetic_corpus)
    index = out_dir / "_Index.md"
    assert index.exists(), "_Index.md not found in output directory"


def test_team_notes_exist(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """At least one team note must be written under Teams/."""
    out_dir = tmp_path / "atlas_out"
    build_atlas(out_dir, corpus_dir=synthetic_corpus)
    team_notes = list((out_dir / "Teams").glob("*.md"))
    assert len(team_notes) >= 1, "No team notes written under Teams/"


def test_league_notes_exist(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """At least one league note must be written under Leagues/."""
    out_dir = tmp_path / "atlas_out"
    build_atlas(out_dir, corpus_dir=synthetic_corpus)
    league_notes = list((out_dir / "Leagues").glob("*.md"))
    assert len(league_notes) >= 1, "No league notes written under Leagues/"


def test_index_has_frontmatter(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Index.md must open with valid YAML frontmatter (--- ... ---)."""
    out_dir = tmp_path / "atlas_out"
    build_atlas(out_dir, corpus_dir=synthetic_corpus)
    text = (out_dir / "_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "_Index.md missing YAML frontmatter"


def test_index_has_wikilinks(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Index.md must contain at least one [[wikilink]]."""
    out_dir = tmp_path / "atlas_out"
    build_atlas(out_dir, corpus_dir=synthetic_corpus)
    text = (out_dir / "_Index.md").read_text(encoding="utf-8")
    assert _has_wikilinks(text), "_Index.md contains no [[wikilinks]]"


def test_team_note_has_frontmatter_and_wikilinks(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Each team note must have YAML frontmatter and at least one [[wikilink]]."""
    out_dir = tmp_path / "atlas_out"
    build_atlas(out_dir, corpus_dir=synthetic_corpus)
    team_notes = list((out_dir / "Teams").glob("*.md"))
    for note in team_notes:
        text = note.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{note.name} missing YAML frontmatter"
        assert _has_wikilinks(text), f"{note.name} missing [[wikilinks]]"


def test_league_note_has_frontmatter_and_wikilinks(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Each league note must have YAML frontmatter and at least one [[wikilink]]."""
    out_dir = tmp_path / "atlas_out"
    build_atlas(out_dir, corpus_dir=synthetic_corpus)
    league_notes = list((out_dir / "Leagues").glob("*.md"))
    for note in league_notes:
        text = note.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{note.name} missing YAML frontmatter"
        assert _has_wikilinks(text), f"{note.name} missing [[wikilinks]]"


def test_idempotent(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Running build_atlas twice must produce identical output (idempotent)."""
    out_dir = tmp_path / "atlas_out"
    paths1 = build_atlas(out_dir, corpus_dir=synthetic_corpus)
    contents1 = {p.name: p.read_text(encoding="utf-8") for p in paths1}
    paths2 = build_atlas(out_dir, corpus_dir=synthetic_corpus)
    contents2 = {p.name: p.read_text(encoding="utf-8") for p in paths2}
    assert set(contents1.keys()) == set(contents2.keys()), "File set differs on second run"
    for name in contents1:
        assert contents1[name] == contents2[name], f"{name} differs on second run"


def test_missing_corpus_raises(tmp_path: pathlib.Path) -> None:
    """build_atlas must raise FileNotFoundError for a missing corpus dir."""
    out_dir = tmp_path / "atlas_out"
    empty_corpus = tmp_path / "empty_corpus"
    empty_corpus.mkdir()
    with pytest.raises(FileNotFoundError):
        build_atlas(out_dir, corpus_dir=empty_corpus)
