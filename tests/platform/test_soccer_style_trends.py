"""tests.platform.test_soccer_style_trends — Acceptance tests for
domains.soccer.atlas_style_trends.

Synthetic multi-season fixture, no real parquet I/O required.

Tests
-----
- build_style_trends returns non-empty list
- overview note exists with frontmatter, [[wikilinks]], and #tags
- overview note has ASCII trend table (Season column header)
- overview note links to [[_Playstyles_Index]]
- at least one per-season snapshot note is emitted
- each snapshot note has frontmatter, wikilinks, and scheme distribution table
- snapshot notes contain over25_rate and goals_pg frontmatter
- no edge/betting language in any emitted note
- idempotent: second run returns same file count
- missing corpus raises FileNotFoundError
- per-season scoring metrics are sane (goals_pg > 0)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from domains.soccer.atlas_style_trends import build_style_trends  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic corpus builder — two seasons, two divisions
# ---------------------------------------------------------------------------


def _make_corpus(tmp_path: Path) -> Path:
    """Build a minimal multi-season matches.parquet."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    rows: List[dict] = []
    eid = 1

    def _add(
        home: str,
        away: str,
        hg: int,
        ag: int,
        season: int,
        div: str = "E0",
        n_rep: int = 12,
    ) -> None:
        nonlocal eid
        total = hg + ag
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        for i in range(n_rep):
            rows.append({
                "event_id": f"ev{eid}",
                "date": f"{season}-08-{(i % 28) + 1:02d}",
                "season": season,
                "div": div,
                "home_team": home,
                "away_team": away,
                "fthg": hg,
                "ftag": ag,
                "total_goals": total,
                "target_over25": 1 if total >= 3 else 0,
                "ftr": ftr,
            })
            eid += 1

    # Season 2019 — lower scoring (many 1-1 draws → Under)
    for pair in [("TeamA", "TeamB"), ("TeamC", "TeamD"),
                 ("TeamE", "TeamF"), ("TeamG", "TeamH")]:
        _add(pair[0], pair[1], 1, 1, season=2019, n_rep=14)  # draw, Under
        _add(pair[1], pair[0], 1, 0, season=2019, n_rep=12)  # win, Under

    # Season 2023 — higher scoring (3-2 games → Over)
    for pair in [("TeamA", "TeamB"), ("TeamC", "TeamD"),
                 ("TeamE", "TeamF"), ("TeamG", "TeamH")]:
        _add(pair[0], pair[1], 3, 2, season=2023, n_rep=14)  # Over
        _add(pair[1], pair[0], 2, 1, season=2023, n_rep=12)  # Over

    # Season 2021 — mixed mid-point
    for pair in [("TeamA", "TeamB"), ("TeamC", "TeamD"),
                 ("TeamE", "TeamF"), ("TeamG", "TeamH")]:
        _add(pair[0], pair[1], 2, 1, season=2021, n_rep=13)  # Over
        _add(pair[1], pair[0], 1, 1, season=2021, n_rep=12)  # draw, Under

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(corpus_dir / "matches.parquet", index=False)
    return corpus_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    return len(lines) >= 3 and lines[0].strip() == "---"


def _has_wikilink(text: str) -> bool:
    return bool(re.search(r"\[\[.*?\]\]", text))


def _has_tag(text: str) -> bool:
    return bool(re.search(r"#[\w/\-]+", text))


def _overview_text(out_dir: Path) -> str:
    return (out_dir / "_Style_Trends_Overview.md").read_text(encoding="utf-8")


def _snapshot_notes(paths: List[Path]) -> List[Path]:
    return [p for p in paths if p.name.endswith("_scheme_snapshot.md")]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_nonempty(tmp_path: Path) -> None:
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    assert len(paths) > 0


