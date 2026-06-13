"""select_tests_helpers.py — Internal helpers for select_tests.py.

Pure stdlib (ast, pathlib, re).  Not a public API — import via select_tests.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(path: str) -> str:
    """Normalise separators to forward-slash and strip leading /."""
    return path.replace("\\", "/").lstrip("/")


def _path_to_module(p: Path, root: Path) -> Optional[str]:
    """Convert an absolute path to a dotted module name relative to root."""
    try:
        rel = p.relative_to(root)
    except ValueError:
        return None
    parts = list(rel.parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _stem(path_str: str) -> str:
    """Return the filename stem (no directory, no extension)."""
    return Path(path_str).stem


def _iter_py_files(directory: Path):
    if directory.exists():
        yield from directory.rglob("*.py")


def _parse_imports(filepath: Path) -> List[str]:
    """AST-parse a Python file, return all imported module names (top-level dotted).
    Skips unparseable files silently."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except Exception:  # noqa: BLE001
        return []

    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Relative imports get a leading dot — normalise away
                imports.append(node.module.lstrip(".") if node.module else "")
    return [m for m in imports if m]


# ---------------------------------------------------------------------------
# Module → src path map (lazy, rebuilt per call)
# ---------------------------------------------------------------------------

def _build_src_module_map(src_root: Path) -> Dict[str, Path]:
    """Map dotted module name → absolute path for everything under src/."""
    result: Dict[str, Path] = {}
    for f in _iter_py_files(src_root):
        mod = _path_to_module(f, src_root)
        if mod:
            result[mod] = f
    return result


def _module_prefix_hits(module_name: str, target_paths: Set[Path]) -> bool:
    """Return True if module_name matches any target path via prefix.
    E.g. 'src.sim.basketball_sim' matches 'src/sim/basketball_sim.py'."""
    for path in target_paths:
        # Try matching the last N parts of the module against the file's relative path
        rel_norm = str(path).replace("\\", "/")
        # Build candidate module strings from the end of the path
        parts = [p for p in rel_norm.replace("/", ".").split(".") if p not in ("py",)]
        # Remove .py extension part
        if rel_norm.endswith(".py"):
            no_ext = rel_norm[:-3].replace("/", ".")
            # module_name might match a suffix
            if no_ext.endswith(module_name) or module_name.endswith(no_ext.split(".")[-1]):
                return True
    return False


# ---------------------------------------------------------------------------
# Reverse import map: test file → frozenset of imported module names (transitive)
# ---------------------------------------------------------------------------

def _build_reverse_import_map(
    tests_dir: Path,
    src_module_map: Dict[str, Path],
) -> Dict[Path, FrozenSet[str]]:
    """For each test file, compute the set of src modules it transitively imports.

    Strategy: BFS from each test file's direct imports through the src module graph.
    We only expand nodes that resolve to src/ files (stops the BFS at stdlib/third-party).
    """
    # Build src import closure cache
    src_closure_cache: Dict[Path, FrozenSet[str]] = {}

    def _src_closure(path: Path, seen: Set[Path]) -> FrozenSet[str]:
        if path in src_closure_cache:
            return src_closure_cache[path]
        if path in seen:
            return frozenset()
        seen.add(path)
        direct = set(_parse_imports(path))
        result = set(direct)
        for imp in direct:
            # Try to resolve this import to a src file
            # Check exact match and prefix matches
            for mod_name, mod_path in src_module_map.items():
                if mod_name == imp or mod_name.startswith(imp + ".") or imp.startswith(mod_name):
                    sub = _src_closure(mod_path, seen)
                    result |= sub
        frozen = frozenset(result)
        src_closure_cache[path] = frozen
        return frozen

    result: Dict[Path, FrozenSet[str]] = {}
    for test_file in _iter_py_files(tests_dir):
        if test_file.name.startswith("test_"):
            imports = set(_parse_imports(test_file))
            # Expand through src modules
            full_imports = set(imports)
            for imp in list(imports):
                for mod_name, mod_path in src_module_map.items():
                    if mod_name == imp or imp.startswith(mod_name + "."):
                        full_imports |= _src_closure(mod_path, set())
            result[test_file] = frozenset(full_imports)

    return result


# ---------------------------------------------------------------------------
# Rule 4: string-grep fallback for subprocess-invoked scripts
# ---------------------------------------------------------------------------

def _grep_tests_for_stem(stem: str, tests_dir: Path) -> List[Path]:
    """Find test files that contain the stem string (script path or filename)."""
    hits: List[Path] = []
    if not stem:
        return hits
    pattern = re.compile(re.escape(stem))
    for tf in _iter_py_files(tests_dir):
        if not tf.name.startswith("test_"):
            continue
        try:
            content = tf.read_text(encoding="utf-8", errors="replace")
            if pattern.search(content):
                hits.append(tf)
        except Exception:  # noqa: BLE001
            pass
    return hits


# ---------------------------------------------------------------------------
# Rule 5: always-include floor
# ---------------------------------------------------------------------------

def _floor_tests(root: Path, floor_dir_rel: str, smoke_globs: List[str]) -> List[Path]:
    """Return the always-include floor: tests/platform/ + smoke globs."""
    found: List[Path] = []

    # tests/platform/
    floor_dir = root / floor_dir_rel.replace("/", "\\") if "\\" in str(root) else root / floor_dir_rel
    for p in sorted(_iter_py_files(floor_dir)):
        if p.name.startswith("test_"):
            found.append(p)

    # Pinned smoke globs
    for glob_pat in smoke_globs:
        for p in sorted(root.glob(glob_pat)):
            if p not in found:
                found.append(p)

    return found
