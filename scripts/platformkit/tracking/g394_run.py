"""G394 pod driver: person-contained DEV negative candidates, crops and rater cards.

Sealed by docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/preregistration.md.
Person rectangles SELECT records only. No pixel is masked, erased or invented, and
no runtime veto is built. Held-out pixels are never opened by this phase.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/workspace/wt/a7")

from scripts.platformkit.tracking.g394_prepare import (  # noqa: E402
    binding_counts, check_binding, crop_transform, evenly_select, rect_contains)

LANE = Path("/workspace/wt/a7")
SCRATCH = LANE / ".g394_scratch"
SHEETS = Path("/workspace/g373_scratch/sheets_v2")
G389 = LANE / "docs/evidence/tracking/g389_ball_reference_completion_2026-09-11"
MANIFEST = Path("/workspace/wt/a11/docs/evidence/tracking/"
                "g373_ball_detector_v2_2026-09-10/sheet_manifest_all.csv")
INIT_WEIGHTS = Path("/workspace/deploy/nba-ai-system/models/weights/yolov8n_ball.pt")
PERSON_WEIGHTS = Path("/workspace/deploy/nba-ai-system/yolov8n.pt")
A8_WEIGHTS = SCRATCH / "a8_final_epoch.pt"
ROUTE = Path("/workspace/nba-ai-system/src/tracking/ball_detect_track.py")
SALT = "G394-person-negative-blind-2026-09-11"

A8_INFER = dict(imgsz=960, conf=0.05, iou=0.70, max_det=300, agnostic_nms=False,
                half=True, device=0, augment=False, visualize=False, verbose=False)
PERSON_INFER = dict(imgsz=640, conf=0.25, iou=0.70, max_det=300, classes=[0],
                    half=True, device=0, augment=False, visualize=False, verbose=False)
ELIG_FIELDS = ("frame_key", "game", "section", "frame_index", "width", "height",
               "n_calls", "call_cx", "call_cy", "call_w", "call_h", "call_score",
               "n_person", "contained", "person_index")
MASK_FIELDS = ("frame_key", "person_index", "x", "y", "width", "height", "score")
MANIFEST_FIELDS = ("packet_id", "position", "frame_key", "game", "section", "frame_index",
                   "call_cx", "call_cy", "call_score", "source_left", "source_top",
                   "source_right", "source_bottom", "dest_left", "dest_top",
                   "dest_right", "dest_bottom", "crop_size", "crop_sha256")


def rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV input."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    """Hash one bounded file without loading unrelated stores."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sheet(frame_key: str) -> Path:
    """Native 1920x1080 sheet for one frame key."""
    return SHEETS / (frame_key[:12] + ".jpg")


