"""G380 PROPOSED producer-provenance patch -- the authoritative edit table.

The four producer files are HUMAN-GATED.  This module never edits a landing
tree.  `apply` rewrites a SCRATCH COPY of the deploy tree; `diff` emits the
unified diff that ships as the PROPOSED artifact.  Every anchor must occur
exactly once, so a drifted producer fails loudly instead of being patched into
the wrong place.

  python3 -m scripts.platformkit.tracking.g380_patch diff  --tree <deploy> --out <file>
  python3 -m scripts.platformkit.tracking.g380_patch apply --tree <scratch copy>
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
from pathlib import Path

TRACKER = "src/tracking/advanced_tracker.py"
PIPE = "src/pipeline/unified_pipeline.py"
CLIP = "scripts/run_clip.py"
DAEMON = "scripts/platformkit/track_daemon.py"
FILES = (TRACKER, PIPE, CLIP, DAEMON)

_T_IMPORT = "from .player_detection import FeetDetector, COLORS, hsv2bgr, PAD, _adaptive_colors\n"
_T_INIT = "        self._lost_ages:    Dict[int, int]              = {i: 0 for i in range(n)}\n"
_T_RESET = "        self._lost_ages = {i: 0 for i in range(n)}\n"
_T_NEWPOS = '        new_pos = (det["homo"][0], det["homo"][1])\n'
_T_CLAMP = """                self._freeze_age[slot] = self._freeze_age.get(slot, 0) + 1
            else:
                self._freeze_age[slot] = 0
        p.positions[timestamp] = new_pos
"""
_T_FLOW_RENDER = """                                    _p.positions[timestamp] = (_homo[0], _homo[1])
                                    self._flow_pts[_slot] = _new_pt
"""
_T_KALMAN = """                                p.positions[timestamp] = (homo[0], homo[1])
                    except Exception:
                        pass
"""
_T_FLOW_BATCH = """                                p.positions[timestamp] = (homo[0], homo[1])
                                self._flow_pts[slot] = new_pt  # advance anchor
"""
_T_MERGE = """                        if age_i >= age_j:
                            del pi.positions[timestamp]
                            break  # pi removed; stop checking pi vs others
                        else:
                            del pj.positions[timestamp]
"""

_P_IMPORT = "from src.tracking.event_detector import EventDetector\n"
_P_COUNTER = ("        gameplay_frames = 0             # gameplay frames actually "
              "processed (for max_frames check)\n")
_P_READ = """            if not ok or frame is None or (self.max_frames and gameplay_frames >= self.max_frames):
                break
"""
_P_MAP = """                last_pos = prev_pos.get(p.ID)
                if last_pos is not None:
                    dx = x2d - last_pos[0]
                    dy = y2d - last_pos[1]
                    if (dx * dx + dy * dy) > 350 * 350:
                        x2d, y2d = last_pos[0], last_pos[1]

                slot     = self.players.index(p)
                conf     = max(0.0, 1.0 - self.feet_det._lost_ages.get(slot, 0) / 15)
"""
_P_DEDUP = ("            # Position jump clamping can re-introduce duplicates; "
            "strip them here.\n")
_P_TRACK = """                    "dribble_hand":     getattr(p, "dribble_hand", "unknown"),
                })
"""
_P_ROW = """                    "homography_valid": int(not self._homography_suspended),
                })
"""
_P_RESULTS = '            "evaluated_frames": gameplay_frames,  # G331: past the detector gate\n'
_P_HEADER = """            "homography_valid",  # FIX 1 replay/cut detector
        ]
"""

_C_PUBLISH = """        side.update(evaluated_frames=count,
                    reason=(None if count is not None else side.get("reason")))
        open(sidecar_path, "w", encoding="utf-8").write(
            json.dumps(side, indent=2, sort_keys=True))
"""

_D_IMPORT = ("from scripts.platformkit.tracking.source_timebase import probe_source, "
             "probe_status, stamp_tracking_csv\n")
_D_LOG = """        log_path = path.with_suffix(".log")
        try:
