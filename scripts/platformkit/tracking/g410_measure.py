"""G410 landed-byte measurement: sealed draw, retention and box-advance tables.

Reads only G402's landed artifacts and G380's landed semantics.  It never
modifies a parent table and never infers a court coordinate from an image
coordinate: every court value here is copied from the producer's own row.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking.g410_prepare import (
    draw_orders_from_launches, exact_even, ordered_ticks, read_rows,
)

PAD = 15                     # src/tracking/player_detection.py:20
TOPCUT = 60                  # src/tracking/advanced_tracker.py:1825 (video_handler)
MAX_2D_JUMP = 250            # src/tracking/advanced_tracker.py:84
PIPELINE_JUMP = 350          # src/pipeline/unified_pipeline.py:2032
CLASSES = ("CLAMP", "SUBPIXEL")


def sha256_of(path: Path) -> tuple[int, str]:
    """Return (bytes, sha256) for one delivered or consumed input path."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def box_of(row: dict):
    """Return the stored image box as xyxy, or None when the writer stored none."""
    try:
        return (float(row["bbox_x1"]), float(row["bbox_y1"]),
                float(row["bbox_x2"]), float(row["bbox_y2"]))
    except (KeyError, TypeError, ValueError):
        return None


def position_of(row: dict) -> tuple[str, str]:
    """Return the serialized court position exactly as the producer wrote it."""
    return (str(row["x_position"]), str(row["y_position"]))


def archived_foot(box, frame_w: int, frame_h: int) -> tuple[int, int, int]:
    """Reproduce head_x/foot_y from the stored box per the archived code path.

    advanced_tracker.py:1336 stores (y1-PAD, x1-PAD, y2+PAD, x2+PAD); line 1410
    projects ((x1c+x2c)//2, y2c) built from the CLIPPED, UNPADDED detector box.
    The third return value is 1 when either clip actually bit.
    """
    x1 = box[0] + PAD
    x2 = box[2] - PAD
    y2 = box[3] - PAD
    x1c = max(0, int(x1))
    x2c = min(int(frame_w), int(x2))
    y2c = min(int(frame_h), int(y2))
    clipped = int(x1c != int(x1) or x2c != int(x2) or y2c != int(y2))
    return (x1c + x2c) // 2, y2c, clipped


def chain(rows: list) -> dict:
    """Index landed rows by (section, frame, player) and by (section, player)."""
    by_key: dict = {}
    tracks: dict = {}
    for row in rows:
        key = (row["draw_kind"], row["section_id"], int(row["frame"]),
               row["player_id"])
        if key in by_key:
            raise ValueError("duplicate-observation-key")
        by_key[key] = row
        tracks.setdefault((row["draw_kind"], row["section_id"],
                           row["player_id"]), []).append(row)
    for value in tracks.values():
        value.sort(key=lambda item: int(item["frame"]))
    return {"by_key": by_key, "tracks": tracks}


def retention(track_rows: list, index: int) -> dict:
    """Measure retained-position age and box advance against the predecessor."""
    row = track_rows[index]
    out = {"predecessor_frame": "", "position_retained": "", "box_moved": "",
           "box_foot_dx_px": "", "box_foot_dy_px": "", "box_l2_px": "",
           "retained_position_age": "", "box_identical_age": "",
           "predecessor_status": "MISSING_INITIAL_HISTORY"}
    if index == 0:
        return out
    prev = track_rows[index - 1]
    out["predecessor_frame"] = prev["frame"]
    out["predecessor_status"] = "PRESENT"
    out["position_retained"] = int(position_of(row) == position_of(prev))
    here, there = box_of(row), box_of(prev)
    if here is None or there is None:
        return out
    dx = (here[0] + here[2]) / 2.0 - (there[0] + there[2]) / 2.0
    dy = here[3] - there[3]
    out["box_foot_dx_px"] = "%.3f" % dx
    out["box_foot_dy_px"] = "%.3f" % dy
    out["box_l2_px"] = "%.3f" % ((dx * dx + dy * dy) ** 0.5)
    out["box_moved"] = int(here != there)
    age = 0
    while (index - age - 1 >= 0
           and position_of(track_rows[index - age - 1]) == position_of(row)):
        age += 1
    out["retained_position_age"] = age
    bage = 0
    while index - bage - 1 >= 0 and box_of(track_rows[index - bage - 1]) == here:
        bage += 1
    out["box_identical_age"] = bage
    return out


