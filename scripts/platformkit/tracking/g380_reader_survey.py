"""Produce the required narrow CSV survey of tracking and ledger readers."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

_NEEDLES = ("tracking_data.csv", "ball_tracking.csv", "evaluated_frames")
_CLOSED_KEY = re.compile(
    r"(fieldnames\s*==|columns\s*==|set\s*\([^\n]*keys|len\s*\([^\n]*columns)",
    re.IGNORECASE,
)


def survey(root: Path, output: Path) -> int:
    """Scan source files line by line and write every relevant reader citation."""
    grouped: dict[str, list[tuple[int, str, bool]]] = {}
    for top in ("src", "scripts", "tests"):
        base = root / top
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                kinds = [needle for needle in _NEEDLES if needle in line]
                if kinds:
                    key = path.relative_to(root).as_posix()
                    grouped.setdefault(key, []).append(
                        (number, "+".join(kinds), bool(_CLOSED_KEY.search(line))))
    rows = []
    for path, hits in grouped.items():
        rows.append({
            "reader_path": path,
            "citations": ";".join("%s:%d" % (kind, number)
                                  for number, kind, _ in hits),
            "closed_key_assertion": str(any(closed for _, _, closed in hits)).lower(),
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("reader_path", "citations", "closed_key_assertion"))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    """Run the survey from the repository root."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("reader survey rows=%d" % survey(args.root.resolve(), args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
