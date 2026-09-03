"""Independent per-file checks for the S187 deploy pathspec."""
from __future__ import annotations

import ast
from collections import deque
from pathlib import Path

from scripts.platformkit.ops import deploy_pathspec as dps
from supervisor.config import load_profile

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SEARCH_ROOTS = (_REPO_ROOT, _REPO_ROOT / "scripts" / "platformkit")

WITH_PROBE = {
    "data_registry": 2,
    "domains": 72,
    "frontend": 23,
    "governance": 4,
    "improve": 8,
    "kernel": 1,
    "ops": 9,
    "predict_service": 53,
    "scripts": 330,
    "src": 9,
    "supervisor": 13,
}
WITHOUT_PROBE = {
    "data_registry": 2,
    "domains": 67,
    "frontend": 23,
    "governance": 2,
    "improve": 7,
    "kernel": 1,
    "ops": 4,
    "predict_service": 50,
    "scripts": 229,
    "src": 9,
    "supervisor": 12,
}
OMITTED = {"data_registry", "frontend", "governance", "improve", "kernel", "ops", "src"}


def _resolve(name: str) -> Path | None:
    relative = Path(*name.split("."))
    for root in _SEARCH_ROOTS:
        source = root / relative.with_suffix(".py")
        package = root / relative / "__init__.py"
        if source.is_file():
            return source.resolve()
        if package.is_file():
            return package.resolve()
    return None


def _closure(*, submodule_probe: bool) -> set[Path]:
    pending = deque(
        spec.module
        for spec in load_profile("paper").specs()
        if spec.kind == "py" and spec.module
    )
    seen_names: set[str] = set()
    seen_paths: set[Path] = set()
    while pending:
        name = pending.popleft()
        if name in seen_names:
            continue
        seen_names.add(name)
        path = _resolve(name)
        if path is None or path in seen_paths:
            continue
        seen_paths.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                pending.append(node.module)
                if submodule_probe:
                    pending.extend(
                        "%s.%s" % (node.module, alias.name)
                        for alias in node.names
                        if alias.name != "*"
                    )
    return seen_paths


def _counts(paths: set[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        tree = path.relative_to(_REPO_ROOT).parts[0]
        counts[tree] = counts.get(tree, 0) + 1
    return dict(sorted(counts.items()))


def test_paper_closure_reproduces_both_resolver_counts(capsys) -> None:
    with_probe = _counts(_closure(submodule_probe=True))
    without_probe = _counts(_closure(submodule_probe=False))
    assert with_probe == WITH_PROBE
    assert without_probe == WITHOUT_PROBE
    assert set(with_probe) == set(without_probe)
    assert dps.deploy_trees("paper") == tuple(sorted(with_probe))

    assert dps.main(["--profile", "paper", "--emit"]) == 0
    assert capsys.readouterr().out.strip().split() == sorted(with_probe)

    assert dps.main(["--profile", "paper", "--check"]) == 1
    line = capsys.readouterr().out.strip()
    assert line.startswith("OMITTED: ")
    assert set(line.removeprefix("OMITTED: ").split()) == OMITTED
