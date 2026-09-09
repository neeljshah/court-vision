"""Run G360's binding 22-frame premise from G350's adjudicated units."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import cv2

from scripts.platformkit.tracking.court_presence_cue import auc, choose_rule, court_presence


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _references(ratings: list[dict[str, str]], adjudication: list[dict[str, str]]) -> dict[str, str]:
    pairs: dict[str, dict[str, str]] = {}
    for row in ratings:
        pairs.setdefault(row["unit_id"], {})[row["rater"]] = row["label"]
    overrides = {row["unit_id"]: row["label"] for row in adjudication}
    resolved: dict[str, str] = {}
    for unit_id, pair in pairs.items():
        if set(pair) != {"terra", "sol"}:
            raise ValueError("missing G350 rating: %s" % unit_id)
        resolved[unit_id] = pair["terra"] if pair["terra"] == pair["sol"] else overrides.get(unit_id, "")
        if not resolved[unit_id]:
            raise ValueError("missing G350 adjudication: %s" % unit_id)
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _frame(path: Path, index: int):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("unreadable source: %s" % path)
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise ValueError("unreadable representative frame: %s:%d" % (path, index))
    return frame


def run(candidates: Path, ratings: Path, adjudication: Path, corpus_root: Path,
        output: Path) -> dict[str, object]:
    """Measure both sealed premise cues and write one additive row per G350 unit."""
    reference = _references(_read(ratings), _read(adjudication))
    candidate_by_unit = {row["unit_id"]: row for row in _read(candidates)}
    rows: list[dict[str, object]] = []
    for unit_id, label in sorted(reference.items()):
        candidate = candidate_by_unit.get(unit_id)
        if candidate is None:
            raise ValueError("G350 candidate absent: %s" % unit_id)
        source = corpus_root / Path(candidate["source_path"]).name
        if not source.is_file():
            print("ABSENT-IN-WORKTREE %s" % source.as_posix())
            raise FileNotFoundError(source)
        frame = _frame(source, int(candidate["representative_frame"]))
        score, families, longest, surface = court_presence(frame)
        rows.append({"unit_id": unit_id, "reference_label": label,
                     "source_path": str(source.absolute()), "video_sha256": _sha256(source),
                     "byte_size": source.stat().st_size, "source_width": frame.shape[1],
                     "source_height": frame.shape[0], "frame_index": candidate["representative_frame"],
                     "score": "%.9f" % score, "families": families,
                     "longest_px": "%.3f" % longest, "surface": "%.9f" % surface,
                     "positive": label == "USABLE_WIDE"})
    line_auc = auc((float(row["families"]) for row in rows), (bool(row["positive"]) for row in rows))
    surface_auc = auc((float(row["surface"]) for row in rows), (bool(row["positive"]) for row in rows))
    family_floor, surface_floor = choose_rule(rows)
    for row in rows:
        row["line_auc"] = "%.9f" % line_auc
        row["surface_auc"] = "%.9f" % surface_auc
        row["family_floor"] = "%06d" % family_floor
        row["surface_floor"] = "%.9f" % surface_floor
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return {"n": len(rows), "line_auc": line_auc, "surface_auc": surface_auc,
            "family_floor": family_floor, "surface_floor": surface_floor,
            "premise_pass": max(line_auc, surface_auc) >= 0.75}


def main() -> None:
    parser = argparse.ArgumentParser(description="G360 binding premise runner")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.candidates, args.ratings, args.adjudication,
                         args.corpus_root, args.out), sort_keys=True))


if __name__ == "__main__":
    main()
