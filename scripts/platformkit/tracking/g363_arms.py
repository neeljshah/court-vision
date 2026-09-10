"""G363 arm runner: the sealed detection arms, run one at a time on the pod GPU.

Sealed by docs/evidence/tracking/g363_ball_coverage_2026-09-09/g363_prereg_2026-09-09.md.
The deployed detector is IMPORTED from the deploy tree and never edited: the model
handle comes from src.tracking.ball_detect_track._get_ball_yolo_model, and the
deployed class filter and radius guard are reproduced here so arm A0 reproduces
the deployed call exactly.  Arms run sequentially; a VRAM floor is checked first.
"""
from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_var] = "1"

import csv
import hashlib
import math
import subprocess
import sys
import time
from pathlib import Path

DEPLOYED_IMGSZ, DEPLOYED_CONF = 384, 0.05
MAX_RADIUS_PX = 50
TILE_OVERLAP = 0.20
DEDUPE_PX = 24.0
TEMPORAL_RADIUS_720P = 96.0
CUT_CORRELATION = 0.5
MIN_FREE_VRAM_MIB = 4000
TARGET_HEIGHT = 720.0

ARMS: dict[str, dict] = {
    "A0": {"imgsz": DEPLOYED_IMGSZ, "conf": DEPLOYED_CONF, "tile": 0, "temporal": False},
    "A1": {"imgsz": 640, "conf": 0.05, "tile": 0, "temporal": False},
    "A2": {"imgsz": 640, "conf": 0.10, "tile": 0, "temporal": False},
    "A3": {"imgsz": 640, "conf": 0.25, "tile": 0, "temporal": False},
    "A4": {"imgsz": 960, "conf": 0.05, "tile": 0, "temporal": False},
    "A5": {"imgsz": 960, "conf": 0.10, "tile": 0, "temporal": False},
    "A6": {"imgsz": 640, "conf": 0.05, "tile": 2, "temporal": False},
    "A7": {"imgsz": None, "conf": None, "tile": None, "temporal": True},
    "A8": {"imgsz": None, "conf": None, "tile": None, "temporal": False, "finetune": True},
}
PRED_FIELDS = ("arm", "inherits", "split", "frame_key", "rank", "x", "y", "w", "h",
               "score", "tick_history", "source", "imgsz", "conf")


