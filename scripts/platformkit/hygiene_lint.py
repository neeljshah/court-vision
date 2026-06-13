"""hygiene_lint.py — Public-doc hygiene lint for retracted numbers and edge-claim phrases.

Scans every file tracked by ``git ls-files`` for two classes of violation:

(a) **Retracted numbers** — ``+18.38%``, ``0.119`` / ``0.1191`` (endQ3 Brier),
    ``+54%`` / ``+54.57%`` — appearing *outside* an explicit retraction/quarantine
    context (i.e. the matching line does NOT contain a retraction keyword:
    ``retracted``, ``artifact``, ``do-not-claim``, ``do not claim``, ``superseded``,
    ``quarantine``, ``do_not_claim``).

(b) **Edge-claim phrases** — ``our edge``, ``profitable``, ``beats the market``,
    ``guaranteed``, ``+EV proven``, ``proven edge`` — exact case-insensitive matches.

Usage::

    python scripts/platformkit/hygiene_lint.py          # scan repo, print hits, exit nonzero if any
    python scripts/platformkit/hygiene_lint.py --help

Exit codes:
    0 — no violations found
    1 — one or more violations found
    2 — could not run git ls-files (fatal)

Output format per hit::

    path:line_number:CATEGORY: matched_text

Where CATEGORY is ``RETRACTED_NUMBER`` or ``EDGE_CLAIM``.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterator, List, NamedTuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Retracted-number patterns.  Each tuple: (label, compiled regex)
_RETRACTED_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    # +18.38%  (with or without leading "+")
    ("RETRACTED_NUMBER(+18.38%)", re.compile(r"18\.38\s*%", re.IGNORECASE)),
    # endQ3 Brier 0.119 / 0.1191 — match "0.119" as a standalone decimal token
    # Avoid matching e.g. "0.1192" by asserting no trailing digit.
    ("RETRACTED_NUMBER(0.119/endQ3)", re.compile(r"\b0\.1191?\b", re.IGNORECASE)),
    # +54% / +54.57% ROI
    ("RETRACTED_NUMBER(+54%)", re.compile(r"\+54(?:\.57)?\s*%", re.IGNORECASE)),
]

# Retraction-context keywords — if ANY of these appear on the same line, the
# retracted-number match is considered contextualised and is NOT flagged.
_RETRACTION_KEYWORDS: List[str] = [
    "retracted",
    "artifact",
    "do-not-claim",
    "do not claim",
    "do_not_claim",
    "superseded",
    "quarantine",
    "never claim",
    "not claim",
    "inflated",
    "leaked",
    "leak-inflated",
]

# Edge-claim phrases (case-insensitive, full substring match)
_EDGE_CLAIM_PHRASES: List[str] = [
    "our edge",
    "profitable",
    "beats the market",
    "guaranteed",
    "+EV proven",
    "proven edge",
]
_EDGE_CLAIM_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    (f"EDGE_CLAIM({phrase})", re.compile(re.escape(phrase), re.IGNORECASE))
    for phrase in _EDGE_CLAIM_PHRASES
]

# Binary / irrelevant extensions to skip (saves time, avoids decode errors)
_SKIP_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
        ".pdf", ".zip", ".gz", ".tar", ".whl", ".pkl", ".pt", ".onnx",
        ".engine", ".npy", ".npz", ".parquet", ".db", ".sqlite",
        ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
        ".mp4", ".avi", ".mov", ".mkv",
        ".lock",
    }
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class LintHit(NamedTuple):
    """A single lint violation."""

    path: str
    line_number: int
    category: str
    matched_text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line_number}:{self.category}: {self.matched_text!r}"


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _line_has_retraction_context(line_lower: str) -> bool:
    """Return True if the line contains any retraction-context keyword."""
    return any(kw in line_lower for kw in _RETRACTION_KEYWORDS)


def _scan_line(
    path: str,
    line_number: int,
    line: str,
) -> Iterator[LintHit]:
    """Yield LintHit objects for all violations on a single line."""
    line_lower = line.lower()

    # (a) Retracted numbers — skip if line has a retraction keyword
    if not _line_has_retraction_context(line_lower):
        for label, pattern in _RETRACTED_PATTERNS:
            m = pattern.search(line)
            if m:
                yield LintHit(
                    path=path,
                    line_number=line_number,
                    category=label,
                    matched_text=m.group(0),
                )

    # (b) Edge-claim phrases — always flagged (no retraction exemption)
    for label, pattern in _EDGE_CLAIM_PATTERNS:
        m = pattern.search(line)
        if m:
            yield LintHit(
                path=path,
                line_number=line_number,
                category=label,
                matched_text=m.group(0),
            )


def _scan_file(path: str) -> List[LintHit]:
    """Scan a single file and return all LintHit objects found."""
    hits: List[LintHit] = []
    ext = Path(path).suffix.lower()
    if ext in _SKIP_EXTENSIONS:
        return hits
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line_number, line in enumerate(fh, start=1):
                hits.extend(_scan_line(path, line_number, line.rstrip("\n")))
    except OSError:
        # File not readable (e.g. symlink to absent target) — skip silently
        pass
    return hits


def list_tracked_files(repo_root: str) -> List[str]:
    """Return absolute paths of all files tracked by git ls-files.

    Raises ``RuntimeError`` if the git command fails (exit 2 from main).
    """
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed (exit {result.returncode}):\n{result.stderr}"
        )
    root = Path(repo_root)
    paths: List[str] = []
    for rel in result.stdout.splitlines():
        rel = rel.strip()
        if rel:
            paths.append(str(root / rel))
    return paths


def run_lint(repo_root: str) -> List[LintHit]:
    """Scan all git-tracked files in *repo_root* and return all violations."""
    tracked = list_tracked_files(repo_root)
    hits: List[LintHit] = []
    for path in tracked:
        hits.extend(_scan_file(path))
    return hits


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    """CLI entry point.  Returns 0 (clean), 1 (violations), or 2 (git error)."""
    if argv is None:
        argv = sys.argv[1:]

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    # Determine repo root: walk up from this file until CLAUDE.md is found.
    candidate = Path(__file__).resolve()
    repo_root: Path | None = None
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            repo_root = candidate
            break
    if repo_root is None:
        print("ERROR: could not locate repo root (CLAUDE.md not found)", file=sys.stderr)
        return 2

    try:
        hits = run_lint(str(repo_root))
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if hits:
        for hit in hits:
            print(hit)
        print(
            f"\nhygiene_lint: {len(hits)} violation(s) found.",
            file=sys.stderr,
        )
        return 1

    print("hygiene_lint: clean — no violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