def test_overview_exists_with_frontmatter(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_trends(out, _make_corpus(tmp_path))
    text = _overview_text(out)
    assert _has_frontmatter(text), "Overview missing YAML frontmatter"


def test_overview_has_wikilinks(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_trends(out, _make_corpus(tmp_path))
    assert _has_wikilink(_overview_text(out)), "Overview missing [[wikilinks]]"


def test_overview_has_tags(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_trends(out, _make_corpus(tmp_path))
    assert _has_tag(_overview_text(out)), "Overview missing #tags"


def test_overview_has_ascii_table(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_trends(out, _make_corpus(tmp_path))
    text = _overview_text(out)
    assert "Season" in text, "Overview missing trend table Season column"
    assert "Goals/G" in text, "Overview missing Goals/G column"
    assert "O2.5%" in text, "Overview missing O2.5% column"


def test_overview_links_to_playstyles(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_trends(out, _make_corpus(tmp_path))
    assert "_Playstyles_Index" in _overview_text(out), (
        "Overview missing link to [[_Playstyles_Index]]"
    )


def test_at_least_one_snapshot(tmp_path: Path) -> None:
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    assert len(_snapshot_notes(paths)) >= 1, "No per-season snapshot notes emitted"


def test_snapshot_count_matches_seasons(tmp_path: Path) -> None:
    """3 seasons in corpus → 3 snapshot notes."""
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    snapshots = _snapshot_notes(paths)
    assert len(snapshots) == 3, f"Expected 3 snapshot notes; got {len(snapshots)}"


def test_snapshot_frontmatter(tmp_path: Path) -> None:
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    for p in _snapshot_notes(paths):
        text = p.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{p.name}: missing YAML frontmatter"
        assert "over25_rate" in text, f"{p.name}: missing over25_rate frontmatter"
        assert "goals_pg" in text, f"{p.name}: missing goals_pg frontmatter"


def test_snapshot_has_wikilinks(tmp_path: Path) -> None:
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    for p in _snapshot_notes(paths):
        text = p.read_text(encoding="utf-8")
        assert _has_wikilink(text), f"{p.name}: missing [[wikilinks]]"


def test_snapshot_has_scheme_table(tmp_path: Path) -> None:
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    for p in _snapshot_notes(paths):
        text = p.read_text(encoding="utf-8")
        assert "Scheme" in text and "Share" in text, (
            f"{p.name}: missing Scheme | Share table"
        )


def test_per_season_scoring_sane(tmp_path: Path) -> None:
    """Extracted goals_pg values must be > 0 (corpus has real goals scored)."""
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    for p in _snapshot_notes(paths):
        text = p.read_text(encoding="utf-8")
        m = re.search(r"goals_pg:\s*([\d.]+)", text)
        assert m, f"{p.name}: could not parse goals_pg"
        assert float(m.group(1)) > 0.0, f"{p.name}: goals_pg is zero"


def test_2023_over_rate_higher_than_2019(tmp_path: Path) -> None:
    """Corpus is constructed so 2023 has all-Over scores; 2019 has mostly Under."""
    out = tmp_path / "out"
    build_style_trends(out, _make_corpus(tmp_path))

    def _over_rate(year: int) -> float:
        p = out / f"{year}_scheme_snapshot.md"
        text = p.read_text(encoding="utf-8")
        m = re.search(r"over25_rate:\s*([\d.]+)", text)
        assert m, f"Could not parse over25_rate from {year} snapshot"
        return float(m.group(1))

    assert _over_rate(2023) > _over_rate(2019), (
        "2023 should have higher Over-2.5 rate than 2019 in this corpus"
    )


def test_no_edge_language(tmp_path: Path) -> None:
    """Notes must not contain betting-edge language."""
    banned = re.compile(r"\b(ROI|edge|expected value|EV|bet|wager|arbitrage)\b", re.I)
    paths = build_style_trends(tmp_path / "out", _make_corpus(tmp_path))
    for p in paths:
        text = p.read_text(encoding="utf-8")
        m = banned.search(text)
        assert m is None, f"{p.name}: found edge language '{m.group()}'"


def test_idempotent(tmp_path: Path) -> None:
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    n1 = len(build_style_trends(out, corpus))
    n2 = len(build_style_trends(out, corpus))
    assert n1 == n2, f"Idempotency failed: first={n1}, second={n2}"


def test_missing_corpus_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_style_trends(tmp_path / "out", tmp_path / "no_such_dir")
