"""tests/platform/test_vault_organize_multi.py — unit tests for vault_organize_multi.

Builds a tiny synthetic fixture vault in tmp_path, runs organize_all(), and asserts:
  1. No matchup notes in output (no path contains "Matchups" or " vs ").
  2. Duplicate player collapsed to ONE canonical (richest) note under its team.
  3. Each team hub (_Team.md) folds the source team-note text.
  4. _Index/_Brain.md exists and names the sports present.
  5. Per-sport _Index.md exists.
  6. Person-free intel categories are copied for each sport present.

Pure stdlib only; no pandas/pyarrow at module top (pytest contamination guard).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ensure repo root on path before importing platformkit
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.vault_organize_multi import organize_all  # noqa: E402


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


def test_duplicate_player_collapsed(run_result):
    """The duplicate player id 1234 should produce exactly ONE canonical note."""
    out, report = run_result
    nba_teams = out / "NBA" / "Teams"
    player_files = list(nba_teams.rglob("*.md"))
    # find files for id 1234
    id1234 = [f for f in player_files if f.stem.startswith("1234_")]
    assert len(id1234) == 1, f"Expected 1 canonical note for id 1234, got {len(id1234)}: {id1234}"
    # the richer note (more content) should be kept
    assert "1234_alice_smith" in id1234[0].stem, (
        f"Expected richer note '1234_alice_smith', got '{id1234[0].stem}'"
    )
    # also verify dupes count in report
    assert report["per_sport"]["NBA"]["duplicates_collapsed"] >= 1


def test_team_hub_contains_source_text(run_result):
    """_Team.md for GSW must fold in the source team note content."""
    out, _ = run_result
    hub = out / "NBA" / "Teams" / "GSW" / "_Team.md"
    assert hub.exists(), f"_Team.md not found at {hub}"
    content = hub.read_text(encoding="utf-8")
    assert "Great defense" in content, (
        "Source team note text not folded into _Team.md"
    )


def test_team_hub_contains_roster(run_result):
    """_Team.md for GSW must list the canonical player."""
    out, _ = run_result
    hub = out / "NBA" / "Teams" / "GSW" / "_Team.md"
    content = hub.read_text(encoding="utf-8")
    assert "1234_alice_smith" in content, "Canonical player not listed in team hub"


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
