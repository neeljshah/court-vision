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
    """Build a minimal synthetic matches.parquet with 4 teams in a single season.

    Match layout (round-robin home/away, 12 matches total):
      Arsenal  vs Chelsea    2-0  (H)
      Arsenal  vs ManCity    1-1  (D)
      Arsenal  vs Liverpool  3-1  (H)
      Chelsea  vs Arsenal    0-1  (A)   → Arsenal away win
      Chelsea  vs ManCity    2-2  (D)
      Chelsea  vs Liverpool  1-0  (H)
      ManCity  vs Arsenal    2-0  (H)
      ManCity  vs Chelsea    1-0  (H)
      ManCity  vs Liverpool  3-2  (H)
      Liverpool vs Arsenal   0-0  (D)
      Liverpool vs Chelsea   1-2  (A)   → Chelsea away win
      Liverpool vs ManCity   0-1  (A)   → ManCity away win

    Hand-computed final table:
      Arsenal:   H(2-0W, 1-1D, 3-1W)  A(1-0W* via Chelsea home, 0-0D)
        Actually must compute from the above rows carefully.

    Let's use a simpler deterministic layout for testability.
    4 teams × 3 opponents × 2 (H/A) = 12 matches.
    We define explicit results:
      Match 1:  Arsenal home, Chelsea away  → 2-0 (H)
      Match 2:  Arsenal home, ManCity away  → 1-1 (D)
      Match 3:  Arsenal home, Liverpool away → 3-0 (H)
      Match 4:  Chelsea home, Arsenal away  → 0-2 (A)   → Arsenal wins
      Match 5:  Chelsea home, ManCity away  → 1-1 (D)
      Match 6:  Chelsea home, Liverpool away → 2-0 (H)
      Match 7:  ManCity home, Arsenal away  → 3-0 (H)
      Match 8:  ManCity home, Chelsea away  → 2-1 (H)
      Match 9:  ManCity home, Liverpool away → 1-0 (H)
      Match 10: Liverpool home, Arsenal away  → 0-1 (A)
      Match 11: Liverpool home, Chelsea away  → 0-2 (A)
      Match 12: Liverpool home, ManCity away  → 1-2 (A)

    Arsenal results:  H(2-0W, 1-1D, 3-0W) → 7W, 1D, 0L home
                      A(0-2W*, 0-3L, 0-1L, 1-0W*) wait let me simplify.

    --- Simplified for readability ---
    We derive expected pts below from the actual rows we write.
    """
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    base = datetime.date(2022, 8, 6)
    rows = []
    matches = [
        # home, away, fthg, ftag
        ("Arsenal",   "Chelsea",   2, 0),   # Arsenal H win
        ("Arsenal",   "ManCity",   1, 1),   # draw
        ("Arsenal",   "Liverpool", 3, 0),   # Arsenal H win
        ("Chelsea",   "Arsenal",   0, 2),   # Arsenal A win
        ("Chelsea",   "ManCity",   1, 1),   # draw
        ("Chelsea",   "Liverpool", 2, 0),   # Chelsea H win
        ("ManCity",   "Arsenal",   3, 0),   # ManCity H win
        ("ManCity",   "Chelsea",   2, 1),   # ManCity H win
        ("ManCity",   "Liverpool", 1, 0),   # ManCity H win
        ("Liverpool", "Arsenal",   0, 0),   # draw
        ("Liverpool", "Chelsea",   0, 2),   # Chelsea A win
        ("Liverpool", "ManCity",   1, 2),   # ManCity A win
    ]
    for idx, (home, away, fthg, ftag) in enumerate(matches):
        ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
        total = fthg + ftag
        rows.append({
            "date": str(base + datetime.timedelta(days=idx * 7)),
            "season": season,
            "div": div,
            "home_team": home,
            "away_team": away,
            "fthg": fthg,
            "ftag": ftag,
            "ftr": ftr,
            "total_goals": total,
        })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(corpus_dir / "matches.parquet", index=False)
    return corpus_dir