def free_vram_mib() -> int:
    """Free VRAM on the single pod GPU; an unreadable probe reports zero."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=60).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return 0


def load_detector(deploy_root: str):
    """Import the deployed detector module read-only and return it with its model."""
    if deploy_root not in sys.path:
        sys.path.insert(0, deploy_root)
    import importlib

    module = importlib.import_module("src.tracking.ball_detect_track")
    return module, module._get_ball_yolo_model()


def route_hashes(deploy_root: str) -> dict[str, str]:
    """Contract A11 code identity for every route file the arms exercise."""
    hashes = {}
    for relative in ("src/tracking/ball_detect_track.py", "models/weights/yolov8n_ball.pt"):
        path = Path(deploy_root) / relative
        if path.exists():
            digested = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digested.update(chunk)
            hashes[relative] = digested.hexdigest()
    return hashes


def detect(module, model, image, imgsz: int, conf: float) -> list[tuple]:
    """Boxes from one image with the deployed class filter and radius guard."""
    results = model(image, imgsz=imgsz, conf=conf, half=True, device=0, verbose=False)
    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return []
    classes = boxes.cls.cpu().numpy() if boxes.cls is not None else None
    scores = boxes.conf.cpu().numpy()
    corners = boxes.xyxy.cpu().numpy()
    if classes is not None and not module._ball_yolo_is_coco:
        keep = classes == 0
        scores, corners = scores[keep], corners[keep]
    height, width = image.shape[:2]
    out = []
    for score, corner in zip(scores, corners):
        x1, y1 = max(0, int(corner[0])), max(0, int(corner[1]))
        x2, y2 = min(width, int(corner[2])), min(height, int(corner[3]))
        if x2 <= x1 or y2 <= y1:
            continue
        radius = max(1, ((x2 - x1) + (y2 - y1)) // 4)
        if radius > MAX_RADIUS_PX:
            continue
        out.append(((x1 + x2) // 2, (y1 + y2) // 2, x2 - x1, y2 - y1, float(score)))
    return sorted(out, key=lambda box: -box[4])


def tiles(image, count: int) -> list[tuple[int, int, object]]:
    """count x count crops at native pixel scale with the sealed overlap."""
    height, width = image.shape[:2]
    tile_w = int(round(width * (1.0 + TILE_OVERLAP) / count))
    tile_h = int(round(height * (1.0 + TILE_OVERLAP) / count))
    out = []
    for row in range(count):
        for column in range(count):
            x0 = min(int(round(column * (width - tile_w) / max(1, count - 1))), width - tile_w)
            y0 = min(int(round(row * (height - tile_h) / max(1, count - 1))), height - tile_h)
            out.append((max(0, x0), max(0, y0), image[max(0, y0):y0 + tile_h, max(0, x0):x0 + tile_w]))
    return out


def dedupe(boxes: list[tuple]) -> list[tuple]:
    """Suppress the lower-scored of two boxes closer than the sealed crop distance."""
    kept: list[tuple] = []
    for box in sorted(boxes, key=lambda item: -item[4]):
        if all(math.hypot(box[0] - other[0], box[1] - other[1]) > DEDUPE_PX for other in kept):
            kept.append(box)
    return kept


def is_cut(cv2, first, second) -> bool:
    """A shot boundary resets the causal history; grey 32-bin histogram correlation."""
    grids = [cv2.calcHist([cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)], [0], None, [32], [0, 256])
             for image in (first, second)]
    for grid in grids:
        cv2.normalize(grid, grid, 0, 1, cv2.NORM_MINMAX)
    return float(cv2.compareHist(grids[0], grids[1], cv2.HISTCMP_CORREL)) < CUT_CORRELATION


def temporal_keep(observed: list[tuple], history: list[tuple], scale: float) -> list[tuple]:
    """Causal 3-tick suppression: drop a box far from the extrapolated history."""
    if len(history) < 2:
        return observed
    predicted = (2 * history[-1][0] - history[-2][0], 2 * history[-1][1] - history[-2][1])
    return [box for box in observed
            if math.hypot(box[0] - predicted[0], box[1] - predicted[1]) * scale
            <= TEMPORAL_RADIUS_720P]


def _appender(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    handle = path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=list(PRED_FIELDS), lineterminator="\n")
    if not exists:
        writer.writeheader()
    return handle, writer


def run(args) -> None:
    """Run one named arm over the cached frames of one split."""
    import cv2

    from scripts.platformkit.tracking.g363_ball_coverage import read_csv

    cv2.setNumThreads(1)
    arm = args.arm
    if arm not in ARMS:
        raise SystemExit("unknown arm " + arm)
    if ARMS[arm].get("finetune"):
        raise SystemExit("A8 LIMIT: the fine-tune arm needs >= 500 audited boxes; skip it")
    plan = dict(ARMS[arm])
    if plan["temporal"]:
        if args.inherit not in ARMS or ARMS[args.inherit]["temporal"]:
            raise SystemExit("A7 needs --inherit set to the development winner among A1-A6")
        plan.update({key: ARMS[args.inherit][key] for key in ("imgsz", "conf", "tile")})
    free = free_vram_mib()
    if free < MIN_FREE_VRAM_MIB:
        raise SystemExit(f"VRAM floor: {free} MiB free, {MIN_FREE_VRAM_MIB} MiB required")
    module, model = load_detector(args.deploy_root)
    if model is None:
        raise SystemExit("the deployed detector returned no model handle")
    print("ROUTE " + " ".join(f"{key}={value}" for key, value in
                              sorted(route_hashes(args.deploy_root).items())))
    print(f"VRAM free_mib={free} coco_fallback={module._ball_yolo_is_coco} arm={arm} "
          f"imgsz={plan['imgsz']} conf={plan['conf']} tile={plan['tile']}")
    frames = [row for row in read_csv(Path(args.frames)) if row["split"] == args.split]
    handle, writer = _appender(Path(args.out))
    started, decoded, mismatches = time.time(), 0, 0
    cache = Path(args.cache)
    for row in frames:
        image = cv2.imread(str(cache / (row["frame_key"] + ".png")))
        if image is None:
            print("ABSENT-CACHE " + row["frame_key"])
            continue
        decoded += 1
        scale = TARGET_HEIGHT / image.shape[0]
        if plan["tile"]:
            boxes = dedupe([(box[0] + x0, box[1] + y0) + box[2:]
                            for x0, y0, crop in tiles(image, plan["tile"])
                            for box in detect(module, model, crop, plan["imgsz"], plan["conf"])])
            source = "tile" + str(plan["tile"])
        else:
            boxes, source = detect(module, model, image, plan["imgsz"], plan["conf"]), "full"
        history: list[tuple] = []
        if plan["temporal"]:
            neighbours = [cv2.imread(str(cache / (row[key] + ".png")))
                          for key in ("m2_sha256", "m1_sha256")]
            if all(item is not None for item in neighbours) and not is_cut(cv2, neighbours[1], image):
                history = [found[0] for found in
                           (detect(module, model, neighbour, plan["imgsz"], plan["conf"])
                            for neighbour in neighbours) if found]
            boxes = temporal_keep(boxes, history, scale)
        common = {"arm": arm, "inherits": args.inherit, "split": args.split,
                  "frame_key": row["frame_key"], "imgsz": plan["imgsz"], "conf": plan["conf"]}
        for rank, box in enumerate(boxes):
            writer.writerow({**common, "rank": rank, "x": box[0], "y": box[1], "w": box[2],
                             "h": box[3], "score": round(box[4], 6),
                             "tick_history": "OBSERVED", "source": source})
        for index, box in enumerate(history):
            writer.writerow({**common, "rank": -1, "x": box[0], "y": box[1], "w": box[2],
                             "h": box[3], "score": round(box[4], 6),
                             "tick_history": "INFERRED", "source": "history" + str(index)})
        if arm == "A0":
            deployed = module.BallDetectTrack._detect_ball_yolo(None, image)
            top = (boxes[0][0], boxes[0][1], max(1, (boxes[0][2] + boxes[0][3]) // 4)) if boxes else None
            mismatches += int(deployed != top)
    handle.close()
    elapsed = time.time() - started
    print(f"ARM {arm} split={args.split} frames={decoded} gpu_minutes={elapsed / 60.0:.2f} "
          f"fps={decoded / elapsed if elapsed else 0.0:.2f} a0_fidelity_mismatches={mismatches}")
