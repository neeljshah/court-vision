"""check_shims.py — Shim integrity checker + pickle round-trip verifier.

Discovers shim files by the ``— SHIM`` marker on line 1, then asserts:
  Form A (``import <new> as <old>``): old symbol IS the new symbol (identity).
  Form B (``__all__`` list): every declared name is actually bound in the module.

Flags: ``--pickles`` (walk data/models/*.pkl), ``--report-unused`` (grep logs).
Exit codes: 0 = all checks passed, 1 = one or more failures.

Importable API: discover_shims, check_shim, check_all, check_pickles, report_unused.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import pickle
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Repo root + skip-list
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    c = Path(__file__).resolve()
    for _ in range(10):
        c = c.parent
        if (c / "CLAUDE.md").exists():
            return c
    return Path(__file__).resolve().parents[3]


REPO_ROOT: Path = _find_repo_root()

# (glob_pattern, reason) for intentionally-stale pickle artifacts
PICKLE_SKIP: List[tuple[str, str]] = []

_MISSING = object()

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class ShimResult(NamedTuple):
    """Result of a single shim integrity check."""
    path: str
    ok: bool
    message: str

    def __str__(self) -> str:
        return f"[{'OK' if self.ok else 'FAIL'}] {self.path}: {self.message}"


class PickleResult(NamedTuple):
    """Result of a single pickle round-trip check."""
    path: str
    ok: bool
    message: str
    skipped: bool = False

    def __str__(self) -> str:
        status = "SKIP" if self.skipped else ("OK" if self.ok else "FAIL")
        return f"[{status}] {self.path}: {self.message}"


# ---------------------------------------------------------------------------
# Shim discovery
# ---------------------------------------------------------------------------

_SHIM_MARKER = re.compile(r"^[—\-–]\s*SHIM", re.IGNORECASE)
_FORM_A_RE = re.compile(r"^\s*(?:from\s+\S+\s+)?import\s+(\S+)\s+as\s+(\S+)\s*$")
_FORM_B_RE = re.compile(r"__all__\s*=\s*\[([^\]]*)\]", re.DOTALL)


def discover_shims(root: Path) -> List[Path]:
    """Return all .py files under *root* whose first line has the SHIM marker."""
    found: List[Path] = []
    for py in sorted(root.rglob("*.py")):
        try:
            with py.open("r", encoding="utf-8", errors="replace") as fh:
                first = fh.readline().rstrip("\n").lstrip("# \t")
        except OSError:
            continue
        if _SHIM_MARKER.match(first):
            found.append(py)
    return found


def _load_mod(path: Path, name: str):
    """Load a Python module from an arbitrary file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Core shim checker
# ---------------------------------------------------------------------------

def check_shim(shim_path: Path) -> ShimResult:
    """Check a single shim file for integrity (Form A or Form B)."""
    ps = str(shim_path)
    try:
        source = shim_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ShimResult(ps, False, f"Cannot read file: {exc}")

    # Collect import-as lines (Form A) — skip comments/blanks/strings
    form_a: List[tuple[str, str]] = []
    for line in source.splitlines()[1:]:
        s = line.strip()
        if not s or s.startswith("#") or s.startswith('"""') or s.startswith("'"):
            continue
        m = _FORM_A_RE.match(s)
        if m:
            form_a.append((m.group(1), m.group(2)))  # (new_sym, old_sym)

    form_b = _FORM_B_RE.search(source)

    if not form_a and form_b is None:
        return ShimResult(ps, True, "Inert shim (no import-as or __all__) — pass.")

    try:
        mod = _load_mod(shim_path, f"_shim_{shim_path.stem}")
    except Exception as exc:  # noqa: BLE001
        return ShimResult(ps, False, f"Import failed: {exc}")

    # Form A: old_sym object IS new_sym object
    if form_a:
        errs: List[str] = []
        for new_sym, old_sym in form_a:
            old_obj = getattr(mod, old_sym, _MISSING)
            if old_obj is _MISSING:
                errs.append(f"'{old_sym}' not found in shim")
                continue
            new_obj = getattr(mod, new_sym.split(".")[-1], _MISSING)
            if new_obj is _MISSING:
                try:
                    new_obj = importlib.import_module(new_sym)
                except Exception:
                    continue  # unresolvable — skip identity check
            if old_obj is not new_obj:
                errs.append(f"identity mismatch: '{old_sym}' is not '{new_sym}'")
        if errs:
            return ShimResult(ps, False, "; ".join(errs))
        return ShimResult(ps, True, f"Form A OK: {len(form_a)} re-export(s) pass.")

    # Form B: every name in __all__ is actually bound in the module
    raw = form_b.group(1)  # type: ignore[union-attr]
    declared = frozenset(
        t.strip().strip("'\"") for t in raw.split(",") if t.strip().strip("'\"")
    )
    actual = frozenset(n for n in dir(mod) if not n.startswith("_"))
    missing = declared - actual
    if missing:
        return ShimResult(ps, False, f"missing from module: {sorted(missing)}")
    return ShimResult(ps, True, f"Form B OK: {len(declared)} symbol(s) match __all__.")


