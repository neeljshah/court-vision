"""G389: merge the completed blind adjudications into the full 1,620-key census.

The merge runs through the SAME sealed functions that produced reference_v2 and the
G384 receipt (g373_reference_v2.census over g363_ball_coverage.read_csv rows), so
every G373 and G384 decision is reproduced rather than re-derived: the run asserts
agreement on all 1,114 prior decisions before it writes anything.

No arm is trained, scored or executed here. Development-box counting inherits the
G373 causal-neighbour rule (same section, frame index within two) and never counts a
held-out frame.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import read_csv, write_csv
from scripts.platformkit.tracking.g373_reference_v2 import REFERENCE_FIELDS, by_frame, census

CHECKPOINTS = (30, 120, 240, 360, 506)
NEIGHBOUR_FRAMES = 2
QUOTA_BOXES, QUOTA_GAMES = 500, 5
BOX_FIELDS = ("frame_key", "game", "section", "frame_index", "width", "height",
              "sheet_scale", "label", "cx", "cy", "diameter", "decided_by", "source")


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def prior_decisions(reference: list[dict], adjudications: list[dict]) -> dict[str, str]:
    """Every decision that already existed; none of these may change or vanish."""
    prior = {row["frame_key"]: row["label"] for row in reference}
    prior.update({row["frame_key"]: row["label"] for row in adjudications})
    return prior


def assert_no_drop(merged: list[dict], prior: dict[str, str]) -> dict[str, int]:
    """Refuse the merge if any earlier decision was dropped or relabelled."""
    have = {row["frame_key"]: row["label"] for row in merged}
    missing = [key for key in prior if key not in have]
    changed = [key for key, label in prior.items() if have.get(key) not in (None, label)]
    if missing or changed:
        raise ValueError("prior-decision-lost missing=%d changed=%d" % (len(missing), len(changed)))
    return {"prior_decisions": len(prior), "prior_reproduced": len(prior)}


def even_subset(order: list[dict], completed: set[str]) -> dict[str, object]:
    """A partial pass must be an EVEN subset of the sealed order, never a prefix.

    The sealed permutation already interleaves 30 contiguous quantile bins, so
    consuming it in order keeps any stopping point even. A completed set that is
    exactly a leading run of that permutation is still refused, because a prefix of a
    DIFFERENT ordering would look identical here and would be a head slice (B7).
    """
    keys = [row["frame_key"] for row in order]
    bins = sorted({row["bin"] for row in order})
    covered = sorted({row["bin"] for row in order if row["frame_key"] in completed})
    if completed and len(completed) < len(keys):
        expected = min(len(bins), len(completed))
        if len(covered) < expected:
            raise ValueError("partial-pass-not-even covered=%d expected=%d"
                             % (len(covered), expected))
    partial = bool(completed) and len(completed) < len(keys)
    return {"bins_total": len(bins), "bins_covered": len(covered),
            "partial_pass": partial,
            "is_prefix_of_sealed_order": partial and set(keys[:len(completed)]) == set(completed)}


def dev_boxes(merged: list[dict], frames: dict[str, dict]) -> tuple[list[dict], int]:
    """Unique valid native development boxes, causal neighbours counted once."""
    rows: list[dict] = []
    claimed: set[tuple[str, int]] = set()
    skipped = 0
    for entry in sorted(merged, key=lambda row: row["frame_key"]):
        frame = frames.get(entry["frame_key"])
        if entry["split"] != "development" or entry["label"] != "VISIBLE" or frame is None:
            continue
        if _float(entry.get("cx")) is None or not _float(entry.get("diameter")):
            continue
        index = int(frame["frame_index"] or 0)
        if any(item[0] == frame["section"] and abs(item[1] - index) <= NEIGHBOUR_FRAMES
               for item in claimed):
            skipped += 1
            continue
        claimed.add((frame["section"], index))
        rows.append({"frame_key": entry["frame_key"], "game": frame["game"],
                     "section": frame["section"], "frame_index": frame["frame_index"],
                     "width": frame["width"], "height": frame["height"],
                     "sheet_scale": frame["sheet_scale"], "label": entry["label"],
                     "cx": entry["cx"], "cy": entry["cy"], "diameter": entry["diameter"],
                     "decided_by": entry["decided_by"], "source": entry["source"]})
    return rows, skipped


def checkpoint_table(order: list[dict], merged: list[dict], frames: dict[str, dict],
                     done: set[str]) -> list[dict]:
    """Even checkpoints over the sealed permutation -- never a completed prefix."""
    index = {row["frame_key"]: row for row in merged}
    rows = []
    for mark in CHECKPOINTS:
        keys = [row["frame_key"] for row in order[:mark] if row["frame_key"] in done]
        subset = [index[key] for key in keys if key in index]
        boxes, _ = dev_boxes(subset, frames)
        rows.append({"checkpoint": mark, "reached": len(keys),
                     "settled": sum(1 for row in subset if row["label"]),
                     "development": sum(1 for row in subset if row["split"] == "development"),
                     "heldout": sum(1 for row in subset if row["split"] == "heldout"),
                     "visible": sum(1 for row in subset if row["label"] == "VISIBLE"),
                     "absent": sum(1 for row in subset if row["label"] == "ABSENT"),
                     "unknown": sum(1 for row in subset if row["label"] == "UNKNOWN"),
                     "new_dev_boxes": len(boxes)})
    return rows


def run(args) -> int:
    out = Path(args.out_dir)
    manifest = read_csv(Path(args.manifest))
    frame_rows = read_csv(Path(args.frames))
    frames = {row["frame_key"]: row for row in frame_rows}
    reference = read_csv(Path(args.reference))
    g384 = read_csv(Path(args.g384))
    new = read_csv(Path(args.new)) if Path(args.new).exists() else []
    order = read_csv(out / "sweep_permutation.csv")
    scheduled = [{"frame_key": row["frame_key"], "split": row["split"],
                  "source": row.get("source", "")} for row in manifest]
    merged, summary = census(scheduled, by_frame(read_csv(Path(args.ratings)) + g384 + new))
    receipt = assert_no_drop(merged, prior_decisions(reference, g384))

    index = {row["frame_key"]: row for row in merged}
    full = []
    for row in manifest:
        entry = index.get(row["frame_key"])
        base = {field: "" for field in REFERENCE_FIELDS}
        base.update(entry or {})
        base.update(frame_key=row["frame_key"], split=row["split"], source=row["source"],
                    review_state="REVIEWED" if entry else "UNVISITED")
        full.append(base)
    write_csv(out / "reference_v3.csv", REFERENCE_FIELDS + ("review_state",), full)
    write_csv(out / "frames_v3.csv", tuple(frame_rows[0].keys()),
              [frames[row["frame_key"]] for row in manifest if row["frame_key"] in frames])

    boxes, skipped = dev_boxes(merged, frames)
    write_csv(out / "dev_boxes_v3.csv", BOX_FIELDS, boxes)
    done = {row["frame_key"] for row in new}
    write_csv(out / "checkpoints.csv",
              ("checkpoint", "reached", "settled", "development", "heldout",
               "visible", "absent", "unknown", "new_dev_boxes"),
              checkpoint_table(order, merged, frames, done))

    games = sorted({row["game"] for row in boxes})
    heldout = [row for row in merged if row["split"] == "heldout"]
    evenness = even_subset(order, done)
    payload = {
        "manifest": len(manifest), "settled": len(merged),
        "unsettled": len(manifest) - len(merged),
        "keys_completed_g389": len(done), "queue_total": 506,
        "completion": "DONE" if len(done) == 506 else "PARTIAL",
        "prior_decision_receipt": receipt, "partial_pass_evenness": evenness,
        "settled_by_split": {name: sum(1 for row in merged if row["split"] == name)
                             for name in ("development", "heldout")},
        "heldout_labels": {label: sum(1 for row in heldout if row["label"] == label)
                           for label in ("VISIBLE", "ABSENT", "UNKNOWN")},
        "labels": {label: sum(1 for row in merged if row["label"] == label)
                   for label in ("VISIBLE", "ABSENT", "UNKNOWN")},
        "dev_boxes": len(boxes), "dev_boxes_quota": QUOTA_BOXES,
        "dev_box_games": len(games), "dev_box_games_quota": QUOTA_GAMES,
        "dev_box_game_ids": games,
        "dev_boxes_skipped_causal_neighbour": skipped,
        "census_diagnostics": summary,
        "g390_condition_met": bool(len(boxes) >= QUOTA_BOXES and len(games) >= QUOTA_GAMES),
        "candidate_executions": 0, "gpu_minutes": 0}
    (out / "summary.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                      encoding="ascii", newline="\n")
    heldout_labels = payload["heldout_labels"]
    readiness = {
        "dev_boxes_audited": len(boxes), "dev_boxes_quota": QUOTA_BOXES,
        "dev_box_games": len(games), "dev_box_games_quota": QUOTA_GAMES,
        "heldout_visible": heldout_labels["VISIBLE"], "heldout_absent": heldout_labels["ABSENT"],
        "heldout_unknown": heldout_labels["UNKNOWN"],
        "reference_settled": len(merged), "reference_scheduled": len(manifest),
        "still_queued": len(manifest) - len(merged),
        "queue_keys_completed": len(done), "queue_keys_total": 506,
        "readiness": {
            "reference_complete": len(done) == 506,
            "heldout_visible_150": heldout_labels["VISIBLE"] >= 150,
            "heldout_absent_150": heldout_labels["ABSENT"] >= 150,
            "development_boxes_500": len(boxes) >= QUOTA_BOXES,
            "development_games_5": len(games) >= QUOTA_GAMES,
            "g390_premise_check_permitted": bool(len(boxes) >= QUOTA_BOXES
                                                 and len(games) >= QUOTA_GAMES)},
        "candidate_heldout_executions": 0, "gpu_minutes_used": 0,
        "note": "a permitted G390 premise check is not an authorisation to score any arm"}
    (out / "readiness.json").write_text(json.dumps(readiness, indent=1, sort_keys=True) + "\n",
                                        encoding="ascii", newline="\n")
    print(json.dumps({key: payload[key] for key in
                      ("settled", "unsettled", "keys_completed_g389", "completion",
                       "dev_boxes", "dev_box_games", "heldout_labels",
                       "g390_condition_met")}, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g389_finish")
    for flag in ("--manifest", "--frames", "--reference", "--g384", "--ratings",
                 "--new", "--out-dir"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
