"""G396 practice feedback and the one frozen ASTRA correction.

Feedback exists for the PRACTICE set only, and only for the fresh rater. Sol
carries its already-frozen G392 instruction unchanged and sees no feedback.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g392_feedback as feedback

RATER = "astra"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, default=None)
    args = parser.parse_args()
    truth_rows, score_rows = tiles.read_csv(args.truth), tiles.read_csv(args.scores)
    sheet = args.evidence / "practice" / ("feedback_%s.md" % RATER)
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(feedback.build_sheet(truth_rows, score_rows, RATER).replace("G392", "G396"),
                     encoding="ascii", newline="\n")
    entry: dict[str, object] = {"feedback_sheet": sheet.as_posix()}
    if args.corrections is not None:
        path = args.corrections / ("correction_%s.json" % RATER)
        payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        entry["requested"] = bool(payload.get("requested"))
        entry["correction"] = feedback.freeze(args.evidence / "rater_instruction_control.md", payload,
                                              args.evidence / ("frozen_instructions_%s.md" % RATER))
        entry["rationale"] = str(payload.get("rationale", ""))[:400]
    receipt = {"raters": {RATER: entry},
               "sol": {"instruction": "frozen_instructions_sol.md carried verbatim from G392",
                       "feedback_given": False, "correction_permitted": False}}
    (args.evidence / "correction_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