def homography_flags(parent: Path, keys: set) -> dict:
    """Read homography_valid for the selected keys from G402's raw tables."""
    flags: dict = {}
    sections = set((kind, section) for kind, section, _f, _p in keys)
    for kind, section in sorted(sections):
        path = parent / "raw_tables" / kind / section / "tracking_data.csv"
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                key = (kind, section, row.get("frame", ""),
                       row.get("player_id", ""))
                if key in keys:
                    flags[key] = row.get("homography_valid", "")
    return flags


def build(mask_rows: list, launch_rows: list, dims: dict) -> dict:
    """Return population, draw, and the per-row measurement table."""
    orders = draw_orders_from_launches(launch_rows)
    population: list = []
    draw: list = []
    for label in CLASSES:
        ticks = ordered_ticks(mask_rows, orders, label)
        for ordinal, tick in enumerate(ticks):
            population.append({"class": label, "ordinal": ordinal,
                               "draw_kind": tick[0], "section_id": tick[1],
                               "frame": tick[2], "population_n": len(ticks)})
        for j, tick in enumerate(exact_even(ticks)):
            draw.append({"class": label, "j": j, "draw_kind": tick[0],
                         "section_id": tick[1], "frame": tick[2]})
    linked = chain(mask_rows)
    selected = set((d["draw_kind"], d["section_id"], d["frame"]) for d in draw)
    per_row: list = []
    for (kind, section, pid), track_rows in sorted(linked["tracks"].items()):
        width, height = dims.get((kind, section), (0, 0))
        for index, row in enumerate(track_rows):
            tick = (kind, section, int(row["frame"]))
            if tick not in selected:
                continue
            box = box_of(row)
            foot = (archived_foot(box, width, max(0, height - TOPCUT))
                    if box else ("", "", ""))
            record = {
                "draw_kind": kind, "section_id": section, "frame": row["frame"],
                "player_id": pid, "position_source": row["position_source"],
                "source_branch": row["source_branch"],
                "matched_event_id": row["matched_event_id"],
                "x_position": row["x_position"], "y_position": row["y_position"],
                "bbox_x1": row["bbox_x1"], "bbox_y1": row["bbox_y1"],
                "bbox_x2": row["bbox_x2"], "bbox_y2": row["bbox_y2"],
                "native_width": width, "native_height": height,
                "topcut_px": TOPCUT,
                "detector_frame_height": max(0, height - TOPCUT),
                "archived_head_x": foot[0], "archived_foot_y": foot[1],
                "archived_foot_clipped": foot[2],
                "stored_box_bottom_minus_projected_foot_px": (
                    "%.3f" % (box[3] - foot[1]) if box else ""),
                "homography_valid": "",
            }
            record.update(retention(track_rows, index))
            record["role"] = "SELECTED"
            per_row.append(record)
            if index > 0:
                prior = dict(track_rows[index - 1])
                prior_box = box_of(prior)
                pfoot = (archived_foot(prior_box, width, max(0, height - TOPCUT))
                         if prior_box else ("", "", ""))
                per_row.append({
                    "draw_kind": kind, "section_id": section,
                    "frame": prior["frame"], "player_id": pid,
                    "position_source": prior["position_source"],
                    "source_branch": prior["source_branch"],
                    "matched_event_id": prior["matched_event_id"],
                    "x_position": prior["x_position"],
                    "y_position": prior["y_position"],
                    "bbox_x1": prior["bbox_x1"], "bbox_y1": prior["bbox_y1"],
                    "bbox_x2": prior["bbox_x2"], "bbox_y2": prior["bbox_y2"],
                    "native_width": width, "native_height": height,
                    "topcut_px": TOPCUT,
                    "detector_frame_height": max(0, height - TOPCUT),
                    "archived_head_x": pfoot[0], "archived_foot_y": pfoot[1],
                    "archived_foot_clipped": pfoot[2],
                    "stored_box_bottom_minus_projected_foot_px": (
                        "%.3f" % (prior_box[3] - pfoot[1]) if prior_box else ""),
                    "homography_valid": "",
                    **{k: "" for k in ("predecessor_frame", "position_retained",
                                       "box_moved", "box_foot_dx_px",
                                       "box_foot_dy_px", "box_l2_px",
                                       "retained_position_age",
                                       "box_identical_age")},
                    "predecessor_status": "IS_PREDECESSOR_OF_SELECTED",
                    "role": "PREDECESSOR"})
    return {"population": population, "draw": draw, "per_row": per_row}


