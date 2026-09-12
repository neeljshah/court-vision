"""Build the G409 coordinate-cause evidence tables from sealed inputs.

Every table is bounded to the sealed 60 ticks. No coordinate is fitted: the
only transform applied is the integer crop origin read out of the archived
producer source.
"""
from __future__ import annotations

import csv
import hashlib
import statistics as stats
from pathlib import Path

from scripts.platformkit.tracking.g409_prepare import require_absolute_window, retain_silence
from scripts.platformkit.tracking.g409_transforms import as_fraction_box, uncrop_xyxy

ROOT = Path(__file__).resolve().parents[3]
G402 = ROOT / "docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11"
G406 = ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11"
OUT = ROOT / "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12"
RECEIVER = Path("C:/Users/neelj/g402_receiver")
FRAMES = Path("C:/Users/neelj/g406_frames")
TOPCUT = 60


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            total += len(chunk)
    return total, digest.hexdigest()


def sha256_lf(path: Path) -> str:
    """Digest of the LF-normalized bytes.

    This worktree has core.autocrlf=true, so text files materialize with CRLF
    while every sealed digest was taken over LF bytes. Both are reported.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def centre(row: dict, prefix: str = "bbox_") -> tuple[float, float]:
    return (
        (float(row[prefix + "x1"]) + float(row[prefix + "x2"])) / 2.0,
        (float(row[prefix + "y1"]) + float(row[prefix + "y2"])) / 2.0,
    )


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct / 100.0
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 2)


EXPECTED = {
    "target_mask.csv": "c2c4f57a56330afbc9a7772b61743864aa04d746d9715e0374743e724a79dc71",
    "g402_eye_index.csv": "d0019a5b0460cca99fe5afade3e414173c104eba5997fc1683f43d1de2bcd436",
    "g406_summary.json": "734e2ed8f092942a86c68b64dfaaf8047dfe84a63b551a37ade2ef97c9d70e0f",
}


def build_input_hashes() -> list[dict]:
    named = [
        (G402 / "target_mask.csv", EXPECTED["target_mask.csv"]),
        (G402 / "eye_index.csv", EXPECTED["g402_eye_index.csv"]),
        (G406 / "summary.json", EXPECTED["g406_summary.json"]),
    ]
    extra = [
        G402 / "launch_receipts.csv", G402 / "route_hashes.json", G402 / "window_pts.csv",
        G406 / "all_masked_rows.csv", G406 / "comparator_detections.csv",
        G406 / "associations.csv", G406 / "eye_index.csv", G406 / "frame_receipts.csv",
        G406 / "source_receipts.csv", G406 / "adjudications.csv", G406 / "per_tick.csv",
        G406 / "draw.csv", G406 / "frozen_args.json", G406 / "window_accounting.csv",
        OUT / "prereg.md",
    ]
    rows = []
    for path, expected in named + [(p, "") for p in extra]:
        rel = path.relative_to(ROOT).as_posix()
        if not path.exists():
            rows.append({"path": rel, "bytes": "", "sha256_on_disk": "ABSENT-IN-WORKTREE",
                         "sha256_lf": "ABSENT-IN-WORKTREE", "expected_sha256": expected,
                         "expected_match_lf": "0" if expected else ""})
            continue
        size, digest = sha256_file(path)
        lf = sha256_lf(path)
        rows.append({"path": rel, "bytes": size, "sha256_on_disk": digest, "sha256_lf": lf,
                     "expected_sha256": expected,
                     "expected_match_lf": ("1" if lf == expected else "0") if expected else ""})
    return rows


def build_source_receipts() -> list[dict]:
    rows = []
    for src in read_csv(G406 / "source_receipts.csv"):
        path = RECEIVER / Path(src["receiver_path"].replace("\\", "/")).name
        base = {"section_id": src["section_id"], "draw_kind": src["draw_kind"],
                "receiver_path": path.as_posix(), "g406_sha256": src["source_sha256"],
                "width": src["width"], "height": src["height"],
                "avg_fps": src["avg_fps"], "codec_name": src["codec_name"]}
        if not path.exists():
            rows.append(dict(base, receiver_bytes="", g409_rehash_sha256="ABSENT-IN-WORKTREE",
                             rehash_equal="0", status="ABSENT"))
            continue
        size, digest = sha256_file(path)
        rows.append(dict(base, receiver_bytes=size, g409_rehash_sha256=digest,
                         rehash_equal="1" if digest == src["source_sha256"] else "0",
                         status="RETAINED" if digest == src["source_sha256"] else "MISMATCH"))
    return rows


def build_draw() -> list[dict]:
    launch = {(r["draw_kind"], r["section_id"]): r for r in read_csv(G402 / "launch_receipts.csv")}
    rows = []
    for row in read_csv(G406 / "eye_index.csv"):
        rec = launch[(row["draw_kind"], row["section_id"])]
        start = int(rec["start_frame"])
        cap = start + int(rec["frames"])
        frame = require_absolute_window(int(row["frame"]), start, cap)
        rows.append({"card_id": row["card_id"], "draw_kind": row["draw_kind"],
                     "section_id": row["section_id"], "frame": frame,
                     "sealed_start_frame": start, "sealed_end_frame_exclusive": cap,
                     "sealed_ordinal": row["sealed_ordinal"],
                     "native_width": row["native_width"], "native_height": row["native_height"],
                     "source_sha256": rec["source_sha256"],
                     "draw_formula": "frozen G406 draw reused verbatim; no redraw"})
    return rows


def build_residuals() -> tuple[list[dict], dict]:
    rows = {r["box_id"]: r for r in read_csv(G406 / "all_masked_rows.csv")}
    dets = {r["det_id"]: r for r in read_csv(G406 / "comparator_detections.csv")}
    pairs = [r for r in read_csv(G406 / "associations.csv")
             if (r["left_set"], r["right_set"]) == ("producer", "comparator")]
    out = []
    for pair in pairs:
        prod, det = rows[pair["left_id"]], dets[pair["right_id"]]
        stored = as_fraction_box((prod["bbox_x1"], prod["bbox_y1"],
                                  prod["bbox_x2"], prod["bbox_y2"]))
        mapped = uncrop_xyxy(stored, 0, TOPCUT)
        px, py = centre(prod)
        mx = float((mapped[0] + mapped[2]) / 2)
        my = float((mapped[1] + mapped[3]) / 2)
        cx, cy = centre(det)
        out.append({
            "pair_id": pair["left_id"] + "#" + pair["right_id"], "card_id": pair["card_id"],
            "frame": prod["frame"], "position_source": prod["position_source"], "iou": pair["iou"],
            "stored_x1": prod["bbox_x1"], "stored_y1": prod["bbox_y1"],
            "stored_x2": prod["bbox_x2"], "stored_y2": prod["bbox_y2"],
            "mapped_x1": float(mapped[0]), "mapped_y1": float(mapped[1]),
            "mapped_x2": float(mapped[2]), "mapped_y2": float(mapped[3]),
            "comparator_x1": det["bbox_x1"], "comparator_y1": det["bbox_y1"],
            "comparator_x2": det["bbox_x2"], "comparator_y2": det["bbox_y2"],
            "dx_before": round(px - cx, 4), "dy_before": round(py - cy, 4),
            "dx_after": round(mx - cx, 4), "dy_after": round(my - cy, 4),
            "transform": "uncrop_xyxy(origin_y=+%d) at unified_pipeline.py:1693" % TOPCUT,
        })
    geometry = {}
    for label, before, after in (("dx", "dx_before", "dx_after"), ("dy", "dy_before", "dy_after")):
        pre = [r[before] for r in out]
        post = [r[after] for r in out]
        geometry[label] = {
            "n": len(out),
            "before": {"median": round(stats.median(pre), 2),
                       "p10": percentile(pre, 10), "p90": percentile(pre, 90)},
            "after": {"median": round(stats.median(post), 2),
                      "p10": percentile(post, 10), "p90": percentile(post, 90)},
            "within_15px_before": sum(1 for v in pre if abs(v) <= 15),
            "within_15px_after": sum(1 for v in post if abs(v) <= 15),
        }
    geometry["by_position_source"] = {}
    for source in sorted({r["position_source"] for r in out}):
        subset = [r for r in out if r["position_source"] == source]
        geometry["by_position_source"][source] = {
            "n": len(subset),
            "dy_before_median": round(stats.median([r["dy_before"] for r in subset]), 2),
            "dy_after_median": round(stats.median([r["dy_after"] for r in subset]), 2),
            "dx_median": round(stats.median([r["dx_before"] for r in subset]), 2),
        }
    return out, geometry


def _raw_index() -> dict[str, object]:
    parents: dict[str, object] = {}
    for path in sorted((G402 / "raw_tables").rglob("*.csv")):
        if path.name != "tracking_data.csv":
            continue
        section = path.parent.name
        for row in read_csv(path):
            if not row.get("bbox_x1"):
                continue
            key = "%s/%s/%s/%s/%s" % (section, row["frame"], row["player_id"],
                                      row["bbox_x1"], row["bbox_y1"])
            parents[key] = None if key in parents else dict(
                row, _raw_table=path.relative_to(ROOT).as_posix())
    return parents


def build_export_join() -> list[dict]:
    """Join the frozen masked rows back to the original G402 raw producer rows."""
    parents = _raw_index()
    out = []
    for row in read_csv(G406 / "all_masked_rows.csv"):
        key = "%s/%s/%s/%s/%s" % (row["section_id"], row["frame"], row["player_id"],
                                  row["bbox_x1"], row["bbox_y1"])
        parent = parents.get(key)
        status = "ABSENT" if key not in parents else ("DUPLICATE" if parent is None else "MATCH")
        parent = parent if isinstance(parent, dict) else {}
        equal = bool(parent) and all(
            parent.get("bbox_" + k) == row["bbox_" + k] for k in ("x1", "y1", "x2", "y2"))
        out.append({
            "box_id": row["box_id"], "card_id": row["card_id"], "section_id": row["section_id"],
            "frame": row["frame"], "player_id": row["player_id"], "event_key": key,
            "join_status": status, "raw_table": parent.get("_raw_table", ""),
            "raw_bbox_x1": parent.get("bbox_x1", ""), "raw_bbox_y1": parent.get("bbox_y1", ""),
            "raw_bbox_x2": parent.get("bbox_x2", ""), "raw_bbox_y2": parent.get("bbox_y2", ""),
            "masked_bbox_x1": row["bbox_x1"], "masked_bbox_y1": row["bbox_y1"],
            "masked_bbox_x2": row["bbox_x2"], "masked_bbox_y2": row["bbox_y2"],
            "coordinates_equal": "1" if equal else "0",
        })
    return out


def build_tick_accounting() -> list[dict]:
    """Account for every sealed tick, including the ticks with no producer row."""
    draw = build_draw()
    selected = [{"source_sha256": r["source_sha256"], "window_id": r["section_id"],
                 "frame": int(r["frame"]), "card_id": r["card_id"],
                 "draw_kind": r["draw_kind"],
                 "sealed_start_frame": r["sealed_start_frame"],
                 "sealed_end_frame_exclusive": r["sealed_end_frame_exclusive"]} for r in draw]
    by_card = {r["card_id"]: r for r in draw}
    rows = []
    for row in read_csv(G406 / "all_masked_rows.csv"):
        card = by_card[row["card_id"]]
        rows.append({"source_sha256": card["source_sha256"], "window_id": row["section_id"],
                     "frame": int(row["frame"])})
    comparator: dict[str, int] = {}
    for det in read_csv(G406 / "comparator_detections.csv"):
        comparator[det["card_id"]] = comparator.get(det["card_id"], 0) + 1
    out = []
    for entry in retain_silence(selected, rows):
        out.append({k: entry[k] for k in ("card_id", "draw_kind", "window_id", "frame",
                                          "sealed_start_frame", "sealed_end_frame_exclusive",
                                          "source_sha256", "producer_row_count", "silence")}
                   | {"comparator_box_count": comparator.get(entry["card_id"], 0)})
    return out
