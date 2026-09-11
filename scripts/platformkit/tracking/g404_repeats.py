"""G404 fresh-process reproduction of every delivered table this row computes.

Runs the committed census and scoring routes twice in fresh processes and records
the parent repeat shape: identical, runs with stdout and returncode, and per-table
digests. A reproduction proves only these arithmetic and render operations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digests(out: Path, names: list[str]) -> dict[str, str]:
    found = {}
    for name in names:
        path = out / name
        found[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    return found


def run(args) -> int:
    out = Path(args.out_dir)
    names = args.table
    delivered = digests(out, names)
    runs = []
    for attempt in (1, 2):
        result = subprocess.run(["python", "-c", Path(args.script).read_text(encoding="ascii")],
                                capture_output=True, text=True, cwd=args.repo)
        current = digests(out, names)
        runs.append({"attempt": attempt, "returncode": result.returncode,
                     "stdout": result.stdout.strip()[-400:],
                     "digests": current,
                     "matches_delivered": {name: current[name] == delivered[name]
                                           for name in names}})
    identical = all(row["digests"] == delivered and row["returncode"] == 0 for row in runs)
    payload = {"identical": identical, "runs": runs, "delivered_digests": delivered,
               "renders": len(list((out / "renders").glob("*.jpg"))),
               "note": "the reproduced operations are the whole-pool census, the "
                       "disjointness join and the gate-audit scoring; decode, embedding "
                       "and rating are not reproduced by this receipt"}
    (out / "repeats.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                      encoding="ascii")
    print("REPEATS identical", identical)
    return 0 if identical else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_repeats")
    for flag in ("--out-dir", "--script", "--repo"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--table", action="append", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
