"""Reproduce S188 tree-absence cases with a sys.meta_path blocker.

The blocker is installed in every child through a temporary sitecustomize.py.
Use --gate existing before the change and --gate composed after the change.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOTS: Tuple[str, ...] = (
    "ops", "kernel", "governance", "data_registry", "improve", "frontend", "src")
CASES: Tuple[Tuple[str, Tuple[str, ...]], ...] = tuple(
    (root, (root,)) for root in ROOTS) + (("all", ROOTS),)
REPO = Path(__file__).resolve().parents[3]
CHECK = REPO / "scripts" / "platformkit" / "ops" / "pod_bootstrap_check.py"
TREE_GATE = REPO / "scripts" / "platformkit" / "ops" / "deploy_tree_gate.py"

_SITECUSTOMIZE = """\
import importlib.abc
import os
import sys

blocked = set(filter(None, os.environ.get("S188_BLOCKED_ROOTS", "").split(",")))
mode = os.environ.get("S188_BLOCK_MODE", "")

class S188Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".", 1)[0]
        if root in blocked:
            raise ModuleNotFoundError("No module named '%s'" % root)
        return None

if mode == "defer":
    os.environ["S188_BLOCK_MODE"] = "block"
elif mode == "block":
    sys.meta_path.insert(0, S188Blocker())
"""


def _env(site_dir: str, blocked: Iterable[str]) -> Dict[str, str]:
    env = os.environ.copy()
    prior = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (site_dir, str(REPO), prior) if part)
    env["S188_BLOCKED_ROOTS"] = ",".join(blocked)
    env["S188_BLOCK_MODE"] = "defer"
    return env


def _run(command: Sequence[str], env: Dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(REPO), env=env, capture_output=True,
                          text=True, timeout=700, check=False)


def run_gate(gate: str, blocked: Sequence[str], site_dir: str
             ) -> Tuple[int, List[subprocess.CompletedProcess[str]]]:
    """Run the existing gate, then the tree gate when composed and reachable."""
    env = _env(site_dir, blocked)
    existing = _run((sys.executable, str(CHECK), "--profile", "paper",
                     "--python", sys.executable, "--repo", str(REPO)), env)
    runs = [existing]
    if existing.returncode or gate == "existing":
        return existing.returncode, runs
    tree = _run((sys.executable, str(TREE_GATE), "--python", sys.executable,
                 "--repo", str(REPO)), env)
    runs.append(tree)
    return tree.returncode, runs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", choices=("existing", "composed"), required=True)
    parser.add_argument("--case", choices=tuple(name for name, _ in CASES) + ("control",))
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--sharp", action="store_true",
                        help="also import supervisor.supervisor with ops blocked")
    args = parser.parse_args(argv)
    selected = ((args.case, ()) if args.case == "control" else None,)
    if args.case and args.case != "control":
        selected = tuple(case for case in CASES if case[0] == args.case)
    elif not args.case:
        selected = CASES + (("control", ()),)

    with tempfile.TemporaryDirectory(prefix="s188_blocker_") as site_dir:
        Path(site_dir, "sitecustomize.py").write_text(_SITECUSTOMIZE, encoding="ascii")
        outcomes = []
        for name, blocked in selected:
            code, runs = run_gate(args.gate, blocked, site_dir)
            outcomes.append((name, code))
            print("CASE %-13s EXIT %d" % (name, code))
            if args.verbose:
                for run in runs:
                    print(run.stdout.rstrip())
                    if run.stderr:
                        print(run.stderr.rstrip())
        failed_closed = sum(code != 0 for name, code in outcomes if name != "control")
        print("SUMMARY: %d/8 tree-absent cases exited nonzero" % failed_closed)
        if args.sharp:
            env = _env(site_dir, ("ops",))
            env["S188_BLOCK_MODE"] = "block"
            sharp = _run((sys.executable, "-c", "import supervisor.supervisor"), env)
            print("SHARP ops supervisor.supervisor EXIT %d" % sharp.returncode)
            if sharp.stdout:
                print(sharp.stdout.rstrip())
            if sharp.stderr:
                print(sharp.stderr.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
