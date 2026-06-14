"""tests/platform/test_vault_person_free_scrub.py — unit tests for the TRUE content
person-free scrub + the brain_pipeline self-policing verification gates.

Hermetic: synthetic markdown / a tiny synthetic vault in tmp_path. NO live vault touched.

JOB 1 — content_person_free_scrub:
  * a "Top N by Impact" table of player wikilinks  -> rows + header GONE
  * an Exploiters table of BARE player names        -> rows + section header GONE
  * a team-roster link DUMP                          -> collapsed to a "Used by N teams" count
  * concept content (stat-signature, thresholds, prevalence %, mechanism prose) -> KEPT
  * no orphaned/dangling table headers or empty section headers remain

JOB 2 — brain_pipeline gates:
  * compute_gates returns person_free + graph_clean booleans on an organized tree
  * run_pipeline's summary dict includes the person_free / graph_clean keys

Pure stdlib only; no pandas/pyarrow at module top (pytest contamination guard).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ensure repo root on path before importing platformkit
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.vault_organize_multi import (  # noqa: E402
    content_person_free_scrub, organize_all)
from scripts.platformkit import brain_pipeline  # noqa: E402


# --------------------------------------------------------------------------- #
# synthetic fixtures
# --------------------------------------------------------------------------- #

# Player-leaderboard table (pathed player wikilinks) + bare-name exploiter table +
# team-link dump section + KEEP concept content + mechanism prose naming people.
SAMPLE_MD = """\
# Switch Heavy — Scheme

## Statistical Fingerprint

| Metric | Median |
|---|---|
| Usage rate | 20.4% |
| Minutes/g | 19.1 |

**Classification rule:** GF/game >= 1.60 AND Over-2.5 rate >= 58%

Prevalence: this scheme is run by 12% of teams.

## Top 15 by Impact

| Name | Team | Usage% | Top Strength |
|---|---|---|---|
| [[Players/1631214_alondes_williams|Alondes Williams]] | WAS | 31.1% | On/off impact |
| [[Players/1642484_rayj_dennis|RayJ Dennis]] | ATL | 24.4% | On/off impact |

### Top Exploiters — players who punish switch-heavy defenses

| Rank | Player | TS-spread | n |
|------|--------|-----------|---|
| 1 | Antonio Reeves | +0.505 | 44 |
| 2 | Kristaps Porzingis | +0.040 | 164 |

## Team Links

[[Teams/ATL]] · [[Teams/BKN]] · [[Teams/CLE]] · [[Teams/DET]]

**Teams whose identity is this scheme:** [[Teams/LAL]], [[Teams/PHX]]

## Position-by-Position

| Position | Stat | delta vs baseline | reading |
|---|---|---|---|
| PF | pts | +0.44 | concedes |
| SF | pts | +0.40 | concedes |

## Basketball read

