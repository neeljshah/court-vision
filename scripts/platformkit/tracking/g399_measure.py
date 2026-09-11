"""Decoded-PTS census, planned-state freeze and native tile export for G399."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.platformkit.tracking import g399_protocol as protocol

TILE_W, TILE_H = 640, 540
OFFSETS = ((0, 0), (640, 0), (1280, 0), (0, 540), (640, 540), (1280, 540))
PTS_RE = re.compile(r"pts_time:([0-9]+\.?[0-9]*)")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


def competition(name: str) -> str:
    """Name the competition prefix carried by the retained object file name."""
    return name.split("__")[0] if "__" in name else "unlabelled"


def frozen_order(rows: list[dict[str, str]], root: Path) -> list[dict[str, str]]:
    """Freeze competition/video/section/source-digest order before any label."""
    ordered = []
    for row in rows:
        name = Path(row["source_path"]).name
        ordered.append({"attempt_id": row["attempt_id"], "object_name": name,
                        "object_path": (root / name).as_posix(),
                        "competition": competition(name),
                        "ytid": row.get("ytid", ""), "section": row.get("offset", ""),
                        "source_sha256": row["source_sha256"]})
    ordered.sort(key=lambda item: (item["competition"], item["ytid"],
                                   int(item["section"] or 0), item["source_sha256"]))
    for index, item in enumerate(ordered, start=1):
        item["source_rank"] = index
    return ordered


def _pts_values(text: str) -> set[float]:
    """Parse one ffprobe csv column, tolerating the trailing empty field."""
    values = set()
    for line in text.splitlines():
        token = line.split(",")[0].strip()
        if token and token != "N/A":
            values.add(float(token))
    return values


def decoded_census(path: Path) -> dict[str, object]:
    """Decode every video frame once and record the real presentation span."""
    probe = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                  "stream=width,height,avg_frame_rate,nb_frames", "-of", "json", str(path)])
    stream = json.loads(probe.stdout)["streams"][0] if probe.returncode == 0 else {}
    frames = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                   "frame=pts_time", "-of", "csv=p=0", str(path)])
    values = sorted(_pts_values(frames.stdout))
    packets = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                    "packet=pts_time", "-of", "csv=p=0", str(path)])
    n_packets = len(_pts_values(packets.stdout))
    return {"object_path": path.as_posix(), "width": stream.get("width"),
            "height": stream.get("height"), "avg_frame_rate": stream.get("avg_frame_rate"),
            "header_nb_frames": stream.get("nb_frames"), "n_packets": n_packets,
            "n_decoded": len(values), "first_pts": values[0] if values else None,
            "last_pts": values[-1] if values else None,
            "decode_status": "DECODED" if len(values) >= 2 else "DECODE_FAILED",
            "_pts": values}


def census_all(sources: list[dict[str, str]], workers: int = 4) -> list[dict[str, object]]:
    """Run the read-only decoded census across the frozen source order."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda item: decoded_census(Path(item["object_path"])), sources))
    for source, result in zip(sources, results):
        result.update({key: source[key] for key in ("attempt_id", "object_name", "competition",
                                                    "ytid", "section", "source_sha256", "source_rank")})
    return results


def plan_states(census: list[dict[str, object]]) -> list[dict[str, object]]:
    """Emit the two planned interior states per source, failures retained."""
    states: list[dict[str, object]] = []
    index = 0
    for row in sorted(census, key=lambda item: item["source_rank"]):
        for fraction in (1.0 / 3.0, 2.0 / 3.0):
            index += 1
            states.append({"context_id": "G399_%03d" % index, "attempt_id": row["attempt_id"],
                           "object_name": row["object_name"], "competition": row["competition"],
                           "ytid": row["ytid"], "section": row["section"],
                           "source_sha256": row["source_sha256"],
                           "target_fraction": "1/3" if fraction < 0.5 else "2/3",
                           "planned_pts": "", "status": row["decode_status"]})
        if row["decode_status"] != "DECODED":
            continue
        try:
            chosen = protocol.planned_targets(row["first_pts"], row["last_pts"], row["_pts"])
        except ValueError as error:
            for state in states[-2:]:
                state["status"] = "SELECTION_FAILED:%s" % error
            continue
        for state, pts in zip(states[-2:], chosen):
            state["planned_pts"] = "%.6f" % pts
            state["status"] = "PLANNED"
    return states


