"""Rewrite atlas manifest card_path values to repo-relative (clone-safe).

The 7 built atlas manifests (out/atlas_*_manifest.json) historically stored
ABSOLUTE card_path values ("C:\\Users\\neelj\\nba-ai-system\\docs\\img\\...")
which break on a fresh clone / any other machine. This rewriter makes every
entry's card_path repo-relative + forward-slashed (e.g.
"docs/img/atlas/nba/nolan_traore.png"); the atlas_card resolver rejoins it
against the repo root at runtime.

Idempotent: a manifest already relative is left byte-identical. Absent-of-data
is fine -- no manifests just means nothing to do.

    python scripts/platformkit/analytics_showcase/atlas_manifest_relpath.py          # rewrite in place
    python scripts/platformkit/analytics_showcase/atlas_manifest_relpath.py --check   # verify only, nonzero exit on any absolute/unresolvable path

ponytail: anchors on the repo root, with a "docs/img/atlas/" fallback for a
stray path rooted elsewhere -- all 7 manifests store paths under that tree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "scripts/platformkit/analytics_showcase/out"
_ANCHOR = "docs/img/atlas/"


def _is_abs(s: str) -> bool:
    """Windows-drive OR posix-absolute, platform-independent (a Windows abs
    path is not recognized as absolute by posixpath on a Linux clone)."""
    s = s.replace("\\", "/")
    return s.startswith("/") or (len(s) >= 2 and s[1] == ":")


def to_relpath(card_path: str) -> str:
    """Absolute-or-relative card_path -> repo-relative forward-slashed path.
    Idempotent: an already-relative path returns unchanged."""
    s = str(card_path).replace("\\", "/")
    root = str(_REPO).replace("\\", "/").rstrip("/")
    if s.startswith(root + "/"):
        s = s[len(root) + 1:]
    if _is_abs(s):  # rooted elsewhere -- anchor on the atlas tree
        i = s.find(_ANCHOR)
        if i != -1:
            s = s[i:]
    return s


def _manifests() -> list[Path]:
    return sorted(_OUT_DIR.glob("atlas_*_manifest.json")) if _OUT_DIR.is_dir() else []


def rewrite(path: Path) -> int:
    """Rewrite one manifest in place. Returns count of card_path values changed
    (0 => already relative => file left untouched)."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for entry in manifest.get("entries", []):
        cp = entry.get("card_path")
        if cp is None:
            continue
        rel = to_relpath(cp)
        if rel != cp:
            entry["card_path"] = rel
            changed += 1
    if changed:
        path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return changed


def check(path: Path) -> list[str]:
    """Return a list of problem strings for one manifest: any card_path that is
    still absolute, or is relative but does not resolve to a file under the
    repo. Empty list => clean."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    for entry in manifest.get("entries", []):
        cp = entry.get("card_path")
        if cp is None:
            continue
        if _is_abs(cp):
            problems.append(f"ABSOLUTE {entry.get('entity')!r}: {cp}")
        elif not (_REPO / cp).exists():
            problems.append(f"UNRESOLVED {entry.get('entity')!r}: {cp}")
    return problems


def main(argv: list[str]) -> int:
    do_check = "--check" in argv
    manifests = _manifests()
    if not manifests:
        print("no atlas manifests in out/ -- nothing to do")
        return 0
    if do_check:
        total = 0
        for p in manifests:
            problems = check(p)
            total += len(problems)
            status = "OK" if not problems else f"{len(problems)} PROBLEM(S)"
            print(f"[check] {p.name}: {status}")
            for pr in problems[:5]:
                print(f"        {pr}")
        if total:
            print(f"FAIL: {total} absolute/unresolvable card_path(s) remain")
            return 1
        print(f"PASS: {len(manifests)} manifests, all card_path values repo-relative and resolvable")
        return 0
    for p in manifests:
        n = rewrite(p)
        print(f"[rewrite] {p.name}: {n} card_path(s) made relative"
              + (" (already relative)" if n == 0 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