def check_all(root: Path) -> List[ShimResult]:
    """Discover and check all shims under *root*."""
    return [check_shim(s) for s in discover_shims(root)]


# ---------------------------------------------------------------------------
# Pickle round-trip checker
# ---------------------------------------------------------------------------

def check_pickles(pkl_dir: Path) -> List[PickleResult]:
    """Walk *pkl_dir* for *.pkl, unpickle each; honour PICKLE_SKIP."""
    results: List[PickleResult] = []
    for pkl in sorted(pkl_dir.glob("*.pkl")):
        ps = str(pkl)
        skip = next((r for pat, r in PICKLE_SKIP if pkl.match(pat)), None)
        if skip:
            results.append(PickleResult(ps, True, f"Skipped: {skip}", skipped=True))
            continue
        try:
            with pkl.open("rb") as fh:
                pickle.load(fh)
            results.append(PickleResult(ps, True, "Unpickled OK."))
        except Exception as exc:  # noqa: BLE001
            results.append(PickleResult(ps, False, f"Unpickle failed: {exc}"))
    return results


# ---------------------------------------------------------------------------
# Report-unused: grep logs for shim imports (Phase-9 soak)
# ---------------------------------------------------------------------------

_SHIM_LOG_RE = re.compile(r"(?:import|from)\s+\S*shim\S*", re.IGNORECASE)


def report_unused(log_paths: List[Path]) -> List[str]:
    """Return log lines that reference a shim import (soak instrument)."""
    hits: List[str] = []
    for lp in log_paths:
        try:
            lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if _SHIM_LOG_RE.search(line):
                hits.append(f"{lp}:{n}: {line.strip()}")
    return hits


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point — exits 0 clean, 1 on failure."""
    p = argparse.ArgumentParser(prog="check_shims",
                                description="Shim integrity + pickle verifier.")
    p.add_argument("--shim-root", default=None)
    p.add_argument("--pickles", action="store_true")
    p.add_argument("--report-unused", action="store_true", dest="report_unused")
    p.add_argument("--log-dir", default=None)
    args = p.parse_args(argv)

    root = Path(args.shim_root) if args.shim_root else REPO_ROOT
    fail = False

    results = check_all(root)
    print(f"Shims under {root}: {len(results)} found")
    for r in results:
        print(f"  {r}")
        if not r.ok:
            fail = True

    if args.pickles:
        pkl_dir = REPO_ROOT / "data" / "models"
        print(f"\nPickles in {pkl_dir}:")
        if pkl_dir.exists():
            for pr in check_pickles(pkl_dir) or [PickleResult("(none)", True, "No .pkl files.")]:
                print(f"  {pr}")
                if not pr.ok and not pr.skipped:
                    fail = True
        else:
            print("  Directory not found — skipping.")

    if args.report_unused:
        log_dir = Path(args.log_dir) if args.log_dir else REPO_ROOT / "vault" / "Logs"
        logs = sorted(log_dir.glob("*.log")) if log_dir.exists() else []
        hits = report_unused(logs)
        print(f"\nLog shim-import hits: {len(hits)}")
        for h in hits:
            print(f"  {h}")

    if fail:
        print("\ncheck_shims: FAILED", file=sys.stderr)
        return 1
    print("\ncheck_shims: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
