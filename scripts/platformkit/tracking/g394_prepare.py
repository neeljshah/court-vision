"""Pure preparation rails for the G394 person-contained negative design."""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path


SEAL_PREFIX = b"SEAL sha256 "
EXPECTED_BINDING = {
    "dev_boxes": 530,
    "dev_games": 27,
    "dev_absent": 425,
    "dev_absent_in_box_games": 386,
    "heldout_visible": 302,
    "heldout_absent": 188,
    "heldout_unknown": 59,
}
FROZEN_BARS = {
    "c0_min": 0.25,
    "precision_wilson_lower_min": 0.90,
    "all_fp_per_absent_max": 0.01,
    "heldout_states": 549,
    "visible_states": 302,
    "absent_states": 188,
    "unknown_states": 59,
    "candidate_conf": 0.05,
}


def verify_preregistration(path: Path) -> str:
    """Return the verified seal after CRLF-safe preregistration validation."""
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    body, marker, recorded = raw.rpartition(b"\n" + SEAL_PREFIX)
    if not marker or body.endswith(b"\n"):
        raise ValueError("invalid-preregistration-seal-layout")
    expected = hashlib.sha256(body + b"\n").hexdigest()
    actual = recorded.decode("ascii").strip()
    if len(actual) != 64 or actual != expected:
        raise ValueError("preregistration-seal-mismatch")
    return actual


def _index(rows: Iterable[Mapping[str, str]], field: str) -> dict[str, dict[str, str]]:
    materialized = [dict(row) for row in rows]
    indexed = {str(row[field]): row for row in materialized}
    if "" in indexed or len(indexed) != len(materialized):
        raise ValueError("duplicate-or-missing-identity " + field)
    return indexed


def binding_counts(boxes: Sequence[Mapping[str, str]], reference: Sequence[Mapping[str, str]],
                   frames: Sequence[Mapping[str, str]]) -> dict[str, int]:
    """Reproduce the complete G394 dispatch counts without candidate inference."""
    frame_by_key = _index(frames, "frame_key")
    box_keys = [str(row.get("frame_key", "")) for row in boxes]
    if "" in box_keys or len(box_keys) != len(set(box_keys)) or not set(box_keys) <= set(frame_by_key):
        raise ValueError("box-frame-identity-mismatch")
    reference_by_key = _index(reference, "frame_key")
    if not set(reference_by_key) <= set(frame_by_key):
        raise ValueError("reference-frame-identity-mismatch")
    box_games = {frame_by_key[key]["game"] for key in box_keys}
    development_absent = [key for key, row in reference_by_key.items()
                          if row.get("split") == "development" and row.get("label") == "ABSENT"]
    heldout = {label: sum(row.get("split") == "heldout" and row.get("label") == label
                          for row in reference_by_key.values())
               for label in ("VISIBLE", "ABSENT", "UNKNOWN")}
    return {
        "dev_boxes": len(box_keys), "dev_games": len(box_games),
        "dev_absent": len(development_absent),
        "dev_absent_in_box_games": sum(frame_by_key[key]["game"] in box_games
                                         for key in development_absent),
        "heldout_visible": heldout["VISIBLE"], "heldout_absent": heldout["ABSENT"],
        "heldout_unknown": heldout["UNKNOWN"],
    }


def check_binding(counts: Mapping[str, int]) -> None:
    """Reject preparation if the fixed dispatch premise has changed."""
    changed = {key: (value, counts.get(key)) for key, value in EXPECTED_BINDING.items()
               if counts.get(key) != value}
    if changed:
        raise ValueError("binding-counts-changed " + repr(changed))


def crop_transform(cx: float, cy: float, width: int, height: int, size: int = 320) -> dict[str, int]:
    """Return the native source and destination rectangles for a padded square crop."""
    if width <= 0 or height <= 0 or size <= 0 or not math.isfinite(cx) or not math.isfinite(cy):
        raise ValueError("invalid-native-crop-input")
    left, top = math.floor(cx - size / 2), math.floor(cy - size / 2)
    right, bottom = left + size, top + size
    source_left, source_top = max(0, left), max(0, top)
    source_right, source_bottom = min(width, right), min(height, bottom)
    return {
        "source_left": source_left, "source_top": source_top,
        "source_right": source_right, "source_bottom": source_bottom,
        "dest_left": source_left - left, "dest_top": source_top - top,
        "dest_right": source_right - left, "dest_bottom": source_bottom - top,
        "crop_size": size,
    }


def rect_contains(cx: float, cy: float, box: Mapping[str, float]) -> bool:
    """Test inclusive containment in one person rectangle without altering pixels."""
    x, y, width, height = (float(box[name]) for name in ("x", "y", "width", "height"))
    if width < 0 or height < 0:
        raise ValueError("negative-person-rectangle")
    return x <= cx <= x + width and y <= cy <= y + height


def evenly_select(rows: Sequence[Mapping[str, str]], maximum: int = 120) -> list[dict[str, str]]:
    """Select the frozen evenly spaced candidate records, including both endpoints."""
    if maximum != 120:
        raise ValueError("unmoved-selection-maximum-required")
    ordered = sorted((dict(row) for row in rows),
                     key=lambda row: (row["game"], row["section"], int(row["frame_index"]),
                                      row["frame_key"]))
    if len({row["frame_key"] for row in ordered}) != len(ordered):
        raise ValueError("duplicate-candidate-frame-key")
    selected_count = min(maximum, len(ordered))
    if selected_count == 0:
        return []
    if selected_count == 1:
        return [ordered[0]]
    return [ordered[round(index * (len(ordered) - 1) / (selected_count - 1))]
            for index in range(selected_count)]


def assert_split_isolation(development: Iterable[Mapping[str, str]],
                           heldout: Iterable[Mapping[str, str]]) -> None:
    """Refuse a negative design with any held-out game or section overlap."""
    dev = list(development)
    hold = list(heldout)
    dev_games = {row["game"] for row in dev}
    held_games = {row["game"] for row in hold}
    dev_sections = {row["section"] for row in dev}
    held_sections = {row["section"] for row in hold}
    if dev_games & held_games or dev_sections & held_sections:
        raise ValueError("heldout-game-or-context-overlap")


def all_planned_states(planned_keys: Iterable[str], predictions: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Retain every planned key, explicitly naming a missing future inference."""
    keys = list(planned_keys)
    if len(keys) != FROZEN_BARS["heldout_states"] or len(keys) != len(set(keys)):
        raise ValueError("fixed-549-state-denominator-required")
    prediction_rows = [dict(row) for row in predictions]
    prediction_by_key = {str(row["frame_key"]): row for row in prediction_rows}
    if not set(prediction_by_key) <= set(keys) or len(prediction_by_key) != len(prediction_rows):
        raise ValueError("prediction-key-identity-mismatch")
    return [prediction_by_key.get(key, {"frame_key": key, "status": "MISSING_INFERENCE"})
            for key in keys]


def assert_launch_not_spent(accounting: Mapping[str, object], phase: str) -> None:
    """Refuse a restart once the fixed training or candidate token was charged."""
    if phase not in ("training", "candidate_inference"):
        raise ValueError("unknown-launch-phase")
    field = phase + "_charged"
    if bool(accounting.get(field)):
        raise ValueError("spent-token-restart-refused")
