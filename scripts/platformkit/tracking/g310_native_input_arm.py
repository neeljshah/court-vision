"""G310 -- SCREENING row: production-default vs native detector input size.

SCREENING ONLY: no ground truth, no registration or pass claim. More rows per
frame can mean more players found OR more false boxes; this cannot tell them apart.
Nothing under src/ is edited. ARM N sets the detector INSTANCE attribute
`_infer_imgsz` at runtime -- the attribute unified_pipeline.py:917/:1021 and
advanced_tracker.py:425/:1188 read back through getattr. ARM P sets nothing.
Both arms carry the same passive call-site recorder, forwarding every argument.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import runpy
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
NATIVE_IMGSZ = 1920
GPU_FREE_MIN_MIB = 8192
WALL_BUDGET_S = 3600
CORPUS = "data/footage_corpus"


def footpoint(row: dict) -> tuple:
    """Image-space footpoint convention: bbox BOTTOM-CENTRE ((x1+x2)/2, y2)."""
    return (float(row["bbox_x1"]) + float(row["bbox_x2"])) / 2.0, float(row["bbox_y2"])


def p95(values: list):
    """p95 at the ROUNDED LINEAR INDEX round(0.95 * (n - 1)), NOT nearest-rank; kept unchanged
    so the committed G310 p95 columns keep their meaning (B2). G331 prints both estimators."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int(round(0.95 * (len(ordered) - 1)))]


def proxies(rows: list, ball_rows: list, evaluated_frames, source_height: int) -> dict:
    """Image-space screening proxies. Every denominator is named in the result."""
    by_track: dict = {}
    for row in rows:
        by_track.setdefault(str(row["player_id"]), []).append(row)
    steps = []
    for track in by_track.values():
        track = sorted(track, key=lambda r: int(float(r["frame"])))
        for a, b in zip(track, track[1:]):
            ax, ay = footpoint(a)
            bx, by = footpoint(b)
            steps.append(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / float(source_height))
    lengths = [len(v) for v in by_track.values()]
    detected = sum(1 for r in ball_rows
                   if str(r.get("detected", "")).strip().lower() in ("1", "true", "yes"))
    den = float(evaluated_frames) if evaluated_frames is not None else None  # G331: 0 is real
    return {
        "person_rows": len(rows),
        "denominator_evaluated_frames": evaluated_frames,
        "frames_with_rows": len({int(float(r["frame"])) for r in rows}),
        "person_rows_per_evaluated_frame": (len(rows) / den) if den else None,
        "distinct_track_ids": len(by_track),
        "median_track_len_rows": statistics.median(lengths) if lengths else None,
        "ball_rows_total": len(ball_rows),
        "ball_rows_detected": detected,
        "p95_norm_footpoint_step": p95(steps),
        "denominator_step_pairs": len(steps),
        "source_height": source_height,
    }


def read_csv(path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))


def proxies_for_dir(data_dir, source_height: int) -> dict:
    data_dir, evaluated, why = Path(data_dir), None, "sidecar_absent"
    sidecar = data_dir / "evaluated_frame_count.json"
    if sidecar.exists():
        side = json.loads(sidecar.read_text())
        evaluated, why = side.get("evaluated_frames"), side.get("reason")
    out = proxies(read_csv(data_dir / "tracking_data.csv"),
                  read_csv(data_dir / "ball_tracking.csv"), evaluated, source_height)
    # The route may report evaluated_frames=null; carry ITS reason, never substitute.
    out["denominator_reason"] = why
    return out


class _Recorder:
    """Passive pass-through around the YOLO callable; records the imgsz kwarg."""

    def __init__(self, model, sink):
        object.__setattr__(self, "_m", model)
        object.__setattr__(self, "_s", sink)

    def __call__(self, *args, **kwargs):
        object.__getattribute__(self, "_s").append(kwargs.get("imgsz"))
        return object.__getattribute__(self, "_m")(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_m"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_m"), name, value)


