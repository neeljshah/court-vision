"""Read-only pod measurement for the tennis two-slot emission rule."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_CLIPS = (
    "tennis__tennis_09.mp4",
    "tennis__tennis_10.mp4",
    "tennis__tennis_459iho5_AFs.mp4",
)
POD_HOST = "config.pod"
POD_ROOT = "/workspace/nba-ai-system/data/footage_corpus"


def evenly_spaced(items: Sequence[object], limit: int) -> list[object]:
    """Select endpoints and evenly distributed interior items without repeats."""
    if limit < 1:
        raise ValueError("limit must be positive")
    if len(items) <= limit:
        return list(items)
    return [items[round(index * (len(items) - 1) / (limit - 1))]
            for index in range(limit)]


def _remote_program() -> str:
    """Return the read-only remote runner; it writes results only to stdout."""
    return r'''import base64, cv2, hashlib, io, json, pathlib, sys, zipfile
import numpy as np
from domains.tennis.tracking.adapter import TennisAdapter

cfg = json.loads(base64.b64decode(sys.argv[1]))
root = pathlib.Path(cfg["pod_root"])
def spaced(items, limit):
    if len(items) <= limit:
        return list(items)
    return [items[round(index * (len(items) - 1) / (limit - 1))] for index in range(limit)]
def jpeg(image):
    ok, packed = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return packed.tobytes()
all_rows, all_one = {}, []
for source_clip in cfg["clips"]:
    path = root / source_clip
    if not path.is_file():
        raise FileNotFoundError(path)
    adapter = TennisAdapter()
    detector, original = adapter.detector, adapter.detect_players
    latest, calls = {}, []
    def recorded(frame):
        boxes = detector(frame)
        latest["boxes"] = [list(map(float, box)) for box in boxes]
        return boxes
    def instrumented(frame, homography):
        emitted = original(frame, homography)
        halves = {}
        for box in latest.pop("boxes"):
            x1, y1, x2, y2 = box[:4]
            if len(box) >= 5 and box[4] < adapter.tracker_conf:
                continue
            if x2 <= x1 or y2 <= y1:
                continue
            foot = adapter._project(((x1 + x2) / 2.0, y2), homography)
            half = 0 if foot[0] < 39.0 else 1
            center = np.array(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
            key = (-min(np.linalg.norm(center - prior) for prior in adapter._centroids.values())
                   if adapter._centroids else (x2 - x1) * (y2 - y1))
            if half not in halves or key > halves[half][0]:
                halves[half] = (key, box)
        outcome = "both" if set(halves) == {0, 1} else ("one" if halves else "neither")
        if bool(emitted) != (outcome == "both") or (outcome == "both" and len(emitted) != 2):
            raise AssertionError("instrumentation disagrees with detect_players")
        calls.append({"outcome": outcome, "boxes": [value[1] for value in halves.values()]})
        return emitted
    adapter.detector, adapter.detect_players = recorded, instrumented
    adapter.process_video(path)
    manifest = adapter.last_frame_manifest.to_dict("records")
    cursor, by_frame = 0, {}
    counts = {"both": 0, "one": 0, "neither": 0, "not_callable": 0}
    for row in manifest:
        frame = int(row["frame"])
        if row["status"] in ("emitted_players", "no_complete_player_pair"):
            call = calls[cursor]; cursor += 1
            counts[call["outcome"]] += 1
            by_frame[frame] = call
            if call["outcome"] == "one":
                all_one.append({"source_clip": source_clip, "frame": frame, "boxes": call["boxes"]})
        else:
            counts["not_callable"] += 1
            by_frame[frame] = {"outcome": "not_callable", "boxes": []}
    if cursor != len(calls) or len(manifest) != sum(counts.values()):
        raise AssertionError("manifest and instrumented-call counts differ")
    sampled = []
    for frame in spaced(list(range(len(manifest))), cfg["sample_per_clip"]):
        sampled.append({"frame": frame, "outcome": by_frame[frame]["outcome"]})
    all_rows[source_clip] = {"decoded_frames": len(manifest), "counts": counts, "samples": sampled}

chosen = spaced(sorted(all_one, key=lambda row: (row["source_clip"], row["frame"])), 5)
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
    for row in chosen:
        cap = cv2.VideoCapture(str(root / row["source_clip"]))
        cap.set(cv2.CAP_PROP_POS_FRAMES, row["frame"]); ok, image = cap.read(); cap.release()
        if not ok:
            raise RuntimeError("cannot read selected frame")
        for box in row["boxes"]:
            x1, y1, x2, y2 = map(round, box[:4])
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 255), 3)
        cv2.putText(image, row["source_clip"] + " f" + str(row["frame"]) + " one-half",
                    (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        archive.writestr("discarded/" + row["source_clip"].replace(".mp4", "") + "_f%06d.jpg" % row["frame"], jpeg(image))
    for source_clip, clip_data in all_rows.items():
        cap = cv2.VideoCapture(str(root / source_clip))
        samples = clip_data["samples"]
        for sheet_index, rows in enumerate([samples[index:index + 20] for index in range(0, len(samples), 20)]):
            sheet = np.zeros((900, 1600, 3), dtype=np.uint8)
            for tile_index, row in enumerate(rows):
                cap.set(cv2.CAP_PROP_POS_FRAMES, row["frame"]); ok, image = cap.read()
                if not ok:
                    raise RuntimeError("cannot read sampled frame")
                image = cv2.resize(image, (320, 180))
                x, y = (tile_index % 5) * 320, (tile_index // 5) * 225
                sheet[y:y + 180, x:x + 320] = image
                cv2.putText(sheet, "f%d %s" % (row["frame"], row["outcome"]),
                            (x + 4, y + 202), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 1)
            name = source_clip.replace(".mp4", "") + "_s%02d.jpg" % sheet_index
            archive.writestr("rally_samples/" + name, jpeg(sheet))
        cap.release()
result = {"adapter_sha256": hashlib.sha256((pathlib.Path("domains/tennis/tracking/adapter.py")).read_bytes()).hexdigest(),
          "clips": all_rows, "selected_discarded": chosen}
sys.stdout.buffer.write(b"JSON\n" + json.dumps(result, sort_keys=True).encode("ascii") + b"\nZIP\n" + base64.b64encode(buffer.getvalue()))
'''


def _parse_remote_output(payload: bytes) -> tuple[dict, bytes]:
    prefix, marker, zipped = payload.partition(b"\nZIP\n")
    if marker != b"\nZIP\n" or not prefix.startswith(b"JSON\n"):
        raise ValueError("remote runner did not return JSON and ZIP payloads")
    return json.loads(prefix[5:].decode("ascii")), base64.b64decode(zipped)


def run_measurement(clips: Iterable[str], sample_per_clip: int, out: Path) -> dict:
    """Run the immutable adapter remotely and materialize only local evidence."""
    requested = tuple(clips)
    if len(requested) < 3:
        raise ValueError("G148 requires at least three clips")
    config = {"clips": requested, "pod_root": POD_ROOT, "sample_per_clip": sample_per_clip}
    source = base64.b64encode(_remote_program().encode("ascii")).decode("ascii")
    encoded_config = base64.b64encode(json.dumps(config, sort_keys=True).encode("ascii")).decode("ascii")
    command = "cd /workspace/nba-ai-system && echo {} | base64 -d | python3 - {}".format(source, encoded_config)
    completed = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", POD_HOST, command],
                               check=False, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace").strip())
    result, rendered = _parse_remote_output(completed.stdout)
    local_hash = hashlib.sha256(Path("domains/tennis/tracking/adapter.py").read_bytes()).hexdigest()
    if result["adapter_sha256"] != local_hash:
        raise ValueError("pod adapter hash differs from the worktree adapter")
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(rendered)) as archive:
        for member in archive.infolist():
            destination = (out / member.filename).resolve()
            if out.resolve() not in destination.parents:
                raise ValueError("unsafe remote archive member")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))
    (out / "measurement.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample-per-clip", type=int, default=100)
    parser.add_argument("--clips", nargs="+", default=list(DEFAULT_CLIPS))
    args = parser.parse_args()
    result = run_measurement(args.clips, args.sample_per_clip, args.out)
    print("WROTE %s" % args.out)
    for clip, data in result["clips"].items():
        print("%s decoded=%d counts=%s" % (clip, data["decoded_frames"], data["counts"]))


if __name__ == "__main__":
    main()
