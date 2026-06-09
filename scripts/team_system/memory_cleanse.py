"""MEMORY CLEANSE -- deterministic, knowledge-preserving repair of broken [[links]] + stale file:line
citations across the Claude memory (MASTER_SYSTEM_BUILD section 5). NEVER deletes a memory file or a
recorded rejection; only re-points a dangling link to its real target, or unwraps it to plain text.

  - A broken [[x]]: find the existing memory whose filename / name-slug normalizes to the same key
    (case/underscore/hyphen/known-prefix-insensitive). If found -> rewrite the link to that slug.
    If not found -> UNWRAP ([[x]] -> x): the text/knowledge is preserved, the dangling link is gone.
  - A stale file.ext:line citation: glob the repo for that basename; if a unique file matches -> rewrite
    the path; else leave the line but the lint stays informational for it.

  python scripts/team_system/memory_cleanse.py             # DRY RUN (report only)
  python scripts/team_system/memory_cleanse.py --apply     # edit files atomically
"""
from __future__ import annotations
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_lint import MEM_DIR, _known_names, _memory_files, _WIKILINK, _CITATION, _strip_code  # noqa: E402

_PREFIXES = ("project_", "feedback_", "reference_", "user_")


def _norm_key(s: str) -> str:
    s = s.lower().strip()
    for p in _PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    return re.sub(r"[^a-z0-9]", "", s)


def _resolver() -> dict:
    """normalized-key -> canonical slug (the filename-without-ext, the loop's preferred link form)."""
    res = {}
    for fp in _memory_files():
        slug = os.path.splitext(os.path.basename(fp))[0]
        res.setdefault(_norm_key(slug), slug)
        head = open(fp, encoding="utf-8").read(800)
        m = re.search(r"^name:\s*(.+?)\s*$", head, re.M)
        if m:
            res.setdefault(_norm_key(m.group(1)), slug)
    return res


def _atomic_write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def plan() -> dict:
    names = set(_known_names())
    res = _resolver()
    link_actions, cite_actions = {}, {}
    for fp in [os.path.join(MEM_DIR, "MEMORY.md")] + _memory_files():
        try:
            t = open(fp, encoding="utf-8").read()
        except Exception:
            continue
        stripped = _strip_code(t)
        for link in set(_WIKILINK.findall(stripped)):
            link = link.strip()
            if not link or link in names:
                continue
            tgt = res.get(_norm_key(link))
            link_actions[link] = ("rewrite", tgt) if tgt else ("unwrap", None)
        for path, _line in set((p, l) for p, l in _CITATION.findall(t)):
            cands = glob.glob(os.path.join(ROOT, "**", os.path.basename(path)), recursive=True)
            if not (os.path.exists(os.path.join(ROOT, path)) or
                    os.path.exists(os.path.join(os.path.expanduser("~"), path)) or cands):
                # a real basename match elsewhere?
                base = os.path.basename(path)
                hits = glob.glob(os.path.join(ROOT, "**", base), recursive=True)
                if len(hits) == 1:
                    cite_actions[path] = ("rewrite", os.path.relpath(hits[0], ROOT).replace("\\", "/"))
                else:
                    # try fuzzy: a file ENDING in this basename (e.g. golive.ps1 -> courtvision_golive.ps1)
                    fuzzy = [h for h in glob.glob(os.path.join(ROOT, "**", f"*{base}"), recursive=True)]
                    cite_actions[path] = ("rewrite", os.path.relpath(fuzzy[0], ROOT).replace("\\", "/")) \
                        if len(fuzzy) == 1 else ("unwrap", None)
    return dict(links=link_actions, citations=cite_actions)


def apply_plan(p: dict) -> dict:
    changed = 0
    for fp in [os.path.join(MEM_DIR, "MEMORY.md")] + _memory_files():
        try:
            t = open(fp, encoding="utf-8").read()
        except Exception:
            continue
        orig = t
        for link, (action, tgt) in p["links"].items():
            esc = re.escape(link)
            if action == "rewrite" and tgt:
                t = re.sub(r"\[\[" + esc + r"\]\]", f"[[{tgt}]]", t)
            else:
                t = re.sub(r"\[\[" + esc + r"\]\]", link, t)   # unwrap
        for path, (action, tgt) in p["citations"].items():
            if action == "rewrite" and tgt:
                # word-boundary aware (same lookbehind as the detector) so `golive.ps1:` does NOT match
                # inside `courtvision_golive.ps1:`
                t = re.sub(r"(?<![\w/])" + re.escape(path) + r":", tgt + ":", t)
        if t != orig:
            _atomic_write(fp, t)
            changed += 1
    return dict(files_changed=changed)


if __name__ == "__main__":
    p = plan()
    print("=== LINK ACTIONS ===")
    for k, (a, tgt) in sorted(p["links"].items()):
        print(f"  [{a:7s}] [[{k}]]" + (f" -> [[{tgt}]]" if tgt else "  (unwrap to plain text)"))
    print("=== CITATION ACTIONS ===")
    for k, (a, tgt) in sorted(p["citations"].items()):
        print(f"  [{a:7s}] {k}" + (f" -> {tgt}" if tgt else "  (leave; no unique match)"))
    if "--apply" in sys.argv:
        out = apply_plan(p)
        print(f"\nAPPLIED: {out['files_changed']} files edited atomically.")
    else:
        print("\n(dry run -- pass --apply to edit)")
