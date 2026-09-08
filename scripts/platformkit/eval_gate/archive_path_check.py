"""Compare preregistered scratch locations to memo-reported realised locations."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

PATH_RE = re.compile(r"(?:/workspace/wt/[^\s`)]*(?:inputs|data/cache/eval_gate)[^\s`)]*)|(?:NONE \(committed evidence read in place\))")
PREREG_RE = re.compile(r"Preregistration:\s*`([^`]+)`", re.IGNORECASE)


def _paths(text: str) -> list[str]:
    return sorted(set(PATH_RE.findall(text)))


def check_pair(memo: Path, prereg: Path | None) -> list[dict[str, str]]:
    """Return one archive status row per declared artifact/location."""
    if not memo.exists():
        return [{"memo": str(memo), "prereg": str(prereg or ""), "expected": "", "realised": "", "status": "ABSENT"}]
    memo_text = memo.read_text(encoding="utf-8")
    if prereg is None:
        match = PREREG_RE.search(memo_text)
        prereg = Path(match.group(1)) if match else None
    if prereg is None or not prereg.exists():
        return [{"memo": str(memo), "prereg": str(prereg or ""), "expected": "", "realised": "", "status": "UNSTATED"}]
    expected, realised = _paths(prereg.read_text(encoding="utf-8")), _paths(memo_text)
    if not expected or not realised:
        return [{"memo": str(memo), "prereg": str(prereg), "expected": "", "realised": "", "status": "UNSTATED"}]
    rows = []
    for item in expected:
        status = "MATCH" if item in realised else "MISMATCH"
        rows.append({"memo": str(memo), "prereg": str(prereg), "expected": item, "realised": ";".join(realised), "status": status})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("memo", nargs="+", type=Path)
    args = parser.parse_args()
    rows = [row for memo in args.memo for row in check_pair(memo, None)]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("memo", "prereg", "expected", "realised", "status"), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    print(f"ARCHIVE_PATH_ROWS {len(rows)}")


if __name__ == "__main__":
    main()
