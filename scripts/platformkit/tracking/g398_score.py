"""G398 scorer: frozen G363 scoring of the saved paired DEV shadow predictions.

Reads only the archived prediction tables. The continuation rule is the sealed
DEV planning rule; the historical 0.25/0.90/0.01 bars are printed unchanged and
are NOT tested by this row.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.tracking.g363_score import score_arm  # noqa: E402
from scripts.platformkit.tracking.g390_sealed_input import load_sealed_input  # noqa: E402
from scripts.platformkit.tracking.g398_prepare import (  # noqa: E402
    DEV_KEYS, continuation_met, preserve_planned_keys)

TRACKING = ROOT / "docs/evidence/tracking"
G389 = TRACKING / "g389_ball_reference_completion_2026-09-11"
OUT = TRACKING / "g398_a8_high_resolution_dev_shadow_2026-09-11"
SHEETS = Path("/workspace/g373_scratch/sheets_v2")
BASELINE, CANDIDATE = "A8_IMG960", "A8_IMG1920"
FILES = {BASELINE: "predictions_960.csv", CANDIDATE: "predictions_1920.csv"}
HISTORICAL_BARS = {"c0_min": 0.25, "precision_wilson_lower_min": 0.90,
                   "all_fp_per_absent_max": 0.01, "tested_by_this_row": False}
PAIRED_FIELDS = ("frame_key", "game", "section", "label", "in_dev_boxes",
                 "n_pred_960", "tp_960", "fp_960", "distance_720p_960", "score_960",
                 "n_pred_1920", "tp_1920", "fp_1920", "distance_720p_1920", "score_1920",
                 "threshold_720p")
EYE_FIELDS = ("position", "frame_key", "game", "label", "case_960", "case_1920",
              "distance_720p_960", "distance_720p_1920", "render")


def rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV input."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: tuple[str, ...], records: list[dict]) -> None:
    """Write one ASCII CSV artifact with a fixed field order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_json(path: Path, payload: dict) -> None:
    """Persist one ASCII JSON artifact."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="ascii", newline="\n")


def load() -> tuple[list[dict], dict, list[dict]]:
    """Load the sealed G389 tables and every archived prediction row."""
    sealed = load_sealed_input(G389 / "frames_v3.csv", G389 / "reference_v3.csv")
    predictions: list[dict] = []
    for arm, name in FILES.items():
        table = rows(OUT / name)
        keys = [row["frame_key"] for row in table]
        preserve_planned_keys(keys, {key: {} for key in keys})
        if any(row["arm"] != arm for row in table):
            raise ValueError("prediction-arm-mismatch-" + arm)
        predictions.extend(table)
    return sealed.frames, sealed.reference, predictions


def metrics(summary: dict, frame_rows: list[dict]) -> dict[str, object]:
    """Report the sealed DEV metrics on fixed full-DEV denominators."""
    absent_fp = sum(int(row["fp"]) for row in frame_rows if row["label"] == "ABSENT")
    unknown_fp = sum(int(row["fp"]) for row in frame_rows if row["label"] == "UNKNOWN")
    n_absent = summary["n_absent"]
    return {
        "arm": summary["arm"], "n_dev": summary["n_frames"],
        "n_visible": summary["n_visible"], "n_absent": n_absent,
        "n_unknown": summary["n_unknown"], "tp": summary["tp"], "fp": summary["fp"],
        "fn": summary["n_visible"] - summary["tp"],
        "c0": summary["coverage"], "precision": summary["precision"],
        "precision_wilson_lo": summary["precision_wilson_lo"],
        "precision_wilson_hi": summary["precision_wilson_hi"],
        "all_fp_per_absent": summary["fp_per_absent"],
        "absent_only_fp": absent_fp,
        "absent_only_fp_per_absent": absent_fp / n_absent if n_absent else None,
        "unknown_fp": unknown_fp, "abstention": summary["abstention"],
        "games": summary["games"], "recall_on_visible": summary["recall_on_visible"],
        "per_game_c0": summary["per_game"]}


def score() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Score both arms once through the frozen G363 rule."""
    frames, reference, predictions = load()
    scores: dict[str, dict] = {}
    per_frame: dict[str, list[dict]] = {}
    for arm in (BASELINE, CANDIDATE):
        summary, frame_rows = score_arm(arm, "development", frames, reference, predictions)
        if summary["n_frames"] != DEV_KEYS:
            raise ValueError("dev-denominator-mismatch-" + arm)
        scores[arm] = metrics(summary, frame_rows)
        per_frame[arm] = frame_rows
    return scores, per_frame


