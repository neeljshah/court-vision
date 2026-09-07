"""Relative-markdown-link checker for the public docs lineup.

Two classes of breakage, both fatal:
  BROKEN   -- the target does not exist on disk
  UNTRACKED -- it exists locally but is not tracked at HEAD, so it 404s on a fresh clone
              (the public origin is recruiter/buyer-facing; local-only paths must not be linked)

Usage: python scripts/platformkit/docs_linkcheck.py   (exit 1 if anything is broken)
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LINEUP = [
    "README.md", "CLAUDE.md", "docs/INDEX.md", "docs/PUBLIC_EVIDENCE.md",
    "docs/JOB_EVIDENCE_PACKET.md", "docs/INTELLIGENCE.md", "docs/PLATFORM.md",
    "docs/GLOSSARY.md",
]

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
EXTERNAL = re.compile(r"^(https?:|mailto:|#|data:|tel:)")


def targets():
    """The lineup plus every top-level evidence page."""
    ev = os.path.join(ROOT, "docs", "evidence")
    extra = sorted("docs/evidence/" + f for f in os.listdir(ev) if f.endswith(".md"))
    return LINEUP + extra


def tracked_paths():
    """Files tracked at HEAD, plus every directory prefix (a link may point at a dir)."""
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT).decode("utf-8", "replace")
    files = set(out.split("\n"))
    dirs = set()
    for f in files:
        parts = f.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
    return files | dirs


def check(rel, tracked):
    src = os.path.join(ROOT, rel)
    base = os.path.dirname(src)
    bad = []
    with open(src, encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            for tgt in LINK.findall(line):
                if EXTERNAL.match(tgt):
                    continue
                path = tgt.split("#")[0].split("?")[0]
                if not path:
                    continue
                full = os.path.normpath(os.path.join(base, path))
                if not os.path.exists(full):
                    bad.append(("BROKEN", rel, lineno, tgt))
                    continue
                key = os.path.relpath(full, ROOT).replace("\\", "/").rstrip("/")
                if key not in tracked:
                    bad.append(("UNTRACKED", rel, lineno, tgt))
    return bad


def main():
    tracked = tracked_paths()
    bad = []
    files = targets()
    for rel in files:
        bad.extend(check(rel, tracked))
    for kind, rel, lineno, tgt in bad:
        print("%s %s:%d -> %s" % (kind, rel, lineno, tgt))
    print("checked %d files; %d broken links" % (len(files), len(bad)))
    return 1 if bad else 0


def _selftest():
    """One runnable check: a known-bad file must be reported by both rules."""
    probe = os.path.join(ROOT, "docs", "evidence", "_linkcheck_selftest.md")
    with open(probe, "w", encoding="utf-8") as fh:
        fh.write("[a](NOPE_MISSING_TARGET.md)\n")
    try:
        found = check("docs/evidence/_linkcheck_selftest.md", tracked_paths())
        assert [f[0] for f in found] == ["BROKEN"], found
        assert check("README.md", tracked_paths()) == [], "README should be clean"
        print("selftest OK")
    finally:
        os.remove(probe)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        sys.exit(main())
