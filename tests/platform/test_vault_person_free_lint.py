"""test_vault_person_free_lint.py — Acceptance tests for the vault person-free linter.

Python 3.9 compatible. No network, no real-corpus reads (a synthetic tmp vault is
built per test). Covers:
  - clean archetype notes produce NO leaks;
  - player-id_name filename -> named_filename leak;
  - "# Devin Booker" title -> named_title leak; "# Primary Initiator" -> NO leak;
  - "X vs Y" file -> matchup_vs leak;
  - person_free False when leaks, True when none;
  - inventory_only counts bytes/files correctly;
  - biggest_dirs sorted desc.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))

from vault_person_free_lint import (  # noqa: E402
    Leak,
    inventory_only,
    lint_vault,
    _is_allowlisted_title,
    _vs_pair_is_allowlisted,
    _word_is_concept,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write(base: Path, rel: str, content: str) -> Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _clean_vault(base: Path) -> None:
    """A small, person-free archetype vault."""
    _write(base, "Archetypes/Primary Initiator.md",
           "---\ntags: [archetype]\n---\n\n# Primary Initiator\n\nBall-dominant creator.\n")
    _write(base, "Archetypes/Rim Runner.md",
           "---\ntags: [archetype]\n---\n\n# Rim Runner\n\nVertical roll threat.\n")
    _write(base, "Schemes/Pick And Roll.md",
           "---\ntags: [scheme]\n---\n\n# Pick And Roll\n\nTwo-man action.\n")
    _write(base, "Concepts/accuracy.md",
           "# Notes\n\nWe weigh accuracy vs edge here (a concept, not a matchup).\n")


# ---------------------------------------------------------------------------
# Clean vault -> no leaks
# ---------------------------------------------------------------------------

class TestCleanVault:
    def test_clean_notes_no_leaks(self, tmp_path: Path) -> None:
        _clean_vault(tmp_path)
        report = lint_vault(tmp_path)
        assert report["leaks"] == [], f"Expected clean, got {report['leaks']}"
        assert report["leak_counts"] == {}
        assert report["person_free"] is True

    def test_archetype_title_not_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.md", "# Primary Initiator\n\nstuff\n")
        _write(tmp_path, "b.md", "# Rim Runner\n\nstuff\n")
        _write(tmp_path, "c.md", "# Defensive Anchor\n\nstuff\n")
        report = lint_vault(tmp_path)
        assert not any(l["kind"] == "named_title" for l in report["leaks"])

    def test_lowercase_vs_not_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "x.md", "This is accuracy vs edge, a tradeoff.\n")
        report = lint_vault(tmp_path)
        assert report["person_free"] is True


# ---------------------------------------------------------------------------
# named_filename
# ---------------------------------------------------------------------------

class TestNamedFilename:
    def test_player_id_name_filename(self, tmp_path: Path) -> None:
        _write(tmp_path, "1626164_devin_booker.md", "# Some Title\n\nbody\n")
        report = lint_vault(tmp_path)
        kinds = {l["kind"] for l in report["leaks"]}
        assert "named_filename" in kinds, report["leaks"]
        assert report["person_free"] is False

    def test_plain_archetype_filename_clean(self, tmp_path: Path) -> None:
        _write(tmp_path, "rim_runner.md", "# Rim Runner\n\nbody\n")
        report = lint_vault(tmp_path)
        assert not any(l["kind"] == "named_filename" for l in report["leaks"])


# ---------------------------------------------------------------------------
# named_title
# ---------------------------------------------------------------------------

class TestNamedTitle:
    def test_first_last_title_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "note.md", "# Devin Booker\n\nbody\n")
        report = lint_vault(tmp_path)
        title_leaks = [l for l in report["leaks"] if l["kind"] == "named_title"]
        assert title_leaks, report["leaks"]
        assert "Devin Booker" in title_leaks[0]["sample"]

    def test_primary_initiator_title_not_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "note.md", "# Primary Initiator\n\nbody\n")
        report = lint_vault(tmp_path)
        assert not any(l["kind"] == "named_title" for l in report["leaks"])

    def test_allowlist_helper(self) -> None:
        assert _is_allowlisted_title("Primary", "Initiator") is True
        assert _is_allowlisted_title("Rim", "Runner") is True
        assert _is_allowlisted_title("Devin", "Booker") is False


# ---------------------------------------------------------------------------
# matchup_vs
# ---------------------------------------------------------------------------

class TestMatchupVs:
    def test_player_vs_player_file(self, tmp_path: Path) -> None:
        # Two proper-noun surnames (NOT concept tokens) -> a real person matchup.
        _write(tmp_path, "matchup.md", "Curry vs Doncic\n")
        report = lint_vault(tmp_path)
        assert any(l["kind"] == "matchup_vs" for l in report["leaks"]), report["leaks"]

    def test_team_vs_team_filename(self, tmp_path: Path) -> None:
        _write(tmp_path, "LAL vs BOS.md", "body\n")
        report = lint_vault(tmp_path)
        assert any(l["kind"] == "matchup_vs" for l in report["leaks"]), report["leaks"]

    def test_team_at_team(self, tmp_path: Path) -> None:
        _write(tmp_path, "game.md", "Tonight: LAL@BOS tip-off.\n")
        report = lint_vault(tmp_path)
        assert any(l["kind"] == "matchup_vs" for l in report["leaks"]), report["leaks"]


# --- Concept false positives — the bug this fix closes (must NOT flag) --------

# Archetype concept titles that previously tripped named_title.
_ARCHETYPE_TITLES = [
    "# Bench Contributor", "# Floor-Spacing Specialist", "# Role Player",
    "# Defensive Low-Block", "# High-Scoring Attacking",
]
# Concept "X vs Y" comparisons that previously tripped matchup_vs.
_CONCEPT_VS = [
    "Drop vs Switch", "over-dispersed vs Poisson", "Run-scoring vs. run-prevention",
]


class TestConceptNotFlagged:
    def test_archetype_titles_not_flagged(self, tmp_path: Path) -> None:
        for i, title in enumerate(_ARCHETYPE_TITLES):
            _write(tmp_path, f"arch_{i}.md", f"{title}\n\nbody\n")
        report = lint_vault(tmp_path)
        assert not any(l["kind"] == "named_title" for l in report["leaks"]), report["leaks"]
        assert report["person_free"] is True

    def test_concept_vs_not_flagged(self, tmp_path: Path) -> None:
        for i, phrase in enumerate(_CONCEPT_VS):
            _write(tmp_path, f"cmp_{i}.md", f"We contrast {phrase} here.\n")
        report = lint_vault(tmp_path)
        assert not any(l["kind"] == "matchup_vs" for l in report["leaks"]), report["leaks"]
        assert report["person_free"] is True

    def test_allowlisted_title_helper(self) -> None:
        assert _is_allowlisted_title("Bench", "Contributor") is True
        assert _is_allowlisted_title("Floor-Spacing", "Specialist") is True
        assert _is_allowlisted_title("Role", "Player") is True
        assert _is_allowlisted_title("Defensive", "Low-Block") is True
        assert _is_allowlisted_title("High-Scoring", "Attacking") is True

    def test_vs_pair_helper_suppresses_concepts(self) -> None:
        assert _vs_pair_is_allowlisted("Drop", "Switch") is True
        assert _vs_pair_is_allowlisted("over-dispersed", "Poisson") is True
        assert _vs_pair_is_allowlisted("Run-scoring", "run-prevention") is True
        assert _vs_pair_is_allowlisted("accuracy", "edge") is True

    def test_word_is_concept_hyphen_subtokens(self) -> None:
        assert _word_is_concept("Floor-Spacing") is True
        assert _word_is_concept("Low-Block") is True
        assert _word_is_concept("High-Scoring") is True
        assert _word_is_concept("Doncic") is False


# --- Synthetic REAL names still flag (must NOT be over-suppressed) ------------

class TestRealNamesStillFlag:
    def test_real_named_title_flags(self, tmp_path: Path) -> None:
        _write(tmp_path, "n.md", "# Luka Doncic\n\nbody\n")
        report = lint_vault(tmp_path)
        assert any(l["kind"] == "named_title" for l in report["leaks"]), report["leaks"]
        assert report["person_free"] is False

    def test_real_team_matchup_flags(self, tmp_path: Path) -> None:
        _write(tmp_path, "m.md", "Tonight: Lakers vs Celtics.\n")
        report = lint_vault(tmp_path)
        assert any(l["kind"] == "matchup_vs" for l in report["leaks"]), report["leaks"]
        assert report["person_free"] is False

    def test_real_tricode_matchup_flags(self, tmp_path: Path) -> None:
        _write(tmp_path, "g.md", "Slate: LAL vs BOS.\n")
        report = lint_vault(tmp_path)
        assert any(l["kind"] == "matchup_vs" for l in report["leaks"]), report["leaks"]

    def test_vs_pair_helper_flags_real(self) -> None:
        assert _vs_pair_is_allowlisted("Lakers", "Celtics") is False
        assert _vs_pair_is_allowlisted("LAL", "BOS") is False
        assert _vs_pair_is_allowlisted("Luka", "Doncic") is False


# ---------------------------------------------------------------------------
# person_free verdict
# ---------------------------------------------------------------------------

class TestPersonFreeVerdict:
    def test_false_when_leaks(self, tmp_path: Path) -> None:
        _write(tmp_path, "1626164_devin_booker.md", "# Devin Booker\n")
        assert lint_vault(tmp_path)["person_free"] is False

    def test_true_when_none(self, tmp_path: Path) -> None:
        _clean_vault(tmp_path)
        assert lint_vault(tmp_path)["person_free"] is True

    def test_empty_dir_person_free(self, tmp_path: Path) -> None:
        report = lint_vault(tmp_path)
        assert report["person_free"] is True
        assert report["n_files"] == 0

    def test_missing_dir_no_crash(self, tmp_path: Path) -> None:
        report = lint_vault(tmp_path / "does_not_exist")
        assert report["person_free"] is True
        assert report["n_files"] == 0

    def test_leaks_list_bounded(self, tmp_path: Path) -> None:
        # Many leaky files; the returned leaks list is capped but counts are exact.
        for i in range(250):
            _write(tmp_path, f"{1000 + i}_first_last.md", "body\n")
        report = lint_vault(tmp_path)
        assert len(report["leaks"]) <= 200
        assert report["leak_counts"]["named_filename"] == 250


# ---------------------------------------------------------------------------
# inventory_only
# ---------------------------------------------------------------------------

class TestInventory:
    def test_counts_bytes_and_files(self, tmp_path: Path) -> None:
        _write(tmp_path, "A/one.md", "x" * 100)
        _write(tmp_path, "A/two.md", "y" * 50)
        _write(tmp_path, "B/three.md", "z" * 200)
        _write(tmp_path, "root.md", "r" * 10)
        inv = inventory_only(tmp_path)
        assert inv["n_files"] == 4
        assert inv["total_bytes"] == 100 + 50 + 200 + 10
        assert inv["by_dir"]["A"]["n_files"] == 2
        assert inv["by_dir"]["A"]["bytes"] == 150
        assert inv["by_dir"]["B"]["bytes"] == 200
        assert inv["by_dir"]["."]["n_files"] == 1
        assert inv["by_dir"]["."]["bytes"] == 10

    def test_ignores_non_md(self, tmp_path: Path) -> None:
        _write(tmp_path, "note.md", "hello")
        (tmp_path / "data.parquet").write_bytes(b"\x00\x01\x02")
        (tmp_path / "img.png").write_bytes(b"\x89PNG")
        inv = inventory_only(tmp_path)
        assert inv["n_files"] == 1
        assert inv["total_bytes"] == len("hello")

    def test_biggest_dirs_sorted_desc(self, tmp_path: Path) -> None:
        _write(tmp_path, "Small/a.md", "x" * 10)
        _write(tmp_path, "Big/b.md", "x" * 1000)
        _write(tmp_path, "Mid/c.md", "x" * 100)
        inv = inventory_only(tmp_path)
        dirs = [d for d, _ in inv["biggest_dirs"]]
        assert dirs[:3] == ["Big", "Mid", "Small"]
        sizes = [b for _, b in inv["biggest_dirs"]]
        assert sizes == sorted(sizes, reverse=True)


# ---------------------------------------------------------------------------
# Leak dataclass
# ---------------------------------------------------------------------------

class TestLeakDataclass:
    def test_as_dict(self) -> None:
        leak = Leak("Archetypes/x.md", "named_title", "# Devin Booker")
        d = leak.as_dict()
        assert d == {
            "file": "Archetypes/x.md",
            "kind": "named_title",
            "sample": "# Devin Booker",
        }
