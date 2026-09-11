"""G397 closing receipts: fresh-process repeats, Q6 vocabulary scan, checksum manifest."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.platformkit.tracking.g397_census import sha256_file
from scripts.platformkit.tracking.g397_prepare import TEXT_SUFFIXES, q6_scan

CANONICAL = ("per_section.csv", "evaluated_ticks.csv", "held_pairs.csv",
             "enriched_ledger.jsonl", "summary.json")
MANIFEST = "SHA256SUMS"

__all__ = ["digests", "repeat_recompute", "write_manifest", "main"]


def digests(root: Path) -> dict[str, str]:
    """Digest every canonical table that exists, naming an absent one explicitly."""
    return {name: (sha256_file(root / name) if (root / name).is_file() else "ABSENT")
            for name in CANONICAL}


def repeat_recompute(root: Path, repo: Path, rounds: int = 2) -> dict[str, object]:
    """Recompute the canonical tables in fresh processes and compare the digests."""
    observed = []
    for _ in range(rounds):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);"
             "from scripts.platformkit.tracking.g397_report import main;"
             "sys.exit(main(['g397_report',%r]))" % (str(repo), str(root))],
            capture_output=True, text=True, timeout=3600, cwd=str(repo))
        observed.append({"returncode": result.returncode, "stdout": result.stdout.strip(),
                         "stderr": result.stderr.strip()[-400:], "digests": digests(root)})
    first = observed[0]["digests"]
    return {"rounds": rounds, "runs": observed,
            "identical": all(run["digests"] == first for run in observed),
            "canonical_digests": first}


def write_manifest(root: Path) -> int:
    """Write one checksum line per artifact except the manifest file itself."""
    lines = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_file() and path.name != MANIFEST:
            lines.append("%s  %s" % (sha256_file(path),
                                     path.relative_to(root).as_posix()))
    (Path(root) / MANIFEST).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(lines)


def main(argv: list[str]) -> int:
    """Run the repeats, the Q6 scan and the manifest over one evidence directory."""
    root = Path(argv[1])
    repo = Path(argv[2]) if len(argv) > 2 else Path.cwd()
    if "--repeats" in argv:
        report = repeat_recompute(root, repo)
        (root / "repeats.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")
        print("REPEATS identical=%s" % report["identical"])
    scanned = [path for path in sorted(Path(root).rglob("*"))
               if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES]
    q6_scan(scanned)
    print("Q6 clean files=%d" % len(scanned))
    print("MANIFEST files=%d" % write_manifest(root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
