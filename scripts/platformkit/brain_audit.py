"""brain_audit.py — audit the generated brain for the no-edge discipline.

Adversarial self-check of the platform's OWN output: walk every ``.md`` under
``vault/_Organized/`` and verify NO artifact makes a forbidden edge claim (ROI /
"beats the market" / "+X% edge" / profitable / guaranteed / proven edge), reusing
``brain_critic``'s edge-claim patterns.  Also reports honest-banner coverage.

A clean pass VERIFIES the no-edge/calibration-not-edge contract across the whole
brain; any flag is a real finding to fix.  This audits, it never originates a number.

CLI: ``python -m scripts.platformkit.brain_audit [<root>] [--json]``
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Edge-CLAIM patterns specific to BETTING.  Note: 'profitable' is deliberately
# EXCLUDED (brain_critic flags it for findings, but in scouting prose it is
# tactically ambiguous — "crashing the offensive glass is profitable" is basketball
# strategy, not a betting claim).  We catch the unambiguous betting tokens instead.
_AUDIT_PATTERNS = (
    re.compile(r"\broi\b", re.IGNORECASE),
    re.compile(r"beats?\s+the\s+market", re.IGNORECASE),
    re.compile(r"\+\s*\d+(?:\.\d+)?\s*%\s*edge", re.IGNORECASE),
    re.compile(r"\bguaranteed\b", re.IGNORECASE),
    re.compile(r"\bproven\s+edge\b", re.IGNORECASE),
)

# honest-denial markers an artifact may legitimately carry (NOT edge claims).
_BANNER_RE = re.compile(
    r"no (?:model )?edge|not (?:a )?(?:market )?edge|calibration\s*!?=?\s*not edge|"
    r"calibration is not edge|no edge claimed|prior is not an edge|accuracy.{0,4}!=.{0,4}edge",
    re.IGNORECASE,
)

# A nearby caveat that disqualifies an edge token from being a CLAIM (e.g. the
# documented +5% AST ROI is always stated with these honest disclaimers).
_CAVEAT_RE = re.compile(
    r"not a validated|no edge|not to size|flat-to-negative|inverts to negative|"
    r"not a price model|scouting|did not beat|does not beat|no .{0,20}beat closing|"
    r"calibration is not edge|accuracy.{0,4}!=.{0,4}edge|never claims? .{0,6}edge",
    re.IGNORECASE,
)
_CAVEAT_WINDOW = 260  # chars on each side of an edge token
# A negation directly before the token makes it a DENIAL, not a claim
# (e.g. "none of this beats the market", "never beats", "not profitable").
# negation word, then up to 3 words, then the edge token (anchored at window end):
# matches "none of this <beats>", "never <beats>", "not <guaranteed>".
_NEGATION_RE = re.compile(
    r"\b(?:no|not|none|never|nothing|n't|without)\b(?:\s+\w+){0,3}\s*\W*$",
    re.IGNORECASE)
_NEGATION_WINDOW = 36  # chars immediately before an edge token


def scan_text(text: str) -> List[str]:
    """Return UNCAVEATED, UN-NEGATED forbidden edge-claim substrings (empty = clean).

    A match is dropped if (a) an honest caveat appears within ``_CAVEAT_WINDOW`` chars,
    or (b) a negation word sits just before it (a denial) — distinguishing a fabricated
    claim from a caveated/documented mention or an explicit denial.
    """
    hits: List[str] = []
    for pat in _AUDIT_PATTERNS:
        for m in pat.finditer(text):
            lo = max(0, m.start() - _CAVEAT_WINDOW)
            hi = m.end() + _CAVEAT_WINDOW
            before = text[max(0, m.start() - _NEGATION_WINDOW):m.start()]
            if _CAVEAT_RE.search(text[lo:hi]) or _NEGATION_RE.search(before):
                continue
            hits.append(m.group(0))
    return hits


def audit_tree(root: Optional[Path] = None) -> Dict:
    """Audit every .md under *root* (default vault/_Organized) for edge claims."""
    root = Path(root) if root is not None else (_REPO_ROOT / "vault" / "_Organized")
    if not root.is_dir():
        return {"root": str(root), "error": "not found", "n_files": 0,
                "n_flagged": 0, "flagged": [], "clean": True}

    n_files = 0
    n_with_banner = 0
    flagged: List[Dict] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n_files += 1
        if _BANNER_RE.search(text):
            n_with_banner += 1
        hits = scan_text(text)
        if hits:
            flagged.append({"file": path.relative_to(root).as_posix(),
                            "matches": sorted(set(hits))[:5]})
    return {
        "root": str(root),
        "n_files": n_files,
        "n_with_honest_banner": n_with_banner,
        "n_flagged": len(flagged),
        "flagged": flagged[:50],
        "clean": len(flagged) == 0,
        "note": ("no-edge discipline audit; a clean pass verifies the "
                 "calibration-is-not-edge contract across the brain"),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = audit_tree(Path(root_arg) if root_arg else None)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("clean") else 1
    print(f"brain_audit: {rep['root']}")
    if "error" in rep:
        print(f"  ERROR: {rep['error']}")
        return 0
    print(f"  files audited       : {rep['n_files']}")
    print(f"  honest-banner files : {rep['n_with_honest_banner']}")
    print(f"  edge-claim flagged  : {rep['n_flagged']}")
    for f in rep["flagged"]:
        print(f"    [FLAG] {f['file']}: {f['matches']}")
    print(f"  -> {'CLEAN (no-edge discipline holds)' if rep['clean'] else 'VIOLATIONS FOUND'}")
    return 0 if rep["clean"] else 1


if __name__ == "__main__":
    sys.exit(_main())