"""
_D_ACTIVE = """        active[path.name] = {"proc": proc, "video": path, "log": log_path,
                             "sport": sport, "game_id": game_id,
                             "started": time.time(), "source": probe_source(path),
"""
_D_LEDGER = """    entry.update(decoded_frames=(graded or {}).get("decoded_frames", manifest_frames),
                 evaluated_frames=(graded or {}).get("evaluated_frames"),
"""

EDITS = [
    (TRACKER, _T_IMPORT,
     _T_IMPORT + "from scripts.platformkit.tracking import g380_provenance as _g380\n"),
    (TRACKER, _T_INIT,
     _T_INIT + "        self._pos_source:   Dict[Tuple, Tuple]          = {}"
     "   # G380 (slot, tick) -> (label, branch)\n"),
    (TRACKER, _T_RESET, _T_RESET + "        self._pos_source = {}\n"),
    (TRACKER, _T_NEWPOS, _T_NEWPOS + '        _g380_label = "DETECTION"\n'),
    (TRACKER, _T_CLAMP, _T_CLAMP.replace(
        "            else:\n", '                _g380_label = "CLAMP"\n            else:\n')
     + '        _g380.stamp(self._pos_source, slot, timestamp, _g380_label,\n'
       '                    "src/tracking/advanced_tracker.py:_activate_slot",\n'
       '                    _g380.event_id(timestamp, det["bbox"]))\n'),
    (TRACKER, _T_FLOW_RENDER, _T_FLOW_RENDER +
     '                                    _g380.stamp(self._pos_source, _slot, timestamp,\n'
     '                                                "PREDICTION",\n'
     '                                                "src/tracking/advanced_tracker.py'
     ':flow_gapfill_render")\n'),
    (TRACKER, _T_KALMAN, _T_KALMAN.replace(
        "                    except Exception:\n",
        '                                _g380.stamp(self._pos_source, self._slot(p), timestamp,\n'
        '                                            "PREDICTION",\n'
        '                                            "src/tracking/advanced_tracker.py'
        ':kalman_homography")\n'
        "                    except Exception:\n")),
    (TRACKER, _T_FLOW_BATCH, _T_FLOW_BATCH +
     '                                _g380.stamp(self._pos_source, slot, timestamp, "PREDICTION",\n'
     '                                            "src/tracking/advanced_tracker.py'
     ':flow_gapfill_batched")\n'),
    (TRACKER, _T_MERGE, """                        if age_i >= age_j:
                            del pi.positions[timestamp]
                            _g380.drop(self._pos_source, slot_i, timestamp)
                            _g380.stamp(self._pos_source, slot_j, timestamp, "PREDICTION",
                                        "src/tracking/advanced_tracker.py:id_merge")
                            break  # pi removed; stop checking pi vs others
                        else:
                            del pj.positions[timestamp]
                            _g380.drop(self._pos_source, slot_j, timestamp)
                            _g380.stamp(self._pos_source, slot_i, timestamp, "PREDICTION",
                                        "src/tracking/advanced_tracker.py:id_merge")
"""),

    (PIPE, _P_IMPORT,
     _P_IMPORT + "from scripts.platformkit.tracking import g380_provenance as _g380\n"),
    (PIPE, _P_COUNTER, _P_COUNTER +
     "        attempted_frames_capped = 0     # G380: decoded frames entering the loop, capped\n"
     "        _g380_ticks: set = set()        # G380: evaluated ticks, before row filtering\n"
     "        _g380_prev_int: Dict[int, tuple] = {}\n"),
    (PIPE, _P_READ, _P_READ + "            attempted_frames_capped += 1\n"),
    (PIPE, _P_MAP, """                slot     = self.players.index(p)
                _g380_label, _g380_branch, _g380_event = _g380.label_for(
                    getattr(self.feet_det, "_pos_source", None), slot, frame_idx)
                last_pos = prev_pos.get(p.ID)
                if last_pos is not None:
                    dx = x2d - last_pos[0]
                    dy = y2d - last_pos[1]
                    if (dx * dx + dy * dy) > 350 * 350:
                        x2d, y2d = last_pos[0], last_pos[1]
                        _g380_label = "CLAMP"
                        _g380_branch = "src/pipeline/unified_pipeline.py:jump_clamp"

                _g380_label, _g380_branch = _g380.resolve_emitted(
                    _g380_label, _g380_branch, _g380_prev_int.get(p.ID), (int(x2d), int(y2d)))
                _g380_prev_int[p.ID] = (int(x2d), int(y2d))
                conf     = max(0.0, 1.0 - self.feet_det._lost_ages.get(slot, 0) / 15)
"""),
    (PIPE, _P_DEDUP, "            _g380.note_attempt(_g380_ticks, frame_idx)\n" + _P_DEDUP),
    (PIPE, _P_TRACK, """                    "dribble_hand":     getattr(p, "dribble_hand", "unknown"),
                    "position_source":  _g380_label,
                    "source_branch":    _g380_branch,
                    "matched_event_id": (_g380_event if _g380_label == "DETECTION" else ""),
                })
"""),
    (PIPE, _P_ROW, """                    "homography_valid": int(not self._homography_suspended),
                    "position_source": track.get("position_source", "UNKNOWN"),
                    "source_branch": track.get("source_branch", ""),
                    "matched_event_id": track.get("matched_event_id", ""),
                })
