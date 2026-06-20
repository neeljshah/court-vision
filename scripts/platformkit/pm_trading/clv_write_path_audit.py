"""scripts.platformkit.pm_trading.clv_write_path_audit -- CLV append call-site audit.

WORKSTREAM BE-R3-4-clv-writer-route-audit.

ROOT CAUSE: paper_autobet.py and paper_ingame.py call clv_ledger.append_settlement
directly (no bet_id stamp, no dup guard), producing duplicate-key ledger rows
(upstream cause of BE-R3-3).

THIS MODULE: scan_clv_write_paths(roots) walks .py files, classifies each CLV
append call-site as SAFE (routes through append_if_new_status_aware / write_settlement
/ settle_append / record_open_guarded / record_settlement_guarded) or VIOLATION
(raw append_settlement / raw json.dumps-to-ledger).  READ-ONLY: never mutates files.

Report: {status, scanned_files, violations:[{file,line,text,reason}],
         safe_call_sites:[{file,line,text,guard}], summary}
No $ / pnl / roi / profit field.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets.
Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/pm_trading/test_clv_write_path_audit.py -q
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants -- canonical safe guards and violation patterns
# ---------------------------------------------------------------------------

# Patterns that indicate a SAFE write path (routes through the status-aware
# guard layer). A call-site containing ANY of these is classified SAFE.
_SAFE_GUARDS: tuple = (
    "append_if_new_status_aware",
    "record_open_guarded",
    "record_settlement_guarded",
    "write_settlement",
    "write_open_bet",
    "settle_append",
    "open_append",
)

# Patterns that indicate a VIOLATION: raw CLV append calls that bypass the guard.
# Each entry is (regex_pattern, reason_template).
_VIOLATION_PATTERNS: tuple = (
    # Direct call to clv_ledger.append_settlement (no dup / no bet_id guard).
    (
        re.compile(r"\bappend_settlement\s*\("),
        "raw append_settlement call -- bypasses bet_id stamp and dup guard; "
        "use write_settlement / settle_append instead",
    ),
    # clv_ledger.record_bet used for settlement (fine for open rows, but only
    # when combined with the guarded write path; if isolated, flag as advisory).
    # We flag only the settlement context: a json.dumps + ledger path on same line.
    (
        re.compile(
            r"json\.dumps\s*\(.*\)\s*\+\s*[\"']\\n[\"']"
            r"|fh\.write\s*\(\s*json\.dumps"
        ),
        "raw json.dumps write to file -- may target clv_ledger.jsonl without "
        "routing through append_if_new_status_aware or append_row guard",
    ),
)

# Ledger filename hints: if the surrounding context mentions these the raw-write
# pattern is more likely to be a real violation (not a test fixture helper).
_LEDGER_HINTS: tuple = (
    "clv_ledger",
    "ledger.jsonl",
    "DEFAULT_LEDGER",
)

# Root paths to scan (relative to the repo root).
_DEFAULT_SCAN_ROOTS: tuple = (
    "scripts/platformkit/pm_trading",
    "scripts/platformkit/ingame",
)

# Files to always skip (test helpers that legitimately write fixtures, and the
# write-path modules themselves that contain the implementation not the caller).
_SKIP_FILENAME_PATTERNS: tuple = (
    "test_",
    "clv_ledger_guarded_append.py",
    "clv_ledger_status_append.py",
    "clv_ledger_status_dedup.py",
    "clv_settle_write.py",
    "clv_status_aware_append.py",
    "clv_ledger_io.py",
    "clv_ledger.py",         # the write-primitive itself
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_skipped(path: Path) -> bool:
    name = path.name
    return any(name.startswith(p) or name == p for p in _SKIP_FILENAME_PATTERNS)


def _has_ledger_context(line: str, surrounding: str) -> bool:
    """Return True when line or nearby context mentions a ledger filename."""
    combined = (line + " " + surrounding).lower()
    return any(h in combined for h in _LEDGER_HINTS)


def _context_window(lines: List[str], idx: int, window: int = 5) -> str:
    """Return a small window of lines around *idx* for context checks."""
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    return " ".join(lines[start:end])


def _in_docstring(lines: List[str], idx: int) -> bool:
    """Heuristic: return True when line *idx* (0-based) is inside a docstring.

    Scans backward from *idx* to count triple-quote tokens. If we are between
    an open triple-quote and its matching close we consider the line a docstring
    literal and not executable code. This avoids flagging lines like
    ``# Settlement calls clv_ledger.append_settlement`` that appear inside
    docstrings but are documentation, not real call-sites.
    """
    marker = '"""'
    count = 0
    for i, line in enumerate(lines[:idx]):
        count += line.count(marker)
    # If the cumulative count up to (but not including) this line is odd, we are
    # inside an open triple-quote docstring.
    return (count % 2) == 1


