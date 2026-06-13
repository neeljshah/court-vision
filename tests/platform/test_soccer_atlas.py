"""tests.platform.test_soccer_atlas — Acceptance tests for domains.soccer.atlas.

Uses a small synthetic matches fixture so no parquet I/O is needed.
Asserts structural invariants of the emitted Obsidian note graph.

Test matrix:
  1. build_atlas returns at least _Index.md + 1 team note + 1 league note.
  2. _Index.md contains valid YAML frontmatter + [[wikilink]] + #tags.
  3. At least one Teams/*.md exists with YAML frontmatter + wikilinks.
  4. At least one Leagues/*.md exists with YAML frontmatter + wikilinks.
  5. build_atlas is idempotent (run twice → same file count).
  6. No exceptions raised on valid synthetic corpus.
  7. FileNotFoundError raised on missing parquet.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from domains.soccer.atlas import build_atlas  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_corpus(tmp_path: Path) -> Path:
    """Build a minimal synthetic matches.parquet corpus with 4 teams, 2 divs."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    teams_e0 = ["Arsenal", "Chelsea", "ManCity", "Liverpool"]
    teams_sp1 = ["RealMadrid", "Barcelona", "Atletico", "Valencia"]

    rows = []
    eid = 1
    base = datetime.date(2023, 8, 5)

    for season, teams, div in [
        (2022, teams_e0, "E0"),
        (2022, teams_sp1, "SP1"),
        (2023, teams_e0, "E0"),
        (2023, teams_sp1, "SP1"),
        (2024, teams_e0, "E0"),
        (2024, teams_sp1, "SP1"),
    ]:
        day_offset = (season - 2023) * 200
        match_idx = 0
        for i, home in enumerate(teams):
            for j, away in enumerate(teams):
                if home == away:
                    continue
                date = base + datetime.timedelta(days=day_offset + match_idx * 7)
                # Vary scores to produce over+under outcomes
                if match_idx % 3 == 0:
                    fthg, ftag = 2, 1   # 3 goals → over
                elif match_idx % 3 == 1:
                    fthg, ftag = 1, 0   # 1 goal → under
                else:
                    fthg, ftag = 1, 1   # 2 goals → under
                total = fthg + ftag
                ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
                rows.append(dict(
                    event_id=f"ev{eid}",
                    date=str(date),
                    season=season,
                    div=div,
                    home_team=home,
                    away_team=away,
                    fthg=fthg,
                    ftag=ftag,
                    total_goals=total,
                    target_over25=1 if total >= 3 else 0,
                    ftr=ftr,
                ))
                eid += 1
                match_idx += 1

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(corpus_dir / "matches.parquet", index=False)
    return corpus_dir


def _has_frontmatter(text: str) -> bool:
    """Return True if the note begins with a YAML frontmatter block."""
    lines = text.splitlines()
    return len(lines) >= 3 and lines[0].strip() == "---"


def _has_wikilink(text: str) -> bool:
    """Return True if the note contains at least one [[...]] wikilink."""
    return "[[" in text and "]]" in text


def _has_tag(text: str) -> bool:
    """Return True if the note contains at least one #tag."""
    import re
    return bool(re.search(r"#[\w/]+", text))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# Synthetic fixture has ~18 matches/team; use min_matches=10 so team notes are emitted.
_TEST_MIN = 10


def test_build_atlas_returns_nonempty_list(tmp_path):
    """build_atlas must return a non-empty list of Paths."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    paths = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    assert isinstance(paths, list)
    assert len(paths) > 0, "build_atlas returned empty list"


def test_index_note_exists(tmp_path):
    """_Index.md must exist in out_dir."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    paths = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    path_names = [p.name for p in paths]
    assert "_Index.md" in path_names, f"_Index.md missing; got {path_names[:10]}"


def test_index_note_structure(tmp_path):
    """_Index.md must have frontmatter, wikilinks, and tags."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    idx = (out_dir / "_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(idx), "_Index.md missing YAML frontmatter"
    assert _has_wikilink(idx), "_Index.md missing [[wikilinks]]"
    assert _has_tag(idx), "_Index.md missing #tags"
    assert "sport: soccer" in idx, "_Index.md frontmatter missing sport: soccer"


def test_at_least_one_team_note(tmp_path):
    """At least one Teams/*.md note must be written."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    paths = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    team_notes = [p for p in paths if p.parent.name == "Teams"]
    assert len(team_notes) >= 1, "No team notes written"


def test_team_note_structure(tmp_path):
    """Team notes must have frontmatter and wikilinks."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    paths = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    team_notes = [p for p in paths if p.parent.name == "Teams"]
    assert team_notes, "No team notes to inspect"
    text = team_notes[0].read_text(encoding="utf-8")
    assert _has_frontmatter(text), f"{team_notes[0].name}: missing YAML frontmatter"
    assert _has_wikilink(text), f"{team_notes[0].name}: missing [[wikilinks]]"
    assert _has_tag(text), f"{team_notes[0].name}: missing #tags"


def test_at_least_one_league_note(tmp_path):
    """At least one Leagues/*.md note must be written."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    paths = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    league_notes = [p for p in paths if p.parent.name == "Leagues"]
    assert len(league_notes) >= 1, "No league notes written"


def test_league_note_structure(tmp_path):
    """League notes must have frontmatter and wikilinks."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    paths = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    league_notes = [p for p in paths if p.parent.name == "Leagues"]
    assert league_notes, "No league notes to inspect"
    text = league_notes[0].read_text(encoding="utf-8")
    assert _has_frontmatter(text), f"{league_notes[0].name}: missing YAML frontmatter"
    assert _has_wikilink(text), f"{league_notes[0].name}: missing [[wikilinks]]"


def test_idempotent(tmp_path):
    """Running build_atlas twice must produce the same file count."""
    corpus_dir = _make_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    paths1 = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    paths2 = build_atlas(out_dir, corpus_dir, min_matches=_TEST_MIN)
    assert len(paths1) == len(paths2), (
        f"Idempotency failed: first run={len(paths1)}, second run={len(paths2)}"
    )


def test_missing_corpus_raises(tmp_path):
    """build_atlas must raise FileNotFoundError for a missing corpus dir."""
    out_dir = tmp_path / "atlas"
    missing = tmp_path / "no_such_dir"
    with pytest.raises(FileNotFoundError):
        build_atlas(out_dir, missing)
