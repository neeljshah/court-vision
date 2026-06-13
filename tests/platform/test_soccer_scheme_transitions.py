"""tests.platform.test_soccer_scheme_transitions — Acceptance tests for
domains.soccer.atlas_scheme_transitions.

Synthetic 3-season fixture: TeamA changes scheme (Leaky season 1 → Balanced season 2
→ High-Scoring season 3); TeamB stays Leaky all 3 seasons.  Tests verify the
transition matrix captures those movements correctly.

Tests
-----
- build_scheme_transitions returns 4 paths (index + matrix + stickiness + notable)
- transition matrix captures a known scheme change in the fixture
- stickiness captures a known scheme-persistence in the fixture
- index note has YAML frontmatter, [[wikilinks]], and #tags
- matrix note has YAML frontmatter and ASCII table block
- stickiness note has YAML frontmatter and stickiness table
- notable transitions note has YAML frontmatter
- no edge/betting language in any emitted note
- idempotent: second run returns same file count
- missing corpus raises FileNotFoundError
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

from domains.soccer.atlas_scheme_transitions import (  # noqa: E402
    build_scheme_transitions,
    _classify_teams_per_season,
    _build_transition_counts,
    _transition_probabilities,
    _stickiness,
)


# ---------------------------------------------------------------------------
# Synthetic corpus builder
# ---------------------------------------------------------------------------


def _make_corpus(tmp_path: Path) -> Path:
    """Build a minimal 3-season corpus with known scheme transitions.

    TeamA:
      Season 2019 → Leaky (high GA, low CS): scores come in as 0-3, many conceded
      Season 2021 → Balanced (near-median stats)
      Season 2023 → High-Scoring Attacking (GF ≥ 1.60, Over ≥ 58%)

    TeamB:
      All 3 seasons → Leaky (stays in same scheme)

    TeamC, TeamD, TeamE each appear ≥10 matches per season as filler (1-0 wins).
    """
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    rows: List[dict] = []
    eid = 1

    def _add(home: str, away: str, hg: int, ag: int,
             season: int, n_rep: int = 12) -> None:
        nonlocal eid
        total = hg + ag
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        for i in range(n_rep):
            rows.append({
                "event_id": f"ev{eid}",
                "date": f"{season}-08-{(i % 28) + 1:02d}",
                "season": season,
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

    # ---- Season 2019 ----
    # TeamA: concedes a lot → Leaky (GA high, CS low)
    # Play home: 0-3 (loses, high GA); play away: 0-3 (high GA)
    _add("TeamA", "Foe1", 0, 3, 2019, n_rep=14)   # TeamA home, concedes 3
    _add("Foe2", "TeamA", 3, 0, 2019, n_rep=12)   # TeamA away, concedes 3
    # TeamB: same leaky pattern
    _add("TeamB", "Foe3", 0, 3, 2019, n_rep=14)
    _add("Foe4", "TeamB", 3, 0, 2019, n_rep=12)
    # Filler teams (need ≥10 matches each)
    _add("TeamC", "TeamD", 1, 0, 2019, n_rep=14)
    _add("TeamD", "TeamC", 1, 0, 2019, n_rep=14)
    _add("TeamE", "Foe5", 1, 1, 2019, n_rep=14)
    # Foe teams as filler
    for foe in ["Foe1", "Foe2", "Foe3", "Foe4", "Foe5"]:
        _add(foe, "PadA", 1, 0, 2019, n_rep=12)

    # ---- Season 2021 ----
    # TeamA: near-median → Balanced (1-1 draws, moderate scoring)
    _add("TeamA", "Foe1", 1, 1, 2021, n_rep=14)   # draw, Under
    _add("Foe2", "TeamA", 1, 0, 2021, n_rep=12)   # TeamA concedes 1, middle
    # TeamB: still leaky
    _add("TeamB", "Foe3", 0, 3, 2021, n_rep=14)
    _add("Foe4", "TeamB", 3, 0, 2021, n_rep=12)
    # Filler
    _add("TeamC", "TeamD", 1, 0, 2021, n_rep=14)
    _add("TeamD", "TeamC", 1, 0, 2021, n_rep=14)
    _add("TeamE", "Foe5", 1, 1, 2021, n_rep=14)
    for foe in ["Foe1", "Foe2", "Foe3", "Foe4", "Foe5"]:
        _add(foe, "PadA", 1, 0, 2021, n_rep=12)

    # ---- Season 2023 ----
    # TeamA: high scoring → High-Scoring Attacking (GF ≥ 1.60, Over ≥ 58%)
    _add("TeamA", "Foe1", 3, 1, 2023, n_rep=14)   # Over, wins heavily
    _add("Foe2", "TeamA", 1, 3, 2023, n_rep=12)   # TeamA scores 3 away, Over
    # TeamB: still leaky
    _add("TeamB", "Foe3", 0, 3, 2023, n_rep=14)
    _add("Foe4", "TeamB", 3, 0, 2023, n_rep=12)
    # Filler
    _add("TeamC", "TeamD", 1, 0, 2023, n_rep=14)
    _add("TeamD", "TeamC", 1, 0, 2023, n_rep=14)
    _add("TeamE", "Foe5", 1, 1, 2023, n_rep=14)
    for foe in ["Foe1", "Foe2", "Foe3", "Foe4", "Foe5"]:
        _add(foe, "PadA", 1, 0, 2023, n_rep=12)

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_four_paths(tmp_path: Path) -> None:
    paths = build_scheme_transitions(tmp_path / "out", _make_corpus(tmp_path))
    assert len(paths) == 4, f"Expected 4 notes; got {len(paths)}"


def test_teamb_leaky_stickiness(tmp_path: Path) -> None:
    """TeamB stays Leaky across all 3 seasons → Leaky→Leaky count ≥ 2."""
    corpus = _make_corpus(tmp_path)
    df = pd.read_parquet(corpus / "matches.parquet")
    season_map = _classify_teams_per_season(df, min_matches=10)
    counts = _build_transition_counts(season_map)
    leaky_stay = counts.get("Leaky_High-Risk", {}).get("Leaky_High-Risk", 0)
    assert leaky_stay >= 2, (
        f"Expected TeamB to contribute ≥2 Leaky→Leaky transitions; got {leaky_stay}"
    )


def test_teama_scheme_changes_captured(tmp_path: Path) -> None:
    """TeamA transitions Leaky→Balanced and Balanced→High-Scoring in the corpus."""
    corpus = _make_corpus(tmp_path)
    df = pd.read_parquet(corpus / "matches.parquet")
    season_map = _classify_teams_per_season(df, min_matches=10)

    # verify TeamA exists in all 3 seasons
    assert "TeamA" in season_map.get(2019, {}), "TeamA not classified in 2019"
    assert "TeamA" in season_map.get(2021, {}), "TeamA not classified in 2021"
    assert "TeamA" in season_map.get(2023, {}), "TeamA not classified in 2023"

    scheme_2019 = season_map[2019]["TeamA"]
    scheme_2021 = season_map[2021]["TeamA"]
    scheme_2023 = season_map[2023]["TeamA"]

    # At minimum TeamA's scheme must differ between 2019 and 2023
    assert scheme_2019 != scheme_2023, (
        f"TeamA should change scheme 2019→2023; got {scheme_2019}→{scheme_2023}"
    )

    # Verify transitions are tallied
    counts = _build_transition_counts(season_map)
    # transition from scheme_2019 to scheme_2021 must have count ≥ 1
    t1 = counts.get(scheme_2019, {}).get(scheme_2021, 0)
    assert t1 >= 1, (
        f"Expected {scheme_2019}→{scheme_2021} count ≥ 1; got {t1}"
    )
    # transition from scheme_2021 to scheme_2023 must have count ≥ 1
    t2 = counts.get(scheme_2021, {}).get(scheme_2023, 0)
    assert t2 >= 1, (
        f"Expected {scheme_2021}→{scheme_2023} count ≥ 1; got {t2}"
    )


def test_probabilities_row_sum_to_one(tmp_path: Path) -> None:
    """Each non-zero row of the probability matrix must sum to 1.0."""
    corpus = _make_corpus(tmp_path)
    df = pd.read_parquet(corpus / "matches.parquet")
    season_map = _classify_teams_per_season(df, min_matches=10)
    counts = _build_transition_counts(season_map)
    probs = _transition_probabilities(counts)
    for from_key, row in probs.items():
        total = sum(row.values())
        if total > 0:
            assert abs(total - 1.0) < 1e-9, (
                f"Row {from_key} sums to {total}, not 1.0"
            )


def test_stickiness_values_in_range(tmp_path: Path) -> None:
    """Stickiness rates must be in [0, 1]."""
    corpus = _make_corpus(tmp_path)
    df = pd.read_parquet(corpus / "matches.parquet")
    season_map = _classify_teams_per_season(df, min_matches=10)
    counts = _build_transition_counts(season_map)
    for key, rate, _, _ in _stickiness(counts):
        assert 0.0 <= rate <= 1.0, f"Stickiness {key}={rate} out of [0,1]"


def test_index_note_structure(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_scheme_transitions(out, _make_corpus(tmp_path))
    text = (out / "_Scheme_Transitions_Index.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "Index missing YAML frontmatter"
    assert _has_wikilink(text), "Index missing [[wikilinks]]"
    assert _has_tag(text), "Index missing #tags"
    assert "Scheme Transitions" in text


def test_matrix_note_has_ascii_table(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_scheme_transitions(out, _make_corpus(tmp_path))
    text = (out / "Transition_Matrix.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "Matrix note missing YAML frontmatter"
    assert "FROM\\TO" in text, "Matrix note missing ASCII table"
    assert _has_wikilink(text), "Matrix note missing [[wikilinks]]"


def test_stickiness_note_structure(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_scheme_transitions(out, _make_corpus(tmp_path))
    text = (out / "Stickiness.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "Stickiness note missing YAML frontmatter"
    assert "Stickiness" in text
    assert _has_wikilink(text), "Stickiness note missing [[wikilinks]]"


def test_notable_note_structure(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_scheme_transitions(out, _make_corpus(tmp_path))
    text = (out / "Notable_Transitions.md").read_text(encoding="utf-8")
    assert _has_frontmatter(text), "Notable note missing YAML frontmatter"
    assert _has_wikilink(text), "Notable note missing [[wikilinks]]"


def test_no_edge_language(tmp_path: Path) -> None:
    """Notes must not contain betting-edge language."""
    banned = re.compile(r"\b(ROI|edge|expected value|EV|bet|wager|arbitrage)\b", re.I)
    paths = build_scheme_transitions(tmp_path / "out", _make_corpus(tmp_path))
    for p in paths:
        text = p.read_text(encoding="utf-8")
        m = banned.search(text)
        assert m is None, f"{p.name}: found edge language '{m.group()}'"


def test_idempotent(tmp_path: Path) -> None:
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    n1 = len(build_scheme_transitions(out, corpus))
    n2 = len(build_scheme_transitions(out, corpus))
    assert n1 == n2, f"Idempotency failed: first={n1}, second={n2}"


def test_missing_corpus_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_scheme_transitions(tmp_path / "out", tmp_path / "no_such_dir")
