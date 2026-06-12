"""select_tests.py — blast-radius test selection for wave/task gates.

Maps changed source files to the minimal test subset that covers them.
Pure stdlib (ast, pathlib, re).  Deterministic (sorted output).
Rebuilt per call — seconds over 171K LOC is fine.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "tests"
SRC_DIR = ROOT / "src"

# Always-include floor: the platform test directory
FLOOR_DIR = "tests/platform"

# Pinned smoke tests discovered by glob (include if they exist)
_SMOKE_GLOBS = [
    "tests/platform/test_api_boot.py",         # API boot coverage
    "tests/**/test_brain_flags*.py",            # flags-registry
    "tests/**/test_*flags_registry*.py",        # flags-registry alt name
    "tests/**/test_brain_agent_build.py",       # sim-determinism
    "tests/**/test_*sim_determin*.py",          # sim-determinism alt name
]

# Sentinel returned when selection is too broad for a wave
ALL_SENTINEL = "ALL"
_MAX_TESTS = 200


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

def _floor_tests(root: Path) -> List[Path]:
    """Return the always-include floor: tests/platform/ + smoke globs."""
    found: List[Path] = []

    # tests/platform/
    floor_dir = root / FLOOR_DIR.replace("/", "\\") if "\\" in str(root) else root / FLOOR_DIR
    for p in sorted(_iter_py_files(floor_dir)):
        if p.name.startswith("test_"):
            found.append(p)

    # Pinned smoke globs
    for glob_pat in _SMOKE_GLOBS:
        for p in sorted(root.glob(glob_pat)):
            if p not in found:
                found.append(p)

    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select(changed_files: List[str], repo_root: Path = ROOT) -> dict:
    """Map changed_files → test files to run.

    Returns:
        {
          "tests": [sorted list of relative-path strings],
          "sentinel": "ALL" | None,
          "reason": str,
          "rules_fired": [list of rule names that contributed],
        }

    Rules applied (in order, results unioned):
      1. Changed test files select themselves.
      2. Convention: src/.../foo.py → tests/**/test_foo*.py if present.
      3. Reverse import map: AST-parse imports, transitive closure.
      4. Fallback: scripts/**/*.py → string-grep tests/ for the script stem.
      5. Floor: tests/platform/ + smoke list (always included).
      6. If > MAX_TESTS files selected → sentinel="ALL".
    """
    selected: Set[Path] = set()
    rules_fired: List[str] = []
    tests_dir = repo_root / "tests"
    src_dir = repo_root / "src"

    # Normalise changed_files to absolute paths
    changed_abs: List[Path] = []
    for f in changed_files:
        p = Path(f)
        if not p.is_absolute():
            p = repo_root / p
        changed_abs.append(p.resolve())

    # Identify changed test files vs changed src/script files
    changed_test_files = [p for p in changed_abs if
                          p.suffix == ".py" and
                          (tests_dir in p.parents or str(p).replace("\\", "/").count("tests/") > 0)]
    changed_src_files = [p for p in changed_abs if p not in changed_test_files and p.suffix == ".py"]
    changed_script_files = [p for p in changed_abs if
                             p.suffix == ".py" and
                             "scripts" in str(p).replace("\\", "/")]

    # --- Rule 1: changed test file selects itself ---
    for p in changed_test_files:
        if p.exists():
            selected.add(p)
            rules_fired.append("rule1_self")

    # --- Rule 2: convention test_<stem>*.py ---
    for p in changed_src_files:
        stem = p.stem
        pattern = f"**/test_{stem}*.py"
        hits = list(tests_dir.glob(pattern))
        if hits:
            selected.update(hits)
            rules_fired.append(f"rule2_convention:{stem}")

    # --- Rule 3: reverse import map ---
    if changed_src_files:
        try:
            src_module_map = _build_src_module_map(src_dir)
            # Build a set of module names for changed src files
            changed_modules: Set[str] = set()
            for p in changed_src_files:
                mod = _path_to_module(p, src_dir)
                if mod:
                    changed_modules.add(mod)
                # Also try relative to repo root
                mod2 = _path_to_module(p, repo_root)
                if mod2:
                    changed_modules.add(mod2)

            if changed_modules:
                rev_map = _build_reverse_import_map(tests_dir, src_module_map)
                for test_path, imported_mods in rev_map.items():
                    for cm in changed_modules:
                        # Check if any imported module matches changed module (prefix match)
                        for im in imported_mods:
                            if im == cm or im.startswith(cm + ".") or cm.startswith(im + "."):
                                selected.add(test_path)
                                rules_fired.append(f"rule3_import:{cm}")
                                break
        except Exception:  # noqa: BLE001
            rules_fired.append("rule3_import:SKIPPED(error)")

    # --- Rule 4: script stem grep fallback ---
    for p in changed_script_files:
        # Scripts invoked via subprocess — grep for their path or stem
        stem = p.stem
        hits = _grep_tests_for_stem(stem, tests_dir)
        # Also grep for the relative path
        try:
            rel_norm = _normalise(str(p.relative_to(repo_root)))
        except ValueError:
            rel_norm = _normalise(str(p))
        hits += _grep_tests_for_stem(rel_norm, tests_dir)
        # Deduplicate hits
        unique_hits = list({h: None for h in hits}.keys())
        if unique_hits:
            selected.update(unique_hits)
            # Always record rule4 firing even if hits were already in selection
            rules_fired.append(f"rule4_grep:{stem}")

    # --- Rule 5: always-include floor ---
    floor = _floor_tests(repo_root)
    selected.update(floor)
    if floor:
        rules_fired.append("rule5_floor")

    # Deduplicate and sort
    selected_list = sorted(selected, key=lambda p: str(p))

    # --- Rule 6: too-broad sentinel ---
    if len(selected_list) > _MAX_TESTS:
        return {
            "tests": [],
            "sentinel": ALL_SENTINEL,
            "reason": f"selection too broad ({len(selected_list)} files > {_MAX_TESTS}) → phase tier",
            "rules_fired": list(set(rules_fired)),
        }

    # Return relative paths
    rel_paths: List[str] = []
    for p in selected_list:
        try:
            rel = p.relative_to(repo_root)
            rel_paths.append(str(rel).replace("\\", "/"))
        except ValueError:
            rel_paths.append(str(p).replace("\\", "/"))

    rules_unique = sorted(set(rules_fired))
    reason = (
        f"selected {len(rel_paths)} test files via rules: {', '.join(rules_unique)}"
        if rel_paths else "no tests selected (floor only)"
    )

    return {
        "tests": rel_paths,
        "sentinel": None,
        "reason": reason,
        "rules_fired": rules_unique,
    }
