"""G412 route chain, bbox reader survey and the published coordinate transforms."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g412_contract import (
    BOX_FRAME, CROP_ORIGIN_Y_PX, PADDING_PX, file_digests, write_csv_lf, write_lf,
)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12"
SCAN_TREES = ("src", "scripts", "domains", "api", "kernel", "intel")
BBOX_TOKENS = ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "previous_bb")
STAGES = (
    ("A", "src/pipeline/unified_pipeline.py", 1677, "native", "native",
     "decode", "identity"),
    ("B", "src/tracking/video_handler.py", 11, "native", "native",
     "crop constant", "TOPCUT = 60"),
    ("C", "src/pipeline/unified_pipeline.py", 1693, "native", "cropped",
     "crop", "cropped_y = native_y - 60"),
    ("D", "src/tracking/player_detection.py", 20, "cropped", "cropped",
     "pad constant", "PAD = 15"),
    ("E", "src/tracking/advanced_tracker.py", 1333, "cropped", "cropped",
     "integer conversion", "x1 = int(box[0]) and the other three corners"),
    ("F", "src/tracking/advanced_tracker.py", 1334, "cropped", "cropped",
     "clip for the pixel crop only", "x1c/y1c/x2c/y2c clipped to frame.shape"),
    ("G", "src/tracking/advanced_tracker.py", 1336, "cropped", "cropped",
     "PAD expansion, unclipped store",
     "bbox = (y1 - PAD, x1 - PAD, y2 + PAD, x2 + PAD)"),
    ("H", "src/tracking/advanced_tracker.py", 626, "cropped", "cropped",
     "fresh store", "p.previous_bb = det['bbox']"),
    ("I", "src/tracking/advanced_tracker.py", 1165, "cropped", "cropped",
     "prediction overwrite", "previous_bb = self._kf_pred[slot]"),
    ("J", "src/tracking/advanced_tracker.py", 1410, "cropped", "court_map",
     "court projection from the clipped unpadded box",
     "head_x = (x1c + x2c) // 2 with foot_y = y2c"),
    ("K", "src/pipeline/unified_pipeline.py", 2703, "cropped", "cropped",
     "off-frame drop guard, not a clip",
     "_bbox_off_frame(bbox, frame.shape[1], frame.shape[0])"),
    ("L", "src/pipeline/unified_pipeline.py", 2736, "cropped", "cropped",
     "writer tuple permutation",
     "bbox_x1 = bbox[1], bbox_y1 = bbox[0], bbox_x2 = bbox[3], bbox_y2 = bbox[2]"),
)


def _digest(rel: str) -> dict[str, Any]:
    size, disk, lf = file_digests(ROOT / rel)
    return {"bytes": size, "sha256_on_disk": disk, "sha256_lf": lf}


def _line_text(rel: str, number: int) -> str:
    lines = (ROOT / rel).read_bytes().decode("utf-8", "replace").split(chr(10))
    return lines[number - 1].strip() if 0 < number <= len(lines) else "ABSENT"


def route_chain() -> dict[str, Any]:
    """Build the archived-byte route chain with a digest for every cited file."""
    stages = []
    for code, rel, line, space_in, space_out, role, transform in STAGES:
        stages.append({"stage": code, "path": rel, "line": line,
                       "source_line": _line_text(rel, line), "frame_in": space_in,
                       "frame_out": space_out, "role": role, "transform": transform,
                       "file": _digest(rel)})
    return {
        "worktree_root": ROOT.as_posix(),
        "stages": stages,
        "constants": {"TOPCUT": CROP_ORIGIN_Y_PX, "PAD": PADDING_PX,
                      "box_frame": BOX_FRAME},
        "stored_tuple_order": "previous_bb = (y1 - PAD, x1 - PAD, y2 + PAD, x2 + PAD)",
        "serialized_order": "bbox_x1, bbox_y1, bbox_x2, bbox_y2 in cropped xyxy",
        "clip_status": "the stored tuple is NEVER clipped; only the pixel crop and the "
                       "court projection use the clipped corners",
        "branch_scope": {
            "fresh_box": "position_source DETECTION together with source_branch "
                         "advanced_tracker.py:_activate_slot",
            "prediction": "kalman_homography, an unobserved Kalman box",
            "retained_point": "jump_clamp, subpixel_hold and id_merge reuse a prior "
                              "position and do not re-observe the box",
            "ankle": "ankle keypoint override at unified_pipeline court write; no box",
            "flow": "flow_gapfill_batched; absent from the 206 sealed rows",
        },
        "model_set": [],
        "model_set_reason": "no inference is performed by this row",
    }


def reader_manifest() -> list[dict[str, Any]]:
    """Survey every file that reads or writes a stored bbox field."""
    rows = []
    for tree in SCAN_TREES:
        base = ROOT / tree
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            text = path.read_bytes().decode("utf-8", "replace")
            for number, line in enumerate(text.split(chr(10)), start=1):
                hits = [token for token in BBOX_TOKENS if token in line]
                if not hits:
                    continue
                rows.append({
                    "path": path.relative_to(ROOT).as_posix(), "line": number,
                    "tokens": " ".join(hits), "text": line.strip()[:160],
                    "kind": _kind(line),
                    "receipt_field_present": 0,
                })
    return rows


def _kind(line: str) -> str:
    """Classify a hit as a write when the token is assigned or emitted as a key."""
    stripped = line.strip()
    if re.search(r"(^|[\s.\[])(bbox_\w+|previous_bb)\s*=[^=]", stripped):
        return "write"
    if re.search(r"[\"']((bbox_\w+)|previous_bb)[\"']\s*:", stripped):
        return "emit"
    return "read"


def transforms() -> dict[str, Any]:
    """Publish the exact equations and the clip order, with no fitted constant."""
    return {
        "box_frame": BOX_FRAME,
        "box_crop_origin_y_px": CROP_ORIGIN_Y_PX,
        "box_padding_px": PADDING_PX,
        "stored": "B = (bbox_x1, bbox_y1, bbox_x2, bbox_y2), cropped xyxy, padded, unclipped",
        "native_padded": "(Bx1, By1 + 60, Bx2, By2 + 60)",
        "native_unpadded_detector_form": "(Bx1 + 15, By1 + 75, Bx2 - 15, By2 + 45)",
        "clip_order": [
            "1 clip the cropped-space box to (0, 0, crop_width, crop_height)",
            "2 only then add the native origin offset of 60 to both y coordinates",
        ],
        "cropped_dimensions": "crop_width = native_width, crop_height = native_height - 60",
        "centre_translation": "a stored centre gains exactly +60 in y before clipping",
        "court_point_rule": "a court map point is never translated by 60; the fresh "
                            "box-based write projects ((x1c + x2c) // 2, y2c, 1) through "
                            "M then M1",
        "fitted_constants": [],
        "derivation": "every constant is read from archived source: TOPCUT at "
                      "src/tracking/video_handler.py:11 and PAD at "
                      "src/tracking/player_detection.py:20",
    }


def run() -> dict[str, Any]:
    """Write route_chain.json, reader_manifest.csv and transforms.json."""
    OUT.mkdir(parents=True, exist_ok=True)
    chain = route_chain()
    readers = reader_manifest()
    trans = transforms()
    write_lf(OUT / "route_chain.json", json.dumps(chain, indent=1, sort_keys=True) + chr(10))
    write_csv_lf(OUT / "reader_manifest.csv", list(readers[0]), readers)
    write_lf(OUT / "transforms.json", json.dumps(trans, indent=1, sort_keys=True) + chr(10))
    absent = [s["stage"] for s in chain["stages"] if s["source_line"] == "ABSENT"]
    return {"stages": len(chain["stages"]), "stage_lines_absent": absent,
            "reader_rows": len(readers),
            "reader_files": len({r["path"] for r in readers}),
            "reader_writes": sum(1 for r in readers if r["kind"] == "write"),
            "readers_with_receipt_field": 0}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, sort_keys=True))
