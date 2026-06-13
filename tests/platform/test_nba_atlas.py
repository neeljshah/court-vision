"""tests.platform.test_nba_atlas — scoped test for the NBA memory atlas generator.

Uses synthetic in-memory fixtures so no real parquets are required.
Run with:
    python -m pytest tests/platform/test_nba_atlas.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pytest

from domains.basketball_nba.memory_atlas import build_atlas

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_TAG_RE = re.compile(r"sport/nba")  # matches both YAML "- sport/nba" and inline "#sport/nba"


def _make_base_df() -> pd.DataFrame:
    """Synthetic player base table (3 players, 2 teams)."""
    return pd.DataFrame(
        {
            "player_id": [1001, 1002, 1003],
            "display_name": ["Alice Star", "Bob Guard", "Carol Center"],
            "position": ["Guard", "Guard", "Center"],
            "team": ["NYK", "NYK", "SAS"],
            "usage_rate": [0.32, 0.25, 0.28],
            "minutes_pg": [34.0, 29.5, 31.2],
            "pie_mean": [0.19, 0.14, 0.17],
            "on_off_net_diff": [8.5, 3.2, 5.1],
            "n_games": [50, 45, 48],
            "creator_role": ["primary_creator", "secondary", "primary_creator"],
        }
    )


def _make_adv_df() -> pd.DataFrame:
    """Synthetic player_adv_stats rows (two games per player)."""
    rows = []
    for pid, gdate in [(1001, "2025-03-01"), (1001, "2025-04-01"),
                       (1002, "2025-03-01"), (1002, "2025-04-01"),
                       (1003, "2025-03-01"), (1003, "2025-04-01")]:
        rows.append(
            {
                "player_id": pid,
                "game_id": f"00224{pid}{gdate}",
                "game_date": gdate,
                "usagepercentage": 0.30,
                "trueshootingpercentage": 0.58,
                "effectivefieldgoalpercentage": 0.52,
                "assistpercentage": 0.22,
                "reboundpercentage": 0.09,
                "offensiverating": 115.0,
                "defensiverating": 110.0,
                "netrating": 5.0,
                "pie": 0.18,
                "minutes": 32.0,
                "assisttoturnover": 2.0,
                "assistratio": 0.18,
                "turnoverratio": 12.0,
                "offensivereboundpercentage": 0.04,
                "defensivereboundpercentage": 0.14,
                "possessions": 70.0,
                "paceper40": 98.0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_atlas_creates_expected_files(tmp_path: pathlib.Path) -> None:
    """build_atlas emits _Index + team notes (no player notes) without errors."""
    base = _make_base_df()
    adv = _make_adv_df()

    # Use a nonexistent data_dir so cache/parquet loading silently skips
    fake_data = tmp_path / "fake_data"

    written = build_atlas(
        out_dir=tmp_path / "out",
        data_dir=fake_data,
        _base_df=base,
        _adv_df=adv,
    )

    paths = {p.name for p in written}
    assert "_Index.md" in paths, "Missing _Index.md"

    team_notes = [p for p in written if "Teams" in str(p)]
    assert len(team_notes) >= 1, "No team notes emitted"


def test_no_players_directory(tmp_path: pathlib.Path) -> None:
    """Players/ directory must NOT be created — player notes are retired."""
    base = _make_base_df()
    adv = _make_adv_df()
    fake_data = tmp_path / "fake_data"

    build_atlas(tmp_path / "out", fake_data, _base_df=base, _adv_df=adv)

    players_dir = tmp_path / "out" / "Players"
    assert not players_dir.exists(), (
        f"Players/ directory should not exist but was created at {players_dir}"
    )


def test_index_references_archetypes(tmp_path: pathlib.Path) -> None:
    """_Index.md must reference the Archetypes/_Archetypes_Index wikilink."""
    base = _make_base_df()
    adv = _make_adv_df()
    fake_data = tmp_path / "fake_data"

    build_atlas(tmp_path / "out", fake_data, _base_df=base, _adv_df=adv)

    index_text = (tmp_path / "out" / "_Index.md").read_text(encoding="utf-8")
    assert "Archetypes" in index_text, "_Index.md should reference Archetypes"
    links = _WIKILINK_RE.findall(index_text)
    archetype_links = [l for l in links if "Archetype" in l]
    assert len(archetype_links) >= 1, (
        f"_Index.md should have at least one Archetypes wikilink; found: {links}"
    )


def test_index_has_wikilinks_and_tags(tmp_path: pathlib.Path) -> None:
    """_Index.md must contain valid [[wikilinks]] and #sport/nba tag."""
    base = _make_base_df()
    adv = _make_adv_df()
    fake_data = tmp_path / "fake_data"

    build_atlas(tmp_path / "out", fake_data, _base_df=base, _adv_df=adv)

    index = (tmp_path / "out" / "_Index.md").read_text(encoding="utf-8")
    links = _WIKILINK_RE.findall(index)
    assert len(links) >= 2, f"Expected ≥2 wikilinks, found {len(links)}: {links}"
    assert _TAG_RE.search(index), "Missing #sport/nba tag in _Index.md"


