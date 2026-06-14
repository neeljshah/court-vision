"""vault_archive_legacy — reversibly move legacy graph-polluting notes OUT of the vault.

The Obsidian graph renders EVERY .md under the vault folder, so editing graph.json
to hide nodes does NOT stick while Obsidian is open (it rewrites the file).  The
robust way to get a clean person-free INTELLIGENCE graph (no matchups, no players,
no session/daily noise) is to physically relocate the legacy sprawl OUT of the vault
folder.  This is REVERSIBLE (``--restore``) and LOCAL (vault/ is gitignored).

KEEP in the vault (shown in the graph): ``_Organized`` (the dense person-free brain)
and ``.obsidian`` (config).  Any top-level entry that CONTAINS git-tracked files is
SKIPPED (never move tracked history).  Everything else (Intelligence/, Sports/,
Sessions/, project-doc dirs, daily notes) is moved to ``_vault_legacy_archive/``
(a sibling OUTSIDE the vault, so it is not in the graph).

HONEST: this only reorganizes the local working memory; markets efficient; no edge.

CLI:
    python -m scripts.platformkit.vault_archive_legacy            # archive (live)
    python -m scripts.platformkit.vault_archive_legacy --dry-run  # preview only
    python -m scripts.platformkit.vault_archive_legacy --restore  # move back
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

KEEP_ALWAYS = frozenset({"_Organized", ".obsidian"})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_has_tracked(path: Path, repo_root: Path) -> bool:
    """True if *path* contains any git-tracked file (so we must NOT move it)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            cwd=str(repo_root), capture_output=True, text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            return True
        out2 = subprocess.run(
            ["git", "ls-files", str(path)],
            cwd=str(repo_root), capture_output=True, text=True,
        )
        return bool(out2.stdout.strip())
    except Exception:  # pragma: no cover - if git unavailable, be SAFE (treat as tracked)
        return True


def plan_archive(
    vault_dir: Path,
    keep: frozenset = KEEP_ALWAYS,
    has_tracked: Optional[Callable[[Path], bool]] = None,
) -> Dict[str, List[str]]:
    """Decide which top-level vault entries to MOVE vs KEEP vs SKIP(tracked)."""
    repo_root = _repo_root()
    tracked = has_tracked or (lambda p: _git_has_tracked(p, repo_root))
    move: List[str] = []
    kept: List[str] = []
    skipped_tracked: List[str] = []
    if not vault_dir.is_dir():
        return {"move": [], "kept": [], "skipped_tracked": []}
    for entry in sorted(vault_dir.iterdir()):
        name = entry.name
        if name in keep:
            kept.append(name)
            continue
        if tracked(entry):
            skipped_tracked.append(name)
            continue
        move.append(name)
    return {"move": move, "kept": kept, "skipped_tracked": skipped_tracked}


def archive_legacy(
    vault_dir: Optional[Path] = None,
    archive_dir: Optional[Path] = None,
    *,
    dry_run: bool = False,
    keep: frozenset = KEEP_ALWAYS,
    has_tracked: Optional[Callable[[Path], bool]] = None,
) -> Dict:
    """Move untracked legacy entries out of *vault_dir* into *archive_dir* (reversible)."""
    vault_dir = Path(vault_dir) if vault_dir else _repo_root() / "vault"
    archive_dir = Path(archive_dir) if archive_dir else _repo_root() / "_vault_legacy_archive"
    plan = plan_archive(vault_dir, keep=keep, has_tracked=has_tracked)
    moved: List[str] = []
    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for name in plan["move"]:
            src = vault_dir / name
            dst = archive_dir / name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            shutil.move(str(src), str(dst))
            moved.append(name)
    return {
        "vault_dir": str(vault_dir),
        "archive_dir": str(archive_dir),
        "dry_run": dry_run,
        "to_move": plan["move"],
        "moved": moved,
        "kept": plan["kept"],
        "skipped_tracked": plan["skipped_tracked"],
        "n_moved": len(moved),
        "note": "reversible local reorg of working memory; markets efficient; no edge.",
    }


def restore_legacy(
    vault_dir: Optional[Path] = None,
    archive_dir: Optional[Path] = None,
    *,
    dry_run: bool = False,
) -> Dict:
    """Move everything in *archive_dir* back into *vault_dir* (the inverse op)."""
    vault_dir = Path(vault_dir) if vault_dir else _repo_root() / "vault"
    archive_dir = Path(archive_dir) if archive_dir else _repo_root() / "_vault_legacy_archive"
    restored: List[str] = []
    entries = sorted(archive_dir.iterdir()) if archive_dir.is_dir() else []
    if not dry_run:
        vault_dir.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            dst = vault_dir / entry.name
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            shutil.move(str(entry), str(dst))
            restored.append(entry.name)
    return {
        "vault_dir": str(vault_dir),
        "archive_dir": str(archive_dir),
        "dry_run": dry_run,
        "to_restore": [e.name for e in entries],
        "restored": restored,
        "n_restored": len(restored),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry-run" in argv
    if "--restore" in argv:
        rep = restore_legacy(dry_run=dry)
    else:
        rep = archive_legacy(dry_run=dry)
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["plan_archive", "archive_legacy", "restore_legacy", "KEEP_ALWAYS"]