def export_state(object_path: Path, pts: float, out_dir: Path, context_id: str) -> dict[str, object]:
    """Export one unchanged native frame as six 640x540 tiles and a context view."""
    import cv2  # local import keeps the census usable without the vision stack
    import numpy as np

    out_dir.mkdir(parents=True, exist_ok=True)
    frame_png = out_dir / ("%s_frame.png" % context_id)
    # -copyts keeps the source presentation timestamp so showinfo can prove the frame.
    result = _run(["ffmpeg", "-hide_banner", "-v", "info", "-copyts", "-ss", "%.6f" % pts, "-i",
                   str(object_path), "-vf", "showinfo", "-frames:v", "1", "-y", str(frame_png)])
    found = PTS_RE.findall(result.stderr)
    if not frame_png.is_file() or not found:
        return {"context_id": context_id, "status": "EXPORT_FAILED", "delivered_pts": ""}
    delivered = float(found[0])
    frame = cv2.imdecode(np.fromfile(str(frame_png), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[0] != 1080 or frame.shape[1] != 1920:
        return {"context_id": context_id, "status": "WRONG_RESOLUTION", "delivered_pts": delivered}
    record: dict[str, object] = {
        "context_id": context_id, "status": "EXPORTED", "delivered_pts": delivered,
        "pts_match": abs(delivered - pts) < 1e-3, "width": 1920, "height": 1080,
        "frame_sha256": hashlib.sha256(frame_png.read_bytes()).hexdigest(), "tiles": []}
    for index, (ox, oy) in enumerate(OFFSETS, start=1):
        tile = frame[oy:oy + TILE_H, ox:ox + TILE_W]
        tile_path = out_dir / ("%s_tile%d.png" % (context_id, index))
        cv2.imencode(".png", tile)[1].tofile(str(tile_path))
        record["tiles"].append({"tile": index, "offset_x": ox, "offset_y": oy,
                                "path": tile_path.as_posix(),
                                "sha256": hashlib.sha256(tile_path.read_bytes()).hexdigest()})
    view = out_dir / ("%s_context.jpg" % context_id)
    cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tofile(str(view))
    record["context_view"] = view.as_posix()
    return record


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    """Write one durable per-unit table with a stable ASCII field order."""
    with path.open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("usage: g399_measure <census|plan|export> <out.json> ...")
        return 2
    out = Path(argv[2])
    if argv[1] == "census":
        rows = _read_csv(Path(argv[3]))
        draw = {row["attempt_id"]: row for row in _read_csv(Path(argv[4]))}
        for row in rows:
            row.update({"ytid": draw[row["attempt_id"]]["ytid"],
                        "offset": draw[row["attempt_id"]]["offset"]})
        census = census_all(frozen_order(rows, Path(argv[5])))
        out.write_text(json.dumps(census, indent=1, sort_keys=True) + "\n", encoding="ascii", newline="\n")
        print("CENSUS n=%d decoded=%d" % (len(census), sum(r["decode_status"] == "DECODED" for r in census)))
        return 0
    if argv[1] == "plan":
        states = plan_states(json.loads(Path(argv[3]).read_text(encoding="ascii")))
        out.write_text(json.dumps(states, indent=1, sort_keys=True) + "\n", encoding="ascii", newline="\n")
        print("PLANNED states=%d ok=%d" % (len(states), sum(s["status"] == "PLANNED" for s in states)))
        return 0
    if argv[1] == "export":
        states = json.loads(Path(argv[3]).read_text(encoding="ascii"))
        out_dir, root = Path(argv[4]), Path(argv[5])
        records = []
        for state in states:
            if state["status"] != "PLANNED":
                records.append({"context_id": state["context_id"], "status": state["status"],
                                "delivered_pts": ""})
                continue
            records.append(export_state(root / state["object_name"], float(state["planned_pts"]),
                                        out_dir, state["context_id"]))
        out.write_text(json.dumps(records, indent=1, sort_keys=True) + "\n", encoding="ascii", newline="\n")
        print("EXPORT n=%d ok=%d" % (len(records), sum(r["status"] == "EXPORTED" for r in records)))
        return 0
    if argv[1] == "cards":
        import cv2
        import numpy as np

        out.mkdir(parents=True, exist_ok=True)
        records = json.loads(Path(argv[3]).read_text(encoding="ascii"))
        made = 0
        for record in records:
            if record["status"] != "EXPORTED":
                continue
            frame = cv2.imdecode(np.fromfile(record["context_view"], dtype=np.uint8), cv2.IMREAD_COLOR)
            card = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
            cv2.imencode(".jpg", card, [cv2.IMWRITE_JPEG_QUALITY, 72])[1].tofile(
                str(out / ("%s.jpg" % record["context_id"])))
            made += 1
        print("CARDS n=%d" % made)
        return 0
    if argv[1] == "batches":
        exported = [r for r in json.loads(Path(argv[3]).read_text(encoding="ascii"))
                    if r["status"] == "EXPORTED"]
        size = int(argv[4])
        for rater in protocol.RATERS:
            target = out / ("batch_real_%s" % rater)
            target.mkdir(parents=True, exist_ok=True)
            for index in range(0, len(exported), size):
                lines = ["%s\t%s" % (r["context_id"], ",".join(t["path"] for t in r["tiles"]))
                         for r in exported[index:index + size]]
                (target / ("batch_%02d.tsv" % (index // size + 1))).write_text(
                    "\n".join(lines) + "\n", encoding="ascii", newline="\n")
        print("BATCHES contexts=%d size=%d" % (len(exported), size))
        return 0
    print("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
