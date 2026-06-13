"""tests/platform/test_tennis_tournaments.py — Scoped tests for atlas_tournaments.

Uses a tiny synthetic matches fixture (no network, no GPU, no heavy deps).
Verifies:
  1. _Tournaments_Index.md exists after build_tournaments()
  2. At least one tournament note exists with correct champion [[link]]
  3. Notes contain valid frontmatter + [[wikilinks]]
  4. No betting/edge language
  5. Idempotent re-runs

Run: python -m pytest tests/platform/test_tennis_tournaments.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------

def _make_matches() -> pd.DataFrame:
    """Minimal synthetic match DataFrame with finals across multiple years."""
    rows = []
    # Wimbledon: 4 editions (2019-2022) each with a final
    # Australian Open: 3 editions (2020-2022) each with a final
    # Small event: only 2 editions (should NOT appear in output with min_editions=3)
    tournaments = [
        # (tourney_name, level, surface, year, round, p1_id, p1_name, p2_id, p2_name, winner)
        ("Wimbledon", "G", "Grass", 2019, "R32",  1, "Novak Djokovic", 2, "Roger Federer", "1"),
        ("Wimbledon", "G", "Grass", 2019, "SF",   1, "Novak Djokovic", 3, "Rafael Nadal",  "1"),
        ("Wimbledon", "G", "Grass", 2019, "F",    1, "Novak Djokovic", 2, "Roger Federer", "1"),  # Djokovic wins 2019
        ("Wimbledon", "G", "Grass", 2020, "R32",  2, "Roger Federer",  4, "Andy Murray",   "2"),
        ("Wimbledon", "G", "Grass", 2020, "F",    2, "Roger Federer",  3, "Rafael Nadal",  "2"),  # Nadal wins 2020
        ("Wimbledon", "G", "Grass", 2021, "QF",   1, "Novak Djokovic", 5, "Daniil Medvedev","1"),
        ("Wimbledon", "G", "Grass", 2021, "F",    1, "Novak Djokovic", 2, "Roger Federer", "1"),  # Djokovic wins 2021
        ("Wimbledon", "G", "Grass", 2022, "SF",   6, "Carlos Alcaraz",  1, "Novak Djokovic","1"),
        ("Wimbledon", "G", "Grass", 2022, "F",    6, "Carlos Alcaraz",  3, "Rafael Nadal",  "1"),  # Alcaraz wins 2022

        ("Australian Open", "G", "Hard", 2020, "QF",  1, "Novak Djokovic", 5, "Daniil Medvedev","1"),
        ("Australian Open", "G", "Hard", 2020, "F",   1, "Novak Djokovic", 3, "Rafael Nadal",   "1"),  # Djokovic 2020
        ("Australian Open", "G", "Hard", 2021, "R16", 5, "Daniil Medvedev",4, "Andy Murray",    "1"),
        ("Australian Open", "G", "Hard", 2021, "F",   5, "Daniil Medvedev",3, "Rafael Nadal",   "1"),  # Medvedev 2021
        ("Australian Open", "G", "Hard", 2022, "SF",  1, "Novak Djokovic", 6, "Carlos Alcaraz", "1"),
        ("Australian Open", "G", "Hard", 2022, "F",   1, "Novak Djokovic", 5, "Daniil Medvedev","1"),  # Djokovic 2022

        # Small event — only 2 editions, should be filtered out
        ("Small Challenger", "C", "Clay", 2021, "F",  3, "Rafael Nadal",   4, "Andy Murray",    "1"),
        ("Small Challenger", "C", "Clay", 2022, "QF", 3, "Rafael Nadal",   5, "Daniil Medvedev","1"),
    ]

    records = []
    for i, row in enumerate(rows if rows else []):
        records.append(row)

    for i, t in enumerate(tournaments):
        tname, level, surface, year, rnd, p1id, p1name, p2id, p2name, winner = t
        records.append({
            "tourney_name": tname,
            "tourney_level": level,
            "surface": surface,
            "date": f"{year}-06-01",
            "year": year,
            "round": rnd,
            "winner": winner,
            "p1_id": p1id,
            "p1_name": p1name,
            "p2_id": p2id,
            "p2_name": p2name,
            "best_of": 5,
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_matches() -> pd.DataFrame:
    return _make_matches()


@pytest.fixture(scope="module")
def tournaments_out(
    tmp_path_factory: pytest.TempPathFactory,
    synthetic_matches: pd.DataFrame,
) -> pathlib.Path:
    from domains.tennis.atlas_tournaments import build_tournaments

    out = tmp_path_factory.mktemp("tennis_tournaments")
    build_tournaments(out, min_editions=3, _matches_df=synthetic_matches)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTournamentOutputs:
    def test_index_exists(self, tournaments_out: pathlib.Path) -> None:
        assert (tournaments_out / "_Tournaments_Index.md").exists()

    def test_index_has_frontmatter(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "_Tournaments_Index.md").read_text(encoding="utf-8")
        assert text.startswith("---"), "Index missing YAML frontmatter"
        assert text.count("---") >= 2, "Index frontmatter not closed"

    def test_index_has_wikilinks(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "_Tournaments_Index.md").read_text(encoding="utf-8")
        assert "[[" in text and "]]" in text

    def test_index_has_back_link(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "_Tournaments_Index.md").read_text(encoding="utf-8")
        assert "[[../_Index" in text, "Index missing up-link to [[../_Index]]"

    def test_index_has_tournament_tags(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "_Tournaments_Index.md").read_text(encoding="utf-8")
        assert "#sport/tennis" in text
        assert "#tournament" in text

    def test_wimbledon_note_exists(self, tournaments_out: pathlib.Path) -> None:
        assert (tournaments_out / "Wimbledon.md").exists(), "Wimbledon note not emitted"

    def test_australian_open_note_exists(self, tournaments_out: pathlib.Path) -> None:
        assert (tournaments_out / "Australian Open.md").exists()

    def test_small_event_excluded(self, tournaments_out: pathlib.Path) -> None:
        """Tournament with fewer than min_editions editions must not get a note."""
        assert not (tournaments_out / "Small Challenger.md").exists()

    def test_wimbledon_champion_wikilink(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        # Djokovic won 2019 + 2021 → must appear as a champion link
        assert "Novak Djokovic" in text, "Djokovic not found in Wimbledon note"
        assert "[[../Players/Novak Djokovic" in text, "Champion [[wikilink]] missing"

    def test_wimbledon_correct_champion_year(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        # Alcaraz won 2022 final
        assert "Carlos Alcaraz" in text
        assert "2022" in text

    def test_wimbledon_most_titles(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        # Djokovic has 2 Wimbledon titles in synthetic data
        assert "Novak Djokovic" in text
        assert "2 title" in text

    def test_tournament_note_frontmatter(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "surface:" in text
        assert "editions:" in text
        assert "level:" in text
        assert "span:" in text

    def test_tournament_note_backlinks(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert "[[_Tournaments_Index" in text
        assert "[[../_Index" in text

    def test_returns_paths_list(self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_tournaments import build_tournaments

        paths = build_tournaments(tmp_path / "t2", min_editions=3, _matches_df=synthetic_matches)
        assert isinstance(paths, list)
        assert len(paths) >= 2, f"Expected at least index + 1 tournament note, got {len(paths)}"
        for p in paths:
            assert isinstance(p, pathlib.Path)
            assert p.exists(), f"Returned path does not exist: {p}"

    def test_idempotent(self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_tournaments import build_tournaments

        out = tmp_path / "idem"
        p1 = build_tournaments(out, min_editions=3, _matches_df=synthetic_matches)
        p2 = build_tournaments(out, min_editions=3, _matches_df=synthetic_matches)
        assert len(p1) == len(p2)

    def test_no_betting_language(self, tournaments_out: pathlib.Path) -> None:
        forbidden = ["betting", "edge", "roi", "ev ", "wager", "gamble", "odds"]
        for md_file in tournaments_out.glob("*.md"):
            text = md_file.read_text(encoding="utf-8").lower()
            for term in forbidden:
                assert term not in text, f"Forbidden term '{term}' in {md_file.name}"

    def test_empty_corpus_no_exception(self, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_tournaments import build_tournaments

        empty = pd.DataFrame(
            columns=["tourney_name", "tourney_level", "surface", "date",
                     "round", "winner", "p1_name", "p2_name", "best_of",
                     "p1_id", "p2_id"]
        )
        paths = build_tournaments(tmp_path / "empty", min_editions=3, _matches_df=empty)
        assert isinstance(paths, list)