def run_arm(arm: str, video: str, game_id: str, frames: int, data_dir: str, out_json: str):
    """Run the daemon's own basketball route once; ARM N sets _infer_imgsz=1920."""
    from src.tracking.advanced_tracker import AdvancedFeetDetector
    call_sizes, ctor_sizes = [], []
    original = AdvancedFeetDetector.__init__

    def patched(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if arm == "N":
            self._infer_imgsz = NATIVE_IMGSZ
        ctor_sizes.append(int(getattr(self, "_infer_imgsz", self._yolo_imgsz)))
        self.model = _Recorder(self.model, call_sizes)

    AdvancedFeetDetector.__init__ = patched
    argv = [str(REPO / "scripts" / "run_clip.py"), "--video", video, "--game-id", game_id,
            "--no-show", "--frames", str(frames), "--data-dir", data_dir]
    saved, rc = sys.argv[:], 0
    sys.argv = argv
    start = time.time()
    try:
        runpy.run_path(argv[0], run_name="__main__")
    except SystemExit as exc:
        rc = int(exc.code or 0)
    finally:
        sys.argv = saved
        AdvancedFeetDetector.__init__ = original
    summary = {"arm": arm, "game_id": game_id, "video": os.path.abspath(video),
               "frames_requested": frames, "argv": argv[1:], "rc": rc,
               "wall_seconds": round(time.time() - start, 1),
               "imgsz_at_construction": sorted(set(ctor_sizes)),
               "imgsz_observed_at_call_site": sorted({v for v in call_sizes if v is not None}),
               "detector_calls_recorded": len(call_sizes)}
    Path(out_json).write_text(json.dumps(summary, indent=2) + "\n")
    print("G310_ARM_SUMMARY " + json.dumps(summary))
    return summary


def _sh(cmd: list, timeout: int = 120) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception as exc:  # a probe failure is reported, never fatal
        return "PROBE_ERROR " + type(exc).__name__ + " " + str(exc)


def gpu_probe() -> dict:
    used_total = _sh(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                      "--format=csv,noheader"])
    apps = _sh(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader"])
    try:
        used, total = [int(p.strip().split()[0]) for p in used_total.split(",")]
        free = total - used
    except Exception:
        free = None
    return {"query_gpu": used_total, "query_compute_apps": apps, "free_mib": free}


def gpu_lease(probes: list, max_waits: int = 30) -> dict:
    """Proceed only when free VRAM >= 8192 MiB. Never kills, never signals."""
    probe = gpu_probe()
    for _ in range(max_waits):
        probes.append(probe)
        print("GPU_PROBE " + json.dumps(probe))
        if probe["free_mib"] is not None and probe["free_mib"] >= GPU_FREE_MIN_MIB:
            return probe
        time.sleep(60)
        probe = gpu_probe()
    probes.append(probe)
    return probe


def disk_probe() -> str:
    value = _sh(["bash", "-lc", "timeout 60 du -sm /workspace | cut -f1"], timeout=90)
    return value if value else "UNKNOWN"


def ffprobe(path: str) -> dict:
    raw = _sh(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,r_frame_rate,nb_frames", "-show_entries",
               "format=duration", "-of", "default=nw=1:nk=1", path])
    parts = [p for p in raw.splitlines() if p.strip()]
    out = {"path": os.path.abspath(path), "raw": parts,
           "bytes": os.path.getsize(path) if os.path.exists(path) else None}
    try:
        out["width"], out["height"] = int(parts[0]), int(parts[1])
        out["fps_ratio"], out["nb_frames"] = parts[2], parts[3]
        out["duration_s"] = float(parts[-1])
    except Exception:
        out["width"] = out["height"] = None
    return out


