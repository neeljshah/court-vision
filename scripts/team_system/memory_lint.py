"""MEMORY LINT -- keep the Claude memory a clean, deduped, hash-indexed knowledge graph
(MASTER_SYSTEM_BUILD section 5).

Runs at the START of every session and BLOCKS if MEMORY.md > 200 index lines OR there is any broken
[[link]] OR any stale file:line citation. When it blocks, the session's FIRST lever must be the memory
cleanse (nothing else) until lint passes. Memory is append-with-dedup: sharpen an existing fact, never a
second copy; NEVER delete a recorded rejection (knowledge) -- only de-duplicate it.

  python scripts/team_system/memory_lint.py            # human-readable report
  python scripts/team_system/memory_lint.py --check    # exit 1 if BLOCKING (for the loop / a hook)
"""
from __future__ import annotations
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEM_DIR = os.path.expanduser(os.path.join("~", ".claude", "projects", "C--Users-neelj", "memory"))
INDEX = os.path.join(MEM_DIR, "MEMORY.md")
MAX_INDEX_LINES = 200

_CODE_EXTS = "py|md|json|parquet|ps1|js|ipynb|txt|yaml|yml|toml|cfg|ini|sql|csv"
_CITATION = re.compile(r"(?<![\w/])([\w./\\-]+\.(?:" + _CODE_EXTS + r")):(\d+)")
_WIKILINK = re.compile(r"\[\[([^\]]+?)\]\]")
_MDLINK = re.compile(r"\[[^\]]+\]\(([^)]+\.md)\)")
_NAME_FM = re.compile(r"^name:\s*(.+?)\s*$", re.M)
_FENCED = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`]*`")


def _strip_code(text: str) -> str:
    """Remove fenced + inline code spans so example syntax like `[[Wikilinks]]` is not mistaken for a
    real link. (Citations are NOT stripped -- a `file.py:42` in backticks is a legitimate citation.)"""
    return _INLINE_CODE.sub(" ", _FENCED.sub(" ", text))


def _memory_files() -> list:
    return [f for f in glob.glob(os.path.join(MEM_DIR, "*.md")) if os.path.basename(f) != "MEMORY.md"]


def _known_names() -> dict:
    """slug -> filepath, from each memory file's `name:` frontmatter (fallback to the basename slug)."""
    names = {}
    for fp in _memory_files():
        try:
            head = open(fp, encoding="utf-8").read(800)
        except Exception:
            continue
        m = _NAME_FM.search(head)
        slug = m.group(1).strip() if m else os.path.splitext(os.path.basename(fp))[0]
        names[slug] = fp
        names[os.path.splitext(os.path.basename(fp))[0]] = fp   # also resolvable by filename slug
    return names


def _citation_exists(path: str) -> bool:
    p = path.replace("\\", "/")
    cands = [os.path.join(ROOT, p), os.path.join(os.path.expanduser("~"), p), p]
    if any(os.path.exists(c) for c in cands):
        return True
    if "/" not in p:                                  # bare filename -> bounded glob under repo
        hits = glob.glob(os.path.join(ROOT, "**", p), recursive=True)
        return len(hits) > 0
    return False


def lint() -> dict:
    rep = dict(mem_dir=MEM_DIR, index_exists=os.path.exists(INDEX), line_count=0,
               n_memory_files=len(_memory_files()), broken_links=[], stale_citations=[],
               dead_md_links=[], duplicate_names=[], blocking=False, reasons=[])
    if not os.path.exists(INDEX):
        rep["blocking"] = True
        rep["reasons"].append("MEMORY.md missing")
        return rep
    text = open(INDEX, encoding="utf-8").read()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    rep["line_count"] = len(lines)

    names = _known_names()
    # 1) MD index links that point at a missing memory file
    for tgt in _MDLINK.findall(_strip_code(text)):
        if not os.path.exists(os.path.join(MEM_DIR, tgt)):
            rep["dead_md_links"].append(tgt)

    # 2/3) wikilinks + file:line citations across ALL memory files (index + topic files)
    all_files = [INDEX] + _memory_files()
    seen_citations, seen_links = set(), set()
    dup_name_counts = {}
    for fp in all_files:
        try:
            t = open(fp, encoding="utf-8").read()
        except Exception:
            continue
        for ln in _WIKILINK.findall(_strip_code(t)):
            ln = ln.strip()
            if ln and ln not in names and ln not in seen_links:
                seen_links.add(ln)
                rep["broken_links"].append(dict(link=ln, file=os.path.basename(fp)))
        for path, _line in _CITATION.findall(t):
            if path in seen_citations:
                continue
            seen_citations.add(path)
            if not _citation_exists(path):
                rep["stale_citations"].append(path)
        m = _NAME_FM.search(t[:800])
        if m:
            dup_name_counts.setdefault(m.group(1).strip(), []).append(os.path.basename(fp))
    rep["duplicate_names"] = [(k, v) for k, v in dup_name_counts.items() if len(v) > 1]

    if rep["line_count"] > MAX_INDEX_LINES:
        rep["blocking"] = True
        rep["reasons"].append(f"MEMORY.md {rep['line_count']} lines > {MAX_INDEX_LINES} (cleanse required)")
    if rep["broken_links"]:
        rep["blocking"] = True
        rep["reasons"].append(f"{len(rep['broken_links'])} broken [[link]](s)")
    if rep["stale_citations"]:
        rep["blocking"] = True
        rep["reasons"].append(f"{len(rep['stale_citations'])} stale file:line citation(s)")
    return rep


def print_report(rep: dict) -> None:
    print(f"=== MEMORY LINT ===  dir: {rep['mem_dir']}")
    print(f"MEMORY.md: {rep['line_count']} non-blank lines (cap {MAX_INDEX_LINES}), "
          f"{rep['n_memory_files']} topic files")
    print(f"broken [[links]]: {len(rep['broken_links'])}  {rep['broken_links'][:8]}")
    print(f"stale file:line citations: {len(rep['stale_citations'])}  {rep['stale_citations'][:8]}")
    print(f"dead MD index links: {len(rep['dead_md_links'])}  {rep['dead_md_links'][:8]}")
    print(f"duplicate name slugs: {len(rep['duplicate_names'])}  {rep['duplicate_names'][:5]}")
    print(f"\nBLOCKING: {rep['blocking']}" + (f"  -> {'; '.join(rep['reasons'])}" if rep["reasons"] else ""))


if __name__ == "__main__":
    rep = lint()
    print_report(rep)
    if "--check" in sys.argv:
        sys.exit(1 if rep["blocking"] else 0)
