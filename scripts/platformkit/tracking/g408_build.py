"""Build G408 tables solely from the sealed exact G401 frame-PTS inputs."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

from scripts.platformkit.tracking import g408_argv, g408_tables
from scripts.platformkit.tracking.g408_stop import construct_cases

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/evidence/tracking/g408_pts_duration_stop_proposal_2026-09-11"
G401 = ROOT / "docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11"
PTS_DIR = EVIDENCE / "g401_frame_pts"
MANIFEST = EVIDENCE / "g401_frame_pts_manifest.csv"
DURATION = 100.0
WINDOW = 3

RECEIPT_FIELDS = ["draw_j", "source_name", "source_sha256", "source_bytes",
                  "source_path_at_rehash", "schedule_path", "schedule_sha256",
                  "schedule_pts_count", "duplicate_pts_steps", "dropped_frames",
                  "backwards_steps", "missing_count", "g401_digest_match",
                  "g401_duplicate_match", "g401_dropped_match", "validated_fps"]
LEGACY_RECEIPT_FIELDS = ["source_path", "sha256", "bytes", "codec_name",
                         "width", "height", "duration", "r_frame_rate",
                         "avg_frame_rate", "fps_basis", "pts_count",
                         "valid_count", "gap_steps", "median_step_s",
                         "first_pts", "last_pts", "monotonic", "frame_reader",
                         "packet_reader", "packet_count",
                         "packet_negative_count", "reader_exact_match",
                         "reader_max_abs_delta_s", "reader_disagreeing_frames",
                         "packet_duplicate_pts_steps", "packet_gap_steps",
                         "packet_dropped_frames", "arm_c_admitted_frames",
                         "arm_c_packet_admitted_frames",
                         "arm_c_reader_admitted_delta"]
RECEIPT_FIELDS += LEGACY_RECEIPT_FIELDS
ANOMALY_FIELDS = ["draw_j", "source_name", "frame_index", "kind",
                  "previous_pts_s", "pts_s", "step_s", "native_interval_s",
                  "dropped_ordinal"]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                    encoding="ascii", newline="\n")


def _write_csv(rows: list[dict], path: Path, fields: list[str]) -> str:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in fields} for row in rows)
    return _sha(path)


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="ascii", newline="") as handle:
        return list(csv.DictReader(handle))


def _anomalies(pts: list[float | None], fps: float, draw_j: int,
               name: str) -> tuple[dict[str, int], list[dict]]:
    """Use G401's unrounded interval classification and retain every event."""
    counts = {"duplicate_pts_steps": 0, "dropped_frames": 0,
              "backwards_steps": 0, "missing_count": 0}
    records: list[dict] = []
    previous: float | None = None
    interval = 1.0 / fps
    for index, value in enumerate(pts):
        if value is None:
            counts["missing_count"] += 1
            records.append(_anomaly(draw_j, name, index, "missing", previous,
                                    None, None, interval, ""))
            continue
        point = float(value)
        if previous is not None:
            step = point - previous
            rounded = round(step / interval)
            if step < 0:
                counts["backwards_steps"] += 1
                records.append(_anomaly(draw_j, name, index, "backward",
                                        previous, point, step, interval, ""))
            elif rounded == 0:
                counts["duplicate_pts_steps"] += 1
                records.append(_anomaly(draw_j, name, index, "duplicate",
                                        previous, point, step, interval, ""))
            elif rounded > 1:
                for ordinal in range(1, rounded):
                    counts["dropped_frames"] += 1
                    records.append(_anomaly(draw_j, name, index, "dropped",
                                            previous, point, step, interval,
                                            ordinal))
        previous = point
    return counts, records


def _anomaly(j: int, name: str, index: int, kind: str, previous: float | None,
             point: float | None, step: float | None, interval: float,
             ordinal: object) -> dict:
    return {"draw_j": j, "source_name": name, "frame_index": index,
            "kind": kind, "previous_pts_s": _fmt(previous),
            "pts_s": _fmt(point), "step_s": _fmt(step),
            "native_interval_s": _fmt(interval), "dropped_ordinal": ordinal}


