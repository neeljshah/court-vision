"""select_tests.py — blast-radius test selection for wave/task gates.

Maps changed source files to the minimal test subset that covers them.
Pure stdlib (ast, pathlib, re).  Deterministic (sorted output).
Rebuilt per call — seconds over 171K LOC is fine.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set

try:
    from select_tests_helpers import (  # bare import when scripts/platformkit/ is on sys.path
        _build_reverse_import_map,
        _build_src_module_map,
        _grep_tests_for_stem,
        _iter_py_files,
        _module_prefix_hits,
        _normalise,
        _parse_imports,
        _path_to_module,
        _stem,
        _floor_tests as _floor_tests_impl,
    )
except ModuleNotFoundError:
    from scripts.platformkit.select_tests_helpers import (  # qualified import
        _build_reverse_import_map,
        _build_src_module_map,
        _grep_tests_for_stem,
        _iter_py_files,
        _module_prefix_hits,
        _normalise,
        _parse_imports,
        _path_to_module,
        _stem,
        _floor_tests as _floor_tests_impl,
    )

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
# Rule 5 wrapper — passes module-level constants to the helper
# ---------------------------------------------------------------------------

def _floor_tests(root: Path) -> List[Path]:
    """Return the always-include floor: tests/platform/ + smoke globs."""
    return _floor_tests_impl(root, FLOOR_DIR, _SMOKE_GLOBS)


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
