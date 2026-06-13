"""tests.platform.test_generators_person_free — Generator-level person-free + well-formed invariants.

Guards EACH per-sport generator before notes reach the vault (complements
test_graph_invariants which guards the vault itself).

Invariants per emitted note:
  (a) PERSON-FREE — reuses _is_person_bearing() from graph_health.py
      ([[Players/...]], player_name/display_name frontmatter, ## Players/Roster/Squad).
  (b) BARE-STEM WIKILINKS — no "../" in target, no ".md" suffix.
  (c) YAML FRONTMATTER — note starts with "---".

Hermetic: synthetic DataFrames / fixtures via tmp_path only; no real corpus reads.
Generators without an injectable seam are SKIPped with a reason.

COVERED: build_seasons, build_trends (NBA), build_atlas (tennis/_matches_df),
         build_atlas (NBA memory_atlas/_base_df), build_signals_hub,
         build_taxonomy, build_intelligence_overview.
SKIPPED: mlb.atlas.build_atlas, soccer.atlas.build_atlas (no seam, need full parquet).
"""
from __future__ import annotations

import pathlib
import re
from typing import List

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Person-free checker — reuse the CONSERVATIVE patterns from graph_health.py
# ---------------------------------------------------------------------------
from scripts.platformkit.atlas.graph_health import _is_person_bearing

_WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+)")


# ---------------------------------------------------------------------------
# Shared assertion helpers
# ---------------------------------------------------------------------------

def _collect_notes(out_dir: pathlib.Path) -> List[pathlib.Path]:
    return list(out_dir.rglob("*.md"))


def _assert_person_free(notes: List[pathlib.Path]) -> None:
    bad = [str(p) for p in notes
           if _is_person_bearing(p.read_text(encoding="utf-8", errors="replace"))]
    assert not bad, f"Person-bearing content in {len(bad)} note(s):\n" + "\n".join(bad)


def _assert_bare_stem_wikilinks(notes: List[pathlib.Path]) -> None:
    bad = [
        f"{p}: [[{m.group(1).strip()}]]"
        for p in notes
        for m in _WIKILINK_RE.finditer(p.read_text(encoding="utf-8", errors="replace"))
        if "../" in m.group(1) or m.group(1).strip().endswith(".md")
    ]
    assert not bad, "Malformed wikilink target(s):\n" + "\n".join(bad)


def _assert_has_frontmatter(notes: List[pathlib.Path]) -> None:
    bad = [str(p) for p in notes
           if not p.read_text(encoding="utf-8", errors="replace").lstrip("﻿").startswith("---")]
    assert not bad, f"{len(bad)} note(s) missing YAML frontmatter:\n" + "\n".join(bad)


def _run_all_invariants(out_dir: pathlib.Path) -> None:
    notes = _collect_notes(out_dir)
    assert notes, f"Generator emitted no .md notes under {out_dir}"
    _assert_person_free(notes)
    _assert_bare_stem_wikilinks(notes)
    _assert_has_frontmatter(notes)


# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

def _make_team_df() -> pd.DataFrame:
    rows = []
    for season in ["2022-23", "2023-24"]:
        for tricode, off, defr, pace, efg, ts, tov in [
            ("NYK", 115.0, 110.0, 97.5, 0.545, 0.575, 13.2),
            ("BOS", 119.0, 108.0, 96.0, 0.560, 0.590, 12.8),
        ]:
            rows.append({
                "team_tricode": tricode, "season_label": season,
                "off_rtg": off, "def_rtg": defr, "pace": pace,
                "efg_pct": efg, "ts_pct": ts, "tov_ratio": tov, "n_games": 60,
            })
    return pd.DataFrame(rows)


def _make_player_df() -> pd.DataFrame:
    rows = []
    for season in ["2022-23", "2023-24"]:
        for pid, usg, ts, efg, ast_pct, def_rtg, reb_pct, mins, pos, ng in [
            (1, 0.25, 0.59, 0.53, 0.25, 108.0, 0.08, 32.0, "Guard", 60),
            (2, 0.20, 0.62, 0.55, 0.10, 105.0, 0.14, 30.0, "Center", 55),
        ]:
            rows.append({
                "player_id": pid, "season_label": season, "game_id": ng,
                "usage": usg, "ts": ts, "efg": efg, "ast_pct": ast_pct,
                "def_rtg": def_rtg, "reb_pct": reb_pct, "minutes_avg": mins,
                "position": pos,
            })
    return pd.DataFrame(rows)


def _make_tennis_matches_df() -> pd.DataFrame:
    """Minimal matches DF with required columns for tennis build_atlas."""
    rows = []
    for i in range(15):
        p1_id, p2_id = (i % 5) + 1, (i % 5) + 2
        rows.append({
            "p1_id": p1_id, "p2_id": p2_id,
            "p1_name": f"PLAYER_{p1_id}", "p2_name": f"PLAYER_{p2_id}",
            "winner": 1, "surface": ["Hard", "Clay", "Grass"][i % 3],
            "tourney_name": f"Tour_{i % 3}", "tourney_level": "A",
            "date": f"2023-0{(i % 9) + 1}-15",
            "best_of": 3, "p1_rank": float(i + 1), "p2_rank": float(i + 2),
            "p1_rank_points": 1000.0, "p2_rank_points": 900.0,
        })
    return pd.DataFrame(rows)


