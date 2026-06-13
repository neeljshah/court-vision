"""tests/platform/test_tennis_tournaments.py — Scoped tests for atlas_tournaments.

Uses a tiny synthetic matches fixture (no network, no GPU, no heavy deps).
Verifies:
  1. _Tournaments_Index.md exists after build_tournaments()
  2. At least one tournament note exists with correct style-profile content
  3. Notes contain valid frontmatter + [[wikilinks]]
  4. No betting/edge language
  5. No individual player names (name-free constraint)
  6. Idempotent re-runs

Run: python -m pytest tests/platform/test_tennis_tournaments.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Names that must NOT appear anywhere in rendered output (name-free discipline).
# Kept as a module-level constant so the grep-equivalent is easy to audit.
_FORBIDDEN_NAMES: list[str] = [
    "Djokovic", "Federer", "Nadal", "Alcaraz", "Medvedev", "Murray",
    "Wawrinka", "Sinner", "Novak", "Roger", "Rafael", "Carlos", "Daniil",
    "Andy",
]


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------

def _make_matches() -> pd.DataFrame:
    """Minimal synthetic match DataFrame with finals across multiple years.

    Player names appear in the fixture only to mirror the real corpus format;
    they must NOT propagate into the rendered Markdown output.
    """
    tournaments = [
        # (tourney_name, level, surface, year, round, p1_id, p1_name, p2_id, p2_name, winner)
        # Wimbledon: 4 editions (2019-2022), grass — surface-specialist venue
        ("Wimbledon", "G", "Grass", 2019, "R32",  1, "Player_A", 2, "Player_B", "1"),
        ("Wimbledon", "G", "Grass", 2019, "SF",   1, "Player_A", 3, "Player_C", "1"),
        ("Wimbledon", "G", "Grass", 2019, "F",    1, "Player_A", 2, "Player_B", "1"),
        ("Wimbledon", "G", "Grass", 2020, "R32",  2, "Player_B", 4, "Player_D", "2"),
        ("Wimbledon", "G", "Grass", 2020, "F",    2, "Player_B", 3, "Player_C", "2"),
        ("Wimbledon", "G", "Grass", 2021, "QF",   1, "Player_A", 5, "Player_E", "1"),
        ("Wimbledon", "G", "Grass", 2021, "F",    1, "Player_A", 2, "Player_B", "1"),
        ("Wimbledon", "G", "Grass", 2022, "SF",   6, "Player_F", 1, "Player_A", "1"),
        ("Wimbledon", "G", "Grass", 2022, "F",    6, "Player_F", 3, "Player_C", "1"),

        # Australian Open: 3 editions (2020-2022), hard court — mixed archetype venue
        ("Australian Open", "G", "Hard", 2020, "QF",  1, "Player_A", 5, "Player_E", "1"),
        ("Australian Open", "G", "Hard", 2020, "F",   1, "Player_A", 3, "Player_C", "1"),
        ("Australian Open", "G", "Hard", 2021, "R16", 5, "Player_E", 4, "Player_D", "1"),
        ("Australian Open", "G", "Hard", 2021, "F",   5, "Player_E", 3, "Player_C", "1"),
        ("Australian Open", "G", "Hard", 2022, "SF",  1, "Player_A", 6, "Player_F", "1"),
        ("Australian Open", "G", "Hard", 2022, "F",   1, "Player_A", 5, "Player_E", "1"),

        # Small event — only 2 editions, should be filtered out
        ("Small Challenger", "C", "Clay", 2021, "F",  3, "Player_C", 4, "Player_D", "1"),
        ("Small Challenger", "C", "Clay", 2022, "QF", 3, "Player_C", 5, "Player_E", "1"),
    ]

    records = []
    for t in tournaments:
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

    def test_wimbledon_surface_correct(self, tournaments_out: pathlib.Path) -> None:
        """Surface must be present and correct in the note."""
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert "Grass" in text, "Wimbledon note missing surface 'Grass'"

    def test_wimbledon_level_correct(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert "Grand Slam" in text, "Wimbledon note missing level 'Grand Slam'"

    def test_wimbledon_editions_count(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        # 4 editions in synthetic fixture
        assert "4" in text, "Wimbledon note should reference 4 editions"

    def test_wimbledon_has_archetype_section(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert "Winner Archetype Distribution" in text, (
            "Wimbledon note missing 'Winner Archetype Distribution' section"
        )

    def test_wimbledon_archetype_table_has_percentages(
        self, tournaments_out: pathlib.Path
    ) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        # Must have at least one percentage value in the archetype table
        assert "%" in text, "Archetype section must contain percentage values"

    def test_wimbledon_archetype_labels(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert "surface-specialist" in text.lower() or "all-court" in text.lower(), (
            "Archetype table must contain 'surface-specialist' or 'all-court' labels"
        )

    def test_wimbledon_no_champion_table(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert "Champions by Year" not in text, (
            "Champion-by-year table must be absent (name-free discipline)"
        )
        assert "Most Titles" not in text, (
            "Most Titles section must be absent (name-free discipline)"
        )

    def test_wimbledon_no_player_wikilinks(self, tournaments_out: pathlib.Path) -> None:
        text = (tournaments_out / "Wimbledon.md").read_text(encoding="utf-8")
        assert "[[../Players/" not in text, (
            "Player wikilinks must not appear in tournament notes (name-free discipline)"
        )

    def test_no_real_player_names_in_any_note(self, tournaments_out: pathlib.Path) -> None:
        """The _FORBIDDEN_NAMES list must not appear in any rendered note."""
        for md_file in tournaments_out.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            for name in _FORBIDDEN_NAMES:
                assert name not in text, (
                    f"Forbidden player name '{name}' found in {md_file.name}"
                )

    def test_returns_paths_list(
        self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path
    ) -> None:
        from domains.tennis.atlas_tournaments import build_tournaments

        paths = build_tournaments(tmp_path / "t2", min_editions=3, _matches_df=synthetic_matches)
        assert isinstance(paths, list)
        assert len(paths) >= 2, (
            f"Expected at least index + 1 tournament note, got {len(paths)}"
        )
        for p in paths:
            assert isinstance(p, pathlib.Path)
            assert p.exists(), f"Returned path does not exist: {p}"

    def test_idempotent(
        self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path
    ) -> None:
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
                assert term not in text, (
                    f"Forbidden term '{term}' in {md_file.name}"
                )

    def test_empty_corpus_no_exception(self, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas_tournaments import build_tournaments

        empty = pd.DataFrame(
            columns=["tourney_name", "tourney_level", "surface", "date",
                     "round", "winner", "p1_name", "p2_name", "best_of",
                     "p1_id", "p2_id"]
        )
        paths = build_tournaments(tmp_path / "empty", min_editions=3, _matches_df=empty)
        assert isinstance(paths, list)

    def test_note_line_count_within_limit(self, tournaments_out: pathlib.Path) -> None:
        """Each note must be ≤ 300 lines (CLAUDE.md discipline)."""
        for md_file in tournaments_out.glob("*.md"):
            lines = md_file.read_text(encoding="utf-8").splitlines()
            assert len(lines) <= 300, (
                f"{md_file.name} has {len(lines)} lines (limit 300)"
            )

    def test_canonical_name_dedup_no_dangling_links(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Case-variant names must collapse to one canonical note; index links resolve."""
        import re as _re
        from domains.tennis.atlas_tournaments import build_tournaments

        def _row(name, level, surface, yr):
            return {"tourney_name": name, "tourney_level": level, "surface": surface,
                    "date": f"{yr}-06-01", "year": yr, "round": "F", "winner": "1",
                    "p1_id": 1, "p1_name": "P1", "p2_id": 2, "p2_name": "P2", "best_of": 5}

        records = (
            [_row("US Open", "G", "Hard", y) for y in range(2015, 2020)] +
            [_row("Us Open", "G", "Hard", y) for y in range(2020, 2023)] +
            [_row("Rio de Janeiro", "B", "Clay", y) for y in [2015, 2016, 2017]] +
            [_row("Rio De Janeiro", "B", "Clay", y) for y in [2023, 2024, 2025]]
        )
        out = tmp_path / "canon"
        build_tournaments(out, min_editions=3, _matches_df=pd.DataFrame(records))
        stems = {f.stem for f in out.glob("*.md")}

        assert "US Open" in stems and "Us Open" not in stems
        assert "Rio de Janeiro" in stems and "Rio De Janeiro" not in stems

        idx = (out / "_Tournaments_Index.md").read_text(encoding="utf-8")
        pat = _re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
        for m in pat.finditer(idx):
            stem = m.group(1).strip().split("/")[-1]
            if not stem.startswith("..") and not stem.startswith("_"):
                assert stem in stems, f"Dangling [[{m.group(1)}]] in index"