def seal_inputs(receiver: Path = Path("C:/Users/neelj/g401_receiver")) -> None:
    """Copy and hash the exact retained G401 streams before any scoring pass."""
    PTS_DIR.mkdir(exist_ok=True)
    draw = _rows(G401 / "draw.csv")
    summaries = {row["source_name"]: row for row in _rows(G401 / "pts.csv")}
    selected = [summaries[row["source_name"]] for row in draw]
    _write_csv(selected, EVIDENCE / "g401_pts_rows.csv", list(selected[0]))
    manifest = []
    for row in draw:
        name = row["source_name"]
        source = receiver / "sources" / name
        schedule = receiver / "pts_cache" / (name + ".json")
        target = PTS_DIR / (name + ".json")
        digest, size = _hash_source(source)
        shutil.copyfile(schedule, target)
        manifest.append({"draw_j": row["draw_j"], "source_name": name,
                         "source_path_at_rehash": str(source),
                         "source_sha256": digest, "source_bytes": size,
                         "schedule_path": "g401_frame_pts/" + target.name,
                         "schedule_sha256": _sha(target),
                         "schedule_pts_count": len(json.loads(target.read_text())),
                         "validated_fps": row["validated_fps"]})
    _write_csv(manifest, MANIFEST, list(manifest[0]))


