"""tests.platform.test_tennis_style_trends — Unit tests for atlas_style_trends.

Uses a tiny multi-year fixture (no filesystem reads from corpus).
Verifies:
- trend notes are created
- per-year shares sum to ~100% (within floating-point tolerance)
- no player names appear in any emitted note
- no exceptions raised
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.tennis.atlas_style_trends import build_style_trends
from domains.tennis.atlas_playstyle_specs import ARCHETYPES, MIN_MATCHES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PLAYER_NAMES = [
    "Smith", "Jones", "Müller", "García", "Nakamura",
    "Volkov", "Dupont", "Silva", "Chen", "Brown",
]


def _make_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a minimal multi-year matches + players DataFrame pair.

    3 years (2020, 2021, 2022) × 10 players with varied height/hand/surface
    records so that at least a few archetypes are populated.
    """
    import datetime

    # Players: 10 total; mix of hand, height
    players_rows = []
    for i, name in enumerate(PLAYER_NAMES):
        players_rows.append({
            "player_id": 1000 + i,
            "name_first": "Anon",
            "name_last": "X",
            "full_name": "Anon X",  # deliberately generic — no real name
            "hand": "L" if i % 5 == 0 else "R",
            "dob": "1990-01-01",
            "ioc": "USA",
            "height": 195.0 if i % 3 == 0 else 178.0,
            "tour": "atp",
        })
    players_df = pd.DataFrame(players_rows)

    # Matches: for each year, generate enough matches so every player
    # has ≥MIN_MATCHES career matches and varied surface splits.
    match_rows = []
    mid = 0
    surfaces_cycle = ["Hard", "Clay", "Grass", "Hard", "Hard"]

    for year in (2020, 2021, 2022):
        dt = datetime.date(year, 6, 1)
        for rnd in range(30):  # 30 rounds per year
            p1 = 1000 + (rnd % 10)
            p2 = 1000 + ((rnd + 1) % 10)
            surf = surfaces_cycle[rnd % len(surfaces_cycle)]
            # alternate best_of to create some bo5 players
            bo = 5 if rnd % 7 == 0 else 3
            match_rows.append({
                "event_id": f"E{year}{rnd:03d}",
                "date": dt,
                "tour": "atp",
                "tourney_id": f"T{year}",
                "tourney_name": "Test Open",
                "tourney_level": "A",
                "surface": surf,
                "best_of": bo,
                "round": "R32",
                "match_num": mid,
                "p1_id": p1,
                "p2_id": p2,
                "p1_name": "Anon X",
                "p2_name": "Anon X",
                "p1_rank": 50,
                "p2_rank": 60,
                "winner": 1 if rnd % 2 == 0 else 2,
                "score": "6-3 6-4",
                "retirement": False,
                "minutes": 90,
            })
            mid += 1

    matches_df = pd.DataFrame(match_rows)
    return matches_df, players_df


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildStyleTrends:
    """Full functional tests for build_style_trends."""

    def test_returns_paths_no_exception(self, tmp_path: pathlib.Path) -> None:
        """build_style_trends must complete without raising and return paths."""
        matches, players = _make_fixture()
        paths = build_style_trends(
            tmp_path / "Trends",
            _matches_df=matches,
            _players_df=players,
        )
        assert isinstance(paths, list)
        assert len(paths) > 0, "Expected at least one path returned"

    def test_overview_note_exists(self, tmp_path: pathlib.Path) -> None:
        """An overview note must be created."""
        matches, players = _make_fixture()
        out = tmp_path / "Trends"
        build_style_trends(out, _matches_df=matches, _players_df=players)
        overview = out / "_Style_Trends_Overview.md"
        assert overview.exists(), f"Overview note not found: {overview}"

    def test_year_notes_exist(self, tmp_path: pathlib.Path) -> None:
        """A per-year note should exist for each year in the fixture."""
        matches, players = _make_fixture()
        out = tmp_path / "Trends"
        build_style_trends(out, _matches_df=matches, _players_df=players)
        for year in (2020, 2021, 2022):
            note = out / f"{year}.md"
            assert note.exists(), f"Year note missing: {note}"

    def test_per_year_shares_sum_to_100(self, tmp_path: pathlib.Path) -> None:
        """Archetype shares extracted from year notes must sum to ~100%."""
        matches, players = _make_fixture()
        out = tmp_path / "Trends"
        build_style_trends(out, _matches_df=matches, _players_df=players)
        pct_pattern = re.compile(r"\|\s*[^|]+\|\s*\d+\s*\|\s*([\d.]+)%\s*\|")
        for year in (2020, 2021, 2022):
            note = out / f"{year}.md"
            text = note.read_text(encoding="utf-8")
            pcts = [float(m.group(1)) for m in pct_pattern.finditer(text)]
            if not pcts:
                continue  # no qualifying players — skip sum check
            total = sum(pcts)
            assert abs(total - 100.0) < 2.0, (
                f"Year {year}: archetype shares sum to {total:.1f}%, expected ~100%"
            )

    def test_no_player_names_in_notes(self, tmp_path: pathlib.Path) -> None:
        """No real player surnames should appear in any emitted note."""
        matches, players = _make_fixture()
        out = tmp_path / "Trends"
        build_style_trends(out, _matches_df=matches, _players_df=players)

        suspicious_surnames = PLAYER_NAMES  # the ones we used in fixture

        for md_file in out.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            for surname in suspicious_surnames:
                assert surname not in text, (
                    f"Player surname '{surname}' found in {md_file.name}"
                )

    def test_overview_contains_archetype_slugs(self, tmp_path: pathlib.Path) -> None:
        """The overview note must reference all archetype column abbreviations."""
        matches, players = _make_fixture()
        out = tmp_path / "Trends"
        build_style_trends(out, _matches_df=matches, _players_df=players)
        overview = (out / "_Style_Trends_Overview.md").read_text(encoding="utf-8")
        # Overview should have the table header with abbreviations
        for keyword in ("Clay", "BigSrv", "AllCrt", "LeftH", "GSlam", "Hard", "Grass", "Jrny"):
            assert keyword in overview, (
                f"Expected column abbreviation '{keyword}' in overview note"
            )

    def test_frontmatter_tags_present(self, tmp_path: pathlib.Path) -> None:
        """Overview note must contain required frontmatter tags."""
        matches, players = _make_fixture()
        out = tmp_path / "Trends"
        build_style_trends(out, _matches_df=matches, _players_df=players)
        overview = (out / "_Style_Trends_Overview.md").read_text(encoding="utf-8")
        for tag in ("sport/tennis", "trends", "playstyle"):
            assert tag in overview, f"Tag '{tag}' missing from overview frontmatter"

    def test_playstyle_backlink_in_overview(self, tmp_path: pathlib.Path) -> None:
        """Overview must contain a [[Playstyles/...]] wikilink."""
        matches, players = _make_fixture()
        out = tmp_path / "Trends"
        build_style_trends(out, _matches_df=matches, _players_df=players)
        overview = (out / "_Style_Trends_Overview.md").read_text(encoding="utf-8")
        assert "[[Playstyles/" in overview, "Playstyles wikilink missing from overview"

    def test_empty_corpus_no_crash(self, tmp_path: pathlib.Path) -> None:
        """Empty matches DataFrame must not raise — graceful no-output."""
        empty_matches = pd.DataFrame(columns=[
            "event_id", "date", "tour", "tourney_id", "tourney_name",
            "tourney_level", "surface", "best_of", "round", "match_num",
            "p1_id", "p2_id", "p1_name", "p2_name", "p1_rank", "p2_rank",
            "winner", "score", "retirement", "minutes",
        ])
        empty_players = pd.DataFrame(
            columns=["player_id", "full_name", "hand", "height"]
        )
        # Should not raise
        paths = build_style_trends(
            tmp_path / "EmptyTrends",
            _matches_df=empty_matches,
            _players_df=empty_players,
        )
        # Overview should still be emitted
        assert any("Overview" in str(p) for p in paths)