"""),
    (PIPE, _P_RESULTS, _P_RESULTS +
     '            "attempted_frames_capped": attempted_frames_capped,\n'
     '            "evaluated_tick_ids": sorted(_g380_ticks),\n'),
    (PIPE, _P_HEADER, """            "homography_valid",  # FIX 1 replay/cut detector
            # G380 additive tail: every legacy field keeps its position and value.
            "position_source", "source_branch", "matched_event_id",
        ]
"""),

    (CLIP, _C_PUBLISH, """        receipt = {"evaluated_tick_ids": list(results.get("evaluated_tick_ids") or []),
                   "attempted_frames_capped": results.get("attempted_frames_capped"),
                   "evaluated_tick_ids_schema": "sorted_source_frame_indices"}
        side.update(evaluated_frames=count,
                    attempted_frames_capped=receipt["attempted_frames_capped"],
                    evaluated_tick_ids=receipt["evaluated_tick_ids"],
                    evaluated_tick_ids_schema=receipt["evaluated_tick_ids_schema"],
                    reason=(None if count is not None else side.get("reason")))
        open(sidecar_path, "w", encoding="utf-8").write(
            json.dumps(side, indent=2, sort_keys=True))
        open(os.path.join(os.path.dirname(sidecar_path), "evaluated_tick_receipt.json"),
             "w", encoding="utf-8").write(json.dumps(receipt, indent=2, sort_keys=True) + "\\n")
"""),

    (DAEMON, _D_IMPORT,
     _D_IMPORT + "from scripts.platformkit.tracking.g380_provenance import bind_attempt "
     "as _g380_bind\n"),
    (DAEMON, _D_LOG, """        log_path = path.with_suffix(".log")
        # G380: stateless per-attempt bind, derived from the source inode. It
        # retains no claim and no pending state, so a repeat attempt recomputes
        # the same value -- the G372 re-claim wave came from retained state.
        attempt = _g380_bind(game_id, path, TRACKING)
        try:
"""),
    (DAEMON, _D_ACTIVE, _D_ACTIVE +
     '                             "attempt_id": attempt["attempt_id"],\n'
     '                             "evaluated_tick_receipt_path": attempt["receipt_path"],\n'
     '                             "weight_digest": attempt["weight_digest"],\n'),
    # G376 P2 folded in additively: both fields already exist in the per-section
    # verdict (track_daemon_done.py) and were simply never copied into the ledger.
    (DAEMON, _D_LEDGER, _D_LEDGER +
     '                 attempted_frames_capped=(graded or {}).get("attempted_frames_capped"),\n'
     '                 route_max_frames=(graded or {}).get("route_max_frames"),\n'
     '                 evaluated_tick_receipt_path=job.get("evaluated_tick_receipt_path"),\n'),
]


def _read(tree: Path, rel: str) -> str:
    return (tree / rel).read_text(encoding="utf-8")


def patched(tree: Path) -> dict:
    """Return {relpath: patched text}; every anchor must match exactly once."""
    out = {rel: _read(tree, rel) for rel in FILES}
    for rel, anchor, replacement in EDITS:
        hits = out[rel].count(anchor)
        if hits != 1:
            raise SystemExit("ANCHOR %s occurs %d times in %s" % (anchor[:60], hits, rel))
        out[rel] = out[rel].replace(anchor, replacement, 1)
    return out


def cmd_apply(args) -> None:
    """Rewrite a scratch copy in place; the file is unlinked first so a hardlink survives."""
    tree = Path(args.tree)
    for rel, text in patched(tree).items():
        target = tree / rel
        target.unlink()
        target.write_text(text, encoding="utf-8")
        print("patched %s sha256=%s" % (rel, hashlib.sha256(text.encode("utf-8")).hexdigest()))


def cmd_diff(args) -> None:
    """Emit the unified PROPOSED diff against an unpatched tree."""
    tree, chunks = Path(args.tree), []
    for rel, text in patched(tree).items():
        chunks.extend(difflib.unified_diff(
            _read(tree, rel).splitlines(True), text.splitlines(True),
            fromfile="a/" + rel, tofile="b/" + rel, n=3))
    body = "".join(chunks)
    Path(args.out).write_text(body, encoding="utf-8")
    print("diff bytes=%d sha256=%s"
          % (len(body), hashlib.sha256(body.encode("utf-8")).hexdigest()))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, handler in (("apply", cmd_apply), ("diff", cmd_diff)):
        item = sub.add_parser(name)
        item.add_argument("--tree", required=True)
        item.add_argument("--out")
        item.set_defaults(handler=handler)
    args = parser.parse_args()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
