"""
brain_fix_relative_links.py -- normalize vault wikilinks to Obsidian-valid form.

Obsidian [[...]] links CANNOT follow ``../`` relative paths or a ``.md`` suffix.
Several brain generators emit links like ``[[../Schemes/x.md|x]]`` which silently
fail to resolve -- so those edges never render in the graph and you cannot
navigate page-to-page. This is a post-build normalizer: it resolves every
``../``- or ``.md``-bearing wikilink against the note's own folder on disk and
rewrites it to a canonical vault-root-relative link (``[[_Organized/NBA/Schemes/x|x]]``),
which resolves unambiguously even when note names repeat across sports.

Idempotent: already-clean links are left untouched; targets that do not exist on
disk are left exactly as-is (never invents a new broken link). No network, no
pandas, no edge claims -- pure filesystem + string ops.

    python scripts/platformkit/brain_fix_relative_links.py vault [--dry-run]

Wire this as the FINAL step of any brain rebuild so the fix never regresses.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

_LINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
_FENCE = re.compile(r"^\s*```")

# Hubs that were renamed: dead link target stem -> current stem in the same dir.
# The per-sport "_Index" MOC was consolidated into "_Digest".
_STALE_HUB = {"_Index": "_Digest"}


def _needs_fix(tok: str) -> bool:
    t = tok.split("|", 1)[0].split("#", 1)[0].strip()
    return "../" in t or t.lower().endswith(".md")


def _canonical(tok: str, note_parent: Path, vault: Path) -> str | None:
    """Resolve a raw link token to 'vault-rel/stem(#anchor)', or None if unresolvable."""
    tok = tok.strip()
    if not tok or tok.startswith("#"):
        return None
    anchor = ""
    if "#" in tok:
        tok, _, rest = tok.partition("#")
        anchor = "#" + rest
    tok = tok.strip()
    noext = tok[:-3] if tok.lower().endswith(".md") else tok
    try:
        target = (note_parent / (noext + ".md")).resolve()
    except (OSError, ValueError):
        return None
    if not target.exists():
        # stale-hub remap (e.g. a removed per-sport _Index -> the _Digest MOC)
        leaf = Path(noext)
        if leaf.name in _STALE_HUB:
            alt = note_parent / leaf.with_name(_STALE_HUB[leaf.name])
            alt = Path(str(alt) + ".md")
            try:
                alt = alt.resolve()
            except (OSError, ValueError):
                return None
            if alt.exists():
                target = alt
            else:
                return None
        else:
            return None
    try:
        rel = target.relative_to(vault).as_posix()
    except ValueError:
        return None
    if rel.lower().endswith(".md"):
        rel = rel[:-3]
    return rel + anchor


def fix_text(text: str, note_parent: Path, vault: Path) -> tuple[str, int]:
    out: list[str] = []
    n = 0
    in_fence = False
    for line in text.splitlines(keepends=True):
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or "[[" not in line:
            out.append(line)
            continue

        def repl(m: re.Match) -> str:
            nonlocal n
            inner = m.group(1)
            tok, sep, alias = inner.partition("|")
            if not _needs_fix(tok):
                return m.group(0)
            canon = _canonical(tok, note_parent, vault)
            if canon is None:
                return m.group(0)
            al = alias if sep else Path(tok.split("#")[0].strip()).stem
            new = f"[[{canon}|{al}]]"
            if new != m.group(0):
                n += 1
            return new

        out.append(_LINK.sub(repl, line))
    return "".join(out), n


def normalize_vault(vault_root, write: bool = True) -> dict:
    vault = Path(vault_root).resolve()
    files = sorted(vault.rglob("*.md"))
    scanned = links_fixed = files_changed = 0
    samples: list[str] = []
    for p in files:
        try:
            t = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        new, n = fix_text(t, p.parent, vault)
        if n and new != t:
            links_fixed += n
            files_changed += 1
            if len(samples) < 3:
                samples.append(p.relative_to(vault).as_posix())
            if write:
                p.write_text(new, encoding="utf-8")
    return {"scanned": scanned, "links_fixed": links_fixed,
            "files_changed": files_changed, "sample_files": samples,
            "mode": "WRITE" if write else "DRY"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Normalize vault wikilinks for Obsidian.")
    ap.add_argument("vault", nargs="?", default="vault")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    r = normalize_vault(a.vault, write=not a.dry_run)
    print("mode         :", r["mode"])
    print("files scanned:", r["scanned"])
    print("links fixed  :", r["links_fixed"])
    print("files changed:", r["files_changed"])
    print("sample files :", r["sample_files"])


if __name__ == "__main__":
    main()
