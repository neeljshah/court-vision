"""CLI entry point for the calibration scoreboard."""
from __future__ import annotations

import argparse
from typing import List, Optional

from scripts.platformkit import calibration_scoreboard


def main(argv: Optional[List[str]] = None) -> int:
    """Run the calibration scoreboard CLI without changing the default writer path."""
    parser = argparse.ArgumentParser(description="Build the calibration scoreboard.")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print the scoreboard without writing the vault or ops JSON artifacts.",
    )
    args = parser.parse_args(argv)
    print("Building calibration scoreboard (real providers) ...")
    results = calibration_scoreboard.build_calibration_scoreboard(write=not args.no_write)
    for r in results:
        if "error" in r:
            print(f"  {r['sport']}: ERROR — {r['error']}")
        else:
            bl = r.get("baseline", {})
            im = r.get("improved", {})
            print(
                f"  {r['sport']:6s}  n={im.get('n', bl.get('n', 0)):,}  "
                f"baseline ECE={bl.get('ece', float('nan')):.5f}  "
                f"improved ECE={im.get('ece', float('nan')):.5f}  "
                f"method={r.get('method','?')}"
            )
    print("Artifact not written (--no-write)." if args.no_write else "Artifact written.")
    return 0
