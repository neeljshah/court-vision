"""tests/platform/test_tennis_h2h.py — Scoped tests for atlas_h2h.

Uses a tiny synthetic matches fixture (no network, no GPU, no heavy deps).
Verifies:
  1. _Matchups_Index.md exists after build_h2h()
  2. At least one matchup note exists
  3. Matchup note contains [[wikilinks]] to both players
  4. H2H counts are arithmetically correct
  5. No edge/betting language
  6. Idempotent (reruns overwrite without error)
  7. build_h2h() returns a list of Path objects that all exist

Run: python -m pytest tests/platform/test_tennis_h2h.py -q --timeout=120
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Synthetic fixture — designed so specific rivalries appear multiple times
# ---------------------------------------------------------------------------

def _make_h2h_matches() -> pd.DataFrame:
    """Return a minimal synthetic match DataFrame with repeated pairings."""
    rows = []
    base_date = "2022-01-"

    # Pairing 1: "Alice Smith" vs "Bob Jones" — 5 meetings, Alice wins 3
    for i, (winner, surface, level) in enumerate([
        (1, "Hard", "G"),    # Alice wins, Grand Slam
        (2, "Clay", "A"),    # Bob wins, ATP
        (1, "Grass", "G"),   # Alice wins, Grand Slam
        (1, "Hard", "M"),    # Alice wins, Masters
        (2, "Clay", "A"),    # Bob wins, ATP
    ]):
        rows.append({
            "event_id": f"evt_{i:04d}",
            "date": f"{base_date}{i + 1:02d}",
            "tour": "atp",
            "tourney_id": f"2022-T{i:03d}",
            "tourney_name": "Australian Open" if level == "G" else "Miami Open",
            "tourney_level": level,
            "surface": surface,
            "best_of": 3,
            "round": "QF",
            "match_num": i + 1,
            "p1_id": 1,
            "p2_id": 2,
            "p1_name": "Alice Smith",
            "p2_name": "Bob Jones",
            "p1_rank": 5.0,
            "p2_rank": 10.0,
            "winner": winner,
            "score": "6-4 6-3",
            "retirement": False,
            "minutes": 90.0,
        })

    # Pairing 2: "Carlos Rivera" vs "Diana Lee" — 4 meetings, tied 2-2
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
            "best_of": 3,
            "round": "SF",
            "match_num": i + 10,
            "p1_id": 3,
            "p2_id": 4,
            "p1_name": "Carlos Rivera",
            "p2_name": "Diana Lee",
            "p1_rank": 15.0,
            "p2_rank": 20.0,
            "winner": winner,
            "score": "7-5 6-4",
            "retirement": False,
            "minutes": 95.0,
        })

    # Single match (should NOT appear if MIN_MEETINGS > 1)
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
        "p1_name": "Eddie Novak",
        "p2_name": "Franz Weber",
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

class TestH2HOutputs:

    def test_index_exists(self, h2h_out: pathlib.Path) -> None:
        assert (h2h_out / "_Matchups_Index.md").exists(), "_Matchups_Index.md not found"

    def test_index_has_frontmatter(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Matchups_Index.md").read_text(encoding="utf-8")
        assert text.startswith("---"), "_Matchups_Index.md missing YAML frontmatter"
        assert text.count("---") >= 2, "_Matchups_Index.md frontmatter not closed"

    def test_index_has_wikilinks(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Matchups_Index.md").read_text(encoding="utf-8")
        assert "[[" in text and "]]" in text

    def test_index_links_to_tennis_index(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "_Matchups_Index.md").read_text(encoding="utf-8")
        assert "[[_Index" in text, "_Matchups_Index.md missing [[_Index]] backlink"

    def test_at_least_one_matchup_note(self, h2h_out: pathlib.Path) -> None:
        notes = [p for p in h2h_out.glob("*.md") if p.name != "_Matchups_Index.md"]
        assert len(notes) >= 1, "No matchup notes found"

    def test_alice_bob_note_exists(self, h2h_out: pathlib.Path) -> None:
        # Canonical alphabetical order: Alice Smith vs Bob Jones
        note = h2h_out / "Alice Smith vs Bob Jones.md"
        assert note.exists(), f"Expected note not found: {note.name}"

    def test_alice_bob_h2h_counts(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "Alice Smith vs Bob Jones.md").read_text(encoding="utf-8")
        # Alice wins 3, Bob wins 2 → total 5
        assert "5" in text, "Total meeting count (5) not found in note"
        # Both win counts 3 and 2 must appear
        assert "3" in text and "2" in text

    def test_matchup_note_links_to_both_players(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "Alice Smith vs Bob Jones.md").read_text(encoding="utf-8")
        assert "[[Players/Alice Smith" in text, "Missing wikilink to Alice Smith player note"
        assert "[[Players/Bob Jones" in text, "Missing wikilink to Bob Jones player note"

    def test_matchup_note_has_frontmatter(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "Alice Smith vs Bob Jones.md").read_text(encoding="utf-8")
        assert text.startswith("---"), "Matchup note missing YAML frontmatter"
        assert "total_meetings:" in text

    def test_matchup_note_has_index_backlinks(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "Alice Smith vs Bob Jones.md").read_text(encoding="utf-8")
        assert "[[_Matchups_Index" in text, "Missing [[_Matchups_Index]] backlink"
        assert "[[_Index" in text, "Missing [[_Index]] backlink"

    def test_matchup_note_has_surface_section(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "Alice Smith vs Bob Jones.md").read_text(encoding="utf-8")
        assert "By Surface" in text, "Missing 'By Surface' section"

    def test_matchup_note_has_tourney_level_section(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "Alice Smith vs Bob Jones.md").read_text(encoding="utf-8")
        assert "By Tournament Level" in text or "Grand Slam" in text

    def test_matchup_note_has_recent_meetings_section(self, h2h_out: pathlib.Path) -> None:
        text = (h2h_out / "Alice Smith vs Bob Jones.md").read_text(encoding="utf-8")
        assert "Most Recent Meetings" in text

    def test_carlos_diana_tied(self, h2h_out: pathlib.Path) -> None:
        # Carlos Rivera vs Diana Lee — alphabetical order
        note = h2h_out / "Carlos Rivera vs Diana Lee.md"
        assert note.exists(), f"Expected note not found: {note.name}"
        text = note.read_text(encoding="utf-8")
        assert "tied" in text.lower() or "2-2" in text, "Tied record not reflected in note"

    def test_no_betting_language(self, h2h_out: pathlib.Path) -> None:
        forbidden = ["betting", " edge", " roi", " ev ", "wager", "gamble", " odds"]
        for md_file in h2h_out.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8").lower()
            for term in forbidden:
                assert term not in text, f"Forbidden term '{term}' found in {md_file.name}"

    def test_build_returns_paths(self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_h2h import build_h2h
        paths = build_h2h(tmp_path / "h2h2", _matches_df=synthetic_matches)
        assert isinstance(paths, list) and len(paths) >= 2
        for p in paths:
            assert isinstance(p, pathlib.Path) and p.exists()

    def test_idempotent(self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_h2h import build_h2h
        out = tmp_path / "idem_h2h"
        paths1 = build_h2h(out, _matches_df=synthetic_matches)
        paths2 = build_h2h(out, _matches_df=synthetic_matches)
        assert len(paths1) == len(paths2), "Idempotent re-run returned different count"
