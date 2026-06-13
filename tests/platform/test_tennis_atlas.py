"""tests/platform/test_tennis_atlas.py — Scoped tests for the tennis atlas generator.

Uses a tiny synthetic matches fixture (no network, no GPU, no heavy deps).
Verifies:
  1. _Index.md exists after build_atlas()
  2. At least one player note exists in Players/
  3. Notes contain valid [[wikilinks]] and YAML frontmatter
  4. No exceptions raised
  5. Surface notes exist for Hard, Clay, Grass
  6. Player note has expected stat fields

Run: python -m pytest tests/platform/test_tennis_atlas.py -q --timeout=120
"""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Synthetic fixture factory
# ---------------------------------------------------------------------------

def _make_matches(n: int = 60) -> pd.DataFrame:
    """Return a minimal synthetic match DataFrame matching the Sackmann schema."""
    rng = np.random.default_rng(7)
    base_date = dt.date(2022, 1, 3)
    dates = [base_date + dt.timedelta(days=int(d)) for d in np.cumsum(rng.integers(1, 5, n))]

    player_ids = list(range(1, 12))   # 11 synthetic players
    player_names = {i: f"Player {i:02d}" for i in player_ids}

    rows: list[dict] = []
    for i, d in enumerate(dates):
        p1, p2 = int(rng.choice(player_ids, replace=False)), int(
            rng.choice([x for x in player_ids if x != rng.integers(1, 12)], replace=False)
        )
        # Ensure distinct
        while p1 == p2:
            p2 = int(rng.choice(player_ids))
        surface = ["Hard", "Clay", "Grass"][i % 3]
        winner = int(rng.integers(1, 3))   # 1 or 2
        best_of = 5 if i % 7 == 0 else 3
        rounds = ["R32", "R16", "QF", "SF", "F"]
        rows.append(
            {
                "event_id": f"event_{i:04d}",
                "date": str(d),
                "tour": "atp",
                "tourney_id": f"2022-T{i % 5:03d}",
                "tourney_name": ["Australian Open", "Wimbledon", "Roland Garros"][i % 3],
                "tourney_level": ["G", "A", "M"][i % 3],
                "surface": surface,
                "best_of": best_of,
                "round": rounds[i % len(rounds)],
                "match_num": i + 1,
                "p1_id": p1,
                "p2_id": p2,
                "p1_name": player_names[p1],
                "p2_name": player_names[p2],
                "p1_rank": float(rng.integers(1, 50)),
                "p2_rank": float(rng.integers(1, 100)),
                "winner": winner,
                "score": "6-4 6-3",
                "retirement": False,
                "minutes": float(rng.integers(60, 150)),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_matches() -> pd.DataFrame:
    return _make_matches(60)


@pytest.fixture(scope="module")
def atlas_out(tmp_path_factory: pytest.TempPathFactory, synthetic_matches: pd.DataFrame) -> pathlib.Path:
    """Build the atlas from the synthetic fixture and return the output directory."""
    from domains.tennis.atlas import build_atlas

    out = tmp_path_factory.mktemp("tennis_atlas")
    build_atlas(out, _matches_df=synthetic_matches)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAtlasOutputs:
    def test_index_exists(self, atlas_out: pathlib.Path) -> None:
        assert (atlas_out / "_Index.md").exists(), "_Index.md not found"

    def test_player_notes_exist(self, atlas_out: pathlib.Path) -> None:
        players_dir = atlas_out / "Players"
        assert players_dir.is_dir(), "Players/ directory not created"
        notes = list(players_dir.glob("*.md"))
        assert len(notes) >= 1, f"Expected at least 1 player note, got {len(notes)}"

    def test_surface_notes_exist(self, atlas_out: pathlib.Path) -> None:
        for surf in ("Hard", "Clay", "Grass"):
            path = atlas_out / "Surfaces" / f"{surf}.md"
            assert path.exists(), f"Surface note not found: {surf}.md"

    def test_index_has_wikilinks(self, atlas_out: pathlib.Path) -> None:
        text = (atlas_out / "_Index.md").read_text(encoding="utf-8")
        assert "[[" in text and "]]" in text, "_Index.md contains no [[wikilinks]]"

    def test_index_has_frontmatter(self, atlas_out: pathlib.Path) -> None:
        text = (atlas_out / "_Index.md").read_text(encoding="utf-8")
        assert text.startswith("---"), "_Index.md does not start with YAML frontmatter"
        assert text.count("---") >= 2, "_Index.md frontmatter not closed"

    def test_player_note_has_frontmatter(self, atlas_out: pathlib.Path) -> None:
        notes = list((atlas_out / "Players").glob("*.md"))
        assert notes, "No player notes to check"
        text = notes[0].read_text(encoding="utf-8")
        assert text.startswith("---"), "Player note does not start with YAML frontmatter"
        assert "player_id:" in text, "Player note missing player_id in frontmatter"
        assert "current_elo:" in text, "Player note missing current_elo in frontmatter"

    def test_player_note_has_wikilinks(self, atlas_out: pathlib.Path) -> None:
        notes = list((atlas_out / "Players").glob("*.md"))
        assert notes, "No player notes to check"
        text = notes[0].read_text(encoding="utf-8")
        assert "[[_Index" in text, "Player note missing [[_Index]] backlink"

    def test_player_note_has_surface_section(self, atlas_out: pathlib.Path) -> None:
        notes = list((atlas_out / "Players").glob("*.md"))
        assert notes, "No player notes to check"
        text = notes[0].read_text(encoding="utf-8")
        assert "Surface Splits" in text, "Player note missing Surface Splits section"

    def test_surface_note_has_frontmatter(self, atlas_out: pathlib.Path) -> None:
        path = atlas_out / "Surfaces" / "Hard.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---"), "Surface note does not have YAML frontmatter"
        assert "surface:" in text, "Surface note missing surface: in frontmatter"

    def test_surface_note_has_index_backlink(self, atlas_out: pathlib.Path) -> None:
        path = atlas_out / "Surfaces" / "Clay.md"
        text = path.read_text(encoding="utf-8")
        assert "[[_Index" in text, "Surface note missing [[_Index]] backlink"

    def test_no_betting_language(self, atlas_out: pathlib.Path) -> None:
        """Notes must not contain edge/betting language."""
        forbidden = ["betting", "edge", "ROI", "EV", "wager", "gamble", "odds"]
        for md_file in atlas_out.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8").lower()
            for term in forbidden:
                assert term.lower() not in text, (
                    f"Forbidden term '{term}' found in {md_file.name}"
                )

    def test_build_atlas_returns_paths(
        self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path
    ) -> None:
        """build_atlas() must return a non-empty list of Path objects."""
        from domains.tennis.atlas import build_atlas

        paths = build_atlas(tmp_path / "atlas2", _matches_df=synthetic_matches)
        assert isinstance(paths, list), "build_atlas did not return a list"
        assert len(paths) >= 4, f"Expected at least 4 notes (index+3 surfaces+players), got {len(paths)}"
        for p in paths:
            assert isinstance(p, pathlib.Path), f"Non-Path in returned list: {p!r}"
            assert p.exists(), f"Returned path does not exist: {p}"

    def test_idempotent(
        self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path
    ) -> None:
        """Running build_atlas twice on the same out_dir must not raise."""
        from domains.tennis.atlas import build_atlas

        out = tmp_path / "idem"
        paths1 = build_atlas(out, _matches_df=synthetic_matches)
        paths2 = build_atlas(out, _matches_df=synthetic_matches)
        assert len(paths1) == len(paths2), "Idempotent re-run returned different note count"
