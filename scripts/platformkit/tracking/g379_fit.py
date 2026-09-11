"""G379 per-frame decode, sealed stroke split, the two routes, and validation of the selected H.

Sealed in the G379 prereg sections 4-6. The fitter, the refinement, the selector and the validator
are IMPORTED and called unmodified; not one of their constants is redefined here. The FIT /
VALIDATION split is written to `stroke_split.csv` for a frame BEFORE that frame is fitted, and the
validation half never reaches ranking (contract B8).
"""
from __future__ import annotations

import argparse
import csv
import json
import signal
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking import g362_fit_validate as fv
from scripts.platformkit.tracking import g362_strokes as st
from scripts.platformkit.tracking import g371_symmetry_margin as sm
from scripts.platformkit.tracking.g334_court_template import TEMPLATE_POINTS
from scripts.platformkit.tracking.g364_sampler import frame_key, interior_indices

cv2.setNumThreads(1)

SCHEDULED = 60
FRAME_TIMEOUT_S = 900
STATE_TIMEOUT = "TIMEOUT"
STATE_DECODE_FAILED = "DECODE_FAILED"
STATE_NO_CANDIDATES = "NO_CANDIDATES"
SPLIT_FIELDS = ("frame_key", "section_id", "frame_index", "stroke_id", "side", "family",
                "n_supports", "length_px")
ROW_FIELDS = ("frame_key", "section_id", "game_id", "frame_index", "source_sha256",
              "raw_state", "raw_reason", "raw_forward_median_px", "raw_inverse_median_px",
              "presence_prediction", "selection_status", "orientation_status", "selection_margin",
              "winner_objective_j", "runner_up_objective_j", "validation_status",
              "forward_median_px", "inverse_median_px", "n_strokes", "n_fit_strokes",
              "n_val_strokes", "n_val_families", "n_val_points", "n_template_inframe",
              "n_template_penalty", "candidate_hypotheses_count",
              "deduplicated_symmetry_images_count", "seconds")


class _Timeout(Exception):
    pass


def _alarm(_signum, _frame):
    raise _Timeout()


def scheduled_indices(frame_count: int, count: int = SCHEDULED) -> list[int]:
    """The sealed schedule: `count` unique evenly spaced strict-interior frame indices."""
    return interior_indices(int(frame_count), int(count))


def decode(source: Path, indices: list[int], out_dir: Path, section_id: str,
           digest: str) -> list[dict]:
    """Decode each scheduled index once, store it at 720 rows, and name every failure."""
    out_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(source))
    rows = []
    try:
        for index in indices:
            key = frame_key({"source_sha256": digest, "section_id": section_id,
                             "frame_index": str(index)})
            path = out_dir / ("%s_%06d.png" % (section_id, index))
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, image = capture.read()
            if not ok or image is None:
                rows.append({"frame_key": key, "frame_index": index, "path": "",
                             "state": STATE_DECODE_FAILED})
                continue
            frame, scale = fv.to_base_height(image)
            cv2.imwrite(str(path), frame)
            rows.append({"frame_key": key, "frame_index": index, "path": str(path),
                         "state": "DECODED", "scale": scale,
                         "native_height": image.shape[0], "native_width": image.shape[1]})
    finally:
        capture.release()
    return rows


def split_rows(frame, key: str, section_id: str, index: int) -> tuple[list, list, list]:
    """The content-addressed FIT / VALIDATION cut, as archive rows written before any fit."""
    strokes = st.extract_strokes(frame)
    fit, validation = st.partition(strokes)
    rows = []
    for side, group in (("FIT", fit), ("VALIDATION", validation)):
        for stroke in group:
            rows.append({"frame_key": key, "section_id": section_id, "frame_index": index,
                         "stroke_id": stroke.stroke_id, "side": side, "family": stroke.family,
                         "n_supports": len(stroke.supports), "length_px": round(stroke.length, 4)})
    return strokes, validation, rows


def validate(winner, frame, strokes: list, validation: list):
    """G362's held-out decision on the SELECTED matrix; no refit, every status distinct."""
    counts = {"n_strokes": len(strokes), "n_fit_strokes": len(strokes) - len(validation),
              "n_val_strokes": len(validation), "n_val_families": len(st.families_of(validation)),
              "n_val_points": 0, "n_template_inframe": 0, "n_template_penalty": 0}
    if len(strokes) < fv.MIN_STROKES or len(st.families_of(strokes)) < fv.MIN_FAMILIES:
        return fv.STATE_NO_LINES, float("nan"), float("nan"), counts, None
    supports = st.support_array(validation)
    counts["n_val_points"] = len(supports)
    if counts["n_val_families"] < fv.MIN_VAL_FAMILIES or len(supports) < fv.MIN_VAL_POINTS:
        return fv.STATE_NO_VALIDATION, float("nan"), float("nan"), counts, None
    if winner is None:
        return STATE_NO_CANDIDATES, float("nan"), float("nan"), counts, None
    forward, inverse, n_in, n_out = fv.bidirectional(winner, supports, frame.shape)
    counts["n_template_inframe"], counts["n_template_penalty"] = n_in, n_out
    fwd, inv = float(np.median(forward)), float(np.median(inverse))
    state = fv.STATE_VALID if max(fwd, inv) <= fv.MAX_MEDIAN_PX else fv.STATE_REFUSED
    return state, fwd, inv, counts, forward