def test_team_note_has_frontmatter_and_wikilink(tmp_path: pathlib.Path) -> None:
    """Each team note must have YAML frontmatter and at least one [[wikilink]]."""
    base = _make_base_df()
    adv = _make_adv_df()
    fake_data = tmp_path / "fake_data"

    build_atlas(tmp_path / "out", fake_data, _base_df=base, _adv_df=adv)

    team_dir = tmp_path / "out" / "Teams"
    notes = list(team_dir.glob("*.md"))
    assert len(notes) >= 1

    for note in notes:
        text = note.read_text(encoding="utf-8")
        assert _FRONTMATTER_RE.search(text), f"{note.name}: missing YAML frontmatter"
        links = _WIKILINK_RE.findall(text)
        assert len(links) >= 1, f"{note.name}: missing [[wikilinks]]"
        assert "sport/nba" in text, f"{note.name}: missing sport/nba tag"


def test_team_notes_contain_no_player_names(tmp_path: pathlib.Path) -> None:
    """Team notes must NOT contain any of the fixture player display names.

    The synthetic fixture uses "Alice Star", "Bob Guard", "Carol Center" — none
    of these strings may appear anywhere in any team note after the roster section
    was replaced by archetype composition.
    """
    base = _make_base_df()
    adv = _make_adv_df()
    fake_data = tmp_path / "fake_data"

    build_atlas(tmp_path / "out", fake_data, _base_df=base, _adv_df=adv)

    fixture_names = ["Alice Star", "Bob Guard", "Carol Center", "Alice", "Bob", "Carol"]
    team_dir = tmp_path / "out" / "Teams"
    for note in team_dir.glob("*.md"):
        text = note.read_text(encoding="utf-8")
        for name in fixture_names:
            assert name not in text, (
                f"{note.name} contains player name '{name}' — team notes must be name-free"
            )


def test_team_notes_have_archetype_composition_section(tmp_path: pathlib.Path) -> None:
    """Team notes must contain an 'Archetype Composition' section header."""
    base = _make_base_df()
    adv = _make_adv_df()
    fake_data = tmp_path / "fake_data"

    build_atlas(tmp_path / "out", fake_data, _base_df=base, _adv_df=adv)

    team_dir = tmp_path / "out" / "Teams"
    for note in team_dir.glob("*.md"):
        text = note.read_text(encoding="utf-8")
        assert "## Archetype Composition" in text, (
            f"{note.name}: missing '## Archetype Composition' section"
        )
        # Section must NOT use the old "Roster (Top Players by Usage)" heading
        assert "Roster (Top Players by Usage)" not in text, (
            f"{note.name}: old 'Roster' heading still present — must be removed"
        )


def test_idempotent(tmp_path: pathlib.Path) -> None:
    """Running build_atlas twice produces the same file count."""
    base = _make_base_df()
    adv = _make_adv_df()
    fake_data = tmp_path / "fake_data"
    out = tmp_path / "out"

    w1 = build_atlas(out, fake_data, _base_df=base, _adv_df=adv)
    w2 = build_atlas(out, fake_data, _base_df=base, _adv_df=adv)
    assert len(w1) == len(w2), "Idempotency violation: different file counts on rerun"


def test_return_type_is_list_of_paths(tmp_path: pathlib.Path) -> None:
    """build_atlas must return list[pathlib.Path]."""
    base = _make_base_df()
    adv = _make_adv_df()
    result = build_atlas(tmp_path / "out", tmp_path / "fake", _base_df=base, _adv_df=adv)
    assert isinstance(result, list)
    assert all(isinstance(p, pathlib.Path) for p in result)
