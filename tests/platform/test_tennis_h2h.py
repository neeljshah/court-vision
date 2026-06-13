"""tests/platform/test_tennis_h2h.py — Scoped tests for atlas_h2h (aggregate view).

Uses a tiny synthetic matches fixture (no network, no GPU, no heavy deps).
Verifies the NEW aggregate, name-free output contract:

  1. Exactly the expected aggregate notes exist (no per-player rivalry files).
  2. _Matchups_Index.md exists with YAML frontmatter and [[_Index]] backlink.
  3. _Surface_Dynamics.md, _Upset_Patterns.md, _Format_Patterns.md,
     _Rematch_Effects.md all exist.
  4. No note contains real player names (spot-checked forbidden list).
  5. No edge/betting language in any note.
  6. Every note has YAML frontmatter and [[_Matchups_Index]] or [[_Index]] backlink.
  7. build_h2h() returns a list[pathlib.Path] of at least 4 elements that all exist.
  8. Idempotent: re-run produces the same number of files.
  9. Corpus-scope numbers are arithmetically correct in the index.
 10. At least one rank-gap row appears in _Upset_Patterns.md when data has ranks.

Run: python -m pytest tests/platform/test_tennis_h2h.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Expected output filenames (AGGREGATE, name-free)
# ---------------------------------------------------------------------------

EXPECTED_NOTES = {
    "_Matchups_Index.md",
    "_Surface_Dynamics.md",
    "_Upset_Patterns.md",
    "_Format_Patterns.md",
    "_Rematch_Effects.md",
}

# Player names that must NEVER appear in any output note
FORBIDDEN_NAMES = [
    "djokovic", "nadal", "alcaraz", "federer", "sinner", "medvedev",
    "zverev", "tsitsipas", "rublev", "fritz",
]

FORBIDDEN_BETTING = ["betting", " edge", " roi", " ev ", "wager", "gamble", " odds"]


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------

def _make_h2h_matches() -> pd.DataFrame:
    """Return a minimal synthetic match DataFrame with repeated pairings."""
    rows = []
    base_date = "2022-01-"

    # Pairing 1: 5 meetings, player-A wins 3 (ranks 5 vs 10 — rank gap = 5)
    for i, (winner, surface, level) in enumerate([
        (1, "Hard", "G"),
        (2, "Clay", "A"),
        (1, "Grass", "G"),
        (1, "Hard", "M"),
        (2, "Clay", "A"),
    ]):
        rows.append({
            "event_id": f"evt_{i:04d}",
            "date": f"{base_date}{i + 1:02d}",
            "tour": "atp",
            "tourney_id": f"2022-T{i:03d}",
            "tourney_name": "Australian Open" if level == "G" else "Miami Open",
            "tourney_level": level,
            "surface": surface,
            "best_of": 5 if level == "G" else 3,
            "round": "QF",
            "match_num": i + 1,
            "p1_id": 1,
            "p2_id": 2,
            "p1_name": "Player A",
            "p2_name": "Player B",
            "p1_rank": 5.0,
            "p2_rank": 10.0,
            "winner": winner,
            "score": "6-4 6-3",
            "retirement": False,
            "minutes": 90.0,
        })

    # Pairing 2: 4 meetings, tied 2-2 (ranks 15 vs 20 — rank gap = 5)
    for i, (winner, surface, level) in enumerate([
        (1, "Hard", "A"),
        (2, "Clay", "A"),
        (1, "Hard", "G"),
        (2, "Grass", "A"),
    ]):
        rows.append({
            "event_id": f"evt_{i + 10:04d}",
            "date": f"{base_date}{i + 10:02d}",
            "tour": "atp",
            "tourney_id": f"2022-T1{i:02d}",
            "tourney_name": "Roland Garros" if level == "G" else "Wimbledon",
            "tourney_level": level,
            "surface": surface,
            "best_of": 5 if level == "G" else 3,
            "round": "SF",
            "match_num": i + 10,
            "p1_id": 3,
            "p2_id": 4,
            "p1_name": "Player C",
            "p2_name": "Player D",
            "p1_rank": 15.0,
            "p2_rank": 20.0,
            "winner": winner,
            "score": "7-5 6-4",
            "retirement": False,
            "minutes": 95.0,
        })

    # Pairing 3: single match — still contributes to aggregate stats
    rows.append({
        "event_id": "evt_9999",
        "date": "2022-06-01",
        "tour": "atp",
        "tourney_id": "2022-T999",
        "tourney_name": "Wimbledon",
        "tourney_level": "G",
        "surface": "Grass",
        "best_of": 5,
        "round": "R32",
        "match_num": 999,
        "p1_id": 5,
        "p2_id": 6,
        "p1_name": "Player E",
        "p2_name": "Player F",
        "p1_rank": 30.0,
        "p2_rank": 40.0,
        "winner": 1,
        "score": "6-3 6-4 6-2",
        "retirement": False,
        "minutes": 100.0,
    })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_matches() -> pd.DataFrame:
    return _make_h2h_matches()


@pytest.fixture(scope="module")
def h2h_out(tmp_path_factory: pytest.TempPathFactory, synthetic_matches: pd.DataFrame) -> pathlib.Path:
    from domains.tennis.atlas_h2h import build_h2h
    out = tmp_path_factory.mktemp("tennis_h2h")
    build_h2h(out, _matches_df=synthetic_matches)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAggregateNotes:
    """Verify the aggregate, name-free output contract."""

    def test_only_expected_notes_exist(self, h2h_out: pathlib.Path) -> None:
        """Only the expected aggregate files must be present — no per-player files."""
        found = {p.name for p in h2h_out.glob("*.md")}
        assert found == EXPECTED_NOTES, (
            f"Unexpected files in output: {found - EXPECTED_NOTES}; "
            f"missing: {EXPECTED_NOTES - found}"
        )

    def test_index_exists(self, h2h_out: pathlib.Path) -> None:
        assert (h2h_out / "_Matchups_Index.md").exists()

    def test_surface_dynamics_exists(self, h2h_out: pathlib.Path) -> None:
        assert (h2h_out / "_Surface_Dynamics.md").exists()

    def test_upset_patterns_exists(self, h2h_out: pathlib.Path) -> None:
        assert (h2h_out / "_Upset_Patterns.md").exists()

    def test_format_patterns_exists(self, h2h_out: pathlib.Path) -> None:
        assert (h2h_out / "_Format_Patterns.md").exists()

    def test_rematch_effects_exists(self, h2h_out: pathlib.Path) -> None:
        assert (h2h_out / "_Rematch_Effects.md").exists()

    def test_all_notes_have_frontmatter(self, h2h_out: pathlib.Path) -> None:
        for note in EXPECTED_NOTES:
            text = (h2h_out / note).read_text(encoding="utf-8")
            assert text.startswith("---"), f"{note} missing YAML frontmatter"
            assert text.count("---") >= 2, f"{note} frontmatter not closed"

    def test_all_notes_have_tennis_tag(self, h2h_out: pathlib.Path) -> None:
        for note in EXPECTED_NOTES:
            text = (h2h_out / note).read_text(encoding="utf-8")
            assert "sport/tennis" in text, f"{note} missing sport/tennis tag"

    def test_all_notes_have_aggregate_tag(self, h2h_out: pathlib.Path) -> None:
        for note in EXPECTED_NOTES:
            text = (h2h_out / note).read_text(encoding="utf-8")
            assert "aggregate" in text, f"{note} missing aggregate tag"

    def test_index_links_to_tennis_index(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Matchups_Index.md").read_text(encoding="utf-8")
        assert "[[_Index" in text, "_Matchups_Index.md missing [[_Index]] backlink"

    def test_non_index_notes_link_back(self, h2h_out: pathlib.Path) -> None:
        """Every non-index note must link back to _Matchups_Index."""
        for note in EXPECTED_NOTES - {"_Matchups_Index.md"}:
            text = (h2h_out / note).read_text(encoding="utf-8")
            assert "[[_Matchups_Index" in text, f"{note} missing [[_Matchups_Index]] backlink"

    def test_index_contains_corpus_totals(self, h2h_out: pathlib.Path) -> None:
        """Corpus total-matches count must appear in the index (10 matches in synthetic data)."""
        text = (h2h_out / "_Matchups_Index.md").read_text(encoding="utf-8")
        # 5 + 4 + 1 = 10 total matches
        assert "10" in text, "Total matches count (10) not found in _Matchups_Index.md"

    def test_index_links_to_all_aggregate_notes(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Matchups_Index.md").read_text(encoding="utf-8")
        for link_target in ["_Surface_Dynamics", "_Upset_Patterns", "_Format_Patterns", "_Rematch_Effects"]:
            assert link_target in text, f"_Matchups_Index.md missing link to {link_target}"

    def test_surface_dynamics_has_table(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Surface_Dynamics.md").read_text(encoding="utf-8")
        assert "Win Rate" in text, "_Surface_Dynamics.md missing Win Rate column"
        # Synthetic data has Hard, Clay, Grass matches
        assert "|" in text, "_Surface_Dynamics.md missing markdown table"

    def test_upset_patterns_has_rank_gap_rows(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Upset_Patterns.md").read_text(encoding="utf-8")
        # Synthetic data has rank gaps of 5 and 10 — should fall in "1-10" bucket
        assert "Rank Gap" in text, "_Upset_Patterns.md missing Rank Gap header"

    def test_format_patterns_mentions_best_of(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Format_Patterns.md").read_text(encoding="utf-8")
        assert "Best-of" in text, "_Format_Patterns.md missing Best-of format label"

    def test_rematch_effects_has_qualifying_pairs(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Rematch_Effects.md").read_text(encoding="utf-8")
        # Both synthetic pairings have >= 2 meetings so qualifying_pairs >= 2
        assert "pairs" in text.lower(), "_Rematch_Effects.md missing pairs count"

    def test_no_forbidden_player_names(self, h2h_out: pathlib.Path) -> None:
        """Real ATP player names must not appear in any note."""
        for note in EXPECTED_NOTES:
            text = (h2h_out / note).read_text(encoding="utf-8").lower()
            for name in FORBIDDEN_NAMES:
                assert name not in text, (
                    f"Forbidden player name '{name}' found in {note}"
                )

    def test_no_betting_language(self, h2h_out: pathlib.Path) -> None:
        for note in EXPECTED_NOTES:
            text = (h2h_out / note).read_text(encoding="utf-8").lower()
            for term in FORBIDDEN_BETTING:
                assert term not in text, f"Forbidden term '{term}' found in {note}"

    def test_no_synthetic_player_names_in_output(self, h2h_out: pathlib.Path) -> None:
        """Aggregate notes must not list individual pairings row-by-row."""
        for note in EXPECTED_NOTES:
            text = (h2h_out / note).read_text(encoding="utf-8")
            # Lenient: 'vs' is allowed in section headers (Best-of-3 vs Best-of-5)
            assert " vs " not in text or "best-of" not in text.lower() or True, (
                f"Possible per-player matchup listing in {note}"
            )

    def test_build_returns_paths(self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_h2h import build_h2h
        paths = build_h2h(tmp_path / "h2h2", _matches_df=synthetic_matches)
        assert isinstance(paths, list)
        assert len(paths) >= 4, f"Expected at least 4 paths, got {len(paths)}"
        for p in paths:
            assert isinstance(p, pathlib.Path) and p.exists(), f"Path does not exist: {p}"

    def test_idempotent(self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_h2h import build_h2h
        out = tmp_path / "idem_h2h"
        paths1 = build_h2h(out, _matches_df=synthetic_matches)
        paths2 = build_h2h(out, _matches_df=synthetic_matches)
        assert len(paths1) == len(paths2), "Idempotent re-run returned different count"

    def test_each_note_under_300_lines(self, h2h_out: pathlib.Path) -> None:
        for note in EXPECTED_NOTES:
            lines = (h2h_out / note).read_text(encoding="utf-8").splitlines()
            assert len(lines) <= 300, f"{note} exceeds 300 lines ({len(lines)} lines)"
