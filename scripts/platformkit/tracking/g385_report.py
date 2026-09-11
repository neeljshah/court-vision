"""G385 join, score and receipt: paired gate/shadow decisions over all 360 planned ticks.

Sealed by `docs/evidence/tracking/g385_nonplay_shadow_mask_2026-09-10/
g385_prereg_2026-09-10.md` (SEAL sha256
1dd44f12075456bd18b5797815d23ba8b4bf3e13eb24417d08d813c0f085d589). The shadow
decision is published beside the original gate decision and replaces nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

from scripts.platformkit.tracking.g375_census import read_csv, write_csv
from scripts.platformkit.tracking.g385_mask import shadow_decision
from scripts.platformkit.tracking.g385_score import DEFINITE_NONPLAY, PLAY, score

PAIRED_FIELDS = ("tick_key", "sheet_id", "section_id", "video_id", "competition",
                 "original_gate_decision", "evidence_status", "p_nonplay",
                 "shadow_decision", "shadow_reason", "reference_label")
CONFUSION_FIELDS = ("reference_label", "shadow_decision", "frames")
RENDER_COUNT = 30
REFERENCE_MAP = {"BASKETBALL_PLAY": PLAY, "BASKETBALL_NONPLAY": "NONPLAY",
                 "OTHER_SPORT": "OTHER_SPORT", "NON_SPORT": "NON_SPORT", "UNKNOWN": "UNKNOWN"}


def join(frames: list[dict[str, str]], scores: list[dict[str, str]],
         labels: list[dict[str, str]]) -> list[dict[str, str]]:
    """Pair every planned tick with its shadow decision and its blind reference label."""
    by_tick = {row["tick_key"]: row for row in scores}
    by_sheet = {row["sheet_id"]: row["final_label"] for row in labels}
    out = []
    for row in frames:
        probability = (by_tick.get(row["tick_key"], {}).get("p_nonplay") or "") or None
        decided = shadow_decision({"p_nonplay": probability,
                                   "evidence_status": row["evidence_status"]})
        reference = REFERENCE_MAP.get(by_sheet.get(row["sheet_id"], ""), "UNKNOWN")
        out.append({"tick_key": row["tick_key"], "sheet_id": row["sheet_id"],
                    "section_id": row["section_id"], "video_id": row["video_id"],
                    "competition": row["competition"],
                    "original_gate_decision": "PRESERVED_BY_LIVE_GATE",
                    "evidence_status": row["evidence_status"],
                    "p_nonplay": probability or "",
                    "shadow_decision": decided["shadow_decision"],
                    "shadow_reason": decided["shadow_reason"],
                    "reference_label": reference})
    return sorted(out, key=lambda row: row["tick_key"])


def confusion(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Full contingency of blind reference label against the unused shadow decision."""
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["reference_label"], row["shadow_decision"])
        counts[key] = counts.get(key, 0) + 1
    return [{"reference_label": left, "shadow_decision": right, "frames": str(counts[(left, right)])}
            for left, right in sorted(counts)]


def section_purity(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Whole-section purity from the sampled ticks only; never extrapolated to unseen ticks."""
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["section_id"], []).append(row)
    out = []
    for section_id in sorted(groups):
        members = groups[section_id]
        definite = sum(row["reference_label"] in DEFINITE_NONPLAY for row in members)
        out.append({"section_id": section_id, "video_id": members[0]["video_id"],
                    "competition": members[0]["competition"],
                    "sampled_ticks": str(len(members)),
                    "reference_play": str(sum(row["reference_label"] == PLAY for row in members)),
                    "reference_definite_nonplay": str(definite),
                    "reference_unknown": str(sum(row["reference_label"] == "UNKNOWN"
                                                 for row in members)),
                    "shadow_masked": str(sum(row["shadow_decision"] == "MASK" for row in members))})
    return out


def renders(rows: list[dict[str, str]], sheets: Path, out: Path) -> dict[str, int]:
    """Thirty evenly spaced scored ticks plus every mask that the reference calls PLAY."""
    out.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: row["tick_key"])
    positions = [math.floor((index + 0.5) * len(ordered) / RENDER_COUNT)
                 for index in range(RENDER_COUNT)]
    picked = {ordered[index]["tick_key"]: ordered[index] for index in positions}
    harmful = {row["tick_key"]: row for row in ordered
               if row["shadow_decision"] == "MASK" and row["reference_label"] == PLAY}
    copied = 0
    for tick_key, row in sorted({**picked, **harmful}.items()):
        if not row["sheet_id"]:
            continue
        tag = "harmful" if tick_key in harmful else "even"
        shutil.copyfile(sheets / (row["sheet_id"] + ".jpg"),
                        out / ("%s_%s_%s.jpg" % (tag, row["sheet_id"], row["reference_label"])))
        copied += 1
    return {"even_spaced": len(picked), "harmful_play_masks": len(harmful), "files": copied}


def main() -> None:
    parser = argparse.ArgumentParser(description="G385 shadow-mask scoring receipt")
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    paired = join(read_csv(args.frames), read_csv(args.scores), read_csv(args.labels))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "paired_masks.csv", paired, PAIRED_FIELDS)
    write_csv(args.out_dir / "confusion.csv", confusion(paired), CONFUSION_FIELDS)
    purity = section_purity(paired)
    write_csv(args.out_dir / "section_purity.csv", purity, tuple(purity[0]))
    result = score(paired)
    result["renders"] = renders(paired, args.sheets, args.out_dir / "renders")
    result["sections"] = len(purity)
    result["videos"] = len({row["video_id"] for row in paired})
    result["shadow_only_no_flag_no_table_no_data_write"] = True
    (args.out_dir / "summary.json").write_text(
        json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="ascii")
    print("PLAY=%d DEFINITE_NONPLAY=%d UNKNOWN=%d MASKED=%d FALSE=%d CAPTURED=%d" % (
        result["reference_play"], result["reference_definite_nonplay"],
        result["reference_unknown"], result["masked_frames"], result["false_masks"],
        result["captured_nonplay"]))
    print("false_mask_rate=%.6f/%.6f/%.6f capture=%.6f/%.6f/%.6f" % (
        *result["false_mask_rate"], *result["nonplay_capture"]))
    print("bars false=%s capture=%s classes=%s zero_absent=%s" % (
        result["bar_false_mask"], result["bar_capture"], result["bar_classes"],
        result["zero_absent_masks"]))


if __name__ == "__main__":
    main()