def _expected_pts() -> dict:
    """Return hand-computed points for the synthetic fixture above."""
    # Arsenal: W(H vs Chelsea), D(H vs ManCity), W(H vs Liverpool),
    #          W(A at Chelsea), D(A at Liverpool), L(A at ManCity)
    #   → W=3, D=2, L=1 → 3*3+2 = 11
    # ManCity: W(H vs Arsenal), W(H vs Chelsea), W(H vs Liverpool), W(A at Liverpool)
    #          L(A at Arsenal) → wait Arsenal wins 2-0 when visiting Chelsea,
    #          but ManCity vs Arsenal: ManCity 3-0 → ManCity wins at home vs Arsenal
    #          Arsenal wins away at Chelsea (Chelsea 0 Arsenal 2).
    # Re-derive cleanly from the match list:
    # Arsenal home: vs Chelsea W, vs ManCity D, vs Liverpool W  → 3+1+3=7
    # Arsenal away: at Chelsea (Chelsea 0-2 → Arsenal W), at ManCity (3-0 → Arsenal L),
    #               at Liverpool (0-0 D)                          → 3+0+1=4
    # Arsenal total: W=3, D=2, L=1, pts=11
    #
    # Chelsea home: vs Arsenal L(0-2), vs ManCity D(1-1), vs Liverpool W(2-0) → 0+1+3=4
    # Chelsea away: at Arsenal L(2-0), at ManCity L(2-1), at Liverpool W(0-2) → 0+0+3=3
    # Chelsea total: W=2, D=1, L=3, pts=7
    #
    # ManCity home: vs Arsenal W(3-0), vs Chelsea W(2-1), vs Liverpool W(1-0) → 9
    # ManCity away: at Arsenal D(1-1), at Chelsea D(1-1), at Liverpool W(1-2) → 1+1+3=5
    # ManCity total: W=4, D=2, L=0, pts=14
    #
    # Liverpool home: vs Arsenal D(0-0), vs Chelsea L(0-2), vs ManCity L(1-2) → 1+0+0=1
    # Liverpool away: at Arsenal L(3-0), at Chelsea L(2-0), at ManCity L(1-0) → 0+0+0=0
    # Liverpool total: W=0, D=1, L=5, pts=1
    return {
        "Arsenal": 11,
        "ManCity": 14,
        "Chelsea": 7,
        "Liverpool": 1,
    }


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_seasons_returns_nonempty(tmp_path):
    """build_seasons must return a non-empty list."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths = build_seasons(out, corpus)
    assert isinstance(paths, list)
    assert len(paths) > 0, "build_seasons returned empty list"


def test_seasons_index_exists(tmp_path):
    """_Seasons_Index.md must be written."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths = build_seasons(out, corpus)
    names = [p.name for p in paths]
    assert "_Seasons_Index.md" in names, f"_Seasons_Index.md missing; got {names}"


def test_seasons_index_structure(tmp_path):
    """_Seasons_Index.md must have frontmatter, wikilinks, and #sport/soccer tag."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    build_seasons(out, corpus)
    text = (out / "_Seasons_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "_Seasons_Index.md missing YAML frontmatter"
    assert _has_wikilink(text), "_Seasons_Index.md missing [[wikilinks]]"
    assert _has_tag(text), "_Seasons_Index.md missing #sport/soccer"
    assert "[[_Index]]" in text, "_Seasons_Index.md missing up-link [[_Index]]"


def test_at_least_one_season_note(tmp_path):
    """At least one season table note (non-index) must be written."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths = build_seasons(out, corpus)
    season_notes = [p for p in paths if p.name != "_Seasons_Index.md"]
    assert len(season_notes) >= 1, "No season notes written"


def test_season_note_structure(tmp_path):
    """Season note must have frontmatter, wikilinks, and tags."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths = build_seasons(out, corpus)
    season_notes = [p for p in paths if p.name != "_Seasons_Index.md"]
    assert season_notes, "No season notes to inspect"
    text = season_notes[0].read_text(encoding="utf-8")
    assert _has_frontmatter(text), f"{season_notes[0].name}: missing YAML frontmatter"
    assert _has_wikilink(text), f"{season_notes[0].name}: missing [[wikilinks]]"
    assert _has_tag(text), f"{season_notes[0].name}: missing #sport/soccer"
    assert _has_tag(text, "#season"), f"{season_notes[0].name}: missing #season"


def test_correct_points_in_table(tmp_path):
    """Points in the rendered table must match hand-computed expected values."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths = build_seasons(out, corpus)
    season_notes = [p for p in paths if p.name != "_Seasons_Index.md"]
    assert season_notes
    text = season_notes[0].read_text(encoding="utf-8")

    expected = _expected_pts()
    for team, pts in expected.items():
        # Each row in the table looks like: | rank | [[Teams/Arsenal|Arsenal]] | ... | **11** |
        assert f"**{pts}**" in text, (
            f"Expected {team} to have {pts} pts in note, not found.\n"
            f"Note snippet: {text[:1500]}"
        )


def test_champion_correct(tmp_path):
    """The champion frontmatter must match the team with the most points."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths = build_seasons(out, corpus)
    season_notes = [p for p in paths if p.name != "_Seasons_Index.md"]
    assert season_notes
    text = season_notes[0].read_text(encoding="utf-8")
    # ManCity has 14 pts — top of table
    assert 'champion: "ManCity"' in text, (
        f"Expected ManCity as champion (14 pts). Frontmatter snippet:\n{text[:400]}"
    )


def test_team_links_present(tmp_path):
    """Season note must contain [[Teams/...]] wikilinks for at least 2 teams."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths = build_seasons(out, corpus)
    season_notes = [p for p in paths if p.name != "_Seasons_Index.md"]
    text = season_notes[0].read_text(encoding="utf-8")
    import re
    team_links = re.findall(r"\[\[Teams/[^\]]+\]\]", text)
    assert len(team_links) >= 2, (
        f"Expected ≥2 [[Teams/...]] links, found {len(team_links)}"
    )


def test_idempotent(tmp_path):
    """Running build_seasons twice must produce the same file count."""
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    paths1 = build_seasons(out, corpus)
    paths2 = build_seasons(out, corpus)
    assert len(paths1) == len(paths2), (
        f"Idempotency failed: run1={len(paths1)}, run2={len(paths2)}"
    )


def test_missing_corpus_raises(tmp_path):
    """build_seasons must raise FileNotFoundError on a missing corpus."""
    out = tmp_path / "out"
    missing = tmp_path / "no_such_dir"
    with pytest.raises(FileNotFoundError):
        build_seasons(out, missing)
