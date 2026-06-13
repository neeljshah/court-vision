"""tests/platform/test_tennis_atlas.py — Scoped tests for the tennis atlas generator.

Uses a tiny synthetic matches fixture (no network, no GPU, no heavy deps).
Verifies:
  1. _Index.md exists after build_atlas()
  2. NO Players/ directory is emitted (player notes removed)
  3. Notes contain valid [[wikilinks]] and YAML frontmatter
  4. No exceptions raised
  5. Surface notes exist for Hard, Clay, Grass
  6. _Index references Playstyles/_Playstyles_Index
  7. Surface notes do not contain individual player names
  8. No betting/edge language in any note

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

    def test_no_players_dir(self, atlas_out: pathlib.Path) -> None:
        """Players/ directory must NOT be emitted — individual player notes removed."""
        players_dir = atlas_out / "Players"
        assert not players_dir.is_dir(), (
            f"Players/ directory should not exist; found {list(players_dir.glob('*.md'))}"
        )

    def test_playstyles_index_referenced_in_index(self, atlas_out: pathlib.Path) -> None:
        """_Index.md must link to the Playstyles index."""
        text = (atlas_out / "_Index.md").read_text(encoding="utf-8")
        assert "Playstyles/_Playstyles_Index" in text, (
            "_Index.md does not reference [[Playstyles/_Playstyles_Index]]"
        )

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

    def test_surface_note_has_frontmatter(self, atlas_out: pathlib.Path) -> None:
        path = atlas_out / "Surfaces" / "Hard.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---"), "Surface note does not have YAML frontmatter"
        assert "surface:" in text, "Surface note missing surface: in frontmatter"

    def test_surface_note_has_index_backlink(self, atlas_out: pathlib.Path) -> None:
        path = atlas_out / "Surfaces" / "Clay.md"
        text = path.read_text(encoding="utf-8")
        assert "[[_Index" in text, "Surface note missing [[_Index]] backlink"

    def test_surface_notes_no_player_links(self, atlas_out: pathlib.Path) -> None:
        """Surface notes must not contain [[Players/...]] wikilinks."""
        for surf in ("Hard", "Clay", "Grass"):
            text = (atlas_out / "Surfaces" / f"{surf}.md").read_text(encoding="utf-8")
            assert "[[Players/" not in text, (
                f"Surface note {surf}.md contains individual [[Players/...]] link"
            )

    def test_no_betting_language(self, atlas_out: pathlib.Path) -> None:
        """Notes must not contain edge/betting language (whole-word match)."""
        import re
        # Use whole-word boundaries to avoid false positives like "level" containing "EV"
        forbidden = ["betting", "edge", "roi", "wager", "gamble", "odds"]
        for md_file in atlas_out.rglob("*.md"):
            text = md_file.read_text(encoding="utf-8").lower()
            for term in forbidden:
                pattern = r"\b" + re.escape(term) + r"\b"
                assert not re.search(pattern, text), (
                    f"Forbidden term '{term}' found in {md_file.name}"
                )

    def test_build_atlas_returns_paths(
        self, synthetic_matches: pd.DataFrame, tmp_path: pathlib.Path
    ) -> None:
        """build_atlas() must return a non-empty list of Path objects."""
        from domains.tennis.atlas import build_atlas

        paths = build_atlas(tmp_path / "atlas2", _matches_df=synthetic_matches)
        assert isinstance(paths, list), "build_atlas did not return a list"
        # Now: index + 3 surfaces = 4 minimum (no player notes)
        assert len(paths) >= 4, f"Expected at least 4 notes (index+3 surfaces), got {len(paths)}"
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