def _hash_source(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def build(out: Path) -> dict:
    """Write all reproducible cards and tables from the sealed evidence inputs."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "renders").mkdir(exist_ok=True)
    draw = _rows(G401 / "draw.csv")
    g401 = {row["source_name"]: row for row in _rows(G401 / "paired_caps.csv")}
    summaries = {row["source_name"]: row for row in _rows(EVIDENCE / "g401_pts_rows.csv")}
    legacy = {row["source_name"]: row for row in _rows(
        EVIDENCE / "pre_fix1b/source_receipts.csv")}
    sealed = {row["source_name"]: row for row in _rows(MANIFEST)}
    receipts, stops, indices, windows, eye, anomalies = [], [], [], [], [], []
    premise = {"arm_a_reaching_target_n": 0, "arm_b_reaching_target_n": 0,
               "g401_endpoint_matches": 0, "g401_digest_matches": 0}
    for draw_row in draw:
        name, j = draw_row["source_name"], int(draw_row["draw_j"])
        fps = float(draw_row["validated_fps"])
        meta = sealed[name]
        schedule_path = EVIDENCE / meta["schedule_path"]
        pts = json.loads(schedule_path.read_text(encoding="ascii"))
        counts, events = _anomalies(pts, fps, j, name)
        summary = summaries[name]
        arms = g408_tables.arm_rows(name, j, pts, fps, DURATION)
        receipt = {**legacy[name], **meta, **counts,
                   "g401_digest_match": meta["source_sha256"] == draw_row["digest"],
                   "g401_duplicate_match": str(counts["duplicate_pts_steps"])
                   == summary["duplicate_pts_steps"],
                   "g401_dropped_match": str(counts["dropped_frames"])
                   == summary["dropped_frames"]}
        receipts.append(receipt)
        anomalies.extend(events)
        stops.extend(arms)
        premise["g401_digest_matches"] += int(receipt["g401_digest_match"])
        premise["g401_endpoint_matches"] += int(_matches_g401(arms, g401[name]))
        premise["arm_a_reaching_target_n"] += int(_reaches(arms[0]))
        premise["arm_b_reaching_target_n"] += int(_reaches(arms[1]))
        for arm in arms:
            indices.append(_index_row(arm))
            windows.extend(_window_rows(arm, pts, j, name))
        card = _card(name, j, arms, receipt)
        path = out / "renders" / ("j%02d_%s.txt" % (j, name[:-4]))
        path.write_text(card, encoding="ascii", newline="\n")
        eye.append({"draw_j": j, "source_name": name,
                    "render": "renders/" + path.name, "bytes": path.stat().st_size,
                    "sha256": _sha(path)})
    digests = {"source_receipts.csv": _write_csv(receipts, out / "source_receipts.csv", RECEIPT_FIELDS),
               "pts_anomalies.csv": _write_csv(anomalies, out / "pts_anomalies.csv", ANOMALY_FIELDS),
               "paired_stops.csv": _write_csv(stops, out / "paired_stops.csv", g408_tables.STOP_FIELDS),
               "admitted_indices.csv": _write_csv(indices, out / "admitted_indices.csv", list(indices[0])),
               "decoded_pts.csv": _write_csv(windows, out / "decoded_pts.csv", list(windows[0])),
               "eye_index.csv": _write_csv(eye, out / "eye_index.csv", list(eye[0]))}
    controls = construct_cases()
    control_rows = [_control_row(row) for row in controls]
    digests["construct_cases.csv"] = _write_csv(control_rows, out / "construct_cases.csv", list(control_rows[0]))
    _write_json(out / "argv_fixtures.json", {"cases": g408_argv.fixtures(), "legacy_frame_cap": 3000})
    _write_json(out / "source_hashes.json", {row["source_name"]: row["source_sha256"] for row in receipts})
    digests["argv_fixtures.json"] = _sha(out / "argv_fixtures.json")
    digests["source_hashes.json"] = _sha(out / "source_hashes.json")
    summary = {"gap": "G408", "draw_n": len(draw), "duration_seconds": DURATION,
               "construct_n": len(controls), "construct_matching_declared_n": sum(bool(x["matches_declared"]) for x in controls),
               "anomaly_rows_n": len(anomalies), "proposal_applied_anywhere": False,
               **premise, **g408_tables.arm_c_bar(stops)}
    return {"summary": summary, "digests": digests, "eye_rows": eye}


def _reaches(arm: dict) -> bool:
    boundary = arm["first_excluded_pts"]
    first = arm["last_admitted_pts"]
    if boundary == "" or first == "":
        return False
    return abs(float(boundary) - DURATION) <= float(arm["native_frame_interval_s"])


def _matches_g401(arms: list[dict], landed: dict) -> bool:
    return (float(arms[0]["last_admitted_pts"]) == float(landed["arm_a_last_admitted_pts"])
            and float(arms[1]["first_excluded_pts"]) == float(landed["arm_b_first_excluded_pts"])
            and str(arms[1]["frame_cap"]) == landed["arm_b_frame_cap"])


def _index_row(arm: dict) -> dict:
    first, last = arm["first_admitted_index"], arm["last_admitted_index"]
    text = ",".join(str(i) for i in range(first, last + 1)) if first != "" else ""
    return {"source_name": arm["source_name"], "arm": arm["arm"],
            "admitted_frames": arm["admitted_frames"],
            "first_admitted_index": first, "last_admitted_index": last,
            "contiguous": first == "" or int(last) - int(first) + 1
            == int(arm["admitted_frames"]),
            "admitted_index_list_sha256": hashlib.sha256(
                text.encode("ascii")).hexdigest(),
            "termination_reason": arm["termination_reason"], "draw_j": arm["draw_j"]}


def _window_rows(arm: dict, pts: list, j: int, name: str) -> list[dict]:
    rows = []
    for label, centre in (("last_admitted", arm["last_admitted_index"]), ("first_excluded", arm["first_excluded_index"])):
        if centre == "":
            continue
        for index in range(max(0, centre - WINDOW), min(len(pts), centre + WINDOW + 1)):
            rows.append({"draw_j": j, "source_name": name, "arm": arm["arm"], "endpoint": label, "frame_index": index, "pts_s": _fmt(pts[index]), "offset_from_endpoint": index - centre})
    return rows


def _control_row(row: dict) -> dict:
    return {**row, "pts": json.dumps(row["pts"]), "declared_admitted_indices": json.dumps(row["declared_admitted_indices"]), "expected_admitted_indices": json.dumps(row["expected_admitted_indices"]), "declared_unknown_reason": row["declared_unknown_reason"] or "", "expected_unknown_reason": row["expected_unknown_reason"] or "", "first_boundary_index": row["first_boundary_index"] or ""}


def _card(name: str, j: int, arms: list[dict], receipt: dict) -> str:
    lines = ["G408 timeline card j%02d  %s" % (j, name), "sha256 %s  bytes %s" % (receipt["source_sha256"], receipt["source_bytes"]), "duplicate_pts_steps %s  dropped_frames %s  backwards_steps %s  missing_count %s" % tuple(receipt[key] for key in ("duplicate_pts_steps", "dropped_frames", "backwards_steps", "missing_count")), "", "arm                        cap   admitted  last_pts     first_excl_pts  inherited_extent  last_gap     reason"]
    for arm in arms:
        lines.append("%-26s %-5s %-9s %-12s %-16s %-17s %-12s %s" % (arm["arm"], arm["frame_cap"] or "-", arm["admitted_frames"], arm["last_admitted_pts"], arm["first_excluded_pts"] or "-", arm["first_boundary_extent_s"], arm["last_admitted_gap_s"], arm["termination_reason"]))
    return "\n".join(lines) + "\n"


def _fmt(value: object) -> str:
    return "" if value is None else "%.6f" % float(value)


if __name__ == "__main__":
    if sys.argv[1:] == ["--seal-inputs"]:
        seal_inputs()
    else:
        result = build(Path(sys.argv[1]))
        print(json.dumps(result["summary"], sort_keys=True))
