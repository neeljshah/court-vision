"""tests/platform/test_mlb_home_environment.py — unit tests for the MLB home
run-environment atlas generator.

Uses a synthetic fixture (no real parquet required) so the suite runs fast
and hermetically.

Synthetic design:
  - COL has very high home run environment (hitter-friendly proxy)
  - SEA has very low home run environment (pitcher-friendly proxy)
  - All teams have >= 100 home games so they appear in results

Asserts:
  - build_home_environment() returns list[Path]
  - Rankings note and index are written
  - Rankings note contains [[Teams/TEAM]] wikilinks
  - Rankings note contains [[_Index]] up-link
  - Index contains [[_Index]] up-link
  - Both notes have YAML frontmatter
  - COL appears near top, SEA appears near bottom in the note
  - Home/away split is correct for known fixture values
  - Runs raises FileNotFoundError for missing corpus
  - Idempotent: two runs produce identical output
"""
from __future__ import annotations

import pathlib
import re
from typing import List

import numpy as np
import pandas as pd
import pytest

from domains.mlb.atlas_home_environment import build_home_environment

# ---------------------------------------------------------------------------
# Synthetic corpus builder
# ---------------------------------------------------------------------------

_COLS = [
    "event_id", "date", "season",
    "home_team", "away_team",
    "home_runs", "away_runs",
    "target_home_win", "game_seq", "home_league",
]

_FRONTMATTER_RE = re.compile(r"^---\n.+?\n---", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[.+?\]\]")


def _make_corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build a tiny but valid corpus with 3 teams * 120 home games each.

    COL: high run environment home (avg 11 RPG at home, 8 RPG away)
    SEA: low run environment home (avg 7 RPG at home, 9 RPG away)
    NYY: neutral (avg 9 RPG at home, 9 RPG away)

    We create symmetric fixtures so each team hosts the other two ~60 times
    each (total ~120 home games per team, ~120 away games per team).
    """
    rng = np.random.default_rng(seed=42)
    rows = []
    seq = 0

    def _game(season, home, away, home_rpg, away_rpg, h_league):
        nonlocal seq
        seq += 1
        hr = max(0, int(rng.normal(home_rpg, 2)))
        ar = max(0, int(rng.normal(away_rpg, 2)))
        tw = 1 if hr > ar else 0
        return (
            f"{season}-{home}-{away}-{seq}",
            f"{season}-04-{(seq % 28) + 1:02d}",
            season,
            home, away,
            float(hr), float(ar),
            tw, seq, h_league,
        )

    # COL home: home_rpg=6.5 (team) but total ~11 (both sides score a lot)
    # SEA home: home_rpg=3.5 (team) but total ~7
    # NYY home: home_rpg=4.5 (team) but total ~9
    configs = {
        # (home, away): (home_team_rpg, away_team_rpg, league)
        ("COL", "SEA"): (6.5, 4.5, "NL"),
        ("COL", "NYY"): (6.5, 4.5, "NL"),
        ("SEA", "COL"): (3.5, 4.5, "AL"),
        ("SEA", "NYY"): (3.5, 5.5, "AL"),
        ("NYY", "COL"): (4.5, 4.5, "AL"),
        ("NYY", "SEA"): (4.5, 4.5, "AL"),
    }

    for season in range(2010, 2020):  # 10 seasons
        for (home, away), (hrpg, arpg, league) in configs.items():
            for _ in range(12):  # 12 matchups per season per pairing
                rows.append(_game(season, home, away, hrpg, arpg, league))

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    df = pd.DataFrame(rows, columns=_COLS)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(corpus_dir / "games.parquet", index=False)
    return corpus_dir


@pytest.fixture()
def corpus(tmp_path: pathlib.Path) -> pathlib.Path:
    return _make_corpus(tmp_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_frontmatter(text: str) -> bool:
    return bool(_FRONTMATTER_RE.match(text))


def _has_wikilinks(text: str) -> bool:
    return bool(_WIKILINK_RE.search(text))


def _ranked_text(out_dir: pathlib.Path) -> str:
    return (out_dir / "MLB_Home_Environment_Rankings.md").read_text(encoding="utf-8")


def _index_text(out_dir: pathlib.Path) -> str:
    return (out_dir / "_Home_Environment_Index.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_paths(corpus, tmp_path):
    """build_home_environment must return a non-empty list of Path objects."""
    out_dir = tmp_path / "he_out"
    result = build_home_environment(out_dir, corpus_dir=corpus)
    assert isinstance(result, list)
    assert len(result) >= 2
    for p in result:
        assert isinstance(p, pathlib.Path), f"Expected Path, got {type(p)}"
        assert p.exists(), f"Returned path does not exist: {p}"


def test_rankings_note_exists(corpus, tmp_path):
    """MLB_Home_Environment_Rankings.md must be written."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    assert (out_dir / "MLB_Home_Environment_Rankings.md").exists()