def measure(frame, key: str, section_id: str, index: int, presence: str):
    """One frame through both routes. Returns (row, split rows, forward residuals, matrix)."""
    import time

    started = time.time()
    strokes, validation, splits = split_rows(frame, key, section_id, index)
    raw = fv.decide(frame)
    selection, counts = sm.select_frame(frame)
    winner = None if selection.winner is None else selection.winner.matrix
    status, fwd, inv, extra, forward = validate(winner, frame, strokes, validation)
    row = {"frame_key": key, "section_id": section_id, "frame_index": index,
           "raw_state": raw.state, "raw_reason": raw.reason,
           "raw_forward_median_px": round(raw.forward_median, 6),
           "raw_inverse_median_px": round(raw.inverse_median, 6),
           "presence_prediction": presence, "selection_status": selection.geometry_status,
           "orientation_status": selection.orientation_status,
           "selection_margin": "" if selection.margin is None else round(selection.margin, 9),
           "winner_objective_j": ("" if selection.winner is None
                                  else round(selection.winner.objective, 9)),
           "runner_up_objective_j": ("" if selection.runner_up is None
                                     else round(selection.runner_up.objective, 9)),
           "validation_status": status, "forward_median_px": round(fwd, 6),
           "inverse_median_px": round(inv, 6),
           "candidate_hypotheses_count": counts["candidate_hypotheses_count"],
           "deduplicated_symmetry_images_count": counts["deduplicated_symmetry_images_count"],
           "seconds": round(time.time() - started, 3), **extra}
    return row, splits, forward, winner


def _write(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(manifest: Path, out_dir: Path, shard: int, shards: int) -> None:
    """Measure this shard's frames, writing per-shard rows, splits, residuals and matrices."""
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        frames = [row for number, row in enumerate(csv.DictReader(handle))
                  if number % shards == shard]
    signal.signal(signal.SIGALRM, _alarm)
    rows, splits, residuals, matrices = [], [], {}, {}
    for entry in frames:
        key = entry["frame_key"]
        base = {"frame_key": key, "section_id": entry["section_id"], "game_id": entry["game_id"],
                "source_sha256": entry["source_sha256"], "frame_index": entry["frame_index"]}
        if entry["state"] != "DECODED":
            rows.append({**base, "raw_state": entry["state"], "validation_status": entry["state"],
                         "presence_prediction": entry.get("presence_prediction", "")})
            continue
        frame = cv2.imread(entry["path"])
        signal.alarm(FRAME_TIMEOUT_S)
        try:
            row, split, forward, winner = measure(frame, key, entry["section_id"],
                                                  int(entry["frame_index"]),
                                                  entry.get("presence_prediction", ""))
        except _Timeout:
            rows.append({**base, "raw_state": STATE_TIMEOUT, "validation_status": STATE_TIMEOUT,
                         "presence_prediction": entry.get("presence_prediction", "")})
            continue
        finally:
            signal.alarm(0)
        rows.append({**base, **row})
        splits.extend(split)
        if forward is not None:
            residuals[key] = np.asarray(forward, dtype=np.float32)
        if winner is not None:
            matrices[key] = {"image_matrix": np.asarray(winner, dtype=float).tolist(),
                             "court_matrix": (np.linalg.inv(winner)
                                              / np.linalg.inv(winner)[2, 2]).tolist()}
        print("%s %s %s %s" % (key, row["raw_state"], row["selection_status"],
                               row["validation_status"]), flush=True)
    tag = "%02d" % shard
    out_dir.mkdir(parents=True, exist_ok=True)
    _write(out_dir / ("rows_%s.csv" % tag), rows, ROW_FIELDS)
    _write(out_dir / ("splits_%s.csv" % tag), splits, SPLIT_FIELDS)
    np.savez_compressed(out_dir / ("forward_%s.npz" % tag), **residuals)
    (out_dir / ("matrices_%s.json" % tag)).write_text(
        json.dumps(matrices, sort_keys=True, indent=1) + "\n", encoding="ascii")
    print("SHARD %s frames=%d template_points=%d" % (tag, len(rows), len(TEMPLATE_POINTS)))


def decode_sections(sources: Path, frames_dir: Path, out: Path, count: int = SCHEDULED) -> None:
    """Decode every selected section's scheduled frames once and write the frame manifest."""
    with sources.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    manifest = []
    for source in rows:
        indices = scheduled_indices(int(source["frame_count"]), count)
        for entry in decode(Path(source["source_path"]), indices, frames_dir,
                            source["section_id"], source["source_sha256"]):
            manifest.append({**entry, "section_id": source["section_id"],
                            "game_id": source["game_id"],
                             "source_sha256": source["source_sha256"]})
        print("DECODED %s frames=%d" % (source["section_id"], len(indices)), flush=True)
    _write(out, manifest, ("frame_key", "section_id", "game_id", "source_sha256", "frame_index",
                           "path", "state", "scale", "native_width", "native_height"))
    print("DECODE sections=%d frames=%d failed=%d"
          % (len(rows), len(manifest), sum(row["state"] != "DECODED" for row in manifest)))


def main() -> None:
    parser = argparse.ArgumentParser(description="G379 per-frame geometry measurement")
    parser.add_argument("action", choices=("decode", "measure"))
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--count", type=int, default=SCHEDULED)
    args = parser.parse_args()
    if args.action == "decode":
        decode_sections(args.sources, args.frames_dir, args.out, args.count)
    else:
        run(args.manifest, args.out, args.shard, args.shards)


if __name__ == "__main__":
    main()
