"""Print tennis court-registration first-rejection counts for real footage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.tennis.tracking.court_diagnostics import GATE_ORDER, count_gates


def main() -> int:
    """Measure every first-rejection gate for one bounded video prefix."""
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--max-frames", type=int, default=600)
    args = parser.parse_args()
    if args.max_frames < 1:
        parser.error("--max-frames must be positive")
    counts = count_gates(str(args.video), args.max_frames)
    report = {"video": args.video.name, "frames": sum(counts.values()),
              "gates": {gate: counts[gate] for gate in GATE_ORDER}}
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
