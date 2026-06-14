"""Smoke tests for scripts.platformkit.brain_pipeline — the one-command brain runner.

Builds a tiny fixture source vault in tmp_path, runs organize->digest->export, and
asserts the combined report aggregates the three stage reports. Pure stdlib.
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.brain_pipeline import run_pipeline


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_source_vault(root: Path) -> None:
    """Minimal NBA source layout that organize_all can consume."""
    intel = root / "Intelligence"
    _w(intel / "Teams" / "PHX.md", "# PHX\n\nPhoenix team note.\n")
    _w(intel / "Players" / "100_devin_booker.md",
       "# Devin Booker\n\n**Team:** [[PHX]] · **Archetype:** High-Usage Scorer\n\n"
       "- **Position:** Guard\n- **Usage rate:** 31.2%\n")
    _w(intel / "Players" / "101_kevin_durant.md",
       "# Kevin Durant\n\n**Team:** [[PHX]] · **Archetype:** Three Level Scorer\n\n"
       "- **Position:** Forward\n- **Usage rate:** 29.0%\n")
    _w(intel / "Archetypes" / "high_usage_scorer.md",
       "# High Usage Scorer\n\n**Usage:** high\n\nA primary on-ball scorer.\n")
    _w(intel / "Schemes" / "drop_coverage.md", "# Drop Coverage\n\nBig sags below screen.\n")
    # a matchup note that must be DROPPED
    _w(intel / "Matchups" / "PHX vs LAL.md", "# PHX vs LAL\n\nmatchup note.\n")


def test_pipeline_runs_all_three_stages(tmp_path):
    src = tmp_path / "vault"
    _make_source_vault(src)
    out = tmp_path / "out"
    rep = run_pipeline(vault_dir=src, out_dir=out)

    # combined report shape
    assert set(rep["stages"]) == {"organize", "digest", "export", "models", "audit"}
    # with_models defaults OFF -> no real-data model stages run (keeps test hermetic)
    assert rep["stages"]["models"] == {}
    assert rep["summary"]["model_artifacts"] == {}
    # final self-policing gate: the generated tree carries no un-caveated edge claim
    assert rep["summary"]["edge_clean"] is True
    assert rep["summary"]["edge_flagged"] == 0
    assert "summary" in rep and "note" in rep
    assert "edge" not in rep["note"].lower() or "not a betting edge" in rep["note"].lower()

    # organize stage produced the tree — person-free by default: _Identity, not _Team
    assert Path(rep["organized_root"]).is_dir()
    assert (out / "NBA" / "Teams" / "PHX" / "_Identity.md").is_file()
    assert not (out / "NBA" / "Teams" / "PHX" / "_Team.md").exists()

    # digest + export stages wrote files
    assert rep["summary"]["digests_written"] >= 1
    assert rep["summary"]["reads_written"] >= 1
    assert (out / "NBA" / "_Read.md").is_file()


def test_pipeline_drops_matchups_and_is_person_free(tmp_path):
    src = tmp_path / "vault"
    _make_source_vault(src)
    out = tmp_path / "out"
    rep = run_pipeline(vault_dir=src, out_dir=out)

    # no matchup file leaked into the organized tree
    assert not list(out.rglob("*vs*.md"))
    assert not list(out.rglob("Matchups/*"))

    # person-free default: NO per-player notes emitted; player count is zero
    assert rep["summary"]["players_total"] == 0
    nba_team_dir = out / "NBA" / "Teams" / "PHX"
    player_notes = [p for p in nba_team_dir.glob("*.md") if not p.name.startswith("_")]
    assert player_notes == [], f"Player notes leaked: {player_notes}"
    # the only team file is the person-free identity hub, and it names no players
    identity = (nba_team_dir / "_Identity.md").read_text(encoding="utf-8")
    assert "booker" not in identity.lower() and "durant" not in identity.lower()
    # team hub still tracked in the digest counts (subdir present)
    assert rep["summary"]["teams_total"] >= 1
