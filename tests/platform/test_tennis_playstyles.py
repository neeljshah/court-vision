"""tests/platform/test_tennis_playstyles.py — Unit tests for atlas_playstyles.py.

Uses a tiny synthetic fixture (no real files needed).
Asserts archetype notes exist, _Playstyles_Index.md exists, no player names
leaked, valid frontmatter/links, counts sum to total, no betting language,
and idempotency.

Run: python -m pytest tests/platform/test_tennis_playstyles.py -q --timeout=120
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
from typing import List

import numpy as np
import pandas as pd
import pytest

# Player names that must NOT appear in any emitted note
_SYNTHETIC_NAMES = [f"SynthPlayer {i:02d}" for i in range(1, 16)]


def _make_matches(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base_date = dt.date(2020, 1, 1)
    dates = [base_date + dt.timedelta(days=int(d)) for d in np.cumsum(rng.integers(1, 4, n))]
    player_ids = list(range(1, 16))
    player_names = {i: _SYNTHETIC_NAMES[i - 1] for i in player_ids}
    surfaces = ["Hard", "Clay", "Grass"]
    rows: list[dict] = []
    for i, d in enumerate(dates):
        p1 = int(rng.choice(player_ids))
        p2 = int(rng.choice([x for x in player_ids if x != p1]))
        rows.append({
            "event_id": f"ev_{i:04d}", "date": str(d), "tour": "atp",
            "tourney_id": f"2020-T{i % 5:03d}", "tourney_name": "Synthetic Open",
            "tourney_level": "A", "surface": surfaces[i % 3],
            "best_of": 5 if i % 6 == 0 else 3, "round": "R32", "match_num": i + 1,
            "p1_id": p1, "p2_id": p2,
            "p1_name": player_names[p1], "p2_name": player_names[p2],
            "p1_rank": float(rng.integers(1, 100)), "p2_rank": float(rng.integers(1, 100)),
            "winner": int(rng.integers(1, 3)), "score": "6-4 6-3",
            "retirement": False, "minutes": float(rng.integers(60, 180)),
        })
    return pd.DataFrame(rows)


def _make_players() -> pd.DataFrame:
    rows: list[dict] = []
    for i in range(1, 16):
        rows.append({
            "player_id": i, "full_name": _SYNTHETIC_NAMES[i - 1],
            "name_first": "Synth", "name_last": f"Player {i:02d}",
            "hand": "L" if i % 5 == 0 else "R",
            "height": float(185 + (i % 10) * 3),
            "ioc": "USA", "dob": "1995-01-01", "tour": "atp",
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def synthetic_matches() -> pd.DataFrame:
    return _make_matches(120)


@pytest.fixture(scope="module")
def synthetic_players() -> pd.DataFrame:
    return _make_players()


@pytest.fixture(scope="module")
def playstyles_out(
    tmp_path_factory: pytest.TempPathFactory,
    synthetic_matches: pd.DataFrame,
    synthetic_players: pd.DataFrame,
) -> pathlib.Path:
    from domains.tennis.atlas_playstyles import build_playstyles
    out = tmp_path_factory.mktemp("tennis_playstyles")
    build_playstyles(out, _matches_df=synthetic_matches, _players_df=synthetic_players)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoteExistence:
    def test_playstyles_index_exists(self, playstyles_out: pathlib.Path) -> None:
        assert (playstyles_out / "_Playstyles_Index.md").exists()

    def test_all_archetype_notes_exist(self, playstyles_out: pathlib.Path) -> None:
        from domains.tennis.atlas_playstyles import ARCHETYPES
        for spec in ARCHETYPES:
            assert (playstyles_out / f"{spec.slug}.md").exists(), f"Missing: {spec.slug}.md"

    def test_correct_file_count(self, playstyles_out: pathlib.Path) -> None:
        from domains.tennis.atlas_playstyles import ARCHETYPES
        notes = list(playstyles_out.glob("*.md"))
        assert len(notes) == len(ARCHETYPES) + 1, f"Got {len(notes)} notes"


class TestNoPlayerNamesLeaked:
    def test_no_synthetic_names(self, playstyles_out: pathlib.Path) -> None:
        for md_file in playstyles_out.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            for name in _SYNTHETIC_NAMES:
                assert name not in text, f"Name '{name}' leaked into {md_file.name}"

    def test_no_player_tag(self, playstyles_out: pathlib.Path) -> None:
        for md_file in playstyles_out.glob("*.md"):
            assert "#player" not in md_file.read_text(encoding="utf-8"), \
                f"#player tag in {md_file.name}"

    def test_no_players_wikilink(self, playstyles_out: pathlib.Path) -> None:
        for md_file in playstyles_out.glob("*.md"):
            assert "[[Players/" not in md_file.read_text(encoding="utf-8"), \
                f"[[Players/...]] link in {md_file.name}"


class TestFrontmatterAndLinks:
    def test_index_frontmatter(self, playstyles_out: pathlib.Path) -> None:
        text = (playstyles_out / "_Playstyles_Index.md").read_text(encoding="utf-8")
        assert text.startswith("---") and text.count("---") >= 2
        assert "total_qualifying_players:" in text
        assert "[[_Index" in text

    def test_archetype_frontmatter_and_links(self, playstyles_out: pathlib.Path) -> None:
        from domains.tennis.atlas_playstyles import ARCHETYPES
        for spec in ARCHETYPES:
            text = (playstyles_out / f"{spec.slug}.md").read_text(encoding="utf-8")
            assert text.startswith("---"), f"{spec.slug}.md missing frontmatter"
            assert "archetype:" in text and "player_count:" in text
            assert "Playstyles/_Playstyles_Index" in text
            assert "sport/tennis" in text


class TestArchetypeCounts:
    def test_counts_non_negative(self, playstyles_out: pathlib.Path) -> None:
        from domains.tennis.atlas_playstyles import ARCHETYPES
        for spec in ARCHETYPES:
            text = (playstyles_out / f"{spec.slug}.md").read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("player_count:"):
                    assert int(line.split(":")[1].strip()) >= 0

    def test_counts_sum_to_total(self, playstyles_out: pathlib.Path) -> None:
        from domains.tennis.atlas_playstyles import ARCHETYPES
        idx = (playstyles_out / "_Playstyles_Index.md").read_text(encoding="utf-8")
        total_line = next(l for l in idx.splitlines() if l.startswith("total_qualifying_players:"))
        total = int(total_line.split(":")[1].strip())
        summed = 0
        for spec in ARCHETYPES:
            text = (playstyles_out / f"{spec.slug}.md").read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("player_count:"):
                    summed += int(line.split(":")[1].strip()); break
        assert summed == total, f"Sum {summed} != total {total}"

    def test_build_returns_paths(
        self, synthetic_matches: pd.DataFrame, synthetic_players: pd.DataFrame,
        tmp_path: pathlib.Path,
    ) -> None:
        from domains.tennis.atlas_playstyles import ARCHETYPES, build_playstyles
        paths = build_playstyles(
            tmp_path / "ps2", _matches_df=synthetic_matches, _players_df=synthetic_players
        )
        assert len(paths) == len(ARCHETYPES) + 1
        for p in paths:
            assert isinstance(p, pathlib.Path) and p.exists()


class TestNoBettingLanguage:
    def test_no_betting_language(self, playstyles_out: pathlib.Path) -> None:
        forbidden = ["betting", "edge", "roi", "wager", "gamble", "odds"]
        for md_file in playstyles_out.glob("*.md"):
            text = md_file.read_text(encoding="utf-8").lower()
            for term in forbidden:
                assert not re.search(r"\b" + re.escape(term) + r"\b", text), \
                    f"Forbidden term '{term}' in {md_file.name}"


class TestIdempotency:
    def test_idempotent(
        self, synthetic_matches: pd.DataFrame, synthetic_players: pd.DataFrame,
        tmp_path: pathlib.Path,
    ) -> None:
        from domains.tennis.atlas_playstyles import build_playstyles
        out = tmp_path / "idem"
        p1 = build_playstyles(out, _matches_df=synthetic_matches, _players_df=synthetic_players)
        p2 = build_playstyles(out, _matches_df=synthetic_matches, _players_df=synthetic_players)
        assert len(p1) == len(p2)
