"""tests/platform/test_vault_organize_multi.py — unit tests for vault_organize_multi.

Builds a tiny synthetic fixture vault in tmp_path, runs organize_all(), and asserts
the PERSON-FREE default plus the legacy ``with_named`` escape hatch:
  1. No matchup notes in output (no path contains "Matchups" or " vs ").
  2. Default = person-free: NO per-player .md files anywhere in the output tree.
  3. Each team gets a person-free ``_Identity.md`` (style signature / scheme tags /
     archetype distribution) with NO roster table and NO named players.
  4. _Index/_Brain.md exists and names the sports present.
  5. Per-sport _Index.md exists.
  6. Person-free intel categories are copied for each sport present.
  7. The ``with_named=True`` escape hatch restores legacy per-player notes + _Team.md
     and collapses duplicate player ids to ONE canonical (richest) note.

Pure stdlib only; no pandas/pyarrow at module top (pytest contamination guard).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

# ensure repo root on path before importing platformkit
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.vault_organize_multi import organize_all  # noqa: E402

# player-id_first_last.md filename (a person leak we must NOT emit by default)
NAMED_FILENAME_RE = re.compile(r"^\d{3,}_[a-z]+_[a-z]+", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# fixture builder helpers
# --------------------------------------------------------------------------- #

def _mkfile(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_fixture(vault: Path) -> None:
    """Create a minimal multi-sport fixture vault."""

    # ----- NBA: Intelligence/Players --- two notes for same player id (dedup test)
    # "richer" note: more content
    _mkfile(
        vault / "Intelligence" / "Players" / "1234_alice_smith.md",
        "# Alice Smith\n**Team:** [[GSW]] · **Archetype:** Floor Spacer\n"
        + "A" * 500 + "\n",
    )
    # "thinner" duplicate (same id prefix) — should be dropped
    _mkfile(
        vault / "Intelligence" / "Players" / "1234_alice_s.md",
        "# Alice Smith\n**Team:** [[GSW]] · **Archetype:** Floor Spacer\nShort.\n",
    )
    # second player on different team
    _mkfile(
        vault / "Intelligence" / "Players" / "5678_bob_jones.md",
        "# Bob Jones\n**Team:** [[BOS]] · **Archetype:** Rim Runner\n" + "B" * 300 + "\n",
    )

    # ----- NBA: Intelligence/Teams (source team notes)
    _mkfile(
        vault / "Intelligence" / "Teams" / "GSW.md",
        "# GSW — Team Intelligence Card\nGreat defense, pace pusher.\n",
    )
    _mkfile(
        vault / "Intelligence" / "Teams" / "BOS.md",
        "# BOS — Team Intelligence Card\nStrong perimeter D.\n",
    )

    # ----- NBA: matchup note that MUST be dropped
    _mkfile(
        vault / "Intelligence" / "Matchups" / "GSW vs BOS.md",
        "# GSW vs BOS matchup\n",
    )

    # ----- NBA: Archetypes (person-free intel)
    _mkfile(
        vault / "Intelligence" / "Archetypes" / "floor_spacer.md",
        "# Floor Spacer\nProfile content.\n",
    )

    # ----- NBA: Schemes
    _mkfile(
        vault / "Intelligence" / "Schemes" / "drop_coverage.md",
        "# Drop Coverage\nScheme details.\n",
    )

    # ----- NBA: Trends
    _mkfile(
        vault / "Intelligence" / "Trends" / "pace_trend.md",
        "# Pace Trend\nTrend data.\n",
    )

    # ----- MLB: Teams
    _mkfile(
        vault / "Sports" / "MLB" / "Teams" / "BOS.md",
        "# BOS\nLeague: AL\nMLB team stats.\n",
    )
    # ----- MLB: Matchups — MUST be dropped
    _mkfile(
        vault / "Sports" / "MLB" / "Matchups" / "BOS vs NYY.md",
        "# BOS vs NYY\nMatchup note.\n",
    )
    # ----- MLB: Playstyles (archetypes)
    _mkfile(
        vault / "Sports" / "MLB" / "Playstyles" / "power_run_scoring.md",
        "# Power Run Scoring\nMLB archetype.\n",
    )
    # ----- MLB: StyleMatchups — MUST be dropped
    _mkfile(
        vault / "Sports" / "MLB" / "StyleMatchups" / "power_vs_grinder.md",
        "# Power vs Grinder style matchup.\n",
    )

    # ----- Soccer: Teams
    _mkfile(
        vault / "Sports" / "Soccer" / "Teams" / "Arsenal.md",
        "# Arsenal\nSoccer team content.\n",
    )
    # ----- Soccer: Matchups — MUST be dropped
    _mkfile(
        vault / "Sports" / "Soccer" / "Matchups" / "Arsenal vs Chelsea.md",
        "# Arsenal vs Chelsea\n",
    )
    # ----- Soccer: Playstyles
    _mkfile(
        vault / "Sports" / "Soccer" / "Playstyles" / "high_scoring_attacking.md",
        "# High Scoring Attacking\nSoccer style.\n",
    )

    # ----- Tennis: Playstyles (no player notes)
    _mkfile(
        vault / "Sports" / "Tennis" / "Playstyles" / "clay_court_specialist.md",
        "# Clay Court Specialist\nTennis style.\n",
    )
    _mkfile(
        vault / "Sports" / "Tennis" / "Surfaces" / "Clay.md",
        "# Clay Surface\nSurface details.\n",
    )


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def run_result(tmp_path_factory):
    """Build the fixture vault once, run organize_all, return (out_dir, report)."""
    vault = tmp_path_factory.mktemp("vault")
    out = tmp_path_factory.mktemp("out")
    _build_fixture(vault)
    report = organize_all(vault_dir=vault, out_dir=out)
    return out, report


def test_no_matchup_notes_in_output(run_result):
    """No output file path should contain 'Matchups' or ' vs '."""
    out, _ = run_result
    violations = []
    for p in out.rglob("*.md"):
        rel = p.relative_to(out).as_posix()
        if "Matchups" in rel or " vs " in rel:
            violations.append(rel)
    assert violations == [], f"Matchup notes leaked into output: {violations}"


def test_person_free_default_no_player_notes(run_result):
    """Default run must be PERSON-FREE: no per-player .md files anywhere in output."""
    out, report = run_result
    # the player-id_first_last filename pattern (e.g. 1234_alice_smith.md) must NOT appear
    player_files = [
        p.relative_to(out).as_posix()
        for p in out.rglob("*.md")
        if NAMED_FILENAME_RE.match(p.stem)
    ]
    assert player_files == [], f"Player notes leaked into person-free output: {player_files}"
    # report should reflect zero emitted players and flag person-free
    assert report["per_sport"]["NBA"]["n_players"] == 0
    assert report["with_named"] is False
    assert report["person_free"] is True
    # dedup still happens internally (records are parsed for the distribution)
    assert report["per_sport"]["NBA"]["duplicates_collapsed"] >= 1


def test_with_named_escape_hatch_restores_players(tmp_path_factory):
    """with_named=True restores legacy per-player notes; dupe id collapses to richest."""
    vault = tmp_path_factory.mktemp("vault_named")
    out = tmp_path_factory.mktemp("out_named")
    _build_fixture(vault)
    report = organize_all(vault_dir=vault, out_dir=out, with_named=True)
    assert report["with_named"] is True
    nba_teams = out / "NBA" / "Teams"
    id1234 = [f for f in nba_teams.rglob("*.md") if f.stem.startswith("1234_")]
    assert len(id1234) == 1, f"Expected 1 canonical note for id 1234, got {id1234}"
    assert "1234_alice_smith" in id1234[0].stem  # richest note kept
    assert report["per_sport"]["NBA"]["duplicates_collapsed"] >= 1
    assert report["per_sport"]["NBA"]["n_players"] >= 2
    # legacy roster hub is emitted (not _Identity)
    assert (nba_teams / "GSW" / "_Team.md").exists()
    assert not (nba_teams / "GSW" / "_Identity.md").exists()


def test_identity_hub_is_person_free(run_result):
    """Default GSW hub is _Identity.md (NOT _Team.md) and is person-free."""
    out, _ = run_result
    team_dir = out / "NBA" / "Teams" / "GSW"
    identity = team_dir / "_Identity.md"
    assert identity.exists(), f"_Identity.md not found at {identity}"
    assert not (team_dir / "_Team.md").exists(), "Legacy _Team.md emitted by default"
    content = identity.read_text(encoding="utf-8")
    # NO named player, NO roster table, NO 'X vs Y' matchup, NO raw source prose
    assert "alice" not in content.lower(), "Named player leaked into _Identity.md"
    assert "1234_" not in content, "Player-id stem leaked into _Identity.md"
    assert "| Player |" not in content, "Roster table leaked into _Identity.md"
    assert " vs " not in content, "Matchup line leaked into _Identity.md"
    assert "Great defense" not in content, "Raw source prose folded into _Identity.md"


def test_identity_hub_carries_style_intelligence(run_result):
    """_Identity.md must carry person-free style intelligence (archetype distribution)."""
    out, _ = run_result
    content = (out / "NBA" / "Teams" / "GSW" / "_Identity.md").read_text(encoding="utf-8")
    # the archetype label (a concept, not a person) IS expected
    assert "Floor Spacer" in content, "Archetype distribution missing from _Identity.md"
    assert "Style Identity" in content, "_Identity.md header missing"


def test_brain_exists_and_names_sports(run_result):
    """_Index/_Brain.md must exist and reference each sport."""
    out, _ = run_result
    brain = out / "_Index" / "_Brain.md"
    assert brain.exists(), "_Brain.md not found"
    text = brain.read_text(encoding="utf-8")
    for sport in ("NBA", "MLB", "Soccer", "Tennis"):
        assert sport in text, f"Sport '{sport}' missing from _Brain.md"


def test_per_sport_index_exists(run_result):
    """Each sport must have a _Index.md."""
    out, _ = run_result
    for sport in ("NBA", "MLB", "Soccer", "Tennis"):
        idx = out / sport / "_Index.md"
        assert idx.exists(), f"{sport}/_Index.md missing"


def test_intel_categories_copied(run_result):
    """Person-free intel categories must be copied for relevant sports."""
    out, _ = run_result
    # NBA archetypes
    assert (out / "NBA" / "Archetypes" / "floor_spacer.md").exists()
    # MLB playstyles -> Archetypes
    assert (out / "MLB" / "Archetypes" / "power_run_scoring.md").exists()
    # Soccer
    assert (out / "Soccer" / "Archetypes" / "high_scoring_attacking.md").exists()
    # Tennis
    assert (out / "Tennis" / "Archetypes" / "clay_court_specialist.md").exists()
    assert (out / "Tennis" / "Reference" / "Clay.md").exists()


def test_no_stylematchups_in_output(run_result):
    """StyleMatchups notes should not appear in output."""
    out, _ = run_result
    violations = [
        p.relative_to(out).as_posix()
        for p in out.rglob("*.md")
        if "StyleMatchups" in p.relative_to(out).as_posix()
        or "power_vs_grinder" in p.stem
    ]
    assert violations == [], f"StyleMatchups leaked: {violations}"


def test_report_structure(run_result):
    """Report dict must contain expected keys."""
    _, report = run_result
    assert "before" in report
    assert "after" in report
    assert "per_sport" in report
    assert set(report["per_sport"].keys()) >= {"NBA", "MLB", "Soccer", "Tennis"}
    assert report["after"]["matchup_vs_leaks"] == 0, (
        f"matchup_vs leaks in output: {report['after']['matchup_vs_leaks']}"
    )
