"""Derive the deploy pathspec from a boot profile's Python import closure.

The resolver is intentionally static and stdlib-only. It follows absolute
``import`` statements and optionally probes every ``from X import Y`` as the
candidate module ``X.Y``. A candidate is first-party only when it resolves to
a Python file below the repository root or ``scripts/platformkit``. Repository
root resolution always wins so the top-level ``ops`` package is not shadowed.

This module reads source files and the existing bootstrap command only. It does
not deploy, start processes, change configuration, or write runtime data.
"""
from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLATFORMKIT = _REPO_ROOT / "scripts" / "platformkit"
_SEARCH_ROOTS = (_REPO_ROOT, _PLATFORMKIT)
_BOOTSTRAP = Path(__file__).with_name("pod_bootstrap.sh")


def _put_repo_first() -> None:
    """Order both first-party roots before any ambient import locations."""
    wanted = [str(_REPO_ROOT), str(_PLATFORMKIT)]
    sys.path[:] = wanted + [entry for entry in sys.path if entry not in wanted]


def _profile_modules(profile: str) -> Tuple[str, ...]:
    _put_repo_first()
    from supervisor.config import load_profile

    return tuple(
        spec.module
        for spec in load_profile(profile).specs()
        if spec.kind == "py" and spec.module
    )


def _resolve_module(name: str) -> Optional[Path]:
    relative = Path(*name.split("."))
    for root in _SEARCH_ROOTS:
        source = root / relative.with_suffix(".py")
        package = root / relative / "__init__.py"
        if source.is_file():
            return source.resolve()
        if package.is_file():
            return package.resolve()
    return None


def _import_candidates(path: Path, submodule_probe: bool) -> Iterable[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module
            if submodule_probe:
                for alias in node.names:
                    if alias.name != "*":
                        yield "%s.%s" % (node.module, alias.name)


def _closure_paths(profile: str, submodule_probe: bool = True) -> Set[Path]:
    pending = deque(_profile_modules(profile))
    seen_names: Set[str] = set()
    seen_paths: Set[Path] = set()
    while pending:
        name = pending.popleft()
        if name in seen_names:
            continue
        seen_names.add(name)
        path = _resolve_module(name)
        if path is None or path in seen_paths:
            continue
        seen_paths.add(path)
        pending.extend(_import_candidates(path, submodule_probe))
    return seen_paths


def closure_counts(profile: str, *, submodule_probe: bool = True) -> Dict[str, int]:
    """Return resolved module counts keyed by repository top-level tree."""
    counts = Counter(
        path.relative_to(_REPO_ROOT).parts[0]
        for path in _closure_paths(profile, submodule_probe)
    )
    return dict(sorted(counts.items()))


def deploy_trees(profile: str) -> Tuple[str, ...]:
    """Return the exhaustive top-level pathspec derived from *profile*."""
    return tuple(closure_counts(profile))


def _bootstrap_trees(path: Path = _BOOTSTRAP) -> Set[str]:
    marker = "git archive HEAD "
    for line in path.read_text(encoding="utf-8").splitlines():
        if marker not in line:
            continue
        fields = line.split(marker, 1)[1].split("\\", 1)[0].split()
        return {Path(field).parts[0] for field in fields}
    raise ValueError("git archive HEAD pathspec not found in %s" % path)


def main(argv: Optional[List[str]] = None) -> int:
    """Emit the derived pathspec or name the current bootstrap omissions."""
    parser = argparse.ArgumentParser(description="derive the boot-profile deploy pathspec")
    parser.add_argument("--profile", default="paper")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit", action="store_true", help="print the derived pathspec")
    mode.add_argument("--check", action="store_true", help="report bootstrap omissions")
    args = parser.parse_args(argv)

    trees = deploy_trees(args.profile)
    if args.emit:
        print(" ".join(trees))
        return 0

    omitted = sorted(set(trees) - _bootstrap_trees())
    if omitted:
        print("OMITTED: %s" % " ".join(omitted))
        return 1
    print("OK: bootstrap pathspec names every derived tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
