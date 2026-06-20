"""
brain_reachability.py -- prove the brain is ONE navigable graph from the index.

BFS from vault/_Index.md following resolved Obsidian wikilinks. A note is
"reachable" iff you can click your way to it starting at the master index.
Obsidian resolves [[target|alias]] by, in order:
  1. exact vault-relative path (with or without a .md suffix),
  2. a unique path SUFFIX  (link path matches the tail of exactly one note),
  3. a unique basename     (final component matches exactly one note),
  4. Obsidian's shortest-path tiebreak when a basename is ambiguous
     (prefer the same folder as the source note, then the shortest path).
Links inside `inline code` spans and ``` fenced blocks are ignored (Obsidian
does not render those as links).

Reports total / reachable / unreachable notes and the undirected component
count. Non-note files (e.g. *.canvas) are never counted; a tiny, explicit
EXCLUDE set documents any .md deliberately left out of the navigable graph.

    python scripts/platformkit/brain_reachability.py vault [--list] [--assert]

Wire --assert as the FINAL gate of any brain rebuild (see brain_graph_finalize).
"""
from __future__ import annotations
import argparse
import re
import sys
from collections import deque
from pathlib import Path

ROOT_NOTE = "_Index.md"

# Documented exclusions: real .md files intentionally OUTSIDE the navigable graph.
# Keep this list SHORT and explicit. (Currently empty -- every note is linked.)
EXCLUDE: frozenset[str] = frozenset()

_LINK = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
_FENCE = re.compile(r"^\s*```")
_INLINE_CODE = re.compile(r"`[^`]*`")


def _all_notes(vault: Path) -> list[Path]:
    return sorted(p for p in vault.rglob("*.md") if ".obsidian" not in p.parts)


def _rel(p: Path, vault: Path) -> str:
    return p.relative_to(vault).as_posix()[:-3]  # drop ".md"


def extract_links(text: str) -> list[str]:
    """Return raw link targets (before '|'/'#'), skipping code spans/fences."""
    targets: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = _INLINE_CODE.sub("", line)  # drop inline-code so its [[..]] is ignored
        for m in _LINK.finditer(line):
            tok = m.group(1).split("|", 1)[0].split("#", 1)[0].strip()
            if tok:
                targets.append(tok)
    return targets


class Resolver:
    """Maps a raw link token to a vault-relative note key, Obsidian-style."""

    def __init__(self, vault: Path):
        self.vault = vault
        notes = _all_notes(vault)
        self.keys = {_rel(p, vault) for p in notes}          # vault-rel, no .md
        self.by_base: dict[str, list[str]] = {}
        for k in self.keys:
            self.by_base.setdefault(k.rsplit("/", 1)[-1], []).append(k)

    def _norm(self, tok: str) -> str:
        t = tok.replace("\\", "/").strip()
        if t.lower().endswith(".md"):
            t = t[:-3]
        return t.lstrip("/")

    def resolve(self, tok: str, src_key: str) -> str | None:
        t = self._norm(tok)
        if not t:
            return None
        if t in self.keys:                                   # 1. exact path
            return t
        if "/" in t:                                         # 2. unique suffix
            hits = [k for k in self.keys if k == t or k.endswith("/" + t)]
            if len(hits) == 1:
                return hits[0]
            if hits:
                return self._tiebreak(hits, src_key)
        base = t.rsplit("/", 1)[-1]
        cand = self.by_base.get(base, [])                    # 3 + 4. basename
        if len(cand) == 1:
            return cand[0]
        if cand:
            return self._tiebreak(cand, src_key)
        return None

    @staticmethod
    def _tiebreak(cands: list[str], src_key: str) -> str:
        src_dir = src_key.rsplit("/", 1)[0] if "/" in src_key else ""
        same = [c for c in cands if (c.rsplit("/", 1)[0] if "/" in c else "") == src_dir]
        pool = same or cands
        return min(pool, key=lambda c: (c.count("/"), len(c), c))


def analyze(vault_root, list_unreached: bool = False) -> dict:
    vault = Path(vault_root)
    notes = _all_notes(vault)
    keys = {_rel(p, vault) for p in notes}
    excluded = {k for k in keys if (k + ".md") in EXCLUDE or k in EXCLUDE}
    in_scope = keys - excluded

    res = Resolver(vault)
    adj: dict[str, set[str]] = {k: set() for k in keys}
    for p in notes:
        src = _rel(p, vault)
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw in extract_links(text):
            tgt = res.resolve(raw, src)
            if tgt and tgt != src:
                adj[src].add(tgt)

    root = ROOT_NOTE[:-3]
    reachable: set[str] = set()
    if root in keys:
        q = deque([root])
        reachable.add(root)
        while q:
            cur = q.popleft()
            for nxt in adj[cur]:
                if nxt not in reachable:
                    reachable.add(nxt)
                    q.append(nxt)

    # Undirected connected components over in-scope notes.
    und: dict[str, set[str]] = {k: set() for k in in_scope}
    for a, outs in adj.items():
        if a not in in_scope:
            continue
        for b in outs:
            if b in in_scope:
                und[a].add(b)
                und[b].add(a)
    seen: set[str] = set()
    comps = 0
    for k in in_scope:
        if k in seen:
            continue
        comps += 1
        q = deque([k]); seen.add(k)
        while q:
            c = q.popleft()
            for n in und[c]:
                if n not in seen:
                    seen.add(n); q.append(n)

    unreached = sorted((in_scope & keys) - reachable)
    out = {
        "total": len(keys),
        "in_scope": len(in_scope),
        "excluded": sorted(excluded),
        "reachable": len(reachable & in_scope),
        "unreachable": len(unreached),
        "components": comps,
        "root_present": root in keys,
    }
    if list_unreached:
        out["unreachable_notes"] = unreached
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="BFS reachability of the brain graph.")
    ap.add_argument("vault", nargs="?", default="vault")
    ap.add_argument("--list", action="store_true", help="list unreachable notes")
    ap.add_argument("--assert", dest="assert_full", action="store_true",
                    help="exit 1 unless every in-scope note is reachable")
    a = ap.parse_args()
    r = analyze(a.vault, list_unreached=a.list or a.assert_full)
    print(f"root present : {r['root_present']}")
    print(f"total notes  : {r['total']}")
    print(f"in scope     : {r['in_scope']}  (excluded: {len(r['excluded'])})")
    print(f"reachable    : {r['reachable']}")
    print(f"unreachable  : {r['unreachable']}")
    print(f"components   : {r['components']}")
    if r["excluded"]:
        print("excluded     :", ", ".join(r["excluded"]))
    if (a.list or a.assert_full) and r["unreachable"]:
        print("-- unreachable notes --")
        for k in r["unreachable_notes"][:80]:
            print("  ", k)
        if r["unreachable"] > 80:
            print(f"   ... and {r['unreachable'] - 80} more")
    if a.assert_full and r["unreachable"]:
        print("ASSERT FAILED: graph is not fully reachable from _Index.")
        sys.exit(1)
    if a.assert_full:
        print("ASSERT OK: reachable == in_scope.")


if __name__ == "__main__":
    main()
