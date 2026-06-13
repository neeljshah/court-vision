"""tests.platform.test_soccer_seasons — Acceptance tests for domains.soccer.atlas_seasons.

Uses a tiny synthetic one-league one-season round-robin fixture (4 teams, 12 matches)
so no parquet I/O against the real corpus is needed.

Test matrix:
  1. build_seasons returns at least 1 season note + the index.
  2. _Seasons_Index.md exists, has frontmatter, wikilinks, tags.
  3. At least one season table note exists.
  4. Season note has YAML frontmatter, [[wikilinks]], #tags.
  5. Points are hand-computed correctly for one known fixture layout.
  6. Rank 1 team in the note matches the hand-computed champion.
  7. [[Team]] links are present in the season note body.
  8. Idempotent: second run produces the same file count.
  9. FileNotFoundError on missing corpus dir.
"""
from __future__ import annotations

import datetime
import re as _re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from domains.soccer.atlas_seasons import build_seasons  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------

def _make_corpus(tmp_path: Path, *, season: int = 2022, div: str = "E0") -> Path:
    """Build a minimal synthetic matches.parquet: 4 teams, 12 matches, one season."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    base = datetime.date(2022, 8, 6)
    matches = [
        # home, away, fthg, ftag
        ("Arsenal",   "Chelsea",   2, 0),
        ("Arsenal",   "ManCity",   1, 1),
        ("Arsenal",   "Liverpool", 3, 0),
        ("Chelsea",   "Arsenal",   0, 2),
        ("Chelsea",   "ManCity",   1, 1),
        ("Chelsea",   "Liverpool", 2, 0),
        ("ManCity",   "Arsenal",   3, 0),
        ("ManCity",   "Chelsea",   2, 1),
        ("ManCity",   "Liverpool", 1, 0),
        ("Liverpool", "Arsenal",   0, 0),
        ("Liverpool", "Chelsea",   0, 2),
        ("Liverpool", "ManCity",   1, 2),
    ]
    rows = []
    for idx, (home, away, fthg, ftag) in enumerate(matches):
        ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
        rows.append({
            "date": str(base + datetime.timedelta(days=idx * 7)),
            "season": season, "div": div,
            "home_team": home, "away_team": away,
            "fthg": fthg, "ftag": ftag,
            "ftr": ftr, "total_goals": fthg + ftag,
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(corpus_dir / "matches.parquet", index=False)
    return corpus_dir


def _expected_pts() -> dict:
    """Hand-computed points from the synthetic fixture.

    Arsenal:   W=3, D=2, L=1 → 11 pts
    ManCity:   W=4, D=2, L=0 → 14 pts
    Chelsea:   W=2, D=1, L=3 → 7 pts
    Liverpool: W=0, D=1, L=5 → 1 pt
    """
    return {"Arsenal": 11, "ManCity": 14, "Chelsea": 7, "Liverpool": 1}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    return len(lines) >= 3 and lines[0].strip() == "---"


def _has_wikilink(text: str) -> bool:
    return "[[" in text and "]]" in text


def _has_tag(text: str, tag: str = "#sport/soccer") -> bool:
    return tag in text


def _season_notes(paths: list) -> list:
    return [p for p in paths if p.name != "_Seasons_Index.md"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_seasons_returns_nonempty(tmp_path):
    paths = build_seasons(tmp_path / "out", _make_corpus(tmp_path))
    assert isinstance(paths, list) and len(paths) > 0, "build_seasons returned empty list"


def test_seasons_index_exists(tmp_path):
    paths = build_seasons(tmp_path / "out", _make_corpus(tmp_path))
    assert "_Seasons_Index.md" in [p.name for p in paths]


def test_seasons_index_structure(tmp_path):
    out = tmp_path / "out"
    build_seasons(out, _make_corpus(tmp_path))
    text = (out / "_Seasons_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "_Seasons_Index.md missing YAML frontmatter"
    assert _has_wikilink(text), "_Seasons_Index.md missing [[wikilinks]]"
    assert _has_tag(text), "_Seasons_Index.md missing #sport/soccer"
    assert "[[_Index]]" in text, "_Seasons_Index.md missing up-link [[_Index]]"


def test_at_least_one_season_note(tmp_path):
    paths = build_seasons(tmp_path / "out", _make_corpus(tmp_path))
    assert len(_season_notes(paths)) >= 1, "No season notes written"


def test_season_note_structure(tmp_path):
    paths = build_seasons(tmp_path / "out", _make_corpus(tmp_path))
    notes = _season_notes(paths)
    assert notes, "No season notes to inspect"
    text = notes[0].read_text(encoding="utf-8")
    assert _has_frontmatter(text), f"{notes[0].name}: missing YAML frontmatter"
    assert _has_wikilink(text), f"{notes[0].name}: missing [[wikilinks]]"
    assert _has_tag(text), f"{notes[0].name}: missing #sport/soccer"
    assert _has_tag(text, "#season"), f"{notes[0].name}: missing #season"


def test_correct_points_in_table(tmp_path):
    paths = build_seasons(tmp_path / "out", _make_corpus(tmp_path))
    notes = _season_notes(paths)
    assert notes
    text = notes[0].read_text(encoding="utf-8")
    for team, pts in _expected_pts().items():
        assert f"**{pts}**" in text, (
            f"Expected {team} to have {pts} pts in note, not found.\n"
            f"Note snippet: {text[:1500]}"
        )


def test_champion_correct(tmp_path):
    paths = build_seasons(tmp_path / "out", _make_corpus(tmp_path))
    notes = _season_notes(paths)
    assert notes
    text = notes[0].read_text(encoding="utf-8")
    assert 'champion: "ManCity"' in text, (
        f"Expected ManCity as champion (14 pts). Frontmatter snippet:\n{text[:400]}"
    )


def test_team_links_present(tmp_path):
    paths = build_seasons(tmp_path / "out", _make_corpus(tmp_path))
    text = _season_notes(paths)[0].read_text(encoding="utf-8")
    team_links = _re.findall(r"\[\[Teams/[^\]]+\]\]", text)
    assert len(team_links) >= 2, f"Expected ≥2 [[Teams/...]] links, found {len(team_links)}"


def test_idempotent(tmp_path):
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths1 = build_seasons(out, corpus)
    paths2 = build_seasons(out, corpus)
    assert len(paths1) == len(paths2), \
        f"Idempotency failed: run1={len(paths1)}, run2={len(paths2)}"


def test_missing_corpus_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_seasons(tmp_path / "out", tmp_path / "no_such_dir")


def test_season_index_links_resolve(tmp_path):
    """Season wikilinks in _Seasons_Index.md must resolve to actual written note stems.

    Regression: _season_link() must use ``"{_slug(display)} {season}"`` so the
    link target has a literal space before the year (matching the filename), not
    ``_slug(f"{display} {season}")`` which merges the space into an underscore.
    """
    out = tmp_path / "out"
    paths = build_seasons(out, _make_corpus(tmp_path))
    written_stems = {p.stem for p in paths if p.name != "_Seasons_Index.md"}
    idx_text = (out / "_Seasons_Index.md").read_text(encoding="utf-8")
    dangling = [
        m.group(1).strip()
        for m in _re.finditer(r"\[\[([^\]\|]+)(?:\|[^\]]*)?\]\]", idx_text)
        if _re.match(r".*\d{4}$", m.group(1).strip())
        and m.group(1).strip() not in written_stems
    ]
    assert dangling == [], f"_Seasons_Index.md dangling season links: {dangling[:5]}"
