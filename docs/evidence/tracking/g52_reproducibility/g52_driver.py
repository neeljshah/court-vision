import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/workspace/nba-ai-system")
VIDEOS = {"nyYk": ROOT / "data/footage_corpus/tennis__tennis_nyYk2nPZAwY_720p.mp4", "tennis09": ROOT / "data/footage_corpus/tennis__tennis_09.mp4", "tennis10": ROOT / "data/footage_corpus/tennis__tennis_10.mp4"}
EXPECTED = [("nyYk", 5715, 6014, 0.61), ("nyYk", 33105, 33404, 0.99), ("nyYk", 33855, 34154, 0.9966666666666667), ("nyYk", 41985, 42284, 0.5733333333333334), ("nyYk", 43830, 44129, 0.56), ("tennis09", 615, 914, 0.7066666666666667), ("tennis09", 5070, 5369, 1.0), ("tennis09", 5775, 6074, 0.5933333333333334), ("tennis09", 6960, 7259, 1.0), ("tennis09", 7140, 7439, 1.0), ("tennis10", 150, 449, 0.39666666666666667), ("tennis10", 3585, 3884, 0.46), ("tennis10", 3930, 4229, 0.6766666666666666), ("tennis10", 6345, 6644, 0.8433333333333334), ("tennis10", 6405, 6704, 0.6533333333333333)]
OUT = Path("/tmp/cx_g52_tennis_reproducibility_20260902.jsonl")


def emit(record):
    record["timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = json.dumps(record, sort_keys=True)
    print(line, flush=True)
    with OUT.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def one(match, start, stop, mode):
    if mode == "cpu_pinned":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    if mode in ("gpu_pinned", "cpu_pinned"):
        from scripts.platformkit.detection.deterministic import configure_deterministic_inference
        configure_deterministic_inference(20260901)
    from scripts.platformkit.tracking.tennis_sequential_plan import run_range
    result = run_range(VIDEOS[match], start, stop)
    return {"type": "range", "match": match, "start": start, "stop": stop, "mode": mode, "coverage": result["solved_frame_coverage"], "decoded_frames": result["decoded_frames"], "fresh_solves": result["fresh_solves"], "drift_checked_reuses": result["drift_checked_reuses"]}


def child(match, start, stop, mode):
    code = "import base64,os;exec(compile(base64.b64decode(os.environ['G52_SOURCE']),'g52_driver','exec'))"
    completed = subprocess.run([sys.executable, "-c", code, "one", match, str(start), str(stop), mode], cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, check=True)
    return json.loads(completed.stdout.strip().splitlines()[-1])


def decode_probe(match, frame):
    import cv2
    values = []
    for _ in range(10):
        capture = cv2.VideoCapture(str(VIDEOS[match]))
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, image = capture.read()
        capture.release()
        if not ok:
            raise RuntimeError("decode failed %s %s" % (match, frame))
        values.append(hashlib.sha256(image.tobytes()).hexdigest())
    emit({"type": "decode_probe", "match": match, "frame": frame, "runs": 10, "distinct_sha256": sorted(set(values)), "byte_identical": len(set(values)) == 1})


def main():
    if len(sys.argv) == 6 and sys.argv[1] == "one":
        print(json.dumps(one(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]), sort_keys=True))
        return
    import cv2
    files = [ROOT / "scripts/platformkit/tracking/tennis_sequential_plan.py", ROOT / "domains/tennis/tracking/camera_lock.py", ROOT / "domains/tennis/tracking/court_lines.py"]
    emit({"type": "environment", "cv2": cv2.__version__, "seed": 20260901, "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}})
    measured = []
    for match, start, stop, coverage in EXPECTED:
        record = child(match, start, stop, "gpu_baseline")
        emit(record)
        measured.append(record["coverage"] == coverage)
    emit({"type": "premise", "baseline_identical_all_15": all(measured), "identical_ranges": sum(measured), "total_ranges": len(measured)})
    if all(measured):
        return
    decode_probe("nyYk", 5715)
    decode_probe("tennis10", 150)
    for mode in ("gpu_baseline", "gpu_pinned", "cpu_pinned"):
        for match, start, stop in (("nyYk", 5715, 6014), ("tennis10", 150, 449)):
            for repeat in range(1, 6):
                record = child(match, start, stop, mode)
                record["repeat"] = repeat
                emit(record)


if __name__ == "__main__":
    main()
