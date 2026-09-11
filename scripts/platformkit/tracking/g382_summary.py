"""G382 specificity summary: two shares, category attribution, completeness, repeat identity."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from scripts.platformkit.tracking.g382_masks import LABELS, UNKNOWN

NON_MARKING = tuple(label for label in LABELS if label != "PAINTED") + (UNKNOWN,)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build(planned: list[dict[str, str]], scored: list[dict[str, str]], strokes: list[dict[str, str]],
          supports: list[dict[str, str]], repeats: dict[str, object], rated: int) -> dict[str, object]:
    """Every planned frame, every emitted stroke and every emitted support stays in a denominator."""
    on_marking = sum(row["on_marking"] == "1" for row in strokes)
    labels = Counter(row["base_label"] for row in supports)
    painted = labels.get("PAINTED", 0)
    per_frame: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in strokes:
        entry = per_frame[row["frame_key"]]
        entry[0] += int(row["on_marking"] == "1")
        entry[1] += 1
    shares = {key: value[0] / value[1] for key, value in per_frame.items() if value[1]}
    with_strokes = [key for key in shares]
    scored_keys = [row["frame_key"] for row in scored if row["status"] == "SCORED"]
    no_strokes = [key for key in scored_keys if key not in per_frame]
    return {
        "denominators": {"planned_frames": len(planned), "retained_frames":
                         sum(row["retained"] == "RETAINED" for row in planned),
                         "rated_frames": rated, "scored_frames": len(scored_keys),
                         "decode_failed_frames": sum(row["retained"] != "RETAINED" for row in planned)},
        "stroke_specificity": {"on_marking_strokes": on_marking, "all_strokes": len(strokes),
                               "share": (on_marking / len(strokes)) if strokes else None},
        "support_specificity": {"painted_supports": painted, "all_supports": len(supports),
                                "share": (painted / len(supports)) if supports else None},
        "per_frame": {"frames_with_strokes": len(with_strokes),
                      "macro_mean_on_marking_share": (sum(shares.values()) / len(shares)) if shares else None,
                      "min": min(shares.values()) if shares else None,
                      "max": max(shares.values()) if shares else None,
                      "shares": {key: round(value, 8) for key, value in sorted(shares.items())}},
        "empty_frames": {"no_stroke_scored_frames": len(no_strokes),
                         "over_planned": len(no_strokes) / len(planned) if planned else None,
                         "frame_keys": sorted(no_strokes)},
        "support_label_counts": {label: labels.get(label, 0) for label in LABELS + (UNKNOWN,)},
        "non_marking_attribution": {label: labels.get(label, 0) for label in NON_MARKING},
        "repeat_identity": repeats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--rated", type=int, required=True)
    args = parser.parse_args()
    base = args.evidence
    value = build(_rows(base / "frames.csv"), _rows(base / "frames_scored.csv"),
                  _rows(base / "strokes.csv"), _rows(base / "support_labels.csv"),
                  json.loads((base / "repeats.json").read_text(encoding="utf-8")), args.rated)
    (base / "summary.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("G382_SUMMARY strokes=%s supports=%s" % (value["stroke_specificity"]["share"],
                                                   value["support_specificity"]["share"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
