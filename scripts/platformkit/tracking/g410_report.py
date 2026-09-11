"""G410 same-invocation contract checks over the observer replay trace.
Every value compared here comes from ONE observed invocation: the matrices the
archived detector multiplied, the box it stored, and the court point it stored,
all captured inside the same call.  No second run supplies identity.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import numpy as np
from scripts.platformkit.tracking.g410_contract import (
    classify, exact_values_equal, native_to_cropped, project_homogeneous,
)
from scripts.platformkit.tracking.g410_measure import (
    MAX_2D_JUMP, PAD, TOPCUT, write_csv,
)
TRACE_TAGS = ("M", "B", "P")
def parse_trace(path: Path) -> dict:
    """Parse one observer trace into per-tick matrices and pre/post slot state."""
    mats: dict = {}
    pre: dict = {}
    post: dict = {}
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        if not line:
            continue
        parts = line.split(",")
        tag = parts[0]
        if tag == "M":
            tick = int(parts[1])
            mats[tick] = {
                "M": [float(v) for v in parts[2:11]],
                "M1": [float(v) for v in parts[11:20]],
                "frame_w": int(parts[20]), "frame_h": int(parts[21]),
                "map_w": int(parts[22]), "map_h": int(parts[23]),
            }
        elif tag in ("B", "P"):
            tick, slot = int(parts[1]), int(parts[2])
            box = parts[5:9]
            pos = parts[9:11]
            record = {
                "player_id": parts[3], "team": parts[4],
                "box": [float(v) for v in box] if all(v != "" for v in box) else None,
                "pos": [float(v) for v in pos] if all(v != "" for v in pos) else None,
            }
            (pre if tag == "B" else post)[(tick, slot)] = record
    return {"matrices": mats, "pre": pre, "post": post}
def archived_projection(box_yxyx, frame_w: int, frame_h: int, mat: dict):
    """Reproduce the archived foot and its projection from ONE stored box.

    advanced_tracker.py:1336 stores (y1-PAD, x1-PAD, y2+PAD, x2+PAD) and
    line 1410 projects ((x1c+x2c)//2, y2c) from the CLIPPED, UNPADDED box;
    line 1427 truncates the homogeneous quotient with numpy int32.
    """
    stored_y1, stored_x1, stored_y2, stored_x2 = box_yxyx
    x1c = max(0, int(stored_x1 + PAD))
    x2c = min(int(frame_w), int(stored_x2 - PAD))
    y2c = min(int(frame_h), int(stored_y2 - PAD))
    head_x, foot_y = (x1c + x2c) // 2, y2c
    matrix = (np.array(mat["M1"], dtype=np.float64).reshape(3, 3)
              @ np.array(mat["M"], dtype=np.float64).reshape(3, 3))
    projected = project_homogeneous(matrix.tolist(), (head_x, foot_y), "native")
    trunc = np.int32([projected.x, projected.y])
    return {"head_x": head_x, "foot_y": foot_y,
            "projected_x": int(trunc[0]), "projected_y": int(trunc[1]),
            "clipped": int(x1c != int(stored_x1 + PAD)
                           or x2c != int(stored_x2 - PAD)
                           or y2c != int(stored_y2 - PAD))}
def back_project(mat: dict, position) -> tuple:
    """Return the image point that maps to one stored court point, or None."""
    matrix = (np.array(mat["M1"], dtype=np.float64).reshape(3, 3)
              @ np.array(mat["M"], dtype=np.float64).reshape(3, 3))
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return None
    vec = inverse @ np.array([float(position[0]), float(position[1]), 1.0])
    if vec[2] == 0.0:
        return None
    return (float(vec[0] / vec[2]), float(vec[1] / vec[2]))
def derive_branch(observed, expected, prior, guard: float) -> str:
    """Reproduce the archived branch test from one invocation's own values.

    advanced_tracker.py:636 keeps the previous point when the freshly projected
    point is more than MAX_2D_JUMP * stride court pixels away; the remaining
    unmoved fresh write is the SUBPIXEL case (g380_provenance.resolve_emitted).
    """
    fresh = exact_values_equal(observed, expected)
    held = prior is not None and exact_values_equal(observed, prior)
    if fresh and not held:
        return "DETECTION_FRESH_BOX"
    if fresh and held:
        return "SUBPIXEL_UNMOVED_FRESH_WRITE"
    if held:
        distance = ((expected[0] - prior[0]) ** 2
                    + (expected[1] - prior[1]) ** 2) ** 0.5
        return ("CLAMP_GUARD_REPRODUCED" if distance > guard
                else "RETAINED_WITHOUT_GUARD")
    return "NON_BOX_WRITE"
def check_section(kind: str, section: str, trace: dict, ticks: set,
                  labels: dict, stride: int = 3) -> tuple:
    """Classify every observed slot at the selected ticks of one section."""
    rows, unknowns, matrices = [], [], []
    prev_pos: dict = {}
    for tick in sorted(trace["matrices"]):
        mat = trace["matrices"][tick]
        if tick in ticks:
            matrices.append({"draw_kind": kind, "section_id": section,
                             "frame": tick, **mat})
        for (t, slot), post in sorted(trace["post"].items()):
            if t != tick:
                continue
            pre = trace["pre"].get((tick, slot))
            if post["box"] is None or post["pos"] is None:
                if tick in ticks and not (post["box"] is None and post["pos"] is None):
                    unknowns.append({"draw_kind": kind, "section_id": section,
                                     "frame": tick, "slot": slot,
                                     "reason": ("NO_STORED_POSITION" if post["pos"]
                                                is None else "NO_STORED_BOX")})
                continue
            trace_arch = archived_projection(post["box"], mat["frame_w"],
                                             mat["frame_h"], mat)
            stored_box = None if pre is None else pre["box"]
            stored_arch = (None if stored_box is None else archived_projection(
                stored_box, mat["frame_w"], mat["frame_h"], mat))
            observed = [int(post["pos"][0]), int(post["pos"][1])]
            trace_expected = [trace_arch["projected_x"], trace_arch["projected_y"]]
            stored_expected = (None if stored_arch is None else [
                stored_arch["projected_x"], stored_arch["projected_y"]])
            last = prev_pos.get(slot)
            age = int(last is not None and exact_values_equal(observed, last[1]))
            prev_pos[slot] = (age, observed)
            if tick in ticks:
                label = labels.get((kind, section, tick, post["player_id"]), "")
                derived = ("RETAINED_PRIOR_POSITION" if age > 0
                           else ("FRESH_BOX_PROJECTION"
                                 if exact_values_equal(observed, trace_expected)
                                 else "FRESH_NON_BOX_POSITION"))
                prior_value = None if last is None else last[1]
                guard = MAX_2D_JUMP * max(1, stride)
                jump = ("" if prior_value is None else "%.3f" % (
                    (trace_expected[0] - prior_value[0]) ** 2
                    + (trace_expected[1] - prior_value[1]) ** 2) ** 0.5)
                trace_branch = derive_branch(observed, trace_expected, prior_value, guard)
                stored_branch = ("" if stored_expected is None else derive_branch(
                    observed, stored_expected, prior_value, guard))
                back = back_project(mat, observed)
                rows.append({
                    "draw_kind": kind, "section_id": section, "frame": tick,
                    "slot": slot, "player_id": post["player_id"],
                    "landed_position_source": label,
                    "derived_same_invocation_state": derived,
                    "derived_branch": trace_branch,
                    "stored_box_derived_branch": stored_branch,
                    "trace_box_derived_branch": trace_branch,
                    "current_box_projection_minus_prior_position_px": jump,
                    "branch_guard_px": MAX_2D_JUMP * max(1, stride),
                    "stored_box_y1": post["box"][0], "stored_box_x1": post["box"][1],
                    "stored_box_y2": post["box"][2], "stored_box_x2": post["box"][3],
                    "pre_call_box_y2": ("" if pre is None or pre["box"] is None
                                        else pre["box"][2]),
                    "stored_pre_call_box_y1": "" if stored_box is None else stored_box[0],
                    "stored_pre_call_box_x1": "" if stored_box is None else stored_box[1],
                    "stored_pre_call_box_y2": "" if stored_box is None else stored_box[2],
                    "stored_pre_call_box_x2": "" if stored_box is None else stored_box[3],
                    "stored_box_projection_x": "" if stored_expected is None else stored_expected[0],
                    "stored_box_projection_y": "" if stored_expected is None else stored_expected[1],
                    "trace_box_projection_x": trace_expected[0],
                    "trace_box_projection_y": trace_expected[1],
                    "archived_head_x": trace_arch["head_x"],
                    "archived_foot_y": trace_arch["foot_y"],
                    "archived_foot_clipped": trace_arch["clipped"],
                    "observed_x": observed[0], "observed_y": observed[1],
                    "expected_x": trace_expected[0], "expected_y": trace_expected[1],
                    "position_equals_current_box_projection":
                        int(exact_values_equal(observed, trace_expected)),
                    "position_equals_prior_evaluated_tick": age,
                    "backprojected_image_x": ("" if back is None else "%.3f" % back[0]),
                    "backprojected_image_y": ("" if back is None else "%.3f" % back[1]),
                    "backprojected_minus_archived_foot_y":
                        ("" if back is None else "%.3f" % (back[1] - trace_arch["foot_y"])),
                    "backprojection_inside_stored_box":
                        ("" if back is None else int(
                            post["box"][1] <= back[0] <= post["box"][3]
                            and post["box"][0] <= back[1] <= post["box"][2])),
                    "frame_w": mat["frame_w"], "frame_h": mat["frame_h"],
                    "map_w": mat["map_w"], "map_h": mat["map_h"],
                    "classification_reason": ("NO_PRE_CALL_STORED_BOX"
                                              if stored_box is None else ""),
                    "classification": classify(
                        stored_branch, trace_branch, observed, trace_expected,
                        stored_box, post["box"], age),
                })
    return rows, unknowns, matrices


def construct_cases() -> list:
    """CONSTRUCT control: synthetic boxes and a known matrix through the chain."""
    cases = []
    mats = {
        "identity": [1, 0, 0, 0, 1, 0, 0, 0, 1],
        "scale_translate": [2.0, 0, 100.0, 0, 3.0, -50.0, 0, 0, 1],
        "projective": [1.4, 0.2, 30.0, -0.1, 1.9, 12.0, 0.0002, 0.0001, 1.0],
    }
    boxes = {
        "interior": (185, 285, 457, 415),
        "left_clipped": (185, -20, 457, 120),
        "bottom_clipped": (900, 285, 1100, 415),
    }
    for mat_name, flat in sorted(mats.items()):
        for box_name, box in sorted(boxes.items()):
            mat = {"M": flat, "M1": [1, 0, 0, 0, 1, 0, 0, 0, 1]}
            arch = archived_projection(box, 1920, 1080, mat)
            stored_foot = project_homogeneous(
                np.array(flat, dtype=np.float64).reshape(3, 3).tolist(),
                ((box[1] + box[3]) / 2.0, box[2]), "native")
            flat3 = np.array(flat, dtype=np.float64).reshape(3, 3).tolist()
            native_foot = (arch["head_x"], arch["foot_y"] + TOPCUT)
            from_native = project_homogeneous(flat3, native_foot, "native")
            round_trip = native_to_cropped(native_foot, (0, TOPCUT))
            cases.append({
                "matrix": mat_name, "box": box_name,
                "topcut_origin_y": TOPCUT,
                "native_frame_foot_y": native_foot[1],
                "projected_from_native_foot_x": int(np.int32(from_native.x)),
                "projected_from_native_foot_y": int(np.int32(from_native.y)),
                "native_to_cropped_round_trip_ok": int(
                    round_trip == (float(arch["head_x"]), float(arch["foot_y"]))),
                "stored_y1": box[0], "stored_x1": box[1],
                "stored_y2": box[2], "stored_x2": box[3],
                "archived_head_x": arch["head_x"], "archived_foot_y": arch["foot_y"],
                "archived_foot_clipped": arch["clipped"],
                "archived_projected_x": arch["projected_x"],
                "archived_projected_y": arch["projected_y"],
                "stored_box_foot_projected_x": int(np.int32(stored_foot.x)),
                "stored_box_foot_projected_y": int(np.int32(stored_foot.y)),
                "stored_bottom_minus_archived_foot_px": box[2] - arch["foot_y"],
                "crop_origin_x": 0, "crop_origin_y": 0,
                "declared_input_frame": "native_decoded_pixels",
            })
    return cases


def main(traces_dir: str, per_row_csv: str, out_dir: str) -> None:
    """Write matrices, branch trace, contract checks, unknowns and constructs."""
    traces, out = Path(traces_dir), Path(out_dir)
    per_row = list(csv.DictReader(open(per_row_csv, newline="", encoding="ascii")))
    ticks: dict = {}
    labels: dict = {}
    for row in per_row:
        if row.get("role") != "SELECTED":
            continue
        key = (row["draw_kind"], row["section_id"])
        ticks.setdefault(key, set()).add(int(row["frame"]))
        labels[(row["draw_kind"], row["section_id"], int(row["frame"]),
                row["player_id"])] = row["position_source"]
    checks, unknowns, matrices = [], [], []
    covered = []
    for (kind, section), selected in sorted(ticks.items()):
        path = traces / ("%s.trace.txt" % section)
        if not path.exists() or path.stat().st_size == 0:
            for frame in sorted(selected):
                unknowns.append({"draw_kind": kind, "section_id": section,
                                 "frame": frame, "slot": "",
                                 "reason": "NO_OBSERVER_REPLAY_TRACE"})
            continue
        trace = parse_trace(path)
        observed_ticks = sorted(trace["matrices"])
        steps = [b - a for a, b in zip(observed_ticks, observed_ticks[1:])]
        stride = min(steps) if steps else 3
        rows, miss, mats = check_section(kind, section, trace, selected, labels,
                                         stride)
        missing = selected - set(trace["matrices"])
        for frame in sorted(missing):
            unknowns.append({"draw_kind": kind, "section_id": section,
                             "frame": frame, "slot": "",
                             "reason": "TICK_NOT_EVALUATED_IN_REPLAY"})
        checks.extend(rows)
        unknowns.extend(miss)
        matrices.extend(mats)
        covered.append(section)
    write_csv(out / "contract_checks.csv", checks)
    write_csv(out / "unknowns.csv", unknowns)
    write_csv(out / "construct_cases.csv", construct_cases())
    with (out / "matrices.jsonl").open("w", encoding="ascii", newline="") as handle:
        for record in matrices:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    with (out / "branch_trace.jsonl").open("w", encoding="ascii", newline="") as handle:
        for record in checks:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    print("checks=%d unknowns=%d sections_covered=%d"
          % (len(checks), len(unknowns), len(covered)))


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], sys.argv[3])
