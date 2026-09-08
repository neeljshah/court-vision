"""G327 -- is the production detector route batch-stable, and is it deterministic?

`detect` runs ON THE POD and IMPORTS the unedited human-gated production detector;
`score` is LOCAL arithmetic over the committed CSVs and never over a pod-side number.

SCREENING ONLY. There is no ground truth here: this row says whether two passes
AGREE, never which one is right, and makes no recall, precision, registration or
accuracy claim. Nothing is adopted and no production default moves.

Rules sealed in `docs/evidence/tracking/g327_prereg_2026-09-08c.md` (attempt 3, seal
6548ebe7d340cb94c021ab363d574438f976628ab5d52ba7c7ebceac6f130534).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from scripts.platformkit.tracking.g327_arms import (
    compare, read_boxes_csv, rows_for, run_arm, write_boxes_csv,
)
from scripts.platformkit.tracking.g327_sources import (
    CORPUS, MIN_WIDTH, N_GAMES, anchor_of, decode, indices, probe, select_sources,
    sha256,
)

DEPLOYED = "/workspace/nba-ai-system"
GATED = ("src/tracking/player_detection.py", "src/tracking/advanced_tracker.py")
# ATTEMPT 3 (prereg g327_prereg_2026-09-08c.md, seal 6548ebe7d3). The pod corpus is a LIVE
# ROTATING QUEUE -- the tracking daemon deletes each clip after tracking it (119 -> 85
# files in 40 minutes, and 2 of attempt 2's 3 freshly sealed clips were gone before the
# run) -- so NO prereg that names source FILES can survive to its own run. The construct
# therefore seals a DETERMINISTIC SELECTION RULE plus an IMMEDIATE SNAPSHOT instead --
# CORPUS, MIN_WIDTH and N_GAMES live in g327_sources.py and are imported above.
# arm -> (batch size, kwarg overrides on the production call). NMSORD is NOT here:
# it is comparison-side only and is derived in `score` from the batch8 boxes. ARM PAD's
# imgsz is filled in from the shape the SINGLE pass was MEASURED to feed, never assumed.
ARMS = {"single": (1, {}), "single_repeat": (1, {}), "batch2": (2, {}),
        "batch8": (8, {}), "pad": (8, {"imgsz": None}), "fp32": (8, {"half": False})}
REF = "single"
PIN_ARMS = ("pad", "fp32", "nmsord")
PIN_BAR = 110       # sealed; CAUSE PINNED needs exactly one arm at or above this
DET_BAR = 120       # sealed; DETERMINISTIC needs all 120


def detect(args) -> None:
    import cv2
    import torch
    import ultralytics
    from src.tracking.advanced_tracker import AdvancedFeetDetector
    from src.tracking.video_handler import TOPCUT

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    gpu = probe(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader"])
    apps = probe(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                  "--format=csv,noheader"])
    used, total = (int(s.strip().split()[0]) for s in gpu["stdout"].splitlines()[0].split(","))
    assert total - used >= 8192, "GPU LEASE: need 8192 MiB free, have %d" % (total - used)
    du = probe(["bash", "-lc", "v=$(timeout 60 du -sm /workspace | cut -f1); "
                               "[ -z \"$v\" ] && v=UNKNOWN; echo $v"])
    disk = probe(["dd", "if=/dev/zero", "of=%s" % (out / "fsync.bin"), "bs=1M",
                  "count=8", "conv=fsync"])
    assert disk["rc"] == 0, "FAILED dd conv=fsync probe"
    (out / "fsync.bin").unlink()
    before = {p: sha256(Path(DEPLOYED, p)) for p in GATED}
    before["yolov8n.pt"] = sha256(Path(DEPLOYED, "yolov8n.pt"))
    for stem in ("yolov8n.pt", "yolov8n-pose.pt"):  # the DEPLOYED weights, never a download
        if Path(DEPLOYED, stem).is_file() and not Path(stem).exists():
            Path(stem).write_bytes(Path(DEPLOYED, stem).read_bytes())

    detector = AdvancedFeetDetector([])
    base = {"classes": [0], "conf": float(detector._fill_conf_threshold), "verbose": False,
            "imgsz": int(getattr(detector, "_infer_imgsz", detector._yolo_imgsz)),
            "half": bool(detector._use_half),
            "device": getattr(detector, "_yolo_device", 0 if detector._use_half else "cpu")}
    print("ROUTE %s" % json.dumps({k: str(v) for k, v in base.items()}), flush=True)
    # The network input is captured with a torch forward pre-hook on the underlying
    # nn.Module, NOT by wrapping the ultralytics predictor: ultralytics REBUILDS its
    # predictor whenever the call kwargs change (e.g. half=False), which silently drops
    # a predictor-level wrapper and lost every tensor record for the fp32 arm and for
    # games 2 and 3 in job 20260908022122_706997_2224. A module hook survives that.
    sink: list = []

    def _rec(_m, a):
        sink.append({"tensor_shape": list(a[0].shape), "dtype": str(a[0].dtype)})

    def hook_live():
        """Attach to whatever module is CURRENTLY live. ultralytics runs a fused
        AutoBackend copy through its predictor, and rebuilds that predictor whenever the
        call kwargs change, so neither the raw nn.Module nor a predictor-level wrapper
        stays hooked -- both were tried and both recorded nothing (jobs ...2224, ...2094).
        The caller warms the arm first so the right predictor exists, then hooks it."""
        pred = getattr(detector.model, "predictor", None)
        target = getattr(pred, "model", None)
        target = getattr(target, "model", target) or detector.model.model
        return target.register_forward_pre_hook(_rec)
    summary = {"screening_only": True, "ground_truth": None, "topcut": TOPCUT,
               "route_kwargs": {k: str(v) for k, v in base.items()},
               "registered_conf": 0.3, "conf_source": "route _fill_conf_threshold",
               "arms": {k: {"batch": v[0], "overrides": {kk: str(vv) for kk, vv in v[1].items()}}
                        for k, v in ARMS.items()},
               "env": {"python": sys.version.split()[0], "torch": torch.__version__,
                       "ultralytics": ultralytics.__version__, "cv2": cv2.__version__,
                       "gpu": torch.cuda.get_device_name(0)},
               "gated_before": before, "probes": {"gpu": gpu, "apps": apps, "du": du,
                                                  "dd": disk},
               "provenance": {}, "games": []}
    for name in ("g327_arms.py", "g327_sources.py", "g327_detector_batch_stability.py"):
        p = Path("scripts/platformkit/tracking", name)
        summary["provenance"][name] = sha256(p)

    selected = select_sources()
    summary["selection_rule"] = {"min_width": MIN_WIDTH, "n_games": N_GAMES,
                                 "order": "mtime descending, first clip per game id",
                                 "corpus": CORPUS,
                                 "selected": [s["game"] for s in selected]}
    print("SELECTED %s" % json.dumps(summary["selection_rule"]), flush=True)
    for slot, src in enumerate(selected, 1):
        game = src["game"]
        anchor = anchor_of(src["path"])
        idxs = indices(anchor)
        src["anchor"] = anchor
        src["frame_list_sha256"] = hashlib.sha256(
            ",".join(str(i) for i in idxs).encode("ascii")).hexdigest()
        frames, stack_sha, frame_shas = decode(src["path"], idxs, TOPCUT)
        print("DECODED %s %d frames anchor=%d stack_sha=%s fed_shape=%r"
              % (game, len(frames), anchor, stack_sha, list(frames[0].shape)), flush=True)
        rows_by_arm, per_arm, single_hw = {}, {}, None
        for arm, (bs, over) in ARMS.items():
            if arm == "pad":
                # ARM PAD pins the batch letterbox to the shape the SINGLE pass was
                # MEASURED to feed -- never assumed. If the shape could not be captured
                # the arm is recorded as NOT APPLIED; instrumentation must not abort a run.
                over = {"imgsz": list(single_hw)} if single_hw else {}
            kwargs = dict(base, **over)

            def call(part, _k=kwargs):
                res = detector.model(list(part), **_k)
                out_rows = []
                for r in res:
                    b = r.boxes
                    if b is None or not len(b):
                        out_rows.append(([], [], []))
                    else:
                        out_rows.append((b.xyxy.cpu().numpy(), b.conf.cpu().numpy(),
                                         b.cls.cpu().numpy()))
                return out_rows

            call([frames[0]])          # warm: build the predictor for THESE kwargs
            handle = hook_live()       # then hook the module that will actually run
            mark = len(sink)
            rows, ms = run_arm(frames, call, bs)
            handle.remove()
            rows_by_arm[arm] = rows
            tensors = sink[mark:]
            if arm == "single" and tensors:
                single_hw = tuple(tensors[0]["tensor_shape"][2:])
            per_arm[arm] = {"batch": bs, "ms_per_frame": ms,
                            "pad_imgsz_applied": bool(arm != "pad" or single_hw),
                            "kwargs": {k: str(v) for k, v in kwargs.items()},
                            "tensor_shapes": sorted({tuple(t["tensor_shape"])
                                                     for t in tensors}),
                            "tensor_dtypes": sorted({t["dtype"] for t in tensors}),
                            "boxes_total": int(sum(len(r[0]) for r in rows)),
                            "zero_box_frames": int(sum(1 for r in rows if not len(r[0])))}
            print("ARM %s %s %s" % (game, arm, json.dumps(per_arm[arm])), flush=True)
        # FIXED slot names: the realised clips cannot be known before the run, so a
        # game-derived filename could not be named as a --fetch target.
        csv = out / ("g327_boxes_g%d.csv" % slot)
        n = write_boxes_csv(csv, idxs, rows_by_arm)
        summary["games"].append({"game": game, "slot": slot, "source": src, "frame_indices": idxs,
                                 "decoded": len(frames), "decoded_stack_sha256": stack_sha,
                                 "decoded_frame_sha256": frame_shas,
                                 "fed_shape": list(frames[0].shape), "csv_rows": n,
                                 "csv": csv.name, "arms": per_arm})
    summary["gated_after"] = {p: sha256(Path(DEPLOYED, p)) for p in GATED}
    summary["gated_after"]["yolov8n.pt"] = sha256(Path(DEPLOYED, "yolov8n.pt"))
    summary["gated_unchanged"] = summary["gated_after"] == before
    summary["probes_after"] = {
        "gpu": probe(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                      "--format=csv,noheader"])}
    (out / "g327_summary.json").write_text(json.dumps(summary, indent=1), encoding="ascii")
    print("WROTE %s" % (out / "g327_summary.json"), flush=True)


def score(args) -> None:
    """LOCAL arithmetic, recomputed from the committed CSVs alone."""
    summary = json.loads(Path(args.summary).read_text(encoding="ascii"))
    report = {"iou_match": 0.5, "pin_bar": PIN_BAR, "det_bar": DET_BAR,
              "ordering_note": "nmsord is COMPARISON-SIDE: the batch8 boxes sorted, "
                               "not a second detector pass", "games": [], "totals": {}}
    totals: dict = {}
    # An isolation arm only counts if the factor it names was ACTUALLY APPLIED. ARM PAD
    # is a no-op unless the shape fed differs from the batch8 baseline's, and ultralytics
    # may quietly coerce a two-element imgsz -- so the MEASURED tensor shapes decide.
    shapes = {a: sorted({tuple(s) for g in summary["games"]
                         for s in g["arms"][a]["tensor_shapes"]})
              for a in summary["games"][0]["arms"]}
    dtypes = {a: sorted({d for g in summary["games"]
                         for d in g["arms"][a]["tensor_dtypes"]})
              for a in summary["games"][0]["arms"]}
    report["measured_tensor_shapes"] = {a: [list(s) for s in v] for a, v in shapes.items()}
    report["measured_tensor_dtypes"] = dtypes
    report["pad_applied"] = shapes["pad"] == shapes["single"]
    report["pad_was_a_noop_vs_batch8"] = shapes["pad"] == shapes["batch8"]
    # ultralytics caches one predictor, so a per-call half=False can be ignored. If the
    # fp32 arm's MEASURED dtype equals batch8's, the factor was NOT applied and the arm
    # says nothing -- report that rather than counting it toward a pinned cause.
    report["fp32_applied"] = dtypes["fp32"] != dtypes["batch8"]
    for g in summary["games"]:
        table = read_boxes_csv(Path(args.artifact) / g["csv"])
        idxs = g["frame_indices"]
        ref = rows_for(table, REF, idxs)
        # POST-HOC ROBUSTNESS CUT, DECLARED AS SUCH AND NOT A BAR. One selected clip
        # returned boxes on only 2 of 40 frames, and two zero-box frames are trivially
        # bit-identical, so the all-frames count can be inflated by empty frames
        # (contract B9). The sealed verdict below still uses ALL 120 frames.
        nonempty = [k for k, r in enumerate(ref) if len(r[0])]
        cells = {}
        for arm in list(ARMS) + ["nmsord"]:
            if arm == REF:
                continue
            src_arm = "batch8" if arm == "nmsord" else arm
            cells[arm] = compare(ref, rows_for(table, src_arm, idxs), sort=(arm == "nmsord"))
            flags = cells[arm]["per_frame_bit_identical"]
            cells[arm]["nonempty_frames"] = len(nonempty)
            cells[arm]["nonempty_bit_identical"] = int(sum(flags[k] for k in nonempty))
            totals.setdefault(arm, {"frames": 0, "bit_identical_frames": 0,
                                    "nonempty_frames": 0, "nonempty_bit_identical": 0})
            totals[arm]["frames"] += cells[arm]["frames"]
            totals[arm]["bit_identical_frames"] += cells[arm]["bit_identical_frames"]
            totals[arm]["nonempty_frames"] += len(nonempty)
            totals[arm]["nonempty_bit_identical"] += cells[arm]["nonempty_bit_identical"]
        report["games"].append({"game": g["game"], "frames": len(idxs),
                                "zero_box_frames_single": len(idxs) - len(nonempty),
                                "arms": cells})
    report["totals"] = totals
    applied = {"pad": report["pad_applied"], "fp32": report["fp32_applied"],
               "nmsord": True}  # nmsord is comparison-side and always applies
    report["isolation_arm_applied"] = applied
    cleared = [a for a in PIN_ARMS
               if applied[a] and totals[a]["bit_identical_frames"] >= PIN_BAR]
    report["arms_not_applied"] = [a for a in PIN_ARMS if not applied[a]]
    baseline_fails = totals["batch8"]["bit_identical_frames"] < PIN_BAR
    report["arms_clearing_pin_bar"] = cleared
    report["batch8_below_pin_bar"] = bool(baseline_fails)
    report["verdict_cause"] = ("CAUSE PINNED: %s" % cleared[0]) if (
        len(cleared) == 1 and baseline_fails) else (
        "NOT PINNED (CONFOUNDED)" if len(cleared) > 1 else "NOT PINNED")
    det = totals["single_repeat"]["bit_identical_frames"]
    report["verdict_determinism"] = "DETERMINISTIC %d/%d" % (det, DET_BAR) if (
        det >= DET_BAR) else "NOT DETERMINISTIC %d/%d" % (det, DET_BAR)
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="ascii")
    print(report["verdict_cause"], "|", report["verdict_determinism"])
    for arm, t in sorted(totals.items()):
        print("  %-14s bit-identical %3d/%-4d | non-empty-frame cut %3d/%d"
              % (arm, t["bit_identical_frames"], t["frames"],
                 t["nonempty_bit_identical"], t["nonempty_frames"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("--output", type=Path, default=Path("g327_out"))
    d.set_defaults(func=detect)
    s = sub.add_parser("score")
    s.add_argument("--artifact", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=score)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