def counts_digest(scores: dict[str, dict]) -> dict[str, list]:
    """The arithmetic fingerprint replayed by each fresh scorer process."""
    return {arm: [row["tp"], row["fp"], row["fn"], round(float(row["c0"]), 12),
                  round(float(row["precision_wilson_lo"]), 12),
                  round(float(row["all_fp_per_absent"]), 12), row["absent_only_fp"]]
            for arm, row in sorted(scores.items())}


def paired(per_frame: dict[str, list[dict]]) -> list[dict]:
    """One paired record per DEV key, both arms side by side."""
    manifest = {row["frame_key"]: row for row in rows(OUT / "dev_manifest.csv")}
    calls = {arm: {row["frame_key"]: row for row in rows(OUT / FILES[arm])}
             for arm in FILES}
    indexed = {arm: {row["frame_key"]: row for row in table}
               for arm, table in per_frame.items()}
    records = []
    for key, source in sorted(manifest.items()):
        base, cand = indexed[BASELINE][key], indexed[CANDIDATE][key]
        records.append({
            "frame_key": key, "game": source["game"], "section": source["section"],
            "label": source["label"], "in_dev_boxes": source["in_dev_boxes"],
            "n_pred_960": base["n_predictions"], "tp_960": base["tp"],
            "fp_960": base["fp"], "distance_720p_960": base["distance_720p"],
            "score_960": calls[BASELINE][key]["score"],
            "n_pred_1920": cand["n_predictions"], "tp_1920": cand["tp"],
            "fp_1920": cand["fp"], "distance_720p_1920": cand["distance_720p"],
            "score_1920": calls[CANDIDATE][key]["score"],
            "threshold_720p": base["threshold_720p"]})
    if len(records) != DEV_KEYS:
        raise ValueError("paired-record-denominator-mismatch")
    write_csv(OUT / "paired_scores.csv", PAIRED_FIELDS, records)
    return records


def case(record: dict, suffix: str) -> str:
    """Name one arm's outcome on one key without hiding silence."""
    if int(record["tp" + suffix]):
        return "TP"
    if int(record["fp" + suffix]):
        return "FP"
    return "NO_DETECTION" if not int(record["n_pred" + suffix]) else "UNMATCHED"


def renders(records: list[dict], count: int = 30) -> list[dict]:
    """Draw evenly spaced paired native cards over every DEV key."""
    from PIL import Image, ImageDraw

    calls = {arm: {row["frame_key"]: row for row in rows(OUT / FILES[arm])} for arm in FILES}
    manifest = {row["frame_key"]: row for row in rows(OUT / "dev_manifest.csv")}
    out = OUT / "renders"
    out.mkdir(parents=True, exist_ok=True)
    picked = [records[round(i * (len(records) - 1) / (count - 1))] for i in range(count)]
    index = []
    for position, record in enumerate(picked):
        key = record["frame_key"]
        image = Image.open(SHEETS / (key[:12] + ".jpg")).convert("RGB")
        draw = ImageDraw.Draw(image)
        if record["label"] == "VISIBLE":
            source = manifest[key]
            cx, cy = float(source["cx"]), float(source["cy"])
            d = max(float(source["diameter"]), 24.0)
            draw.rectangle([cx - d, cy - d, cx + d, cy + d], outline=(0, 255, 0), width=4)
        for arm, colour in ((BASELINE, (255, 0, 0)), (CANDIDATE, (0, 128, 255))):
            call = calls[arm][key]
            if call["rank"] != "0":
                continue
            x, y = float(call["x"]), float(call["y"])
            pad = 6.0 if arm == BASELINE else 12.0
            w, h = float(call["w"]) / 2.0 + pad, float(call["h"]) / 2.0 + pad
            draw.rectangle([x - w, y - h, x + w, y + h], outline=colour, width=4)
        cases = (case(record, "_960"), case(record, "_1920"))
        draw.text((20, 20), "%s %s 960:%s 1920:%s" % (key[:12], record["label"], *cases),
                  fill=(255, 255, 0))
        name = "render_%02d_%s.jpg" % (position, key[:12])
        image.resize((960, 540)).save(out / name, quality=70)
        index.append({"position": position, "frame_key": key, "game": record["game"],
                      "label": record["label"], "case_960": cases[0],
                      "case_1920": cases[1],
                      "distance_720p_960": record["distance_720p_960"],
                      "distance_720p_1920": record["distance_720p_1920"], "render": name})
    write_csv(OUT / "eye_index.csv", EYE_FIELDS, index)
    return index


