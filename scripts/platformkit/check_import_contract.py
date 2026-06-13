"""check_import_contract.py — AST-based import-direction guard.

Enforces two structural invariants of the kernel/adapter architecture:

1. **Kernel purity**: every ``.py`` under ``kernel/`` may only import from the
   allowlisted package families (stdlib, numpy, pandas, scipy, sklearn,
   xgboost, torch, fastapi, and ``kernel.*`` itself).  Any import of
   ``src.*``, ``domains.*``, ``api.*``, ``scripts.*``, ``nba_api``, or any
   sport-named library is a violation.

2. **Cross-adapter ban (falsifier F5)**: ``domains/<a>/`` may not import
   ``domains/<b>/`` where ``a != b``.  A domain adapter may import
   ``kernel.*`` and its own submodules but must never reach into a sibling
   domain.

The checker is AST-only: it parses Python source with ``ast``, walks
``Import`` and ``ImportFrom`` nodes, and never executes or imports the files
it inspects.

Usage::

    python scripts/platformkit/check_import_contract.py          # scan repo tree
    python scripts/platformkit/check_import_contract.py --help

Exit codes:
    0 — no violations
    1 — one or more violations found
    2 — fatal (repo root not found, parse error treated as fatal)

Output per violation::

    <path>:<line>:KERNEL_IMPORT_VIOLATION: <module>
    <path>:<line>:CROSS_ADAPTER_VIOLATION: <module>

Importable API::

    from scripts.platformkit.check_import_contract import check
    violations = check()           # scans the repo tree
    violations = check(root=...)   # scan an explicit root Path
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

# Ensure the repo root is importable so the fully-qualified sibling import below
# resolves even under a bare `python scripts/platformkit/check_import_contract.py`
# invocation (no PYTHONPATH). Harmless when already on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ---------------------------------------------------------------------------
# Re-export everything from the scan helper so importers of this module get
# the full public surface regardless of where names physically live.
# ---------------------------------------------------------------------------
from scripts.platformkit.check_import_contract_scan import (  # noqa: E402,F401
    Violation,
    _KERNEL_ALLOWLIST,
    _KERNEL_BANNED_TOPS,
    _STDLIB_TOPS,
    _top,
    _is_allowed_kernel_import,
    _collect_imports,
    _parse,
    _check_kernel_file,
    _check_domain_file,
)


# ---------------------------------------------------------------------------
# Repo-root detection
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root (contains CLAUDE.md)."""
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    raise RuntimeError(
        "check_import_contract: could not locate repo root "
        "(CLAUDE.md not found within 10 parent directories)"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check(root: Optional[Path] = None) -> List[Violation]:
    """Scan ``kernel/`` and ``domains/`` under *root* and return all violations.

    Parameters
    ----------
    root:
        Repository root.  If ``None``, the repo root is auto-detected by
        walking up from this file until a directory containing ``CLAUDE.md``
        is found.

    Returns
    -------
    List[Violation]
        All violations found; empty list means clean.
    """
    if root is None:
        root = _find_repo_root()

    violations: List[Violation] = []

    # --- kernel/ ---
    kernel_dir = root / "kernel"
    if kernel_dir.is_dir():
        for py_path in sorted(kernel_dir.rglob("*.py")):
            violations.extend(_check_kernel_file(py_path))

    # --- domains/ ---
    domains_dir = root / "domains"
    if domains_dir.is_dir():
        for sport_dir in sorted(p for p in domains_dir.iterdir() if p.is_dir()):
            own_domain = sport_dir.name
            for py_path in sorted(sport_dir.rglob("*.py")):
                violations.extend(_check_domain_file(py_path, own_domain))

    return violations


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.  Returns 0 (clean) or 1 (violations found)."""
    if argv is None:
        argv = sys.argv[1:]

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    try:
        root = _find_repo_root()
    except RuntimeError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    violations = check(root=root)

    if violations:
        for v in violations:
            print(v)
        print(
            f"\ncheck_import_contract: {len(violations)} violation(s) found.",
            file=sys.stderr,
        )
        return 1

    print("check_import_contract: clean — no violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