def write_csv(path: Path, fields: tuple[str, ...], records: list[dict]) -> None:
    """Write one ASCII CSV checkpoint with fixed field order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def save(name: str, payload: dict) -> None:
    """Persist and print one phase report."""
    (SCRATCH / (name + "_report.json")).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    print("G394 " + name.upper() + " COMPLETE " + json.dumps(payload, sort_keys=True), flush=True)


def eligible() -> tuple[list[dict[str, str]], dict]:
    """Freeze the 386 eligible ABSENT DEV keys and assert complete split isolation."""
    frames = {row["frame_key"]: row for row in rows(G389 / "frames_v3.csv")}
    reference = {row["frame_key"]: row for row in rows(G389 / "reference_v3.csv")}
    boxes = rows(G389 / "dev_boxes_v3.csv")
    counts = binding_counts(boxes, list(reference.values()), list(frames.values()))
    check_binding(counts)
    box_games = {frames[row["frame_key"]]["game"] for row in boxes}
    keys = sorted(key for key, row in reference.items()
                  if row["split"] == "development" and row["label"] == "ABSENT"
                  and frames[key]["game"] in box_games)
    held = [row for row in frames.values() if row["split"] == "heldout"]
    dev = [frames[key] for key in keys]
    held_games = {row["game"] for row in held}
    held_sections = {row["section"] for row in held}
    dev_games = {row["game"] for row in dev}
    dev_sections = {row["section"] for row in dev}
    if dev_games & held_games or dev_sections & held_sections:
        raise ValueError("heldout-game-or-context-overlap")
    manifest = {row["frame_key"]: row for row in rows(MANIFEST)}
    for key in keys:
        if sha256_file(sheet(key)) != manifest[key]["sheet_sha256"]:
            raise ValueError("cache-digest-mismatch " + key)
    isolation = {"binding_counts": counts, "eligible_keys": len(keys),
                 "eligible_games": len(dev_games), "eligible_sections": len(dev_sections),
                 "heldout_games": len(held_games), "heldout_sections": len(held_sections),
                 "game_overlap": 0, "section_overlap": 0, "sheets_verified": len(keys),
                 "manifest_rows": len(manifest)}
    (SCRATCH / "split_assertions.json").write_text(
        json.dumps(isolation, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    return [frames[key] for key in keys], isolation


def detect(keys: list[str]) -> tuple[dict[str, list], dict[str, list]]:
    """One A8 DEV pass and one person pass over the same frozen native sheets."""
    from ultralytics import YOLO

    calls: dict[str, list] = {}
    persons: dict[str, list] = {}
    ball = YOLO(str(A8_WEIGHTS))
    for key in keys:
        result = ball.predict(source=str(sheet(key)), **A8_INFER)[0]
        best, score = None, -1.0
        for box in result.boxes:
            confidence = float(box.conf[0])
            if confidence > score:
                best, score = [float(v) for v in box.xywh[0]], confidence
        calls[key] = [best, score, len(result.boxes)]
    del ball
    person = YOLO(str(PERSON_WEIGHTS))
    for key in keys:
        result = person.predict(source=str(sheet(key)), **PERSON_INFER)[0]
        persons[key] = [([float(v) for v in box.xyxy[0]], float(box.conf[0]))
                        for box in result.boxes]
    return calls, persons


def census(frames: list[dict[str, str]], calls: dict, persons: dict) -> list[dict]:
    """Record every eligible key, its rank-0 call and its person containment."""
    eligibility, masks = [], []
    for frame in frames:
        key = frame["frame_key"]
        best, score, n_calls = calls[key]
        boxes = persons[key]
        contained, index = 0, ""
        for position, (xyxy, confidence) in enumerate(boxes):
            rect = {"x": xyxy[0], "y": xyxy[1],
                    "width": xyxy[2] - xyxy[0], "height": xyxy[3] - xyxy[1]}
            masks.append({"frame_key": key, "person_index": position,
                          "x": round(rect["x"], 3), "y": round(rect["y"], 3),
                          "width": round(rect["width"], 3), "height": round(rect["height"], 3),
                          "score": round(confidence, 6)})
            if best is not None and not contained and rect_contains(best[0], best[1], rect):
                contained, index = 1, str(position)
        eligibility.append({
            "frame_key": key, "game": frame["game"], "section": frame["section"],
            "frame_index": frame["frame_index"], "width": frame["width"],
            "height": frame["height"], "n_calls": n_calls,
            "call_cx": round(best[0], 3) if best else "",
            "call_cy": round(best[1], 3) if best else "",
            "call_w": round(best[2], 3) if best else "",
            "call_h": round(best[3], 3) if best else "",
            "call_score": round(score, 6) if best else "",
            "n_person": len(boxes), "contained": contained, "person_index": index})
    write_csv(SCRATCH / "eligibility.csv", ELIG_FIELDS, eligibility)
    write_csv(SCRATCH / "masks.csv", MASK_FIELDS, masks)
    return eligibility


def cards(selected: list[dict]) -> list[dict]:
    """Cut one native 320x320 crop per candidate and render its two-panel blind card."""
    from PIL import Image, ImageDraw

    crops = SCRATCH / "crops"
    deck = SCRATCH / "cards"
    for target in (crops, deck):
        target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for position, row in enumerate(selected):
        key = row["frame_key"]
        cx, cy = float(row["call_cx"]), float(row["call_cy"])
        transform = crop_transform(cx, cy, int(row["width"]), int(row["height"]))
        full = Image.open(sheet(key)).convert("RGB")
        crop = Image.new("RGB", (transform["crop_size"], transform["crop_size"]), (0, 0, 0))
        crop.paste(full.crop((transform["source_left"], transform["source_top"],
                              transform["source_right"], transform["source_bottom"])),
                   (transform["dest_left"], transform["dest_top"]))
        packet = "G394-%03d-%s" % (
            position, hashlib.sha256((SALT + key).encode("ascii")).hexdigest()[:16])
        crop_path = crops / (packet + ".jpg")
        crop.save(crop_path, quality=95)
        panel = Image.new("RGB", (960, 1180), (16, 16, 16))
        panel.paste(full.resize((960, 540)), (0, 0))
        panel.paste(crop.resize((640, 640), Image.NEAREST), (160, 540))
        draw = ImageDraw.Draw(panel)
        half_w = float(row["call_w"]) / 2.0 + 6.0
        half_h = float(row["call_h"]) / 2.0 + 6.0
        for colour, width in (((0, 0, 0), 5), ((255, 255, 255), 2)):
            draw.rectangle([(cx - half_w) / 2.0, (cy - half_h) / 2.0,
                            (cx + half_w) / 2.0, (cy + half_h) / 2.0],
                           outline=colour, width=width)
            draw.rectangle([160 + 320 - half_w * 2.0, 540 + 320 - half_h * 2.0,
                            160 + 320 + half_w * 2.0, 540 + 320 + half_h * 2.0],
                           outline=colour, width=width)
        draw.text((20, 20), packet, fill=(255, 255, 0))
        panel.save(deck / (packet + ".jpg"), quality=85)
        manifest.append({"packet_id": packet, "position": position, "frame_key": key,
                         "game": row["game"], "section": row["section"],
                         "frame_index": row["frame_index"], "call_cx": row["call_cx"],
                         "call_cy": row["call_cy"], "call_score": row["call_score"],
                         "crop_sha256": sha256_file(crop_path), **transform})
    write_csv(SCRATCH / "negative_manifest.csv", MANIFEST_FIELDS, manifest)
    return manifest


def main() -> None:
    """Build the frozen candidate census, the even selection and the blind cards."""
    started = time.time()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    identities = {
        "a8_weights": sha256_file(A8_WEIGHTS), "init_weights": sha256_file(INIT_WEIGHTS),
        "person_weights_path": PERSON_WEIGHTS.as_posix(),
        "person_weights": sha256_file(PERSON_WEIGHTS),
        "route_path": ROUTE.as_posix(), "route": sha256_file(ROUTE),
        "a8_infer": A8_INFER, "person_infer": dict(PERSON_INFER)}
    frames, isolation = eligible()
    calls, persons = detect([row["frame_key"] for row in frames])
    eligibility = census(frames, calls, persons)
    candidates = [row for row in eligibility if row["contained"] == 1]
    selected = evenly_select(candidates) if candidates else []
    manifest = cards(selected) if selected else []
    save("candidates", {
        "identities": identities, "isolation": isolation,
        "eligible": len(eligibility), "with_call": sum(1 for r in eligibility if r["n_calls"]),
        "candidates": len(candidates),
        "candidate_games": len({row["game"] for row in candidates}),
        "selected": len(manifest),
        "selected_games": len({row["game"] for row in selected}),
        "closed_at_limit": len(candidates) < 30,
        "elapsed_seconds": round(time.time() - started, 3)})


if __name__ == "__main__":
    sys.exit(main())
