"""Fail the pod preflight when a required deployed tree root is absent."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.ops.pod_bootstrap_check import check_imports  # noqa: E402


TREE_IMPORTS: Tuple[str, ...] = (
    "ops",                    # circuit breaker used by supervisor startup
    "kernel",                 # shared sport-blind runtime machinery
    "governance",             # runtime policy and safety package
    "data_registry",          # deployed dataset registry code
    "improve",                # self-improvement runtime package
    "frontend",               # prediction-service output package
    "src",                    # legacy runtime imports still used by the stack
    "supervisor.supervisor",  # actual module loaded by `python -m supervisor`
)


def main(argv: Sequence[str] | None = None) -> int:
    """Import all required deploy roots in one child and report failures."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable,
                        help="interpreter used for the import child")
    parser.add_argument("--repo", default=str(_REPO_ROOT),
                        help="repository root used as the import cwd")
    args = parser.parse_args(argv)

    results = check_imports(TREE_IMPORTS, args.python, cwd=args.repo)
    bad = [(module, error) for module, error in results.items()
           if error is not None]
    print("TREES: %d/%d OK" % (len(results) - len(bad), len(results)))
    for module, error in sorted(bad):
        print("FAIL %s -- %s" % (module, error))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
