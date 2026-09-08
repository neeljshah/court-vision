"""G327 -- is the production detector route batch-stable, and is it deterministic?

THREE subcommands, in the order the row runs them:

  `snapshot`  reads the LIVE ROTATING pod corpus ONCE, decodes 3 x 40 frames and
              PERSISTS them beside a per-frame SHA-256 manifest. No detector call and
              no metric of any kind: its only output is the frame set the prereg seals.
  `detect`    runs ON THE POD, IMPORTS the unedited human-gated production detector,
              reads ONLY the snapshot (never the corpus), and writes ONE RAW CSV PER ARM
              with an explicit row for EVERY evaluated frame, zero-box frames included.
  `score`     LOCAL arithmetic. Every reported value is recomputed from those per-arm
              CSVs ALONE -- never from a summary JSON (the attempt-1 defect).

SCREENING ONLY. There is no ground truth here: this row says whether two passes AGREE,
never which one is right, and makes no recall, precision, registration or accuracy claim.
Nothing is adopted and no production default moves.

Rules sealed in `docs/evidence/tracking/g327_prereg_2026-09-08d.md` (attempt 2).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from scripts.platformkit.tracking.g327_arms import canon, run_arm, write_arm_csv
from scripts.platformkit.tracking.g327_report import score
from scripts.platformkit.tracking.g327_sources import (
    CORPUS, MIN_WIDTH, N_GAMES, anchor_of, decode, indices, load_frames, probe,
    save_frames, select_sources, sha256,
)

DEPLOYED = "/workspace/nba-ai-system"
GATED = ("src/tracking/player_detection.py", "src/tracking/advanced_tracker.py")
DAEMON_PIDS = "929149,1039858"   # track_daemon, vol_guard -- OBSERVED, never signalled
# arm -> (batch size, kwarg overrides on the production call, sort own emitted rows).
# ATTEMPT 2 CHANGE, required by the verifier: NMSORD is now its OWN batch-8 detector pass
# whose rows are sorted INSIDE the arm before they are written, not a post-hoc re-sort of
# the batch8 rows. So 7 GPU arms x 120 frames = 840 detector passes. ARM PAD's imgsz is
# filled in from the shape the SINGLE pass was MEASURED to feed, never assumed.
ARMS = {"single": (1, {}, False), "single_repeat": (1, {}, False),
        "batch2": (2, {}, False), "batch8": (8, {}, False),
        "pad": (8, {"imgsz": None}, False), "fp32": (8, {"half": False}, False),
        "nmsord": (8, {}, True)}
MODULES = ("g327_arms.py", "g327_sources.py", "g327_report.py",
           "g327_detector_batch_stability.py")


def _provenance() -> dict:
    return {name: sha256(Path("scripts/platformkit/tracking", name)) for name in MODULES}


def snapshot(args) -> None:
    """Read the rotating corpus ONCE and freeze the sample. No detector, no metric."""
    from src.tracking.video_handler import TOPCUT

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"corpus": CORPUS, "topcut": TOPCUT, "provenance": _provenance(),
                "games": []}
    selected = select_sources()
    manifest["selection_rule"] = {
        "min_width": MIN_WIDTH, "n_games": N_GAMES, "corpus": CORPUS,
        "order": "mtime descending, first clip per game id",
        "selected": [s["game"] for s in selected]}
    print("SELECTED %s" % json.dumps(manifest["selection_rule"]), flush=True)
    rows = ["slot,frame_index,sha256"]
    for slot, src in enumerate(selected, 1):
        anchor = anchor_of(src["path"])
        idxs = indices(anchor)
        src["anchor"] = anchor
        frames, stack_sha, frame_shas = decode(src["path"], idxs, TOPCUT)
        npy = "g327a2_frames_g%d.npy" % slot
        save_frames(out / npy, frames)
        manifest["games"].append(
            {"slot": slot, "game": src["game"], "source": src, "anchor": anchor,
             "frame_indices": idxs, "frame_sha256": frame_shas,
             "stack_sha256": stack_sha, "npy": npy, "fed_shape": list(frames[0].shape)})
        rows.extend("%06d,%06d,%s" % (slot, i, h) for i, h in zip(idxs, frame_shas))
        print("SNAPPED slot=%d %s frames=%d anchor=%d fed_shape=%r stack=%s"
              % (slot, src["game"], len(frames), anchor, list(frames[0].shape),
                 stack_sha), flush=True)
    (out / "g327a2_frames.csv").write_text("\n".join(rows) + "\n", encoding="ascii")
    (out / "g327a2_snapshot.json").write_text(json.dumps(manifest, indent=1),
                                              encoding="ascii")
    print("WROTE %s" % (out / "g327a2_snapshot.json"), flush=True)


def verify_snapshot(manifest: dict, snap: Path) -> list:
    """Reload each snapshotted game and re-hash EVERY frame against the sealed list.

    A game with any mismatched or missing frame is DROPPED, with its reason recorded, and
    the run continues on what verifies -- never silently, and never with a substitute."""
    kept = []
    for g in manifest["games"]:
        path, n = snap / g["npy"], len(g["frame_sha256"])
        if not path.is_file():
            g["verified"] = {"ok": 0, "n": n, "reason": "snapshot file absent"}
            continue
        frames = load_frames(path)
        got = [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]
        ok = sum(1 for a, b in zip(got, g["frame_sha256"]) if a == b)
        g["verified"] = {"ok": ok, "n": n,
                         "reason": "" if ok == n else "frame hash mismatch"}
        print("VERIFY slot=%d %s %d/%d frame hashes match"
              % (g["slot"], g["game"], ok, n), flush=True)
        if ok == n and len(frames) == len(g["frame_indices"]):
            kept.append((g, frames))
    return kept


def detect(args) -> None:
    import cv2
    import torch
    import ultralytics
    from src.tracking.advanced_tracker import AdvancedFeetDetector
    from src.tracking.video_handler import TOPCUT

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    snap = Path(args.snapshot).resolve()
    manifest = json.loads((snap / "g327a2_snapshot.json").read_text(encoding="ascii"))
    ps = ["bash", "-lc", "ps -o pid,etime,rss,args -p %s" % DAEMON_PIDS]
    gpu = probe(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader"])
    apps = probe(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                  "--format=csv,noheader"])
    used, total = (int(s.strip().split()[0])
                   for s in gpu["stdout"].splitlines()[0].split(","))
    assert total - used >= 8192, "GPU LEASE: need 8192 MiB free, have %d" % (total - used)
    probes = {"gpu": gpu, "compute_apps": apps, "daemon_ps": probe(ps),
              "df": probe(["df", "-m", "/workspace"])}
    probes["dd_fsync"] = probe(["dd", "if=/dev/zero", "of=%s" % (out / "fsync.bin"),
                                "bs=1M", "count=8", "conv=fsync"])
    assert probes["dd_fsync"]["rc"] == 0, "FAILED dd conv=fsync probe"
    (out / "fsync.bin").unlink()
    before = {p: sha256(Path(DEPLOYED, p)) for p in GATED}
    before["yolov8n.pt"] = sha256(Path(DEPLOYED, "yolov8n.pt"))
    for stem in ("yolov8n.pt", "yolov8n-pose.pt"):  # the DEPLOYED weights, never a download
        if Path(DEPLOYED, stem).is_file() and not Path(stem).exists():
            Path(stem).write_bytes(Path(DEPLOYED, stem).read_bytes())

    detector = AdvancedFeetDetector([])
    base = {"classes": [0], "conf": float(detector._fill_conf_threshold),
            "verbose": False,
            "imgsz": int(getattr(detector, "_infer_imgsz", detector._yolo_imgsz)),
            "half": bool(detector._use_half),
            "device": getattr(detector, "_yolo_device", 0 if detector._use_half else "cpu")}
    print("ROUTE %s" % json.dumps({k: str(v) for k, v in base.items()}), flush=True)
    # The network input is captured with a torch forward pre-hook on the LIVE predictor
    # module: ultralytics runs a fused AutoBackend copy and REBUILDS its predictor when
    # the call kwargs change, which silently drops a predictor-level wrapper and lost
    # every tensor record for the fp32 arm in attempt 1's job ...2224.
    sink: list = []

    def _rec(_m, a):
        sink.append({"tensor_shape": list(a[0].shape), "dtype": str(a[0].dtype)})

    def hook_live():
        pred = getattr(detector.model, "predictor", None)
        target = getattr(pred, "model", None)
        target = getattr(target, "model", target) or detector.model.model
        return target.register_forward_pre_hook(_rec)

    kept = verify_snapshot(manifest, snap)
    summary = {"screening_only": True, "ground_truth": None, "topcut": TOPCUT,
               "route_kwargs": {k: str(v) for k, v in base.items()},
               "registered_conf": 0.3, "conf_source": "route _fill_conf_threshold",
               "env": {"python": sys.version.split()[0], "torch": torch.__version__,
                       "ultralytics": ultralytics.__version__, "cv2": cv2.__version__,
                       "gpu": torch.cuda.get_device_name(0)},
               "gated_before": before, "provenance": _provenance(),
               "snapshot_provenance": manifest["provenance"],
               "selection_rule": manifest["selection_rule"],
               "verified": [{"slot": g["slot"], "game": g["game"], **g["verified"]}
                            for g in manifest["games"]],
               "games": [], "arm_rows": {}}
    per_arm_games: dict = {arm: [] for arm in ARMS}
    for g, frames in kept:
        slot, idxs = g["slot"], g["frame_indices"]
        single_hw, per_arm = None, {}
        for arm, (bs, over, sort_rows) in ARMS.items():
            if arm == "pad":
                # Pinned to the shape the SINGLE pass was MEASURED to feed, never assumed.
                over = {"imgsz": list(single_hw)} if single_hw else {}
            kwargs = dict(base, **over)

            def call(part, _k=kwargs):
                res = detector.model(list(part), **_k)
                rows = []
                for r in res:
                    b = r.boxes
                    if b is None or not len(b):
                        rows.append(([], [], []))
                    else:
                        rows.append((b.xyxy.cpu().numpy(), b.conf.cpu().numpy(),
                                     b.cls.cpu().numpy()))
                return rows

            call([frames[0]])          # warm: build the predictor for THESE kwargs
            handle = hook_live()       # then hook the module that will actually run
            mark = len(sink)
            rows, ms = run_arm(list(frames), call, bs)
            handle.remove()
            if sort_rows:
                # ARM NMSORD sorts ITS OWN pass INSIDE the arm, before its rows are
                # written -- so its CSV carries emitted rows, not a re-sort of batch8's.
                rows = [(c[:, :4], c[:, 4], c[:, 5])
                        for c in (canon(r, sort=True) for r in rows)]
            tensors = sink[mark:]
            if arm == "single" and tensors:
                single_hw = tuple(tensors[0]["tensor_shape"][2:])
            per_arm_games[arm].append((slot, idxs, rows))
            per_arm[arm] = {"batch": bs, "ms_per_frame_us": int(round((ms or 0) * 1000)),
                            "kwargs": {k: str(v) for k, v in kwargs.items()},
                            "tensor_shapes": sorted({tuple(t["tensor_shape"])
                                                     for t in tensors}),
                            "tensor_dtypes": sorted({t["dtype"] for t in tensors}),
                            "boxes_total": int(sum(len(r[0]) for r in rows)),
                            "zero_box_frames": int(sum(1 for r in rows if not len(r[0])))}
            print("ARM slot=%d %s %s" % (slot, arm, json.dumps(per_arm[arm])), flush=True)
        summary["games"].append({"slot": slot, "game": g["game"], "source": g["source"],
                                 "frame_indices": idxs, "fed_shape": g["fed_shape"],
                                 "stack_sha256": g["stack_sha256"], "arms": per_arm})
    meta = ["arm,slot,batch,ms_per_frame_us,tensor_shape,dtype,boxes_total,"
            "zero_box_frames"]
    for arm in ARMS:
        path = out / ("g327a2_boxes_%s.csv" % arm)
        summary["arm_rows"][arm] = write_arm_csv(path, arm, per_arm_games[arm])
        for g in summary["games"]:
            a = g["arms"][arm]
            meta.append("%s,%06d,%06d,%06d,%s,%s,%06d,%06d" % (
                arm, g["slot"], a["batch"], a["ms_per_frame_us"],
                " ".join("-".join("%06d" % d for d in s) for s in a["tensor_shapes"]),
                " ".join(a["tensor_dtypes"]), a["boxes_total"], a["zero_box_frames"]))
    (out / "g327a2_arms.csv").write_text("\n".join(meta) + "\n", encoding="ascii")
    summary["gated_after"] = {p: sha256(Path(DEPLOYED, p)) for p in GATED}
    summary["gated_after"]["yolov8n.pt"] = sha256(Path(DEPLOYED, "yolov8n.pt"))
    summary["gated_unchanged"] = summary["gated_after"] == before
    probes["gpu_after"] = probe(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                                 "--format=csv,noheader"])
    probes["daemon_ps_after"] = probe(ps)
    (out / "g327a2_probes.txt").write_text(
        "\n\n".join("$ %s\nrc=%d\n%s%s" % (" ".join(v["command"]), v["rc"], v["stdout"],
                                           v["stderr"]) for v in probes.values()),
        encoding="ascii")
    (out / "g327a2_summary.json").write_text(json.dumps(summary, indent=1),
                                             encoding="ascii")
    print("WROTE %s" % (out / "g327a2_summary.json"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("snapshot")
    n.add_argument("--output", type=Path, default=Path("g327a2_snap"))
    n.set_defaults(func=snapshot)
    d = sub.add_parser("detect")
    d.add_argument("--snapshot", required=True)
    d.add_argument("--output", type=Path, default=Path("g327a2_out"))
    d.set_defaults(func=detect)
    s = sub.add_parser("score")
    s.add_argument("--artifact", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--table", required=True)
    s.set_defaults(func=score)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
