"""tests/platform/test_mlb_seasons.py — scoped unit tests for atlas_seasons.

Uses a tiny synthetic fixture (no real parquet required) so the suite runs
fast and hermetically.

Asserts:
  - build_seasons returns a non-empty list of pathlib.Path objects
  - _Seasons_Index.md is written
  - At least one season note is written (e.g. 2015.md)
  - Standings have correct W/L for a hand-computed case
  - [[Team]] wikilinks are present in season notes
  - Notes contain valid YAML frontmatter
  - Idempotent (two runs → identical output)
  - Missing corpus raises FileNotFoundError
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.mlb.atlas_seasons import build_seasons

# ---------------------------------------------------------------------------
# Synthetic corpus
# ---------------------------------------------------------------------------
#
# Hand-computed standings for 2015:
#   Game 1: NYY(home) 5-3 BOS(away)  → home_win=1 → NYY wins, BOS loses
#   Game 2: NYY(home) 2-4 BOS(away)  → home_win=0 → BOS wins, NYY loses
#   Game 3: BOS(home) 4-2 NYY(away)  → home_win=1 → BOS wins, NYY loses
#
#   BOS: 2W 1L  → win_pct = 0.6667  (AL best)
#   NYY: 1W 2L  → win_pct = 0.3333
#
#   Game 4: LAD(home) 6-2 ATL(away)  → home_win=1 → LAD wins, ATL loses
#   Game 5: ATL(home) 4-1 LAD(away)  → home_win=1 → ATL wins, LAD loses
#
#   ATL: 1W 1L  → win_pct = 0.5000
#   LAD: 1W 1L  → win_pct = 0.5000  (NL — tied; ATL ranks ahead alphabetically
#                                      or by sort stability; both are correct)
#
# AL best record: BOS (0.6667)
# NL best record: ATL or LAD (0.5000)

_SYNTHETIC_GAMES = [
    # event_id, date, season, home, away, home_runs, away_runs,
    # target_home_win, game_seq, home_league
    # ---- 2015 AL ----
    ("20150401-NYY-BOS-1", "2015-04-01", 2015, "NYY", "BOS", 5, 3, 1, 1, "AL"),
    ("20150402-NYY-BOS-2", "2015-04-02", 2015, "NYY", "BOS", 2, 4, 0, 2, "AL"),
    ("20150403-BOS-NYY-1", "2015-04-03", 2015, "BOS", "NYY", 4, 2, 1, 1, "AL"),
    # ---- 2015 NL ----
    ("20150401-LAD-ATL-1", "2015-04-01", 2015, "LAD", "ATL", 6, 2, 1, 1, "NL"),
    ("20150402-ATL-LAD-1", "2015-04-02", 2015, "ATL", "LAD", 4, 1, 1, 1, "NL"),
    # ---- 2016 AL (extra season to test index lists multiple seasons) ----
    ("20160401-NYY-BOS-1", "2016-04-01", 2016, "NYY", "BOS", 3, 2, 1, 1, "AL"),
    ("20160402-BOS-NYY-1", "2016-04-02", 2016, "BOS", "NYY", 5, 1, 1, 1, "AL"),
]

_COLS = [
    "event_id", "date", "season", "home_team", "away_team",
    "home_runs", "away_runs", "target_home_win", "game_seq", "home_league",
]


@pytest.fixture()
def synthetic_corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a tiny games.parquet and return its parent dir."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    df = pd.DataFrame(_SYNTHETIC_GAMES, columns=_COLS)
    df["date"] = pd.to_datetime(df["date"])
    df["home_runs"] = df["home_runs"].astype(float)
    df["away_runs"] = df["away_runs"].astype(float)
    df["target_home_win"] = df["target_home_win"].astype(int)
    df.to_parquet(corpus_dir / "games.parquet", index=False)
    return corpus_dir


# ---------------------------------------------------------------------------
# Regex helpers
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


def test_returns_paths(synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """build_seasons must return a non-empty list of pathlib.Path objects."""
    out = tmp_path / "out"
    result = build_seasons(out, corpus_dir=synthetic_corpus)
    assert isinstance(result, list)
    assert len(result) > 0
    for p in result:
        assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"
        assert p.exists(), f"Returned path does not exist: {p}"


def test_index_note_exists(synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """_Seasons_Index.md must be written."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    assert (out / "_Seasons_Index.md").exists(), "_Seasons_Index.md not found"