def _spawn(arm: str, video: str, game_id: str, frames: int, data_dir: str, tag: str,
           out_root: Path) -> dict:
    """One route run as its own process, so the 3,600 s wall stop is enforceable."""
    os.makedirs(data_dir, exist_ok=True)
    summary_path = str(Path(data_dir) / "run_summary.json")
    log_path = out_root / (tag + ".log")
    cmd = [sys.executable, "-m", "scripts.platformkit.tracking.g310_native_input_arm",
           "--arm", arm, "--video", video, "--game-id", game_id, "--frames", str(frames),
           "--data-dir", data_dir, "--out-json", summary_path]
    start = time.time()
    with open(log_path, "w", encoding="utf-8", errors="replace") as handle:
        try:
            rc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT,
                                timeout=WALL_BUDGET_S).returncode
            status = "COMPLETE"
        except subprocess.TimeoutExpired:
            rc, status = None, "BUDGET_LIMIT"
    result = {"tag": tag, "arm": arm, "game_id": game_id, "status": status, "rc": rc,
              "wall_seconds": round(time.time() - start, 1), "log": str(log_path),
              "data_dir": data_dir}
    if Path(summary_path).exists():
        result["run_summary"] = json.loads(Path(summary_path).read_text())
    print("G310_RUN " + json.dumps(result))
    return result


def drive(games: list, frames: int, out_root: Path, repeat_game: str) -> dict:
    out_root.mkdir(parents=True, exist_ok=True)
    probed = [ffprobe(str(p)) for p in sorted(Path(CORPUS).glob("*.mp4"))]
    eligible = [p for p in probed if p.get("width") == 1920 and p.get("height") == 1080]
    plan: dict = {}
    for game in games:
        match = [p for p in eligible if game in p["path"].replace(os.sep, "/").split("/")[-1]]
        if not match:
            raise SystemExit("G310: no eligible 1920x1080 source for " + game)
        plan[game] = match[0]
    gpu_probes, runs = [], []
    disk_before = disk_probe()
    for game in games:
        for arm in ("P", "N"):
            gpu_lease(gpu_probes)
            tag = game + "_arm" + arm
            runs.append(_spawn(arm, plan[game]["path"], game, frames,
                               str(out_root / tag), tag, out_root))
    gpu_lease(gpu_probes)
    tag = repeat_game + "_armP_repeat"
    runs.append(_spawn("P", plan[repeat_game]["path"], repeat_game, frames,
                       str(out_root / tag), tag, out_root))
    for run in runs:
        run["proxies"] = proxies_for_dir(run["data_dir"], plan[run["game_id"]]["height"])
    report = {"spec": "G310",
              "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "frames_requested": frames, "wall_budget_s": WALL_BUDGET_S,
              "native_imgsz": NATIVE_IMGSZ, "corpus_probed": probed,
              "eligible_1920x1080": [p["path"] for p in eligible],
              "rejected_count": len(probed) - len(eligible),
              "games_used": games, "repeat_game": repeat_game, "gpu_probes": gpu_probes,
              "disk_du_sm_before": disk_before, "disk_du_sm_after": disk_probe(),
              "runs": runs}
    dest = Path("docs/evidence/g310")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "g310_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    keys = sorted({k for r in runs for k in r["proxies"]})
    with (dest / "g310_proxies.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["tag", "game_id", "arm", "status", "wall_seconds"] + keys)
        for run in runs:
            writer.writerow([run["tag"], run["game_id"], run["arm"], run["status"],
                             run["wall_seconds"]] + [run["proxies"].get(k) for k in keys])
    print("G310_REPORT_WRITTEN " + str(dest))
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="G310 native-input screening arm")
    ap.add_argument("--arm", choices=["P", "N"])
    ap.add_argument("--video")
    ap.add_argument("--game-id")
    ap.add_argument("--frames", type=int, default=900)
    ap.add_argument("--data-dir")
    ap.add_argument("--out-json")
    ap.add_argument("--games", default="")
    ap.add_argument("--repeat-game", default="")
    ap.add_argument("--out-root", default="g310_out")
    args = ap.parse_args()
    if args.arm and args.video:
        run_arm(args.arm, args.video, args.game_id, args.frames, args.data_dir, args.out_json)
        return
    games = [g for g in args.games.split(",") if g]
    drive(games, args.frames, Path(args.out_root), args.repeat_game or games[0])


if __name__ == "__main__":
    main()
