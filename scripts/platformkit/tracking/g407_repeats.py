"""G407 reproduction receipts: regenerate every delivered table and card twice.

Two fresh processes rebuild the delivered artifacts from the delivered bytes only. The receipt
keeps the parent shape used by the landed rows: an `identical` verdict, one entry per run with
its stdout and returncode, and a per-table digest map. Arithmetic and render reproduction is
never presented as producer or inference repeatability.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g397_census import sha256_file

SKIP = ("repeats.json", "SHA256SUMS")


def table_digests(out: Path) -> dict[str, str]:
    """Digest every delivered artifact except the receipts that record this comparison."""
    return {path.relative_to(out).as_posix(): sha256_file(path)
            for path in sorted(Path(out).rglob("*"))
            if path.is_file() and path.name not in SKIP}


def run_once(out: Path, root: Path, index: int) -> dict[str, Any]:
    """One fresh-process regeneration, recording its own stdout and exit status."""
    command = [sys.executable, "-m", "scripts.platformkit.tracking.g407_report",
               "--out", str(out)]
    done = subprocess.run(command, capture_output=True, text=True,
                          cwd=str(root), env={**__import__("os").environ,
                                              "PYTHONPATH": str(root)})
    return {"run": index, "command": " ".join(command), "stdout": done.stdout.strip(),
            "stderr_head": done.stderr.strip()[:400], "returncode": done.returncode,
            "table_digests": table_digests(out)}


def main() -> int:
    parser = argparse.ArgumentParser(description="G407 two-process reproduction receipt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    out, root = Path(args.out), Path(args.root)
    delivered = table_digests(out)
    runs = [run_once(out, root, index) for index in (1, 2)]
    per_table = {name: {"delivered": delivered[name],
                        "run_1": runs[0]["table_digests"].get(name, "ABSENT"),
                        "run_2": runs[1]["table_digests"].get(name, "ABSENT"),
                        "identical": int(delivered[name]
                                         == runs[0]["table_digests"].get(name)
                                         == runs[1]["table_digests"].get(name))}
                 for name in sorted(delivered)}
    identical = all(entry["identical"] for entry in per_table.values())
    payload = {"identical": int(identical), "runs": runs, "per_table": per_table,
               "tables_compared": len(per_table),
               "tables_identical": sum(entry["identical"] for entry in per_table.values()),
               "scope": "SAVED_INPUT_REGENERATION_ONLY",
               "note": "regeneration of delivered arithmetic and cards from delivered bytes; "
                       "it does not establish producer or inference repeatability"}
    (out / "repeats.json").write_text(json.dumps(payload, indent=1, sort_keys=True),
                                      encoding="utf-8", newline="\n")
    print("REPEATS identical=%d tables=%d matched=%d" % (
        identical, payload["tables_compared"], payload["tables_identical"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
