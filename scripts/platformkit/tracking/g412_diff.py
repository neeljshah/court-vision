"""Generate the G412 PROPOSED additive writer diff from archived src bytes.

This module NEVER writes under src/; it renders a unified diff only.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g412_contract import (
    BOX_FRAME, CROP_ORIGIN_Y_PX, PADDING_PX, file_digests, write_lf,
)
from scripts.platformkit.tracking.g412_premise import OUT, ROOT

DIFF = ROOT / "docs/research/organization-sprint/PROPOSED_g412_box_frame_contract.diff"
COPY = OUT / "PROPOSED_g412_box_frame_contract.diff"
TRACKER = "src/tracking/advanced_tracker.py"
PIPELINE = "src/pipeline/unified_pipeline.py"
Q = chr(34)


def _receipt_block(indent: str, holder: str, box: str) -> list[str]:
    """Additive receipt lines shared by the two writer sites."""
    route = "_g412_route(" + holder + ")"
    bound = route + " == " + Q + "fresh_box" + Q
    return [
        indent + "# G412 additive receipt: representation and nominal padding only.",
        indent + "# It states neither branch freshness nor that a box was observed.",
        indent + Q + "box_frame" + Q + ": (" + Q + BOX_FRAME + Q + " if " + bound
        + " else " + Q + "UNKNOWN" + Q + ") if " + box + " is not None else " + Q + Q + ",",
        indent + Q + "box_crop_origin_y_px" + Q + ": (" + str(CROP_ORIGIN_Y_PX) + " if "
        + bound + " else " + Q + "UNKNOWN" + Q + ") if " + box + " is not None else "
        + Q + Q + ",",
        indent + Q + "box_padding_px" + Q + ": (" + str(PADDING_PX) + " if " + bound
        + " else " + Q + "UNKNOWN" + Q + ") if " + box + " is not None else " + Q + Q + ",",
        indent + Q + "box_receipt_status" + Q + ": (" + Q + "BOUND" + Q + " if " + bound
        + " else " + Q + "UNKNOWN" + Q + ") if " + box + " is not None else "
        + Q + "EMPTY" + Q + ",",
        indent + Q + "box_receipt_reason" + Q + ": (" + Q + Q + " if " + bound + " else "
        + Q + "unbound-" + Q + " + " + route + ") if " + box + " is not None else "
        + Q + "absent-box" + Q + ",",
    ]


def _helper_lines() -> list[str]:
    """The additive route-label helper inserted beside the writer."""
    return [
        "",
        "def _g412_route(holder) -> str:",
        "    " + Q * 3 + "Return the additive box-route label, defaulting to UNKNOWN."
        + Q * 3,
        "    return str(getattr(holder, " + Q + "box_route" + Q + ", " + Q + "UNKNOWN"
        + Q + "))",
        "",
        "",
    ]


def patch_tracker(lines: list[str]) -> list[str]:
    """Mark the fresh store and the Kalman overwrite with an additive route label."""
    out = []
    for line in lines:
        out.append(line)
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]
        if stripped == "p.previous_bb = det[" + Q + "bbox" + Q + "]":
            out.append(indent + "p.box_route = " + Q + "fresh_box" + Q
                       + "  # G412 additive label")
        elif stripped == "self.players[slot].previous_bb = self._kf_pred[slot]":
            out.append(indent + "self.players[slot].box_route = " + Q + "prediction" + Q
                       + "  # G412 additive label")
    return out


def patch_pipeline(lines: list[str]) -> list[str]:
    """Add the receipt at the frame_tracks site and at the serialized CSV site."""
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]
        if stripped == Q + "bbox" + Q + ":             p.previous_bb,":
            out.append(line)
            out.extend(_receipt_block(indent, "p", "p.previous_bb"))
            continue
        if stripped == Q + "bbox_y2" + Q + ":            bbox[2] if bbox else " + Q * 2 + ",":
            out.append(line)
            out.append(indent
                       + "# G412 additive receipt columns, carried through from the track.")
            out.extend([
                indent + Q + field + Q + ": track.get(" + Q + field + Q + ", " + Q * 2 + "),"
                for field in ("box_frame", "box_crop_origin_y_px", "box_padding_px",
                              "box_receipt_status", "box_receipt_reason")
            ])
            continue
        if stripped.startswith("class UnifiedPipeline") and "_g412_route" not in "".join(out):
            out.extend(_helper_lines())
        out.append(line)
    return out


def build() -> dict[str, Any]:
    """Render the two-file unified diff and retain a byte-identical evidence copy."""
    chunks = []
    for rel, patcher in ((TRACKER, patch_tracker), (PIPELINE, patch_pipeline)):
        original = (ROOT / rel).read_bytes().decode("utf-8").split(chr(10))
        patched = patcher(list(original))
        if patched == original:
            raise ValueError("anchor-not-found-" + rel)
        chunks.append(chr(10).join(difflib.unified_diff(
            original, patched, fromfile="a/" + rel, tofile="b/" + rel, n=3, lineterm="")))
    header = ["# G412 PROPOSED additive box-frame receipt. APPLIED NOWHERE.",
              "# Existing bbox and position values, ordering and interpretation are unchanged.",
              ""]
    text = chr(10).join(header + chunks) + chr(10)
    digest = write_lf(DIFF, text)
    copy_digest = write_lf(COPY, text)
    added = [l for l in text.split(chr(10)) if l.startswith("+") and not l.startswith("+++")]
    removed = [l for l in text.split(chr(10)) if l.startswith("-") and not l.startswith("---")]
    return {"diff_path": DIFF.as_posix(), "evidence_copy": COPY.as_posix(),
            "sha256": digest, "copy_sha256": copy_digest,
            "identical_copy": digest == copy_digest,
            "added_lines": len(added), "removed_lines": len(removed),
            "src_files_touched": 0,
            "src_digests_after_render": {rel: file_digests(ROOT / rel)[1]
                                         for rel in (TRACKER, PIPELINE)}}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, sort_keys=True))