def repeats(primary: dict[str, list]) -> dict[str, object]:
    """Replay the saved predictions twice in fresh scorer processes."""
    replays = []
    for _ in range(2):
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--counts"],
                              cwd=str(ROOT), check=True, capture_output=True)
        replays.append(json.loads(done.stdout.decode("ascii").strip().splitlines()[-1]))
    payload = {"primary": primary, "replay_1": replays[0], "replay_2": replays[1],
               "identical": all(replay == primary for replay in replays),
               "note": "deterministic arithmetic replay only; not repeated inference"}
    write_json(OUT / "repeats.json", payload)
    return payload


def main() -> int:
    """Score once, archive the paired tables, eye cards, replays and summary."""
    scores, per_frame = score()
    if "--counts" in sys.argv:
        print(json.dumps(counts_digest(scores), sort_keys=True))
        return 0
    records = paired(per_frame)
    index = renders(records)
    digest = counts_digest(scores)
    replay = repeats(digest)
    base, cand = scores[BASELINE], scores[CANDIDATE]
    met = continuation_met(base, cand)
    launch = json.loads((OUT / "launch_accounting.json").read_text(encoding="ascii"))
    summary = {
        "verdict": "DONE (diagnostic only)" if met else "CLOSED AT LIMIT for this option",
        "continuation_met": met,
        "continuation_rule": ("candidate C0 > baseline C0 AND candidate Wilson95 precision "
                              "lower >= baseline AND candidate ALL FP/N_absent <= baseline; "
                              "ties fail"),
        "continuation_components": {
            "c0_strictly_higher": cand["c0"] > base["c0"],
            "wilson_lower_not_smaller": (cand["precision_wilson_lo"]
                                         >= base["precision_wilson_lo"]),
            "all_fp_per_absent_not_larger": (cand["all_fp_per_absent"]
                                             <= base["all_fp_per_absent"])},
        "arms": scores, "historical_bars": HISTORICAL_BARS,
        "deltas": {"c0": cand["c0"] - base["c0"],
                   "precision_wilson_lo": (cand["precision_wilson_lo"]
                                           - base["precision_wilson_lo"]),
                   "all_fp_per_absent": (cand["all_fp_per_absent"]
                                         - base["all_fp_per_absent"]),
                   "tp": cand["tp"] - base["tp"], "fp": cand["fp"] - base["fp"]},
        "launch": {"paired_launches": launch["paired_launches"], "state": launch["state"],
                   "gpu_stage_seconds": launch["result"]["gpu_stage_seconds"],
                   "peak_reserved_bytes": launch["result"]["peak_reserved_bytes"],
                   "detections": launch["result"]["detections"]},
        "eye_cards": len(index), "repeats_identical": replay["identical"],
        "one_run_status": ("single paired launch; no seed replicate; descriptive only, "
                           "neither causal nor a repeatable-system conclusion"),
        "heldout_inferences": 0}
    write_json(OUT / "summary.json", summary)
    print("G398 SCORE " + summary["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