def _scan_file(
    path: Path,
    repo_root: Path,
) -> tuple:  # -> (violations, safe_sites)
    """Scan one Python file. Returns (list[violation], list[safe_site])."""
    violations: List[Dict[str, Any]] = []
    safe_sites: List[Dict[str, Any]] = []
    rel = str(path.relative_to(repo_root))

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return violations, safe_sites

    lines = text.splitlines()

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Skip lines inside docstrings (documentation, not executable code).
        if _in_docstring(lines, lineno - 1):
            continue

        ctx = _context_window(lines, lineno - 1)

        # Check safe guards first.
        for guard in _SAFE_GUARDS:
            if guard in stripped:
                safe_sites.append({
                    "file": rel,
                    "line": lineno,
                    "text": stripped[:120],
                    "guard": guard,
                })
                break  # one safe match per line is enough

        # Check violation patterns (only when line is NOT itself a safe guard).
        line_is_safe = any(g in stripped for g in _SAFE_GUARDS)
        if line_is_safe:
            continue

        for pattern, reason in _VIOLATION_PATTERNS:
            if not pattern.search(stripped):
                continue
            # For the raw json.dumps pattern, only flag when ledger context is clear.
            if "json.dumps" in stripped and not _has_ledger_context(stripped, ctx):
                continue
            violations.append({
                "file": rel,
                "line": lineno,
                "text": stripped[:120],
                "reason": reason,
            })
            break  # one violation tag per line

    return violations, safe_sites


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def scan_clv_write_paths(
    roots: Optional[Sequence[str]] = None,
    *,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Scan CLV append call-sites and flag any that bypass the status-aware guard.

    Parameters
    ----------
    roots:
        Iterable of directory paths (relative to *repo_root*) to scan.
        Defaults to scripts/platformkit/pm_trading and
        scripts/platformkit/ingame.
    repo_root:
        Absolute path to the repository root.  Autodetected when None.

    Returns
    -------
    dict
        Read-only report:
          status          "ok" always (the audit never raises).
          scanned_files   number of .py files examined.
          violations      list of dicts with file/line/text/reason.
          safe_call_sites list of dicts with file/line/text/guard.
          summary         one-line human-readable verdict.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]

    scan_dirs = list(roots) if roots is not None else list(_DEFAULT_SCAN_ROOTS)

    violations: List[Dict[str, Any]] = []
    safe_sites: List[Dict[str, Any]] = []
    scanned = 0

    for rel_dir in scan_dirs:
        scan_path = repo_root / rel_dir
        if not scan_path.is_dir():
            continue
        for py_file in sorted(scan_path.rglob("*.py")):
            if _is_skipped(py_file):
                continue
            scanned += 1
            v, s = _scan_file(py_file, repo_root)
            violations.extend(v)
            safe_sites.extend(s)

    n_v = len(violations)
    n_s = len(safe_sites)
    if n_v == 0:
        summary = ("CLEAN: all %d safe call-sites route through the status-aware "
                   "guard; 0 violations detected." % n_s)
    else:
        summary = ("VIOLATIONS DETECTED: %d call-site(s) bypass the status-aware "
                   "guard (no bet_id / no dup check); %d safe call-sites found."
                   % (n_v, n_s))

    return {
        "status": "ok",
        "scanned_files": scanned,
        "violations": violations,
        "safe_call_sites": safe_sites,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# CLI entry point (read-only; prints the report, never mutates)
# ---------------------------------------------------------------------------

def _main(argv=None) -> int:
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(
        description="Audit CLV append call-sites for raw/unguarded writes.")
    ap.add_argument("--roots", default="",
                    help="comma-separated relative dir paths to scan")
    ap.add_argument("--repo-root", default="",
                    help="absolute repo root (autodetected when omitted)")
    a = ap.parse_args(argv)

    roots = [r.strip() for r in a.roots.split(",") if r.strip()] or None
    rr = Path(a.repo_root) if a.repo_root else None
    report = scan_clv_write_paths(roots, repo_root=rr)

    print(_json.dumps(report, indent=2))
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["scan_clv_write_paths"]
