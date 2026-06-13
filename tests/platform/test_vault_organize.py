"""Tests for scripts.platformkit.vault_organize — synthetic tmp vault, no real writes.

Verifies the NON-DESTRUCTIVE clean/dedup re-organizer:
  - duplicate player ids collapse to ONE canonical (the largest byte size);
  - team parsed from the ``**Team:** [[PHX]]`` body line;
  - no-team players land under _Unassigned;
  - each player appears exactly once across the whole output;
  - out_dir is fresh + the source vault is untouched (files still exist, unchanged);
  - archetypes/schemes are copied into large categories;
  - report carries before/after counts + duplicates_collapsed;
  - an unreadable/odd note is skipped without crashing.
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.vault_organize import organize_vault


# --------------------------------------------------------------------------- #
# synthetic vault fixture
# --------------------------------------------------------------------------- #

def _player(team: str, name: str, pad: int = 0) -> str:
    body = (
        "<!-- PLAYSTYLE-EXPORT v1 -->\n"
        f"# {name}\n"
        f"**Team:** [[{team}]] · **Archetype:** Primary Initiator / Lead Guard\n\n"
        "## How he plays\nsome content.\n"
    )
    return body + ("x" * pad if pad else "")


def _make_vault(root: Path) -> None:
    players = root / "Intelligence" / "Players"
    players.mkdir(parents=True)
    # Same player id 100 in TWO folders -> duplicate; the larger (pad) is canonical.
    (players / "100_dup_player.md").write_text(_player("PHX", "Dup Player", pad=10), encoding="utf-8")
    sub = players / "Old"
    sub.mkdir()
    (sub / "100_dup_player.md").write_text(_player("PHX", "Dup Player", pad=5000), encoding="utf-8")
    # Two distinct PHX players (one of which is the dup above's team).
    (players / "200_phx_two.md").write_text(_player("PHX", "Phx Two"), encoding="utf-8")
    # A player with NO team line -> _Unassigned.
    (players / "300_no_team.md").write_text(
        "<!-- PLAYSTYLE-EXPORT v1 -->\n# No Team\nno team line here.\n", encoding="utf-8")
    # A non-player odd note (no digit prefix) -> skipped.
    (players / "readme_note.md").write_text("# Readme\nnot a player.\n", encoding="utf-8")

    arch = root / "Intelligence" / "Archetypes"
    arch.mkdir(parents=True)
    (arch / "primary_initiator.md").write_text("# Primary Initiator\nscheme-free.\n", encoding="utf-8")
    schemes = root / "Intelligence" / "Schemes"
    schemes.mkdir(parents=True)
    (schemes / "drop_coverage.md").write_text("# Drop Coverage\nscheme.\n", encoding="utf-8")


def _all_player_notes(out_dir: Path):
    return [p for p in (out_dir / "Teams").rglob("*.md") if p.name != "_Team.md"]


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #

def test_dedup_collapses_to_largest(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"
    rep = organize_vault(vault_dir=vault, out_dir=out)

    assert rep["duplicates_collapsed"] == 1
    # canonical players: 100, 200, 300 (readme skipped).
    assert rep["canonical_players"] == 3
    # the canonical 100 note is the LARGER (pad=5000) one.
    canon = (out / "Teams" / "PHX" / "100_dup_player.md").read_text(encoding="utf-8")
    assert len(canon) > 4000


def test_player_appears_exactly_once(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"
    organize_vault(vault_dir=vault, out_dir=out)

    notes = _all_player_notes(out)
    names = [p.name for p in notes]
    # No duplicate filenames anywhere in the output tree.
    assert len(names) == len(set(names))
    assert names.count("100_dup_player.md") == 1


def test_team_parse_and_layout(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"
    rep = organize_vault(vault_dir=vault, out_dir=out)

    # PHX has its 2 players (the deduped 100 + 200).
    phx = sorted(p.name for p in (out / "Teams" / "PHX").glob("*.md") if p.name != "_Team.md")
    assert phx == ["100_dup_player.md", "200_phx_two.md"]
    assert rep["players_per_team"]["PHX"] == 2
    # No-team player under _Unassigned.
    assert (out / "Teams" / "_Unassigned" / "300_no_team.md").is_file()
    assert rep["players_per_team"]["_Unassigned"] == 1
    # team hubs exist.
    assert (out / "Teams" / "PHX" / "_Team.md").is_file()


def test_skipped_odd_note(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"
    rep = organize_vault(vault_dir=vault, out_dir=out)
    # readme_note.md (no id prefix) skipped, not crashed.
    assert rep["skipped_player_notes"] == 1
    assert not (out / "Teams" / "PHX" / "readme_note.md").is_file()


def test_intel_categories_copied(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"
    rep = organize_vault(vault_dir=vault, out_dir=out)
    assert (out / "Archetypes" / "primary_initiator.md").is_file()
    assert (out / "Schemes" / "drop_coverage.md").is_file()
    assert rep["intel_counts"]["Archetypes"] == 1
    assert rep["intel_counts"]["Schemes"] == 1


def test_report_before_after(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"
    rep = organize_vault(vault_dir=vault, out_dir=out)
    assert "before" in rep and "after" in rep
    for key in ("n_files", "total_bytes", "person_leaks"):
        assert key in rep["before"] and key in rep["after"]
    # canonical players = source player notes minus collapsed dupes (the real win).
    assert rep["canonical_players"] == 3
    assert rep["before"]["person_leaks"] >= rep["after"]["person_leaks"]
    assert "duplicates_collapsed" in rep
    # the brain MOC was written.
    assert (out / "_Index" / "_Brain.md").is_file()


def test_source_untouched_and_out_fresh(tmp_path):
    vault = tmp_path / "vault"
    _make_vault(vault)
    src = vault / "Intelligence" / "Players" / "200_phx_two.md"
    before_text = src.read_text(encoding="utf-8")
    before_count = len(list(vault.rglob("*.md")))

    out = tmp_path / "out"
    # pre-create out with a stale file -> must be wiped fresh.
    out.mkdir()
    (out / "stale.md").write_text("stale", encoding="utf-8")

    organize_vault(vault_dir=vault, out_dir=out)

    # source unchanged.
    assert src.read_text(encoding="utf-8") == before_text
    assert len(list(vault.rglob("*.md"))) == before_count
    # out_dir is fresh (stale file gone).
    assert not (out / "stale.md").is_file()


def test_unreadable_note_skipped(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    _make_vault(vault)
    out = tmp_path / "out"

    import scripts.platformkit.vault_organize as mod
    real_read = Path.read_text

    def flaky(self, *a, **k):  # raise only for one specific player note.
        if self.name == "200_phx_two.md":
            raise OSError("boom")
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", flaky)
    rep = mod.organize_vault(vault_dir=vault, out_dir=out)
    # did not crash; the unreadable note was skipped (readme + 200 -> 2 skipped).
    assert rep["skipped_player_notes"] >= 1
    assert not (out / "Teams" / "PHX" / "200_phx_two.md").is_file()
