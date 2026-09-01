"""scripts.platformkit.memory_claim_guard -- do any memories still assert a retracted claim?

The AST ROI edge was retracted 2026-07-21 in docs/JOB_EVIDENCE_PACKET.md, but the memory
asserting it stayed authoritative for two weeks and nothing surfaced the contradiction. This
is the check that would have caught it on day one.

It reads the retracted-number list from `.claude/rules/no-edge-claims.md` (the rule file is
the source, so the list cannot drift out of sync here), scans every memory file, and flags any
file that prints a retracted number WITHOUT retraction framing around it.

Mentioning a retracted number is fine and often necessary -- that is what the retraction
memories are for. Printing one as a live result is the failure. The two are told apart by
looking for retraction vocabulary anywhere in the file.

# ponytail: file-level framing check, not sentence-level. A file that retracts number A while
# asserting number B would pass. Tighten to paragraph scope only if that case actually appears.

INVARIANTS: read-only; never edits memories; <=300 LOC; ASCII stdout.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

_REPO = Path(__file__).resolve().parents[2]
_RULE = _REPO / ".claude" / "rules" / "no-edge-claims.md"
_DEFAULT_MEMORY = Path(
    os.environ.get("CLAUDE_MEMORY_DIR",
                   r"C:\Users\neelj\.claude\projects\C--Users-neelj\memory"))

# Vocabulary that marks a file as talking ABOUT a retraction rather than making the claim.
_FRAMING = ("retract", "superseded", "artifact", "do not quote", "do not claim",
            "never quote", "never claim", "leak-inflated", "leak inflated", "retired",
            "do-not-claim", "not a live result", "mis-sourced", "debunk")


def retracted_tokens(rule: Path = None) -> List[str]:
    """Parse the backticked numbers from the rule file's NEVER-print list."""
    src = rule or _RULE
    text = src.read_text(encoding="utf-8", errors="replace")
    start = text.find("## NEVER print these retracted numbers")
    if start == -1:
        raise RuntimeError(f"retracted-number section not found in {src}")
    section = text[start:text.find("\n## ", start + 1)]
    return re.findall(r"^- `([^`]+)`", section, flags=re.MULTILINE)


def scan_file(path: Path, tokens: List[str]) -> List[str]:
    """Return the retracted tokens this file prints without any retraction framing."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if any(mark in text.lower() for mark in _FRAMING):
        return []
    return [t for t in tokens if t in text]


def scan(memory_dir: Path = None, rule: Path = None) -> List[Dict]:
    """One row per offending file. Empty list = clean."""
    mem = memory_dir or _DEFAULT_MEMORY
    tokens = retracted_tokens(rule)
    hits: List[Dict] = []
    for path in sorted(mem.glob("*.md")):
        found = scan_file(path, tokens)
        if found:
            hits.append({"file": path.name, "tokens": found})
    return hits


def render(hits: List[Dict], n_tokens: int, mem: Path) -> str:
    if not hits:
        return (f"memory claim guard: CLEAN -- no memory in {mem} prints any of the "
                f"{n_tokens} retracted numbers without retraction framing.")
    L = [f"memory claim guard: {len(hits)} FILE(S) ASSERT A RETRACTED CLAIM", ""]
    for h in hits:
        L.append(f"  {h['file']}: {', '.join(h['tokens'])}")
    L += ["", "Each file above prints a retracted number with no retraction wording anywhere.",
          "Fix by adding the retraction context, or delete the memory if it is simply wrong.",
          "Truth source: docs/JOB_EVIDENCE_PACKET.md"]
    return "\n".join(L)


def _main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description="Flag memories asserting retracted claims.")
    ap.add_argument("--memory-dir", default=None, help="override the memory directory")
    ap.add_argument("--check", action="store_true", help="exit 1 when anything is flagged")
    args = ap.parse_args(argv)
    mem = Path(args.memory_dir) if args.memory_dir else _DEFAULT_MEMORY
    if not mem.is_dir():
        print(f"memory claim guard: SKIP -- no memory dir at {mem}")
        return 0
    hits = scan(mem)
    print(render(hits, len(retracted_tokens()), mem))
    return 1 if (hits and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