def test_season_notes_exist(synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """At least one per-season note (e.g. 2015.md) must be written."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    season_notes = list(out.glob("[0-9]*.md"))
    assert len(season_notes) >= 1, "No season notes found"
    # Both 2015 and 2016 should exist
    assert (out / "2015.md").exists(), "2015.md not found"
    assert (out / "2016.md").exists(), "2016.md not found"


def test_standings_wl_hand_computed(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """2015 season note: BOS must show 2W 1L (rank 1) and NYY must show 1W 2L (rank 2) in AL."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    text = (out / "2015.md").read_text(encoding="utf-8")

    # BOS: 2W 1L (rank 1 in AL) — table format is | rank | [[Teams/TEAM]] | W | L | ...
    assert "[[Teams/BOS]] | 2 | 1 |" in text, (
        f"BOS 2W 1L not found in 2015.md AL standings. Relevant text:\n"
        + "\n".join(l for l in text.splitlines() if "BOS" in l)
    )
    # NYY: 1W 2L (rank 2 in AL)
    assert "[[Teams/NYY]] | 1 | 2 |" in text, (
        f"NYY 1W 2L not found in 2015.md AL standings. Relevant text:\n"
        + "\n".join(l for l in text.splitlines() if "NYY" in l)
    )


def test_wikilinks_present_in_season_note(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Season notes must contain [[wikilinks]] to team notes."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    text = (out / "2015.md").read_text(encoding="utf-8")
    assert _has_wikilinks(text), "2015.md contains no [[wikilinks]]"
    # Specific team wikilinks
    assert "[[Teams/NYY]]" in text, "[[Teams/NYY]] missing from 2015.md"
    assert "[[Teams/LAD]]" in text, "[[Teams/LAD]] missing from 2015.md"


def test_frontmatter_in_season_note(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Season note must open with valid YAML frontmatter."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    text = (out / "2015.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "2015.md missing YAML frontmatter"


def test_frontmatter_in_index(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Seasons_Index.md must open with valid YAML frontmatter."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    text = (out / "_Seasons_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "_Seasons_Index.md missing YAML frontmatter"


def test_index_links_to_seasons(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Seasons_Index.md must link to each season note via [[wikilinks]]."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    text = (out / "_Seasons_Index.md").read_text(encoding="utf-8")
    assert "[[Seasons/2015]]" in text, "[[Seasons/2015]] missing from index"
    assert "[[Seasons/2016]]" in text, "[[Seasons/2016]] missing from index"


def test_index_uplinks_to_main_index(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """_Seasons_Index.md must up-link to [[_Index]] (graph connectivity)."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    text = (out / "_Seasons_Index.md").read_text(encoding="utf-8")
    assert "[[_Index]]" in text, "[[_Index]] up-link missing from _Seasons_Index.md"


def test_al_best_record_bos(
    synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """2015 AL best record must be BOS (0.667 > NYY 0.333)."""
    out = tmp_path / "out"
    build_seasons(out, corpus_dir=synthetic_corpus)
    idx_text = (out / "_Seasons_Index.md").read_text(encoding="utf-8")
    # The index summary row for 2015 should mention BOS as AL best
    assert "BOS" in idx_text, "BOS (AL best 2015) not found in _Seasons_Index.md"


def test_idempotent(synthetic_corpus: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """Running build_seasons twice must produce identical output."""
    out = tmp_path / "out"
    paths1 = build_seasons(out, corpus_dir=synthetic_corpus)
    contents1 = {p.name: p.read_text(encoding="utf-8") for p in paths1}
    paths2 = build_seasons(out, corpus_dir=synthetic_corpus)
    contents2 = {p.name: p.read_text(encoding="utf-8") for p in paths2}
    assert set(contents1.keys()) == set(contents2.keys()), "File set differs on second run"
    for name in contents1:
        assert contents1[name] == contents2[name], f"{name} content differs on second run"


def test_missing_corpus_raises(tmp_path: pathlib.Path) -> None:
    """build_seasons must raise FileNotFoundError for a missing games.parquet."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        build_seasons(tmp_path / "out", corpus_dir=empty)
