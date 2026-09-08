"""G336 harness-only association and evaluator-record utilities."""
from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from scipy.optimize import linear_sum_assignment

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.tracking.g310_instance_key import split_instances

MAX_COST, MAX_AGE = 0.75, 30
# The prereg's per-tick fragmentation contribution is new instances / SLOTS, which the
# unbounded candidate can push above 1. cpcv_evaluate guards its predictor to [0,1], so
# ticks enter the evaluator divided by the fixed TICK_SCALE and are multiplied back out
# unchanged on read; no value is clamped and no ordering changes.
SLOTS, TICK_SCALE = 10, 100.0


def bbox_iou(a: list[float], b: list[float]) -> float:
    """Return IoU for xyxy boxes."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if not inter:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (area_a + area_b - inter)


def cosine(a: list[float], b: list[float]) -> float:
    """Return cosine similarity, or zero for a degenerate signature."""
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _cost(track: dict, det: dict) -> float:
    return 0.75 * (1.0 - bbox_iou(track["bbox"], det["bbox"])) + 0.25 * (
        1.0 - cosine(track["sig"], det["sig"])
    )


def associate(detections: list[dict], max_cost: float = MAX_COST,
              max_age: int = MAX_AGE) -> list[dict]:
    """Assign unbounded, team-separated ids to fixed detector observations."""
    active: dict[tuple[str, str], dict[int, dict]] = defaultdict(dict)
    next_id: dict[tuple[str, str], int] = defaultdict(lambda: 1)
    out: list[dict] = []
    by_frame: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for det in detections:
        by_frame[(det["section"], int(det["frame"]))].append(det)
    for (section, frame), frame_dets in sorted(by_frame.items()):
        for team in sorted({d["team"] for d in frame_dets}):
            key_team = (section, team)
            tracks = active[key_team]
            tracks = {key: value for key, value in tracks.items()
                      if frame - value["frame"] <= max_age}
            active[key_team] = tracks
            dets = [d for d in frame_dets if d["team"] == team]
            ids = sorted(tracks)
            accepted: set[int] = set()
            if ids and dets:
                matrix = [[_cost(tracks[key], det) for det in dets] for key in ids]
                rows, cols = linear_sum_assignment(matrix)
                for row, col in zip(rows, cols):
                    if matrix[row][col] <= max_cost:
                        key, det = ids[row], dets[col]
                        tracks[key] = {"bbox": det["bbox"], "sig": det["sig"], "frame": frame}
                        out.append({**det, "instance_id": key, "new_instance": 0})
                        accepted.add(col)
            for index, det in enumerate(dets):
                if index not in accepted:
                    key = next_id[key_team]
                    next_id[key_team] += 1
                    tracks[key] = {"bbox": det["bbox"], "sig": det["sig"], "frame": frame}
                    out.append({**det, "instance_id": key, "new_instance": 1})
    return sorted(out, key=lambda row: (row["section"], int(row["frame"]), row["team"], row["instance_id"]))


def baseline_instances(rows: list[dict], source_height: int, section: str) -> list[dict]:
    """Return G310-keyed production-slot observations for one section."""
    out: list[dict] = []
    for number, group in enumerate(split_instances(rows, source_height), start=1):
        for index, row in enumerate(group):
            sig = [float(row.get("sig0", 0)), float(row.get("sig1", 0)), float(row.get("sig2", 0))]
            out.append({"section": section, "frame": int(float(row["frame"])),
                        "team": row.get("team", "unknown"), "instance_id": number,
                        "bbox": [float(row[key]) for key in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")],
                        "sig": sig, "new_instance": int(index == 0)})
    return out


def _lengths(records: list[dict]) -> list[int]:
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in records:
        grouped[(row["team"], int(row["instance_id"]))].append(row)
    return [len(group) for group in grouped.values()]


def _p90(values: list[int]) -> float | None:
    if not values:
        return None
    return sorted(values)[math.ceil(0.9 * len(values)) - 1]


def switch_proxy(records: list[dict]) -> int:
    """Count next-frame cross-instance end/start pairs whose centres are <=3 px apart."""
    first, last = {}, {}
    for row in records:
        key = (row["team"], int(row["instance_id"]))
        first.setdefault(key, row)
        last[key] = row
    count = 0
    for end_key, end in last.items():
        ex, ey = (end["bbox"][0] + end["bbox"][2]) / 2, (end["bbox"][1] + end["bbox"][3]) / 2
        for start_key, start in first.items():
            if start_key == end_key or start["team"] != end["team"] or int(start["frame"]) != int(end["frame"]) + 1:
                continue
            sx, sy = (start["bbox"][0] + start["bbox"][2]) / 2, (start["bbox"][1] + start["bbox"][3]) / 2
            if math.hypot(ex - sx, ey - sy) <= 3.0:
                count += 1
    return count


def appearance(records: list[dict]) -> tuple[float | None, float | None]:
    """Return mean within-instance and between-instance signature cosine."""
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in records:
        grouped[(row["team"], int(row["instance_id"]))].append(row)
    within = [cosine(a["sig"], b["sig"]) for rows in grouped.values()
              for a, b in zip(rows, rows[1:])]
    heads = [rows[0] for rows in grouped.values()]
    between = [cosine(a["sig"], b["sig"]) for i, a in enumerate(heads) for b in heads[i + 1:]
               if a["team"] == b["team"]]
    return (statistics.mean(within) if within else None,
            statistics.mean(between) if between else None)


def metrics(records: list[dict], evaluated_frames: int, raw_detections: list[dict],
            runtime_ms: float) -> dict:
    """Compute G336 label-free metrics for one arm and named denominator."""
    lengths = _lengths(records)
    within, between = appearance(records)
    over_ten = len({(r["section"], int(r["frame"])) for r in raw_detections
                    if sum(1 for x in raw_detections if x["section"] == r["section"] and x["frame"] == r["frame"]) > 10})
    return {"instances": len(lengths), "fragmentation_ratio": len(lengths) / (evaluated_frames * 10),
            "median_instance_len": statistics.median(lengths) if lengths else None,
            "p90_instance_len": _p90(lengths), "switch_proxy": switch_proxy(records),
            "within_cosine": within, "between_cosine": between,
            "over_ten_share": over_ten / evaluated_frames, "runtime_ms_per_frame": runtime_ms / evaluated_frames,
            "n_records": len(records), "n_frames": evaluated_frames}


def evaluate_ticks(section: str, frames: list[int], baseline_starts: dict[int, int],
                   candidate_starts: dict[int, int], section_index: int) -> list[dict]:
    """Archive one CPCV evaluator record pair per stable scored tick."""
    base = datetime(2026, 8, 1) + timedelta(days=section_index * 3)
    states = []
    for rank, frame in enumerate(sorted(frames)):
        stamp = base + timedelta(seconds=rank + 1)
        states.append({"game_id": f"{section}:{frame}", "state_ts": stamp.isoformat(), "home": section,
                       "away": "g336", "outcome": 0,
                       "devig_close_prob": baseline_starts.get(frame, 0) / TICK_SCALE,
                       "features": {"baseline": baseline_starts.get(frame, 0) / TICK_SCALE,
                                    "candidate": candidate_starts.get(frame, 0) / TICK_SCALE},
                       "feature_avail": {"baseline": (stamp - timedelta(seconds=1)).isoformat(),
                                         "candidate": (stamp - timedelta(seconds=1)).isoformat()},
                       "section_group": section})
    return states


def evaluator_records(states: list[dict]) -> list[dict]:
    """Run symmetric-embargo CPCV once per arm over the same tick states."""
    groups = len({state["section_group"] for state in states})
    def arm(name):
        return cpcv_evaluate(states, lambda train, test, inside: test["features"][name],
                             n_groups=groups, n_test_groups=1, embargo_days=1,
                             group_key="section_group", guard_state_keys=True)
    base = {r["game_id"]: r for r in arm("baseline")}
    cand = {r["game_id"]: r for r in arm("candidate")}
    factor = TICK_SCALE / SLOTS
    return [{"tick_key": key, "baseline_loss": base[key]["p_model"] * factor,
             "candidate_loss": cand[key]["p_model"] * factor,
             "n_train": base[key]["n_train"]} for key in sorted(base)]


def _cell(value):
    """Artifact cell convention: 6 decimal places trimmed, an integer result padded to 6.

    This is the convention the earlier committed G336 artifacts already used; it lives
    in code now so the padding is reproducible from the harness, not applied by hand.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    text = ("%.6f" % value).rstrip("0").rstrip(".")
    return text if "." in text else text.zfill(6)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    """Write an LF CSV with a fixed schema and the padded numeric-cell convention."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: _cell(v) for k, v in row.items()} for row in rows)
