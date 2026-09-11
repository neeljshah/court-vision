"""Compare canonical G382 receipts emitted by two separately launched scorer processes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking.g382_score import verify_repeat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    first = json.loads(args.first.read_text(encoding="utf-8"))
    second = json.loads(args.second.read_text(encoding="utf-8"))
    result = verify_repeat(first, second)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("G382_REPEAT identical=%d" % result["identical"])
    return 0 if result["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
