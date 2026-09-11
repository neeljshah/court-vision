"""G392 practice feedback sheets and the one frozen rater-side correction.

Feedback exists for the PRACTICE set only. Qualification never receives it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g392_prepare as prepare

HEADER = ("| control | tile | truth p_start (tile) | truth p_end (tile) | your p1 | your p2 |"
          " your p3 | perp p1/p2/p3 | verdict |")
RULE = "|---|---|---|---|---|---|---|---|---|"


def _tile_point(x: str, y: str, offset_x: str, offset_y: str) -> str:
    return "%.1f,%.1f" % (float(x) - float(offset_x), float(y) - float(offset_y))


def build_sheet(truth_rows: list[dict[str, str]], score_rows: list[dict[str, str]],
                rater: str) -> str:
    """Write one rater a full known-coordinate comparison for all 30 practice controls."""
    by_id = {row["control_id"]: row for row in score_rows if row["rater"] == rater}
    lines = ["# G392 practice feedback for %s (PRACTICE ONLY -- qualification is blind)" % rater,
             "", "Truth points below are the two endpoints of the finite centreline in the",
             "TILE-LOCAL frame of the image you opened. Compare them with what you reported.",
             "", HEADER, RULE]
    for row in truth_rows:
        scored = by_id.get(row["control_id"], {})
        answered = scored.get("answered") == "1"
        your = ["%s,%s" % (scored.get("pos_" + key, "?"), scored.get("perp_" + key, "?"))
                for key in ("p1", "p2", "p3")] if answered else ["-", "-", "-"]
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["control_id"], row["tile_index"],
            _tile_point(row["x1"], row["y1"], row["offset_x"], row["offset_y"]),
            _tile_point(row["x2"], row["y2"], row["offset_x"], row["offset_y"]),
            your[0], your[1], your[2],
            "/".join(scored.get("perp_" + key, "-") or "-" for key in ("p1", "p2", "p3")),
            "PASS" if scored.get("passed") == "1" else (scored.get("fail_reason") or "FAIL")))
    lines += ["", "Columns `your p1/p2/p3` are `position-along-band,perpendicular-px`.",
              "A perpendicular value above 3.0 px is a failed point.", ""]
    return "\n".join(lines)


def freeze(base: Path, correction: dict[str, object], target: Path) -> str:
    """Append at most one recorded rater-side correction and freeze the instruction."""
    text = base.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    note = str(correction.get("correction", "")).strip() or "none requested"
    text += ("\n\n## Frozen rater-side correction (exactly one, recorded before qualification)\n\n"
             "%s\n" % note)
    target.write_text(text, encoding="ascii", newline="\n")
    return note


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--corrections", type=Path, default=None)
    args = parser.parse_args()
    truth_rows, score_rows = tiles.read_csv(args.truth), tiles.read_csv(args.scores)
    receipt: dict[str, object] = {"raters": {}}
    for rater in prepare.RATERS:
        sheet = args.evidence / "practice" / ("feedback_%s.md" % rater)
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_text(build_sheet(truth_rows, score_rows, rater), encoding="ascii", newline="\n")
        entry: dict[str, object] = {"feedback_sheet": sheet.as_posix()}
        if args.corrections is not None:
            path = args.corrections / ("correction_%s.json" % rater)
            payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            entry["requested"] = bool(payload.get("requested"))
            entry["correction"] = freeze(args.evidence / "rater_instruction_control.md", payload,
                                         args.evidence / ("frozen_instructions_%s.md" % rater))
            entry["rationale"] = str(payload.get("rationale", ""))[:400]
        receipt["raters"][rater] = entry
    (args.evidence / "correction_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
