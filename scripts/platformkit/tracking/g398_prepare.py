"""Preparation rails for the single G398 paired DEV shadow."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEV_KEYS = 1071
HELDOUT_KEYS = 549
DEV_BOXES = 530
DEV_BOX_GAMES = 27
HELDOUT_GAMES = 32
HELDOUT_LABELS = {"VISIBLE": 302, "ABSENT": 188, "UNKNOWN": 59}
SEAL_PREFIX = b"SEAL sha256 "


def verify_preregistration(path: Path) -> str:
    """Validate the LF-normalized, file-read preregistration seal."""
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
    indexed = {row.get(field, ""): row for row in materialized}
    if "" in indexed or len(indexed) != len(materialized):
        raise ValueError("duplicate-or-missing-identity-" + field)
    return indexed


def validate_dev_inputs(frames: Sequence[Mapping[str, str]],
                        reference: Sequence[Mapping[str, str]],
                        boxes: Sequence[Mapping[str, str]]) -> dict[str, int]:
    """Reproduce fixed DEV coverage while retaining all non-VISIBLE states."""
    frame_index = _index(frames, "frame_key")
    ref_index = _index(reference, "frame_key")
    if set(frame_index) != set(ref_index):
        raise ValueError("frame-reference-key-mismatch")
    development = [row for row in frames if row.get("split") == "development"]
    heldout = [row for row in frames if row.get("split") == "heldout"]
    if len(development) != DEV_KEYS or len(heldout) != HELDOUT_KEYS:
        raise ValueError("frozen-split-count-mismatch")
    box_keys = [row.get("frame_key", "") for row in boxes]
    if len(box_keys) != DEV_BOXES or len(set(box_keys)) != DEV_BOXES:
        raise ValueError("frozen-box-count-mismatch")
    if not set(box_keys) <= {row["frame_key"] for row in development}:
        raise ValueError("heldout-box-key-refused")
    box_games = {frame_index[key].get("game", "") for key in box_keys}
    if "" in box_games or len(box_games) != DEV_BOX_GAMES:
        raise ValueError("frozen-box-game-count-mismatch")
    labels = {label: sum(row.get("split") == "heldout" and row.get("label") == label
                          for row in reference) for label in HELDOUT_LABELS}
    if labels != HELDOUT_LABELS:
        raise ValueError("heldout-label-count-mismatch")
    return {"dev_keys": len(development), "heldout_keys": len(heldout),
            "box_keys": len(box_keys), "box_games": len(box_games),
            "heldout_games": len({row.get("game", "") for row in heldout})}


def assert_heldout_isolation(dev_rows: Iterable[Mapping[str, str]],
                             heldout_rows: Iterable[Mapping[str, str]]) -> None:
    """Refuse DEV tensors with any held-out key, game, or section identity."""
    dev = [dict(row) for row in dev_rows]
    heldout = [dict(row) for row in heldout_rows]
    for field in ("frame_key", "game", "section"):
        left = {row.get(field, "") for row in dev}
        right = {row.get(field, "") for row in heldout}
        if "" in left or "" in right or left & right:
            raise ValueError("heldout-or-context-overlap-" + field)
    if len({row["game"] for row in heldout}) != HELDOUT_GAMES:
        raise ValueError("heldout-game-count-mismatch")


def native_to_720p(value: float, native_height: int) -> float:
    """Apply G363's height-based native-to-720p coordinate transform."""
    if native_height <= 0:
        raise ValueError("invalid-native-height")
    return float(value) * 720.0 / float(native_height)


def roundtrip_native(value: float, native_height: int) -> float:
    """Invert the frozen coordinate transform for the scale receipt."""
    scaled = native_to_720p(value, native_height)
    return scaled * float(native_height) / 720.0


def frame_flags(label: str, observed_predictions: int, matched_predictions: int) -> tuple[int, int]:
    """Return TP and FP counts while charging UNKNOWN observations as FP."""
    if label not in HELDOUT_LABELS or observed_predictions < 0 or matched_predictions < 0:
        raise ValueError("invalid-frame-score-input")
    if matched_predictions > observed_predictions:
        raise ValueError("matched-predictions-exceed-observed")
    if label != "VISIBLE" and matched_predictions:
        raise ValueError("nonvisible-match-refused")
    return (matched_predictions if label == "VISIBLE" else 0,
            observed_predictions - matched_predictions)


def preserve_planned_keys(planned_keys: Iterable[str],
                          predictions: Mapping[str, Mapping[str, str]]) -> list[dict[str, str]]:
    """Keep every planned DEV key and name unavailable inference explicitly."""
    keys = list(planned_keys)
    if len(keys) != DEV_KEYS or len(set(keys)) != DEV_KEYS or "" in keys:
        raise ValueError("fixed-dev-key-denominator-required")
    if not set(predictions) <= set(keys):
        raise ValueError("prediction-key-outside-dev-refused")
    return [dict(predictions.get(key, {"frame_key": key, "status": "MISSING_INFERENCE"}))
            for key in keys]


def charge_paired_launch(path: Path, source_hashes: Mapping[str, str]) -> dict[str, object]:
    """Create the sole paired-launch token before either future traversal."""
    path = Path(path)
    if path.exists():
        raise ValueError("second-paired-launch-refused")
    payload: dict[str, object] = {"paired_launches": 1, "state": "CHARGED_BEFORE_INFERENCE",
                                  "source_hashes": dict(sorted(source_hashes.items()))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="ascii", newline="\n")
    return payload


def continuation_met(baseline: Mapping[str, float], candidate: Mapping[str, float]) -> bool:
    """Apply the sealed strict DEV continuation comparison without changing bars."""
    fields = ("c0", "precision_wilson_lo", "all_fp_per_absent")
    if any(field not in baseline or field not in candidate for field in fields):
        raise ValueError("continuation-field-missing")
    return (float(candidate["c0"]) > float(baseline["c0"])
            and float(candidate["precision_wilson_lo"]) >= float(baseline["precision_wilson_lo"])
            and float(candidate["all_fp_per_absent"]) <= float(baseline["all_fp_per_absent"]))