def write_csv(path: Path, rows: list) -> None:
    """Write one delivered table with LF line endings and a stable header."""
    if not rows:
        path.write_text("", encoding="ascii", newline="")
        return
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(parent: str, out: str) -> None:
    """Build every landed-byte artifact under the G410 evidence directory."""
    src, dst = Path(parent), Path(out)
    dst.mkdir(parents=True, exist_ok=True)
    mask_rows = read_rows(src / "target_mask.csv")
    launch_rows = read_rows(src / "launch_receipts.csv")
    source_rows = read_rows(src / "source_receipts.csv")
    dims = {(r["draw_kind"], r["section_id"]): (int(r["width"]), int(r["height"]))
            for r in source_rows}
    hashes = []
    for name in ("target_mask.csv", "launch_receipts.csv", "source_receipts.csv",
                 "window_pts.csv", "summary.json", "prereg.md"):
        size, digest = sha256_of(src / name)
        hashes.append({"role": "g402_parent", "path": (src / name).as_posix(),
                       "bytes": size, "sha256": digest})
    write_csv(dst / "input_hashes.csv", hashes)
    built = build(mask_rows, launch_rows, dims)
    keys = set((r["draw_kind"], r["section_id"], str(r["frame"]),
                str(r["player_id"])) for r in built["per_row"])
    flags = homography_flags(src, keys)
    for record in built["per_row"]:
        record["homography_valid"] = flags.get(
            (record["draw_kind"], record["section_id"], str(record["frame"]),
             str(record["player_id"])), "RAW_ROW_NOT_FOUND")
    write_csv(dst / "population.csv", built["population"])
    write_csv(dst / "draw.csv", built["draw"])
    write_csv(dst / "per_row.csv", built["per_row"])
    launches = {(r["draw_kind"], r["section_id"]): r for r in launch_rows}
    receivers = {(r["draw_kind"], r["section_id"]): r for r in source_rows}
    queue = []
    for key in sorted(set((d["draw_kind"], d["section_id"]) for d in built["draw"]),
                      key=lambda k: (k[0], int(launches[k]["draw_order"]))):
        launch, receiver = launches[key], receivers[key]
        queue.append(chr(9).join([
            key[0], key[1], receiver["receiver_path"].replace(chr(92), "/"),
            receiver["receiver_sha256"], launch["start_frame"], launch["frames"],
            launch["source_path"]]))
    (dst / "replay_queue.tsv").write_text(chr(10).join(queue) + chr(10),
                                          encoding="ascii", newline="")
    classes: dict = {}
    for row in mask_rows:
        classes[row["position_source"]] = classes.get(row["position_source"], 0) + 1
    (dst / "premise.json").write_text(json.dumps({
        "mask_rows": len(mask_rows),
        "class_row_counts": classes,
        "sections_with_rows": len(set((r["draw_kind"], r["section_id"])
                                      for r in mask_rows)),
        "launches_complete": sum(1 for r in launch_rows
                                 if r.get("status") == "COMPLETE"),
        "retained_source_receipts": len(source_rows),
        "blank_route_labels": sum(1 for r in mask_rows
                                  if not str(r["source_branch"]).strip()),
        "selected_ticks": len(built["draw"]),
        "selected_rows": sum(1 for r in built["per_row"]
                             if r["role"] == "SELECTED"),
        "predecessor_rows": sum(1 for r in built["per_row"]
                                if r["role"] == "PREDECESSOR"),
    }, indent=2, sort_keys=True) + '\n', encoding="ascii", newline="")


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2])
