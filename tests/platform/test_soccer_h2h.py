"""tests.platform.test_soccer_h2h — Acceptance tests for domains.soccer.atlas_h2h.

Tiny synthetic corpus with repeated pairings; no real parquet I/O required.

Tests: returns non-empty list · index has frontmatter/wikilinks/tags · index
links to [[_Index]] · fixture note emitted · note links BOTH teams · correct
meeting count · canonical filename order · sparse pairs excluded · idempotent ·
FileNotFoundError on missing corpus.
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from domains.soccer.atlas_h2h import build_h2h, _MIN_H2H_MEETINGS  # noqa: E402


# --- corpus builder ----------------------------------------------------------

def _make_corpus(tmp_path: Path) -> Path:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    rows = []
    eid = 1
    base = datetime.date(2023, 8, 5)

    def _add(home, away, hg, ag, div, season, off):
        nonlocal eid
        total = hg + ag
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        rows.append(dict(
            event_id=f"ev{eid}", date=str(base + datetime.timedelta(days=off)),
            season=season, div=div, home_team=home, away_team=away,
            fthg=hg, ftag=ag, total_goals=total,
            target_over25=1 if total >= 3 else 0, ftr=ftr,
        ))
        eid += 1

    # Arsenal vs Chelsea — 8 meetings
    for off, (home, away, hg, ag) in enumerate([
        ("Arsenal", "Chelsea",  2, 1), ("Chelsea", "Arsenal",  1, 1),
        ("Arsenal", "Chelsea",  0, 1), ("Chelsea", "Arsenal",  3, 0),
        ("Arsenal", "Chelsea",  2, 2), ("Chelsea", "Arsenal",  1, 2),
        ("Arsenal", "Chelsea",  1, 0), ("Chelsea", "Arsenal",  0, 0),
    ]):
        _add(home, away, hg, ag, "E0", 2023 + off // 4, off * 14)

    # Man City vs Liverpool — 6 meetings
    for off, (home, away, hg, ag) in enumerate([
        ("Man City", "Liverpool", 2, 0), ("Liverpool", "Man City", 1, 1),
        ("Man City", "Liverpool", 1, 2), ("Liverpool", "Man City", 0, 0),
        ("Man City", "Liverpool", 3, 1), ("Liverpool", "Man City", 2, 1),
    ]):
        _add(home, away, hg, ag, "E0", 2023 + off // 3, 200 + off * 14)

    # Spurs vs Everton — 2 meetings only (below threshold)
    _add("Spurs", "Everton", 1, 0, "E0", 2023, 400)
    _add("Everton", "Spurs",  2, 1, "E0", 2023, 414)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(corpus_dir / "matches.parquet", index=False)
    return corpus_dir


# --- helpers -----------------------------------------------------------------

def _has_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    return len(lines) >= 3 and lines[0].strip() == "---"

def _has_wikilink(text: str) -> bool:
    return "[[" in text and "]]" in text

def _has_tag(text: str) -> bool:
    return bool(re.search(r"#[\w/]+", text))

def _fixtures(paths):
    return [p for p in paths if p.name != "_Matchups_Index.md"]


# --- tests -------------------------------------------------------------------

def test_returns_nonempty(tmp_path):
    paths = build_h2h(tmp_path / "out", _make_corpus(tmp_path))
    assert len(paths) > 0

def test_index_structure(tmp_path):
    out = tmp_path / "out"
    build_h2h(out, _make_corpus(tmp_path))
    text = (out / "_Matchups_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text)
    assert _has_wikilink(text)
    assert _has_tag(text)

def test_index_links_up_to_atlas(tmp_path):
    out = tmp_path / "out"
    build_h2h(out, _make_corpus(tmp_path))
    text = (out / "_Matchups_Index.md").read_text(encoding="utf-8")
    assert "[[_Index" in text, "Missing up-link to [[_Index]]"

def test_fixture_notes_emitted(tmp_path):
    paths = build_h2h(tmp_path / "out", _make_corpus(tmp_path))
    assert len(_fixtures(paths)) >= 1

def test_fixture_note_links_both_teams(tmp_path):
    out = tmp_path / "out"
    paths = build_h2h(out, _make_corpus(tmp_path))
    p = next((x for x in paths if "Arsenal" in x.name and "Chelsea" in x.name), None)
    assert p is not None, "Arsenal vs Chelsea note not found"
    text = p.read_text(encoding="utf-8")
    assert "[[Teams/Arsenal|Arsenal]]" in text
    assert "[[Teams/Chelsea|Chelsea]]" in text

def test_fixture_note_correct_meeting_count(tmp_path):
    out = tmp_path / "out"
    paths = build_h2h(out, _make_corpus(tmp_path))
    p = next((x for x in paths if "Arsenal" in x.name and "Chelsea" in x.name), None)
    assert p is not None
    text = p.read_text(encoding="utf-8")
    assert "total_meetings: 8" in text

def test_canonical_filename_order(tmp_path):
    paths = build_h2h(tmp_path / "out", _make_corpus(tmp_path))
    for p in _fixtures(paths):
        if " vs " not in p.stem:
            continue
        a, b = p.stem.split(" vs ", 1)
        assert a <= b, f"Non-canonical filename: {p.name!r}"

def test_sparse_pairs_excluded(tmp_path):
    paths = build_h2h(tmp_path / "out", _make_corpus(tmp_path))
    assert not any("Spurs" in p.name and "Everton" in p.name for p in paths), (
        f"Sparse pair (below threshold={_MIN_H2H_MEETINGS}) produced a note"
    )

def test_idempotent(tmp_path):
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    assert len(build_h2h(out, corpus)) == len(build_h2h(out, corpus))

def test_missing_corpus_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_h2h(tmp_path / "out", tmp_path / "no_such_dir")

def test_fixture_has_frontmatter_and_tags(tmp_path):
    out = tmp_path / "out"
    paths = build_h2h(out, _make_corpus(tmp_path))
    fx = _fixtures(paths)
    assert fx
    text = fx[0].read_text(encoding="utf-8")
    assert _has_frontmatter(text)
    assert _has_tag(text)


def test_index_no_folder_wikilink(tmp_path):
    """_Matchups_Index.md must not contain bare [[Teams/]] folder links.

    Regression for a dangling-link bug where the index prose contained
    ``[[Teams/]]`` (a folder ref Obsidian cannot resolve to a note).
    """
    out = tmp_path / "out"
    build_h2h(out, _make_corpus(tmp_path))
    text = (out / "_Matchups_Index.md").read_text(encoding="utf-8")
    assert "[[Teams/]]" not in text, (
        "_Matchups_Index.md still contains dangling [[Teams/]] folder link"
    )
