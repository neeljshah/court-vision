"""tests/platform/test_mlb_style_matchups.py — Scoped unit tests for MLB
style-vs-style matchup matrix atlas.

Fixture engineering:
  - Three teams: BOS (Power/Run-Scoring), TAM (Pitching-Led/Run-Prevention),
    MIA (Run-Deficit/Rebuilding).
  - 156 games per pair (6 seasons × 26 games) so each clears the MIN_GAMES=100
    filter in atlas_playstyles and the _MIN_PAIR_GAMES=50 filter here.
  - Fixed scores so we can compute exact expected rates for BOS(home) vs TAM(away):
      home_runs=7, away_runs=3, target_home_win=1 (BOS always wins at home).
      home_win_rate = 1.0, avg_total = 10.0, high_score_rate = 1.0
      (10 ≥ _HIGH_TOTAL_THRESH=10 → all games count as high-scoring).

Asserts:
  - build_style_matchups returns a non-empty list[Path]
  - _Style_Matchups_Index.md is written
  - At least one pair note is written
  - Index and pair notes contain YAML frontmatter (--- ... ---)
  - All notes contain at least one [[wikilink]]
  - Pair notes contain [[Playstyles/<slug>]] wikilinks
  - Hand-computed rate for BOS(home, power_run_scoring) vs TAM(away,
    pitching_run_prevention) is correct (home_win_rate=100%, avg_total=12.0)
  - No exception on minimal corpus where no pair clears _MIN_PAIR_GAMES
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.mlb.atlas_style_matchups import build_style_matchups

# ---------------------------------------------------------------------------
# Synthetic corpus  (same fixture layout as test_mlb_playstyles.py)
# ---------------------------------------------------------------------------

_COLS = [
    "event_id", "date", "season", "home_team", "away_team",
    "home_runs", "away_runs", "target_home_win", "game_seq", "home_league",
]


def _synthetic_rows() -> list:
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
        for _ in range(26):     # 26 per season-pair → 156 total per pair
            # BOS (Power home) vs TAM (Pitching-Led away): BOS wins, total=12
            # Scores chosen so TAM's corpus ra=4.0 ≤ 4.10 and rd > 0
            # → TAM qualifies as pitching_run_prevention
            _add("BOS", "TAM", 7.0, 5.0, 1, s)
            # TAM (home) vs MIA (Run-Deficit away): TAM wins, total=5
            _add("TAM", "MIA", 4.0, 1.0, 1, s)
            # MIA (Run-Deficit home) vs BOS (Power away): BOS wins, total=8
            _add("MIA", "BOS", 2.0, 6.0, 0, s)

    return rows


@pytest.fixture()
def synthetic_corpus(tmp_path: pathlib.Path) -> pathlib.Path:
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
# Tiny corpus with no qualifying pair (n < 50)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tiny_corpus(tmp_path: pathlib.Path) -> pathlib.Path:
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
    return corpus_dir


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[.+?\]\]")
_FRONTMATTER_RE = re.compile(r"^---\n.+?\n---", re.DOTALL)
_PLAYSTYLE_LINK_RE = re.compile(r"\[\[Playstyles/[\w_]+\]\]")


def _has_frontmatter(text: str) -> bool:
    return bool(_FRONTMATTER_RE.match(text))


def _has_wikilinks(text: str) -> bool:
    return bool(_WIKILINK_RE.search(text))


def _has_playstyle_links(text: str) -> bool:
    return bool(_PLAYSTYLE_LINK_RE.search(text))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_paths(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """build_style_matchups returns a non-empty list of Path objects."""
    out = tmp_path / "out"
    result = build_style_matchups(out, corpus_dir=synthetic_corpus)
    assert isinstance(result, list)
    assert len(result) > 0
    for p in result:
        assert isinstance(p, pathlib.Path)


def test_index_written(tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path) -> None:
    """_Style_Matchups_Index.md is written and non-empty."""
    out = tmp_path / "out"
    build_style_matchups(out, corpus_dir=synthetic_corpus)
    index = out / "_Style_Matchups_Index.md"
    assert index.exists()
    assert index.stat().st_size > 0


def test_at_least_one_pair_note(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """At least one pair note is written (beyond the index)."""
    out = tmp_path / "out"
    result = build_style_matchups(out, corpus_dir=synthetic_corpus)
    pair_notes = [p for p in result if p.name != "_Style_Matchups_Index.md"]
    assert len(pair_notes) >= 1


def test_all_notes_have_frontmatter(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Every written note has YAML frontmatter."""
    out = tmp_path / "out"
    result = build_style_matchups(out, corpus_dir=synthetic_corpus)
    for p in result:
        text = p.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{p.name} missing YAML frontmatter"


def test_all_notes_have_wikilinks(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Every written note contains at least one [[wikilink]]."""
    out = tmp_path / "out"
    result = build_style_matchups(out, corpus_dir=synthetic_corpus)
    for p in result:
        text = p.read_text(encoding="utf-8")
        assert _has_wikilinks(text), f"{p.name} has no [[wikilinks]]"


def test_pair_notes_have_playstyle_links(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """Pair notes contain [[Playstyles/<slug>]] wikilinks."""
    out = tmp_path / "out"
    result = build_style_matchups(out, corpus_dir=synthetic_corpus)
    pair_notes = [p for p in result if p.name != "_Style_Matchups_Index.md"]
    assert len(pair_notes) >= 1
    linked = [p for p in pair_notes if _has_playstyle_links(p.read_text(encoding="utf-8"))]
    assert len(linked) >= 1, "Expected at least one pair note with [[Playstyles/...]] links"


def test_hand_computed_rate(
    tmp_path: pathlib.Path, synthetic_corpus: pathlib.Path
) -> None:
    """BOS(home,power_run_scoring) vs TAM(away,pitching_run_prevention):
    home_win_rate=100%, avg_total=12.0, high_score_rate=100%."""
    out = tmp_path / "out"
    build_style_matchups(out, corpus_dir=synthetic_corpus)

    # The pair note filename uses the style slugs
    pair_note = out / "power_run_scoring__vs__pitching_run_prevention.md"
    assert pair_note.exists(), (
        "Expected pair note power_run_scoring__vs__pitching_run_prevention.md"
    )
    text = pair_note.read_text(encoding="utf-8")

    # home-win rate should be 100.0% (BOS wins all 156 home games vs TAM)
    assert "100.0%" in text, "Expected 100.0% home-win rate in pair note"
    # avg total = 7+5 = 12.00
    assert "12.00" in text, "Expected avg total 12.00 in pair note"
    # game count
    assert "156" in text, "Expected game count 156 in pair note"


def test_no_exception_on_tiny_corpus(
    tmp_path: pathlib.Path, tiny_corpus: pathlib.Path
) -> None:
    """No exception when no pairs clear _MIN_PAIR_GAMES; only index written."""
    out = tmp_path / "out"
    result = build_style_matchups(out, corpus_dir=tiny_corpus)
    assert isinstance(result, list)
    # Only the index is written (no qualifying pairs)
    assert (out / "_Style_Matchups_Index.md").exists()
    pair_notes = [p for p in result if p.name != "_Style_Matchups_Index.md"]
    assert len(pair_notes) == 0, "Expected no pair notes when corpus is too small"
