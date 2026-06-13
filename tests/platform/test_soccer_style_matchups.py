"""tests.platform.test_soccer_style_matchups — Acceptance tests for
domains.soccer.atlas_style_matchups.

Tiny synthetic corpus; no real parquet I/O required.  Corpus has two clear
tactical archetypes (High-Scoring Attacking home vs Defensive Low-Block away)
meeting ≥50 times so a pair note is always emitted for that pairing.

Tests
-----
- build returns non-empty list
- index note exists with YAML frontmatter, wikilinks, and #tags
- index links up to [[_Index]] (soccer atlas root)
- at least one pair note emitted
- pair note contains [[Playstyles/...]] wikilinks
- pair note has YAML frontmatter and #tags
- hand case: correct home-win count for a hand-crafted fixture mix
- hand case: over-2.5 rate correct for deterministic scores
- missing corpus raises FileNotFoundError
- idempotent second run returns same count
- pair notes use the <SchemeA>_vs_<SchemeB> filename stem convention
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

from domains.soccer.atlas_style_matchups import build_style_matchups  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic corpus builder
# ---------------------------------------------------------------------------


def _make_corpus(tmp_path: Path, n_pair: int = 60) -> Path:
    """Build matches.parquet with two dominant teams that drive two clear schemes.

    Team layout
    -----------
    - "Striker FC"  (High-Scoring Attacking: GF/game ≥ 1.60, Over ≥ 58%)
      Plays home  n_pair times as host at 3-1 vs "Dummy Away"
      Also plays  n_pair times away against "Dummy Away" winning 3-1
    - "Stone Wall"  (Defensive Low-Block: GA ≤ 1.15, CS ≥ 31%, Over ≤ 49%)
      Always 1-0 home wins and 1-0 away wins

    The interesting fixture is Striker FC (home) vs Stone Wall (away):
      - 40 matches at 3-0 (over25=0 since 3>2 but 3≥3 → over25=1 actually,
        wait: over25 means >2.5, i.e., total>=3 → 3-0 = 3 goals → over25=1)
      - 20 matches at 2-0 (2 goals → over25=0)
    So: home_wins=60, draws=0, away_wins=0, over25=40
    over25_rate = 40/60 ≈ 0.667; home_win_rate = 1.0

    We give all teams enough appearances (≥30) to be classified,
    and enough pair meetings (≥50 by default) so a note is always emitted.
    """
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    rows: List[dict] = []
    eid = 0

    def _add(home: str, away: str, hg: int, ag: int, n: int = 1) -> None:
        nonlocal eid
        total = hg + ag
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        for i in range(n):
            rows.append({
                "event_id": f"ev{eid}",
                "date": f"2023-09-{(eid % 28) + 1:02d}",
                "season": 2023,
                "div": "E0",
                "home_team": home,
                "away_team": away,
                "fthg": hg,
                "ftag": ag,
                "total_goals": total,
                "target_over25": 1 if total >= 3 else 0,
                "ftr": ftr,
            })
            eid += 1

    # ------------------------------------------------------------------ #
    # Striker FC — High-Scoring Attacking
    # ------------------------------------------------------------------ #
    # home: 3-1 → gf_h_pg=3, over=1 (total=4), btts=1  ×(n_pair + 5 extra)
    _add("Striker FC", "Dummy Away", 3, 1, n=n_pair + 5)
    # away: 3-1 → gf_a_pg=3 (they score 3 as away = ftag)
    _add("Dummy Away", "Striker FC", 1, 3, n=n_pair + 5)
    # Striker FC stats: GF/game=3, Over=100% → High-Scoring Attacking ✓

    # ------------------------------------------------------------------ #
    # Stone Wall — Defensive Low-Block
    # ------------------------------------------------------------------ #
    # home: 1-0 → ga_h=0, cs=1, over=0  ×(n_pair + 5 extra)
    _add("Stone Wall", "Dummy Home", 1, 0, n=n_pair + 5)
    # away: 0-1 (Stone Wall loses as away in this role — that's fine for GA)
    # We want GA≤1.15: home ga=0, away ga= ftag when Stone Wall is away_team
    # Stone Wall away: fthg=0, ftag=1 → Stone Wall score=1, concede=0 ✓
    _add("Dummy Home", "Stone Wall", 0, 1, n=n_pair + 5)
    # Stone Wall: GA/game=0 (clean sheet every match) → Defensive Low-Block ✓

    # ------------------------------------------------------------------ #
    # Main fixture: Striker FC (home) vs Stone Wall (away)
    #   40 at 3-0 (over25=1), 20 at 2-0 (over25=0)
    # ------------------------------------------------------------------ #
    n_over = (n_pair * 2) // 3      # 40 when n_pair=60
    n_under = n_pair - n_over       # 20 when n_pair=60
    _add("Striker FC", "Stone Wall", 3, 0, n=n_over)    # home wins, over=1
    _add("Striker FC", "Stone Wall", 2, 0, n=n_under)   # home wins, over=0

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


def _pair_notes(paths: List[Path]) -> List[Path]:
    return [p for p in paths if p.name != "_Style_Matchups_Index.md"]


def _index_text(out: Path) -> str:
    return (out / "_Style_Matchups_Index.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_nonempty(tmp_path: Path) -> None:
    paths = build_style_matchups(tmp_path / "out", _make_corpus(tmp_path))
    assert len(paths) > 0


def test_index_exists_with_frontmatter(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_matchups(out, _make_corpus(tmp_path))
    assert _has_frontmatter(_index_text(out)), "Index missing YAML frontmatter"


def test_index_has_wikilinks(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_matchups(out, _make_corpus(tmp_path))
    assert _has_wikilink(_index_text(out)), "Index missing [[wikilinks]]"


def test_index_has_tags(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_matchups(out, _make_corpus(tmp_path))
    assert _has_tag(_index_text(out)), "Index missing #tags"


def test_index_links_up_to_soccer_index(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_style_matchups(out, _make_corpus(tmp_path))
    assert "[[_Index" in _index_text(out), "Index missing up-link to [[_Index]]"


def test_at_least_one_pair_note(tmp_path: Path) -> None:
    paths = build_style_matchups(tmp_path / "out", _make_corpus(tmp_path))
    assert len(_pair_notes(paths)) >= 1, "No pair notes emitted"


def test_pair_note_has_playstyles_wikilinks(tmp_path: Path) -> None:
    """Every pair note must contain [[Playstyles/...]] wikilinks."""
    paths = build_style_matchups(tmp_path / "out", _make_corpus(tmp_path))
    for p in _pair_notes(paths):
        text = p.read_text(encoding="utf-8")
        assert "[[Playstyles/" in text, f"{p.name} missing [[Playstyles/...]] link"


def test_pair_note_has_frontmatter_and_tags(tmp_path: Path) -> None:
    paths = build_style_matchups(tmp_path / "out", _make_corpus(tmp_path))
    for p in _pair_notes(paths):
        text = p.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{p.name} missing YAML frontmatter"
        assert _has_tag(text), f"{p.name} missing #tags"


def test_hand_case_home_win_rate(tmp_path: Path) -> None:
    """Striker FC (home) vs Stone Wall (away): all 60 matches are home wins."""
    n_pair = 60
    out = tmp_path / "out"
    build_style_matchups(out, _make_corpus(tmp_path, n_pair=n_pair), min_pair_meetings=n_pair)
    stem = "High-Scoring_Attacking_vs_Defensive_Low-Block"
    note_path = out / f"{stem}.md"
    assert note_path.exists(), f"Expected pair note at {stem}.md"
    text = note_path.read_text(encoding="utf-8")
    # All 60 fixtures are home wins → home_wins = 60
    m = re.search(r"home_win_rate:\s*([0-9.]+)", text)
    assert m, "home_win_rate not found in frontmatter"
    rate = float(m.group(1))
    assert abs(rate - 1.0) < 0.01, f"Expected home_win_rate≈1.0 got {rate}"


def test_hand_case_over25_rate(tmp_path: Path) -> None:
    """40/60 matches are over-2.5 → over25_rate ≈ 0.667."""
    n_pair = 60
    out = tmp_path / "out"
    build_style_matchups(out, _make_corpus(tmp_path, n_pair=n_pair), min_pair_meetings=n_pair)
    stem = "High-Scoring_Attacking_vs_Defensive_Low-Block"
    text = (out / f"{stem}.md").read_text(encoding="utf-8")
    m = re.search(r"over25_rate:\s*([0-9.]+)", text)
    assert m, "over25_rate not found in frontmatter"
    rate = float(m.group(1))
    expected = (n_pair * 2 // 3) / n_pair
    assert abs(rate - expected) < 0.02, f"Expected over25_rate≈{expected:.3f} got {rate}"


def test_pair_note_filename_convention(tmp_path: Path) -> None:
    """Pair note filenames must follow <SchemeA>_vs_<SchemeB>.md pattern."""
    paths = build_style_matchups(tmp_path / "out", _make_corpus(tmp_path))
    for p in _pair_notes(paths):
        assert "_vs_" in p.stem, f"Unexpected filename stem: {p.name}"


def test_idempotent(tmp_path: Path) -> None:
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    first = len(build_style_matchups(out, corpus))
    second = len(build_style_matchups(out, corpus))
    assert first == second


def test_missing_corpus_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_style_matchups(tmp_path / "out", tmp_path / "no_such_dir")
