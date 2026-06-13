"""scripts/platformkit/kernel_api_map.py — kernel API surface map + drift check.

AST-walks ``kernel/`` (never imports it) and builds a deterministic JSON surface
map: per module → public top-level classes + functions (no leading underscore),
and public methods on each class.

CLI
---
  --freeze [--out PATH]   Write the map to disk (default .planning/platform/kernel_api_map.json).
  --check  [--map PATH]   Rebuild + diff vs frozen; prints ADDED/REMOVED; exits non-zero on drift.
"""
from __future__ import annotations

import ast
import json
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _collect_module_surface(source: str) -> dict[str, Any]:
    """Return public classes and top-level functions from *source* text."""
    tree = ast.parse(source)
    classes: dict[str, list[str]] = {}
    functions: list[str] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                methods: list[str] = []
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not item.name.startswith("_"):
                            methods.append(item.name)
                classes[node.name] = sorted(methods)

    return {
        "classes": {k: v for k, v in sorted(classes.items())},
        "functions": sorted(functions),
    }


def build_api_map(root: str = "kernel") -> dict[str, Any]:
    """Walk *root* with AST and return a sorted surface map.

    Parameters
    ----------
    root:
        Directory name or path (relative to cwd or absolute) to walk.

    Returns
    -------
    dict
        ``{module_path: {"classes": {name: [methods]}, "functions": [names]}}``
        Sorted deterministically (keys are ``<root>.<pkg>.<module>`` dotted
        paths, derived from the file path relative to *root*'s parent).
    """
    root_path = Path(root)
    if not root_path.is_absolute():
        root_path = Path.cwd() / root_path
    root_path = root_path.resolve()

    if not root_path.is_dir():
        raise FileNotFoundError(f"kernel root not found: {root_path}")

    parent = root_path.parent
    surface: dict[str, Any] = {}

    for py_file in sorted(root_path.rglob("*.py")):
        # Derive dotted module key from file path relative to parent
        rel = py_file.relative_to(parent)
        parts = list(rel.with_suffix("").parts)
        module_key = ".".join(parts)

        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            module_surface = _collect_module_surface(source)
        except SyntaxError:
            module_surface = {"classes": {}, "functions": []}

        surface[module_key] = module_surface

    return dict(sorted(surface.items()))


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def diff_maps(frozen: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compute symbolic diff between two surface maps.

    Parameters
    ----------
    frozen:
        Previously frozen surface map.
    current:
        Freshly built surface map.

    Returns
    -------
    dict
        Keys: ``added_modules``, ``removed_modules``,
        ``added_classes``, ``removed_classes``,
        ``added_functions``, ``removed_functions``,
        ``added_methods``, ``removed_methods``.
        Each value is a list of human-readable strings.
    """
    result: dict[str, list[str]] = {
        "added_modules": [],
        "removed_modules": [],
        "added_classes": [],
        "removed_classes": [],
        "added_functions": [],
        "removed_functions": [],
        "added_methods": [],
        "removed_methods": [],
    }

    frozen_mods = set(frozen)
    current_mods = set(current)

    for mod in sorted(current_mods - frozen_mods):
        result["added_modules"].append(mod)
    for mod in sorted(frozen_mods - current_mods):
        result["removed_modules"].append(mod)

    common_mods = frozen_mods & current_mods
    for mod in sorted(common_mods):
        f_mod = frozen[mod]
        c_mod = current[mod]

        f_classes = set(f_mod.get("classes", {}))
        c_classes = set(c_mod.get("classes", {}))
        for cls in sorted(c_classes - f_classes):
            result["added_classes"].append(f"{mod}::{cls}")
        for cls in sorted(f_classes - c_classes):
            result["removed_classes"].append(f"{mod}::{cls}")

        # Methods on common classes
        for cls in sorted(f_classes & c_classes):
            f_methods = set(f_mod["classes"][cls])
            c_methods = set(c_mod["classes"][cls])
            for m in sorted(c_methods - f_methods):
                result["added_methods"].append(f"{mod}::{cls}.{m}")
            for m in sorted(f_methods - c_methods):
                result["removed_methods"].append(f"{mod}::{cls}.{m}")

        f_fns = set(f_mod.get("functions", []))
        c_fns = set(c_mod.get("functions", []))
        for fn in sorted(c_fns - f_fns):
            result["added_functions"].append(f"{mod}::{fn}")
        for fn in sorted(f_fns - c_fns):
            result["removed_functions"].append(f"{mod}::{fn}")

    return result


def _has_drift(diff: dict[str, Any]) -> bool:
    return any(bool(v) for v in diff.values())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_DEFAULT_MAP_PATH = Path(".planning/platform/kernel_api_map.json")


def _freeze(out_path: Path, root: str = "kernel") -> None:
    surface = build_api_map(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(surface, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Frozen {len(surface)} modules → {out_path}")


def _check(map_path: Path, root: str = "kernel") -> int:
    if not map_path.exists():
        print(f"ERROR: frozen map not found: {map_path}", file=sys.stderr)
        return 1

    frozen = json.loads(map_path.read_text(encoding="utf-8"))
    current = build_api_map(root)
    diff = diff_maps(frozen, current)

    if not _has_drift(diff):
        print("OK: no API drift detected.")
        return 0

    for category, symbols in diff.items():
        if symbols:
            label = "ADDED" if "added" in category else "REMOVED"
            for sym in symbols:
                print(f"{label}  {sym}")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Entry point for CLI."""
    parser = ArgumentParser(
        description="Kernel API surface map builder and drift checker.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true", help="Build and freeze the surface map.")
    mode.add_argument("--check", action="store_true", help="Rebuild and diff vs frozen map.")
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_MAP_PATH,
        help="Output path for --freeze (default: %(default)s).",
    )
    parser.add_argument(
        "--map",
        type=Path,
        default=_DEFAULT_MAP_PATH,
        help="Frozen map path for --check (default: %(default)s).",
    )
    parser.add_argument(
        "--root",
        type=str,
        default="kernel",
        help="Kernel root directory (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    if args.freeze:
        _freeze(args.out, root=args.root)
        return 0
    else:
        return _check(args.map, root=args.root)


if __name__ == "__main__":
    sys.exit(main())