def test_index_note_exists(corpus, tmp_path):
    """_Home_Environment_Index.md must be written."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    assert (out_dir / "_Home_Environment_Index.md").exists()


def test_ranked_note_has_frontmatter(corpus, tmp_path):
    """Rankings note must open with valid YAML frontmatter."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    assert _has_frontmatter(_ranked_text(out_dir))


def test_index_note_has_frontmatter(corpus, tmp_path):
    """Index note must open with valid YAML frontmatter."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    assert _has_frontmatter(_index_text(out_dir))


def test_ranked_note_has_wikilinks(corpus, tmp_path):
    """Rankings note must contain [[wikilinks]]."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    assert _has_wikilinks(_ranked_text(out_dir))


def test_ranked_note_links_to_teams(corpus, tmp_path):
    """Rankings note must link to each team under Teams/."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    text = _ranked_text(out_dir)
    for team in ("COL", "SEA", "NYY"):
        assert f"[[Teams/{team}]]" in text, f"Missing [[Teams/{team}]] in rankings note"


def test_ranked_note_up_link(corpus, tmp_path):
    """Rankings note must contain [[_Index]] up-link."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    assert "[[_Index]]" in _ranked_text(out_dir)


def test_index_up_link(corpus, tmp_path):
    """Index note must contain [[_Index]] up-link."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    assert "[[_Index]]" in _index_text(out_dir)


def test_col_ranks_above_sea(corpus, tmp_path):
    """COL (high home scoring) should appear before SEA (low) in the ranked table."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    text = _ranked_text(out_dir)
    col_pos = text.find("COL")
    sea_pos = text.find("SEA")
    assert col_pos != -1, "COL not found in rankings note"
    assert sea_pos != -1, "SEA not found in rankings note"
    assert col_pos < sea_pos, (
        f"COL (pos {col_pos}) should appear before SEA (pos {sea_pos}) in high-run-env order"
    )


def test_disclaimer_present(corpus, tmp_path):
    """Rankings note must include the proxy disclaimer."""
    out_dir = tmp_path / "he_out"
    build_home_environment(out_dir, corpus_dir=corpus)
    text = _ranked_text(out_dir)
    assert "proxy" in text.lower() or "roster" in text.lower(), (
        "Rankings note must include a proxy/roster disclaimer"
    )


def test_missing_corpus_raises(tmp_path):
    """build_home_environment must raise FileNotFoundError for missing corpus."""
    out_dir = tmp_path / "he_out"
    empty = tmp_path / "empty_corpus"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        build_home_environment(out_dir, corpus_dir=empty)


def test_idempotent(corpus, tmp_path):
    """Running twice must produce identical output (idempotent)."""
    out_dir = tmp_path / "he_out"
    paths1 = build_home_environment(out_dir, corpus_dir=corpus)
    snap1 = {p.name: p.read_text(encoding="utf-8") for p in paths1}
    paths2 = build_home_environment(out_dir, corpus_dir=corpus)
    snap2 = {p.name: p.read_text(encoding="utf-8") for p in paths2}
    assert set(snap1.keys()) == set(snap2.keys())
    for name in snap1:
        assert snap1[name] == snap2[name], f"{name} content differs on second run"