The scheme neutralises stars who depend on a screen sequence; a switch removes the
trailing recovery gap so every shot is contested by a fresh defender.
"""


# --------------------------------------------------------------------------- #
# JOB 1 — content scrub tests
# --------------------------------------------------------------------------- #

def test_scrub_removes_player_names_and_links():
    """Player wikilinks + bare player names must be GONE from the scrubbed text."""
    out = content_person_free_scrub(SAMPLE_MD)
    for name in ("Alondes Williams", "RayJ Dennis", "Antonio Reeves",
                 "Kristaps Porzingis", "alondes_williams", "rayj_dennis"):
        assert name not in out, f"player name leaked through scrub: {name}"
    assert "[[Players/" not in out, "player wikilink survived scrub"
    assert "1631214" not in out and "1642484" not in out, "player-id survived scrub"


def test_scrub_removes_player_leaderboard_sections():
    """The 'Top N by Impact' + 'Top Exploiters' sections (headers too) must be dropped."""
    out = content_person_free_scrub(SAMPLE_MD)
    assert "Top 15 by Impact" not in out, "Top-N-by-Impact header survived"
    assert "Top Exploiters" not in out, "Exploiters header survived"
    # the player-table column header 'Top Strength' / 'TS-spread' should be gone too
    assert "TS-spread" not in out, "exploiter table header survived"


def test_scrub_delinks_or_counts_team_dumps():
    """Team-link DUMP -> collapsed to a 'Used by N teams' count; no team links remain."""
    out = content_person_free_scrub(SAMPLE_MD)
    assert "[[Teams/" not in out, "team wikilink survived scrub"
    for tri in ("ATL", "BKN", "CLE", "DET", "LAL", "PHX"):
        assert f"[[Teams/{tri}]]" not in out
    # the Team Links section had 4 team links -> a count line should be emitted
    assert re.search(r"Used by \d+ teams", out), "team-link dump not collapsed to a count"


def test_scrub_keeps_concept_content():
    """Stat-signature / thresholds / prevalence / position deltas / mechanism prose KEPT."""
    out = content_person_free_scrub(SAMPLE_MD)
    assert "Statistical Fingerprint" in out, "stat-signature header dropped"
    assert "Usage rate" in out and "20.4%" in out, "stat-signature row dropped"
    assert "Classification rule" in out, "threshold/classification rule dropped"
    assert "Prevalence" in out and "12%" in out, "prevalence line dropped"
    assert "Position-by-Position" in out, "position-delta section dropped"
    assert "concedes" in out, "position-delta row dropped"
    assert "Basketball read" in out, "mechanism-prose header dropped"
    assert "trailing recovery gap" in out, "mechanism prose dropped"


def test_scrub_leaves_no_orphan_headers_or_tables():
    """No dangling section header (header immediately followed by another header/EOF) and
    no orphaned table header+separator pair (header row + |---| with no data rows)."""
    out = content_person_free_scrub(SAMPLE_MD)
    lines = [ln for ln in out.splitlines()]
    sep_re = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
    row_re = re.compile(r"^\s*\|.*\|\s*$")
    hdr_re = re.compile(r"^#{1,6}\s")
    # no separator line should exist without a data row right after it
    for i, ln in enumerate(lines):
        if sep_re.match(ln):
            after = lines[i + 1] if i + 1 < len(lines) else ""
            assert row_re.match(after) and not sep_re.match(after), (
                f"orphaned table header/separator at line {i}: {ln!r}")
    # no header should be immediately followed (ignoring blanks) by another header or EOF
    for i, ln in enumerate(lines):
        if hdr_re.match(ln):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            assert j < len(lines) and not hdr_re.match(lines[j]), (
                f"empty/dangling section header survived: {ln!r}")


def test_scrub_is_idempotent():
    """Scrubbing already-clean text is a no-op (stable; no further content lost)."""
    once = content_person_free_scrub(SAMPLE_MD)
    twice = content_person_free_scrub(once)
    assert once == twice, "scrub is not idempotent"


# --------------------------------------------------------------------------- #
# JOB 2 — brain_pipeline gate tests (hermetic synthetic vault)
# --------------------------------------------------------------------------- #

def _mkfile(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_min_vault(vault: Path) -> None:
    """A minimal multi-sport source vault with a player leaderboard + team dump that the
    scrub must strip so the organized tree is person-free + graph-clean."""
    _mkfile(vault / "Intelligence" / "Teams" / "GSW.md",
            "# GSW — Team Intelligence Card\nPace pusher.\n")
    _mkfile(vault / "Intelligence" / "Archetypes" / "floor_spacer.md", SAMPLE_MD)
    _mkfile(vault / "Intelligence" / "Schemes" / "drop_coverage.md",
            "# Drop Coverage\n## Statistical Fingerprint\n\n| Metric | Median |\n"
            "|---|---|\n| Drop depth | deep |\n\nMechanism: the big sits in the paint.\n")
    _mkfile(vault / "Sports" / "MLB" / "Teams" / "BOS.md", "# BOS\nLeague: AL\n")
    _mkfile(vault / "Sports" / "MLB" / "Playstyles" / "power_run_scoring.md",
            "# Power Run Scoring\n\n## Teams in This Archetype  (2 total)\n\n"
            "| Team | RS/G |\n|---|---|\n| [[Teams/LAD]] | 5.16 |\n| [[Teams/NYY]] | 4.83 |\n")


def test_compute_gates_on_person_free_tree(tmp_path):
    """compute_gates returns booleans; a scrubbed organized tree is person-free + clean."""
    vault = tmp_path / "vault"
    out = tmp_path / "out"
    _build_min_vault(vault)
    organize_all(vault_dir=vault, out_dir=out)
    gates = brain_pipeline.compute_gates(out)
    assert set(gates) == {"person_free", "graph_clean"}
    assert isinstance(gates["person_free"], bool)
    assert isinstance(gates["graph_clean"], bool)
    assert gates["graph_clean"] is True, "organized tree has player/match NODES"
    assert gates["person_free"] is True, "organized tree still has inline person/team names"


def test_run_pipeline_summary_has_gate_keys(tmp_path):
    """run_pipeline's summary must surface person_free + graph_clean (+ edge_clean)."""
    vault = tmp_path / "vault"
    out = tmp_path / "out"
    _build_min_vault(vault)
    rep = brain_pipeline.run_pipeline(vault_dir=vault, out_dir=out, with_models=False)
    s = rep["summary"]
    for key in ("person_free", "graph_clean", "edge_clean"):
        assert key in s, f"summary missing gate key: {key}"
    assert s["person_free"] is True
    assert s["graph_clean"] is True


def test_gates_pass_helper():
    """_gates_pass is True only when all three gates hold."""
    assert brain_pipeline._gates_pass(
        {"person_free": True, "graph_clean": True, "edge_clean": True}) is True
    assert brain_pipeline._gates_pass(
        {"person_free": False, "graph_clean": True, "edge_clean": True}) is False
    assert brain_pipeline._gates_pass(
        {"person_free": True, "graph_clean": True, "edge_clean": False}) is False
    assert brain_pipeline._gates_pass({}) is False
