"""Observer-only stage capture for the G409 coordinate trace.

The sink is injected into a COPY of the archived route tree in pod scratch.
It records, at every decoded frame, the pre-crop native array identity, the
post-crop array identity, the raw detector box handed to the tracker, and the
serialized export box. It never alters a coordinate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

_SINK = os.environ.get("G409_SINK", "")
_TICKS = frozenset(int(v) for v in os.environ.get("G409_TICKS", "").split(",") if v.strip())
_HANDLE = None


def _out():
    global _HANDLE
    if _HANDLE is None and _SINK:
        Path(_SINK).parent.mkdir(parents=True, exist_ok=True)
        _HANDLE = open(_SINK, "a", encoding="utf-8", newline="\n")
    return _HANDLE


def _emit(record: dict) -> None:
    handle = _out()
    if handle is None:
        return
    handle.write(json.dumps(record, sort_keys=True) + "\n")
    handle.flush()


def _array_id(array) -> dict:
    if array is None:
        return {"shape": None, "sha256": None}
    data = array.tobytes()
    return {"shape": list(array.shape), "sha256": hashlib.sha256(data).hexdigest()}


def obs_crop(frame_idx, pre, post, topcut) -> None:
    """Stage A/B: decoded native array and the post-crop array handed downstream."""
    if _TICKS and int(frame_idx) not in _TICKS:
        return
    _emit({
        "stage": "crop",
        "frame": int(frame_idx),
        "topcut": int(topcut),
        "native": _array_id(pre),
        "post_crop": _array_id(post),
    })


def obs_detector_box(slot, det, timestamp) -> None:
    """Stage C: the raw model box at the moment the tracker stores it."""
    box = det.get("bbox") if isinstance(det, dict) else None
    if _TICKS and int(timestamp) not in _TICKS:
        return
    _emit({
        "stage": "detector_box",
        "slot": int(slot),
        "timestamp": int(timestamp),
        "bbox_tuple_order": "y1x1y2x2",
        "bbox": None if box is None else [float(v) for v in box],
        "confidence": float(det.get("confidence", -1.0)) if isinstance(det, dict) else -1.0,
    })


def obs_export(frame_idx, player_id, bbox, frame_shape) -> None:
    """Stage D/E: the post-tracker box at the CSV serialization site."""
    if _TICKS and int(frame_idx) not in _TICKS:
        return
    _emit({
        "stage": "export",
        "frame": int(frame_idx),
        "player_id": player_id,
        "bbox_tuple_order": "y1x1y2x2",
        "bbox": None if not bbox else [float(v) for v in bbox],
        "export_frame_shape": [int(v) for v in frame_shape],
        "serialized": None if not bbox else {
            "bbox_x1": float(bbox[1]), "bbox_y1": float(bbox[0]),
            "bbox_x2": float(bbox[3]), "bbox_y2": float(bbox[2]),
        },
    })


# --- scratch-tree injection (applied to a COPY, never to the deploy tree) ---

PIPE_ANCHOR = "            _frame_for_ocr = frame\n            frame = frame[TOPCUT:]\n"
PIPE_INJECT = PIPE_ANCHOR + (
    "            import scripts.platformkit.tracking.g409_observer as _g409\n"
    "            _g409.obs_crop(frame_idx, _frame_for_ocr, frame, TOPCUT)\n"
)
EXPORT_ANCHOR = '                bbox = track["bbox"]  # stored as (y1, x1, y2, x2)\n'
EXPORT_INJECT = EXPORT_ANCHOR + (
    "                import scripts.platformkit.tracking.g409_observer as _g409\n"
    "                _g409.obs_export(frame_idx, pid, bbox, frame.shape)\n"
)
TRACKER_ANCHOR = '        p.previous_bb = det["bbox"]\n'
TRACKER_INJECT = TRACKER_ANCHOR + (
    "        import scripts.platformkit.tracking.g409_observer as _g409\n"
    "        _g409.obs_detector_box(slot, det, timestamp)\n"
)

INJECTIONS = (
    ("src/pipeline/unified_pipeline.py", PIPE_ANCHOR, PIPE_INJECT),
    ("src/pipeline/unified_pipeline.py", EXPORT_ANCHOR, EXPORT_INJECT),
    ("src/tracking/advanced_tracker.py", TRACKER_ANCHOR, TRACKER_INJECT),
)


def inject(tree: Path) -> list[dict]:
    """Insert observer calls into a scratch route tree; refuse ambiguous anchors."""
    receipts = []
    for rel, anchor, replacement in INJECTIONS:
        path = tree / rel
        text = path.read_text(encoding="utf-8")
        if text.count(anchor) != 1:
            raise ValueError("anchor-not-unique:%s:%d" % (rel, text.count(anchor)))
        before = hashlib.sha256(text.encode("utf-8")).hexdigest()
        text = text.replace(anchor, replacement, 1)
        path.write_text(text, encoding="utf-8", newline="\n")
        receipts.append({
            "path": rel,
            "sha256_before": before,
            "sha256_after": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "anchor_line_count": anchor.count("\n"),
        })
    return receipts


if __name__ == "__main__":
    import sys
    print(json.dumps(inject(Path(sys.argv[1])), indent=1))
