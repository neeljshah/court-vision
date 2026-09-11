"""G388 text-artifact vocabulary scan using the shared character-built patterns."""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.platformkit.tracking import g334_seal


def scan_paths(paths: list[Path]) -> list[tuple[Path, int, str, str]]:
    """Return every shared-contract vocabulary hit across the supplied text artifacts."""
    findings = []
    for path in paths:
        for number, kind, text in g334_seal.scan_text(path.read_text(encoding="utf-8", errors="replace")):
            findings.append((path, number, kind, text))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args()
    findings = scan_paths(args.paths)
    for path, number, kind, text in findings:
        print("G388_SCAN %s:%d %s %r" % (path.as_posix(), number, kind, text))
    print("G388_SCAN_SUMMARY files=%d hits=%d" % (len(args.paths), len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