def _make_nba_base_df() -> pd.DataFrame:
    """Minimal player base DF for memory_atlas build_atlas (_base_df seam).
    render_all omits player notes; display_name never appears in output.
    """
    return pd.DataFrame({
        "player_id": [1, 2, 3],
        "display_name": ["PLAYER_1", "PLAYER_2", "PLAYER_3"],  # renderer strips these
        "position": ["Guard", "Center", "Forward"],
        "team": ["NYK", "NYK", "BOS"],
        "usage_rate": [0.25, 0.20, 0.18],
        "n_games": [60, 55, 50],
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildSeasons:
    """build_seasons — domains.basketball_nba.memory_atlas_seasons."""

    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.basketball_nba.memory_atlas_seasons import build_seasons

        written = build_seasons(
            tmp_path, _team_df=_make_team_df(), _player_df=_make_player_df()
        )
        assert written, "build_seasons returned no paths"
        _run_all_invariants(tmp_path)


class TestBuildTrends:
    """build_trends — domains.basketball_nba.memory_atlas_trends."""

    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.basketball_nba.memory_atlas_trends import build_trends

        written = build_trends(
            tmp_path, _team_df=_make_team_df(), _player_df=_make_player_df()
        )
        assert written, "build_trends returned no paths"
        _run_all_invariants(tmp_path)


class TestTennisAtlas:
    """build_atlas (tennis) — domains.tennis.atlas (_matches_df seam)."""

    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.tennis.atlas import build_atlas

        written = build_atlas(tmp_path, _matches_df=_make_tennis_matches_df())
        assert written, "tennis build_atlas returned no paths"
        _run_all_invariants(tmp_path)


class TestNBAMemoryAtlas:
    """build_atlas (NBA) — domains.basketball_nba.memory_atlas (_base_df seam).
    Player notes intentionally omitted by render_all; only _Index.md + Teams/*.md written.
    """

    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from domains.basketball_nba.memory_atlas import build_atlas

        written = build_atlas(tmp_path, _base_df=_make_nba_base_df())
        assert written, "NBA memory_atlas build_atlas returned no paths"
        _run_all_invariants(tmp_path)


class TestSignalsHub:
    """build_signals_hub — scripts.platformkit.atlas.signals_hub.

    Driven with a synthetic vault/Sports dir containing one sport with a
    minimal _Catalog.md verdict table.  No person-bearing content in input.
    """

    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from scripts.platformkit.atlas.signals_hub import build_signals_hub

        # Build a minimal vault/Sports/<Sport>/Signals/_Catalog.md
        sports_dir = tmp_path / "Sports"
        catalog = sports_dir / "Tennis" / "Signals" / "_Catalog.md"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(
            "# Signal Catalog\n\n"
            "## Verdict table\n\n"
            "| Signal | Expected | Actual |\n"
            "|--------|----------|--------|\n"
            "| elo_delta | REJECT | REJECT |\n"
            "| surface_win_pct | REJECT | DEFER |\n",
            encoding="utf-8",
        )

        out_path = build_signals_hub(vault_sports_dir=sports_dir)
        assert out_path.exists(), "build_signals_hub did not write output"
        notes = [out_path]
        _assert_person_free(notes)
        _assert_bare_stem_wikilinks(notes)
        _assert_has_frontmatter(notes)


class TestArchetypeTaxonomy:
    """build_taxonomy — scripts.platformkit.atlas.archetype_taxonomy.

    Driven with a synthetic vault/Sports dir with two archetype notes.
    """

    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from scripts.platformkit.atlas.archetype_taxonomy import build_taxonomy

        sports_dir = tmp_path / "Sports"
        # Two minimal archetype notes (no person-bearing content)
        for sport, slug, desc in [
            ("Tennis", "high_usage_creator", "Baseline aggressor"),
            ("Tennis", "defensive_grinder",  "Defense-first style"),
        ]:
            note = sports_dir / sport / "Archetypes" / f"{slug}.md"
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(
                f"---\ntags: [sport/{sport.lower()}, archetype, high_usage]\n---\n\n"
                f"# {slug.replace('_', ' ').title()}\n\n{desc}\n",
                encoding="utf-8",
            )

        out_path = build_taxonomy(vault_sports_dir=sports_dir)
        assert out_path.exists(), "build_taxonomy did not write output"
        notes = [out_path]
        _assert_person_free(notes)
        _assert_bare_stem_wikilinks(notes)
        _assert_has_frontmatter(notes)


class TestIntelligenceOverview:
    """build_intelligence_overview — scripts.platformkit.atlas.intelligence_overview.

    Driven with an empty (but valid) vault/Sports dir.  All optional source
    notes are absent; the generator must still write a valid, person-free note.
    """

    def test_person_free_and_well_formed(self, tmp_path: pathlib.Path) -> None:
        from scripts.platformkit.atlas.intelligence_overview import build_intelligence_overview

        sports_dir = tmp_path / "Sports"
        sports_dir.mkdir(parents=True)

        out_path = build_intelligence_overview(vault_sports_dir=sports_dir)
        assert out_path.exists(), "build_intelligence_overview did not write output"
        notes = [out_path]
        _assert_person_free(notes)
        _assert_bare_stem_wikilinks(notes)
        _assert_has_frontmatter(notes)


# ---------------------------------------------------------------------------
# Skipped generators — no injectable seam; need real parquet corpus
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason=(
    "domains.mlb.atlas.build_atlas: no _games_df seam; "
    "_load_games() raises FileNotFoundError without real games.parquet."
))
def test_mlb_atlas_skip() -> None:
    pass


@pytest.mark.skip(reason=(
    "domains.soccer.atlas.build_atlas: no _matches_df seam; "
    "_load_matches() raises FileNotFoundError without real matches.parquet."
))
def test_soccer_atlas_skip() -> None:
    pass
