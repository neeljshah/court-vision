"""G338 pod-only source snapshot, detector arms, and reproducible raw plausibility table."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from pathlib import Path

from scripts.platformkit.tracking.g338_detector_input_decision import (
    decide, intersects_frame, summarize, verify_seal,
)

SALT = "G338-2026-09-08b"
SIZES = (640, 960, 1280, 1920)
UNDECODABLE: list = []
REPO = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def game_id(path: Path) -> str:
    stem = path.stem
    return stem.rsplit("_s", 1)[0] if "_s" in stem else stem


def rank(path: Path) -> str:
    return hashlib.sha256((path.name + SALT).encode("ascii", "replace")).hexdigest()


def probe(path: Path) -> dict:
    import cv2
    cap = cv2.VideoCapture(str(path))
    out = {"path": str(path.resolve()), "bytes": path.stat().st_size,
           "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
           "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
           "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}
    cap.release()
    return out


def select(candidates: list[dict]) -> tuple[list[dict], dict]:
    """Select the preregistered resolution targets, then deterministic fall-through sections."""
    by_name = sorted(candidates, key=lambda row: rank(Path(row["path"])))
    chosen, games = [], set()
    for width, height in ((1920, 1080), (1280, 720)):
        for row in by_name:
            gid = game_id(Path(row["path"]))
            if (row["width"], row["height"]) == (width, height) and gid not in games:
                chosen.append(row); games.add(gid)
                if sum((r["width"], r["height"]) == (width, height) for r in chosen) == 2:
                    break
    for row in by_name:
        gid = game_id(Path(row["path"]))
        if row["height"] >= 720 and gid not in games and len(chosen) < 6:
            chosen.append(row); games.add(gid)
    counts = {"1920x1080": sum((r["width"], r["height"]) == (1920, 1080) for r in chosen),
              "1280x720": sum((r["width"], r["height"]) == (1280, 720) for r in chosen)}
    return chosen, {"resolution_targets": counts, "six_sections_available": len(chosen) == 6,
                    "requirements_met": counts["1920x1080"] >= 2 and counts["1280x720"] >= 2 and len(chosen) == 6}


def indices(source: dict) -> list[int]:
    stride = max(1, source["frames"] // 60)
    offset = int(hashlib.sha256((Path(source["path"]).name + SALT).encode("ascii")).hexdigest()[:8], 16) % stride
    return [offset + i * stride for i in range(60)]


def snapshot(corpus: Path, out: Path) -> Path:
    if not corpus.is_dir():
        raise FileNotFoundError("ABSENT-IN-WORKTREE data/footage_corpus")
    rows = [probe(path) for path in sorted(corpus.rglob("*.mp4"))]
    chosen, status = select(rows)
    for row in chosen:
        row["sha256"] = sha256(Path(row["path"]))
        row["frame_indices"] = indices(row)
    manifest = {"salt": SALT, "selection": status, "corpus": str(corpus.resolve()), "sections": chosen}
    out.mkdir(parents=True, exist_ok=True)
    path = out / "snapshot.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    print("G338_SNAPSHOT " + json.dumps(status), flush=True)
    return path


def _frame(path: str, index: int):
    """Frame below the scoreboard cut; raises RuntimeError when the sealed index will not decode.

    Container metadata over-reports the frame count on some corpus sections, so a failed
    seek retries sequentially before giving up; the caller decides how to handle a failure.
    """
    import cv2
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        cap = cv2.VideoCapture(path)
        for _ in range(index + 1):
            ok, frame = cap.read()
            if not ok:
                break
    cap.release()
    if not ok:
        raise RuntimeError("decode failed at %s:%d" % (path, index))
    from src.tracking.video_handler import TOPCUT
    return frame[TOPCUT:]


def _resolve_frame(section_id: int, path: str, index: int):
    """Caller around `_frame`: on a decode failure, record the index once and return None."""
    try:
        return _frame(path, index)
    except RuntimeError:
        record = {"section": "%06d" % section_id, "frame_index": index}
        if record not in UNDECODABLE:
            UNDECODABLE.append(record)
        return None


def _fallback_arm():
    import cv2
    from scripts.platformkit.tracking.g330_attempt2 import make_arm
    from scripts.platformkit.tracking.g330_panorama_identity import route
    resources = Path(route()._RESOURCES)
    pano = cv2.imread(str(resources / "pano_enhanced.png"))
    if pano is None:
        raise RuntimeError("fallback panorama unavailable")
    return make_arm(pano)


def _gpu_mib() -> int:
    import torch
    return int(torch.cuda.max_memory_allocated() / (1024 * 1024)) if torch.cuda.is_available() else 0


def _check_gpu_lease() -> None:
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("GPU LEASE: CUDA unavailable")
    free, _ = torch.cuda.mem_get_info()
    if free < 8192 * 1024 * 1024:
        raise RuntimeError("GPU LEASE: need 8192 MiB free, have %d MiB" % (free // (1024 * 1024)))


def detect(manifest_path: Path, out: Path) -> tuple[Path, bool]:
    import cv2
    import torch
    import ultralytics
    from src.tracking.advanced_tracker import AdvancedFeetDetector
    _check_gpu_lease()
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    if not manifest["sections"]:
        raise RuntimeError("no source sections available")
    detector = AdvancedFeetDetector([])
    model, conf = detector.model, float(detector._fill_conf_threshold)
    fallback = _fallback_arm()
    raw = out / "raw.jsonl"
    route_files = [REPO / "src/tracking/advanced_tracker.py", REPO / "src/pipeline/unified_pipeline.py"]
    env = {"python": os.sys.version.split()[0], "torch": torch.__version__,
           "ultralytics": ultralytics.__version__, "conf": conf, "classes": [0, 32],
           "route_sha256": {str(p.relative_to(REPO)): sha256(p) for p in route_files}}
    from scripts.platformkit import env_sidecar
    env["g62_sidecar"] = env_sidecar.capture(modules=sorted(env["route_sha256"]), root=REPO)
    h_cache = {}
    with raw.open("w", encoding="ascii") as handle:
        def run_section(section_id, section, sizes):
            counts = {size: 0 for size in sizes}
            for frame_index in section["frame_indices"]:
                frame = _resolve_frame(section_id, section["path"], frame_index)
                if frame is None:
                    continue
                cache_key = (section["sha256"], frame_index)
                if cache_key not in h_cache:
                    matrix = fallback._get_homography(frame)
                    h_cache[cache_key] = None if matrix is None else (fallback.M1 @ matrix).tolist()
                homography = h_cache[cache_key]
                for size in sizes:
                    if torch.cuda.is_available():
                        torch.cuda.reset_peak_memory_stats()
                        torch.cuda.synchronize()
                    began = time.perf_counter()
                    result = model(frame, classes=[0, 32], conf=conf, verbose=False, imgsz=size,
                                   half=detector._use_half, device=getattr(detector, "_yolo_device", 0))
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    ms = (time.perf_counter() - began) * 1000.0
                    xyxy = [] if result[0].boxes is None else result[0].boxes.xyxy.cpu().numpy().tolist()
                    classes = [] if result[0].boxes is None else result[0].boxes.cls.cpu().numpy().tolist()
                    boxes = [box for box, cls in zip(xyxy, classes) if int(cls) == 0]
                    row = {"section": "%06d" % section_id, "source_sha256": section["sha256"],
                           "frame_index": frame_index, "arm": size, "frame_w": frame.shape[1],
                           "frame_h": frame.shape[0], "boxes": boxes, "homography": homography,
                           "map_w": fallback.map_2d.shape[1], "map_h": fallback.map_2d.shape[0],
                           "ms": round(ms, 6), "gpu_mib": _gpu_mib(),
                           "ball_count": sum(int(cls) == 32 for cls in classes),
                           "state_key": "%s:%d:%d" % (section["sha256"], frame_index, size)}
                    handle.write(json.dumps(row, separators=(",", ":")) + "\n")
                    counts[size] += sum(intersects_frame(box, frame.shape[1], frame.shape[0]) for box in boxes)
            return counts

        first = manifest["sections"][0]
        premise_rows = []
        first_counts = run_section(1, first, (640, 1920))
        ratio = (first_counts[1920] / first_counts[640]) if first_counts[640] else None
        premise_rows.append({"section": "000001", "person_rows_640": first_counts[640],
                             "person_rows_1920": first_counts[1920], "ratio": ratio})
        if ratio is not None and ratio < 1.2 and len(manifest["sections"]) > 1:
            second = manifest["sections"][1]
            second_counts = run_section(2, second, (640, 1920))
            ratio2 = (second_counts[1920] / second_counts[640]) if second_counts[640] else None
            premise_rows.append({"section": "000002", "person_rows_640": second_counts[640],
                                 "person_rows_1920": second_counts[1920], "ratio": ratio2})
        premise_false = sum(row["ratio"] is not None and row["ratio"] < 1.2 for row in premise_rows) >= 2
        if not premise_false:
            run_section(1, first, (960, 1280))
            for section_id, section in enumerate(manifest["sections"][1:], 2):
                existing = (960, 1280) if section_id == 2 and len(premise_rows) == 2 else SIZES
                run_section(section_id, section, existing)
    premise = {"binding_before_condition": "1920 person rows >= 1.5 * 640 on same frames",
               "sections": premise_rows, "premise_false": premise_false}
    premise["undecodable_sealed_indices"] = UNDECODABLE
    (out / "premise.json").write_text(json.dumps(premise, indent=2) + "\n", encoding="ascii")
    (out / "environment.json").write_text(json.dumps(env, indent=2) + "\n", encoding="ascii")
    print("G338_PREMISE " + json.dumps(premise), flush=True)
    return raw, premise_false


def score(raw: Path, out: Path) -> Path:
    groups: dict[tuple[str, int], list] = {}
    with raw.open(encoding="ascii") as handle:
        for line in handle:
            row = json.loads(line)
            groups.setdefault((row["section"], int(row["arm"])), []).append(row)
    rows, by_section = [], {}
    for (section, arm), records in sorted(groups.items()):
        summary = summarize(records)
        by_section.setdefault(section, {})[arm] = summary
        rows.append({"section": section, "arm": "%06d" % arm,
                     **{key: ("%06d" % value if isinstance(value, int) else value)
                        for key, value in summary.items()}})
    path = out / "arms.csv"
    fields = list(rows[0]) if rows else ["section", "arm"]
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    decision = decide(by_section)
    manifest = json.loads((out / "snapshot.json").read_text(encoding="ascii"))
    complete = len(by_section) == 6 and all(set(arms) == set(SIZES) for arms in by_section.values())
    if not manifest["selection"]["requirements_met"] or not complete:
        decision["recommended_imgsz"] = None
        decision["failure_mode"] = "required six-section resolution/arm matrix incomplete"
    (out / "decision.json").write_text(json.dumps(decision, indent=2) + "\n", encoding="ascii")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("snapshot", "detect", "score", "run"))
    ap.add_argument("--corpus", default="data/footage_corpus", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--prereg", default="docs/evidence/tracking/g338_prereg_2026-09-08.md", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    seal = verify_seal(args.prereg)
    print("G338_PREREG_SEAL " + seal, flush=True)
    manifest = args.manifest or args.out / "snapshot.json"
    if args.command in ("snapshot", "run"):
        manifest = snapshot(args.corpus, args.out)
    if args.command in ("detect", "run"):
        _, premise_false = detect(manifest, args.out)
    else:
        premise_false = False
    if args.command in ("score", "run") and not premise_false:
        score(args.out / "raw.jsonl", args.out)


if __name__ == "__main__":
    main()
