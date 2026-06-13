"""tests/platform/test_mlb_style_trends.py — Scoped unit tests for atlas_style_trends.

Uses a tiny synthetic multi-season fixture (no real parquet required).
Fixture design (3 teams × 2 seasons, 30 games each):
  - HIGH_RS: BOS scores 7, allows 3  → power/high-variance archetype territory
  - PITCH:   TAM scores 4, allows 2  → pitching-led territory
  - DEFICIT: MIA scores 2, allows 5  → run-deficit territory

Asserts:
  - build_style_trends returns a non-empty list of pathlib.Path objects
  - _Style_Trends_Overview.md is written with YAML frontmatter
  - Per-season notes (style_trends_<year>.md) are written for each season
  - Overview contains an ASCII table with season metrics
  - Per-season note contains runs-per-game value
  - [[wikilinks]] are present in every note
  - No individual player names appear anywhere in output
  - No exception on well-formed corpus
  - Missing corpus raises FileNotFoundError
  - Idempotent: two runs produce identical output
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.mlb.atlas_style_trends import build_style_trends

# ---------------------------------------------------------------------------
# Synthetic corpus fixture
# ---------------------------------------------------------------------------

_COLS = [
    "event_id", "date", "season", "home_team", "away_team",
    "home_runs", "away_runs", "target_home_win", "game_seq", "home_league",
]

# Three teams: BOS (high scorer), TAM (pitching-led), MIA (run-deficit).
# Two seasons: 2015, 2016.  30 games per team-pair per season (60 total/season).


def _make_fixture_rows() -> list:
    rows = []
    g = 1

    def _add(home: str, away: str, hr: float, ar: float, hw: int, s: int) -> None:
        nonlocal g
        rows.append((
            f"G{g:04d}", f"{s}-04-{(g % 28) + 1:02d}", s,
            home, away, hr, ar, hw, g % 10, "AL",
        ))
        g += 1

    for season in (2015, 2016):
        for _ in range(30):
            # BOS at home vs TAM: BOS 7-3 → BOS wins
            _add("BOS", "TAM", 7.0, 3.0, 1, season)
            # TAM at home vs MIA: TAM 4-2 → TAM wins
            _add("TAM", "MIA", 4.0, 2.0, 1, season)
            # MIA at home vs BOS: MIA 2-5 → BOS wins (home loses)
            _add("MIA", "BOS", 2.0, 5.0, 0, season)

    return rows


@pytest.fixture()
def synthetic_corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    rows = _make_fixture_rows()
    df = pd.DataFrame(rows, columns=_COLS)
    df["home_runs"] = df["home_runs"].astype(float)
    df["away_runs"] = df["away_runs"].astype(float)
    df["target_home_win"] = df["target_home_win"].astype(int)
    df["season"] = df["season"].astype(int)
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


def test_returns_paths(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """build_style_trends returns a non-empty list of pathlib.Path objects."""
    out = tmp_path / "out"
    result = build_style_trends(out, corpus_dir=synthetic_corpus)
    assert isinstance(result, list)
    assert len(result) > 0
    for p in result:
        assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"
        assert p.exists(), f"Returned path does not exist: {p}"


def test_overview_note_written(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """_Style_Trends_Overview.md is written and non-empty."""
    out = tmp_path / "out"
    build_style_trends(out, corpus_dir=synthetic_corpus)
    overview = out / "_Style_Trends_Overview.md"
    assert overview.exists(), "_Style_Trends_Overview.md should be written"
    assert overview.stat().st_size > 100, "_Style_Trends_Overview.md should be non-trivial"


def test_per_season_notes_written(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """One per-season note is written for each season in the corpus."""
    out = tmp_path / "out"
    build_style_trends(out, corpus_dir=synthetic_corpus)
    assert (out / "style_trends_2015.md").exists(), "style_trends_2015.md not found"
    assert (out / "style_trends_2016.md").exists(), "style_trends_2016.md not found"


def test_overview_has_frontmatter(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """_Style_Trends_Overview.md has valid YAML frontmatter."""
    out = tmp_path / "out"
    build_style_trends(out, corpus_dir=synthetic_corpus)
    text = (out / "_Style_Trends_Overview.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "_Style_Trends_Overview.md missing YAML frontmatter"


def test_season_note_has_frontmatter(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """Per-season notes have valid YAML frontmatter."""
    out = tmp_path / "out"
    build_style_trends(out, corpus_dir=synthetic_corpus)
    text = (out / "style_trends_2015.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "style_trends_2015.md missing YAML frontmatter"


def test_wikilinks_in_all_notes(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """Every written note contains at least one [[wikilink]]."""
    out = tmp_path / "out"
    result = build_style_trends(out, corpus_dir=synthetic_corpus)
    for p in result:
        text = p.read_text(encoding="utf-8")
        assert _has_wikilinks(text), f"{p.name} has no [[wikilinks]]"


def test_overview_contains_season_rows(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """Overview table contains at least one season row with a numeric metric."""
    out = tmp_path / "out"
    build_style_trends(out, corpus_dir=synthetic_corpus)
    text = (out / "_Style_Trends_Overview.md").read_text(encoding="utf-8")
    # Should contain year and a numeric RPG value
    assert "2015" in text, "2015 not found in overview"
    assert "2016" in text, "2016 not found in overview"
    # At least one decimal number appears (runs/game)
    assert re.search(r"\d+\.\d+", text), "No decimal metric found in overview"


def test_season_note_has_runs_per_game(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Per-season note contains runs-per-game metric."""
    out = tmp_path / "out"
    build_style_trends(out, corpus_dir=synthetic_corpus)
    text = (out / "style_trends_2015.md").read_text(encoding="utf-8")
    assert "Runs per game" in text, "'Runs per game' label missing from season note"
    # Verify a numeric value follows
    assert re.search(r"Runs per game.*\d+\.\d+", text, re.DOTALL), (
        "Numeric runs-per-game value not found in season note"
    )


