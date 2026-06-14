"""test_vault_archive_legacy — reversible legacy-sprawl archival (hermetic, tmp dirs)."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.vault_archive_legacy import (
    archive_legacy,
    plan_archive,
    restore_legacy,
)


def _mk(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_vault(tmp: Path) -> Path:
    v = tmp / "vault"
    _mk(v / "_Organized" / "NBA" / "_WhatWins.md")
    _mk(v / ".obsidian" / "graph.json", "{}")
    _mk(v / "Intelligence" / "Matchups" / "LAL@BOS_2026.md")  # matchup sprawl
    _mk(v / "Sports" / "MLB" / "Matchups" / "NYY_vs_BOS.md")   # MLB matchup
    _mk(v / "Models" / "Iter61.md")                            # has a "tracked" file
    _mk(v / "Sessions" / "log.md")
    _mk(v / "2026-05-27.md")                                   # daily note
    return v


def _tracked_models_only(entry: Path) -> bool:
    # Simulate git: only the Models dir contains a tracked file.
    return entry.name == "Models"


def test_plan_keeps_brain_skips_tracked_moves_sprawl(tmp_path):
    v = _build_vault(tmp_path)
    plan = plan_archive(v, has_tracked=_tracked_models_only)
    assert set(plan["kept"]) == {"_Organized", ".obsidian"}
    assert plan["skipped_tracked"] == ["Models"]
    assert set(plan["move"]) == {"Intelligence", "Sports", "Sessions", "2026-05-27.md"}


def test_archive_moves_sprawl_out_and_keeps_brain(tmp_path):
    v = _build_vault(tmp_path)
    arch = tmp_path / "_vault_legacy_archive"
    rep = archive_legacy(v, arch, has_tracked=_tracked_models_only)
    # brain + tracked kept in vault
    assert (v / "_Organized" / "NBA" / "_WhatWins.md").exists()
    assert (v / ".obsidian" / "graph.json").exists()
    assert (v / "Models" / "Iter61.md").exists()
    # matchups GONE from the vault (the whole point)
    assert not (v / "Intelligence").exists()
    assert not (v / "Sports").exists()
    assert list(v.rglob("*Matchup*")) == [] and list(v.rglob("*vs*")) == []
    # moved into the archive (reversible)
    assert (arch / "Sports" / "MLB" / "Matchups" / "NYY_vs_BOS.md").exists()
    assert rep["n_moved"] == 4


def test_dry_run_moves_nothing(tmp_path):
    v = _build_vault(tmp_path)
    arch = tmp_path / "_vault_legacy_archive"
    rep = archive_legacy(v, arch, dry_run=True, has_tracked=_tracked_models_only)
    assert rep["moved"] == [] and rep["n_moved"] == 0
    assert (v / "Intelligence").exists()  # untouched
    assert not arch.exists()


def test_restore_is_inverse(tmp_path):
    v = _build_vault(tmp_path)
    arch = tmp_path / "_vault_legacy_archive"
    archive_legacy(v, arch, has_tracked=_tracked_models_only)
    assert not (v / "Sports").exists()
    back = restore_legacy(v, arch)
    assert (v / "Sports" / "MLB" / "Matchups" / "NYY_vs_BOS.md").exists()
    assert (v / "Intelligence" / "Matchups" / "LAL@BOS_2026.md").exists()
    assert back["n_restored"] == 4
    assert not any(arch.iterdir())  # archive emptied