def test_season_note_has_style_table(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Per-season note contains style distribution section."""
    out = tmp_path / "out"
    build_style_trends(out, corpus_dir=synthetic_corpus)
    text = (out / "style_trends_2015.md").read_text(encoding="utf-8")
    assert "Style Distribution" in text or "style" in text.lower(), (
        "Style distribution section missing from season note"
    )
    # At least one archetype label
    assert "Power" in text or "Pitching" in text or "Balanced" in text, (
        "No archetype name found in season note"
    )


def test_no_individual_player_names(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """No note contains individual player names (descriptive, team-level only)."""
    # Player names in MLB context would be things like first+last name patterns.
    # The fixture uses team codes (BOS, TAM, MIA) — check that real human-name
    # patterns are absent from the *static* narrative text (trend descriptions).
    out = tmp_path / "out"
    result = build_style_trends(out, corpus_dir=synthetic_corpus)
    # Check no note mentions common real player first+last name
    # (the narrative is auto-generated with no player references by design)
    player_re = re.compile(
        r"\b(Ohtani|Verlander|deGrom|Scherzer|Trout|Harper)\b", re.IGNORECASE
    )
    for p in result:
        text = p.read_text(encoding="utf-8")
        match = player_re.search(text)
        assert match is None, (
            f"Player name '{match.group()}' found in {p.name} — notes must be player-free"
        )


def test_missing_corpus_raises(tmp_path: pathlib.Path) -> None:
    """build_style_trends raises FileNotFoundError when games.parquet is absent."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        build_style_trends(tmp_path / "out", corpus_dir=empty)


def test_idempotent(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """Two consecutive runs produce identical file contents."""
    out = tmp_path / "out"
    paths1 = build_style_trends(out, corpus_dir=synthetic_corpus)
    c1 = {p.name: p.read_text(encoding="utf-8") for p in paths1}
    paths2 = build_style_trends(out, corpus_dir=synthetic_corpus)
    c2 = {p.name: p.read_text(encoding="utf-8") for p in paths2}
    assert set(c1) == set(c2), "File set differs between runs"
    for name in c1:
        assert c1[name] == c2[name], f"{name} content differs between runs"
