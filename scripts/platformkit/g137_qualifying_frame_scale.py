"""Measure fresh all-four paint-role claims without changing G134 grouping."""
from __future__ import annotations
import argparse
import base64
import csv
import json
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable
import cv2
from domains.basketball.tracking.line_calibration import CandidateLineGroup, assign_paint_roles
from scripts.platformkit.g103_g68_tile_recipe import _records
from scripts.platformkit.g134_grouping_stability import _groups
from scripts.platformkit.g93_line_detection_limit import ROLE_COLOURS, wilson_interval
ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g137_scale"
POD_ROOT = "/workspace/nba-ai-system/data/footage_corpus"
POD_HOST = "config.pod"
SEED = 137092026
STRATA_PER_CLIP = 12
ROLES = ("baseline", "free_throw", "lane_left", "lane_right")
G84_MANIFEST = ROOT / "g84_candidate_quality/sample_manifest.csv"
UNREADABLE = {
    ("ncaa_basketball__ncaa_basketball_IB-_u4gW3ds", "28850"): "source_frame_unreadable_by_seek_or_sequential_decode",
}
def _remote_inventory() -> list[dict[str, str]]:
    code = """
import cv2, json, pathlib
root = pathlib.Path(%r)
files = sorted(list(root.glob('ncaa_basketball__*.mp4')) + list(root.glob('wnba__*.mp4')))
rows = []
for path in files:
    capture = cv2.VideoCapture(str(path))
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    if count <= 0 or width <= 0 or height <= 0:
        raise RuntimeError('invalid metadata: ' + path.name)
    rows.append({'source_clip': path.name, 'clip': path.stem, 'frame_count': str(count),
                 'width': str(width), 'height': str(height)})
print(json.dumps(rows, sort_keys=True))
""" % POD_ROOT
    encoded = base64.b64encode(code.encode("ascii")).decode("ascii")
    command = f"echo {encoded} | base64 -d | python3"
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", POD_HOST, command],
        check=False, capture_output=True,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace").strip())
    rows = json.loads(completed.stdout.decode("ascii"))
    names = [str(row["source_clip"]) for row in rows]
    if not rows or names != sorted(names) or len(names) != len(set(names)):
        raise ValueError("basketball pod inventory must be sorted and unique")
    if any(not (name.startswith("ncaa_basketball__") or name.startswith("wnba__")) for name in names):
        raise ValueError("basketball inventory contains an unexpected clip family")
    return rows
def seeded_samples(inventory: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Draw one deterministic random frame from each temporal stratum per clip."""
    rows = sorted(inventory, key=lambda item: item["source_clip"])
    if len(rows) != len({row["source_clip"] for row in rows}):
        raise ValueError("inventory clip names must be unique")
    rng = random.Random(SEED)
    result: list[dict[str, str]] = []
    for item in rows:
        frame_count = int(item["frame_count"])
        if frame_count < STRATA_PER_CLIP:
            raise ValueError(f"clip shorter than {STRATA_PER_CLIP} frames: {item['source_clip']}")
        for stratum in range(STRATA_PER_CLIP):
            start = frame_count * stratum // STRATA_PER_CLIP
            stop = frame_count * (stratum + 1) // STRATA_PER_CLIP
            frame_index = rng.randrange(start, stop)
            result.append({
                **item, "seed": str(SEED), "stratum": str(stratum),
                "frame_index": str(frame_index),
                "tile_filename": f"{item['clip']}__s{stratum:02d}__f{frame_index}.jpg",
            })
    keys = {(row["clip"], row["frame_index"]) for row in result}
    if len(keys) != len(result):
        raise ValueError("stratified sample contains a duplicate frame")
    return result
def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty artifact: {path}")
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
def write_sample_manifest() -> list[dict[str, str]]:
    """Inventory the read-only pod and persist the fixed pre-score sample."""
    OUT.mkdir(parents=True, exist_ok=True)
    rows = seeded_samples(_remote_inventory())
    _write_csv(OUT / "sample_manifest.csv", rows)
    _write_csv(OUT / "per_clip_counts.csv", [
        {"clip": clip, "sampled_frames": str(sum(row["clip"] == clip for row in rows))}
        for clip in sorted({row["clip"] for row in rows})
    ])
    return rows
def _load_sample() -> list[dict[str, str]]:
    with (OUT / "sample_manifest.csv").open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 200 or any(row["seed"] != str(SEED) for row in rows):
        raise ValueError("G137 requires its complete fixed seeded sample")
    expected = seeded_samples([{
        key: row[key] for key in ("source_clip", "clip", "frame_count", "width", "height")
    } for row in rows[::STRATA_PER_CLIP]])
    if rows != expected:
        raise ValueError("sample manifest differs from the deterministic G137 draw")
    return rows
def _pull_tiles(rows: list[dict[str, str]], tile_dir: Path) -> dict[tuple[str, str], Path]:
    tile_dir.mkdir(parents=True, exist_ok=True)
    locations: dict[tuple[str, str], Path] = {}
    by_clip: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        transport = {
            "source_clip": row["source_clip"], "frame_index": row["frame_index"],
            "tile_filename": row["tile_filename"], "tile_width": "640", "tile_height": "384", "header_height": "24",
            "header_text": f"f{row['frame_index']}", "header_origin_x": "8", "header_origin_y": "13",
            "header_font": "FONT_HERSHEY_SIMPLEX", "header_font_scale": "0.3",
            "header_bgr": "0,255,255", "header_thickness": "1", "jpeg_quality": "92",
        }
        by_clip.setdefault(row["source_clip"], []).append(transport)
    for clip_rows in by_clip.values():
        records = _records(_random_access_payload(clip_rows), len(clip_rows))
        for row, encoded in zip(clip_rows, records):
            destination = tile_dir / row["tile_filename"]
            destination.write_bytes(encoded)
            clip = Path(row["source_clip"]).stem
            locations[(clip, row["frame_index"])] = destination
    if len(locations) != len(rows):
        raise ValueError("not every G137 sampled frame was reconstructed")
    return locations
def _random_access_payload(rows: list[dict[str, str]]) -> bytes:
    """Read the retained, decodable sampled frames through the existing seek path."""
    code = """import base64,cv2,json,numpy as np,struct,sys
root,source,rows=json.loads(base64.b64decode(sys.argv[1]))
for target,name in rows:
 cap=cv2.VideoCapture(root+'/'+source); cap.set(cv2.CAP_PROP_POS_FRAMES,target); ok,frame=cap.read(); cap.release()
 if not ok: raise RuntimeError(source+':'+str(target))
 frame=cv2.resize(frame,(640,360)); tile=np.zeros((384,640,3),dtype=frame.dtype); tile[24:]=frame
 cv2.putText(tile,'f'+str(target),(8,13),cv2.FONT_HERSHEY_SIMPLEX,.3,(0,255,255),1)
 ok,encoded=cv2.imencode('.jpg',tile,[cv2.IMWRITE_JPEG_QUALITY,92])
 if not ok: raise RuntimeError(name)
 data=encoded.tobytes(); sys.stdout.buffer.write(struct.pack('!I',len(data))+data)
"""
    payload_rows = [(int(row["frame_index"]), row["tile_filename"]) for row in rows]
    payload = base64.b64encode(json.dumps([POD_ROOT, rows[0]["source_clip"], payload_rows]).encode("ascii")).decode("ascii")
    encoded = base64.b64encode(code.encode("ascii")).decode("ascii")
    completed = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", POD_HOST,
                                f"echo {encoded} | base64 -d | python3 - {payload}"], check=False, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("ascii", errors="replace").strip())
    return completed.stdout
def _league(clip: str) -> str:
    return "ncaa_legacy" if clip.startswith("ncaa_basketball__") else "nba_wnba"
def _role_claims(stable: list[CandidateLineGroup], league: str) -> dict[str, CandidateLineGroup | None]:
    """Reuse G134 groups and existing all-or-none role assignment unchanged."""
    assigned = assign_paint_roles(stable, league, "left")
    if assigned is None:
        return {role: None for role in ROLES}
    return {
        "baseline": assigned["baseline"], "free_throw": assigned["free_throw"],
        "lane_left": assigned["lane_low"], "lane_right": assigned["lane_high"],
    }
def _score(rows: list[dict[str, str]], tiles: dict[tuple[str, str], Path]) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[tuple[str, str], dict[str, CandidateLineGroup | None]]]:
    role_rows: list[dict[str, str]] = []
    frame_rows: list[dict[str, str]] = []
    assignments: dict[tuple[str, str], dict[str, CandidateLineGroup | None]] = {}
    for sample in rows:
        key = (sample["clip"], sample["frame_index"])
        image = cv2.imread(str(tiles[key]))
        if image is None:
            raise FileNotFoundError(tiles[key])
        _, _, stable = _groups(image)
        assigned = _role_claims(stable, _league(sample["clip"]))
        assignments[key] = assigned
        group_ids = {id(group): index for index, group in enumerate(stable)}
        for role in ROLES:
            group = assigned[role]
            role_rows.append({
                "clip": sample["clip"], "source_clip": sample["source_clip"],
                "frame_index": sample["frame_index"], "stratum": sample["stratum"], "role": role,
                "role_claimed": str(group is not None).lower(),
                "stable_group_index": "" if group is None else str(group_ids[id(group)]),
                "stable_group_length_px": "" if group is None else f"{group.length:.6f}",
            })
        count = sum(group is not None for group in assigned.values())
        frame_rows.append({
            "clip": sample["clip"], "source_clip": sample["source_clip"],
            "frame_index": sample["frame_index"], "stratum": sample["stratum"],
            "roles_detected": str(count), "qualifying_frame": str(count == len(ROLES)).lower(),
        })
    expected = {(row["clip"], row["frame_index"], role) for row in rows for role in ROLES}
    observed = {(row["clip"], row["frame_index"], row["role"]) for row in role_rows}
    if observed != expected or len(role_rows) != len(expected):
        raise ValueError("role artifact must contain four unique rows for every sampled frame")
    return role_rows, frame_rows, assignments
def joint_distribution(frame_rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Return every requested 0-through-4 role-count cell, including zeros."""
    rows = list(frame_rows)
    return [{"roles_detected": str(count), "frames": str(sum(int(row["roles_detected"]) == count for row in rows))}
            for count in range(len(ROLES) + 1)]
def _evenly_spaced(rows: list[dict[str, str]], limit: int = 5) -> list[dict[str, str]]:
    if len(rows) <= limit:
        return rows
    return [rows[round(index * (len(rows) - 1) / (limit - 1))] for index in range(limit)]
def _render(image: Any, assigned: dict[str, CandidateLineGroup | None], path: Path) -> None:
    render = image.copy()
    for role, group in assigned.items():
        if group is None:
            continue
        x0, y0 = group.anchor
        vx, vy = group.direction
        start, stop = group.extent
        first = (round(x0 + start * vx), round(y0 + start * vy))
        last = (round(x0 + stop * vx), round(y0 + stop * vy))
        cv2.line(render, first, last, ROLE_COLOURS[role], 2)
        cv2.putText(render, role, first, cv2.FONT_HERSHEY_SIMPLEX, .42, ROLE_COLOURS[role], 1)
    if not cv2.imwrite(str(path), render, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(path)
def _g84_overlap(rows: Iterable[dict[str, str]]) -> int:
    with G84_MANIFEST.open(newline="", encoding="ascii") as handle:
        g84 = {(row["clip"], row["frame_index"]) for row in csv.DictReader(handle)}
    return sum((row["clip"], row["frame_index"]) in g84 for row in rows)
def write_artifacts() -> None:
    """Score the prewritten sample, then write count and review evidence."""
    samples = _load_sample()
    unreadable_rows = [
        {"clip": row["clip"], "source_clip": row["source_clip"], "frame_index": row["frame_index"],
         "stratum": row["stratum"], "reason": UNREADABLE[(row["clip"], row["frame_index"])]}
        for row in samples if (row["clip"], row["frame_index"]) in UNREADABLE
    ]
    scored_samples = [row for row in samples if (row["clip"], row["frame_index"]) not in UNREADABLE]
    if len(scored_samples) < 200 or len(unreadable_rows) != len(UNREADABLE):
        raise ValueError("G137 requires at least 200 decodable, named sampled frames")
    with tempfile.TemporaryDirectory(prefix="g137_scale_") as temporary:
        tiles = _pull_tiles(scored_samples, Path(temporary))
        role_rows, frame_rows, assignments = _score(scored_samples, tiles)
        qualifiers = [row for row in frame_rows if row["qualifying_frame"] == "true"]
        selected = _evenly_spaced(qualifiers)
        renders = OUT / "renders"
        renders.mkdir(exist_ok=True)
        forwarded: list[dict[str, str]] = []
        for rank, row in enumerate(selected, start=1):
            key = (row["clip"], row["frame_index"])
            image = cv2.imread(str(tiles[key]))
            name = f"{row['clip']}__f{row['frame_index']}.jpg"
            _render(image, assignments[key], renders / name)
            forwarded.append({**row, "selection_rank": str(rank), "render": f"renders/{name}",
                              "eye_check": "PENDING", "solve_handoff": "pending_eye_check"})
    qualifying = len(qualifiers)
    low, high = wilson_interval(qualifying, len(frame_rows))
    _write_csv(OUT / "unreadable_sample_frames.csv", unreadable_rows)
    _write_csv(OUT / "scored_per_clip_counts.csv", [
        {"clip": clip, "scored_frames": str(sum(row["clip"] == clip for row in frame_rows))}
        for clip in sorted({row["clip"] for row in frame_rows})
    ])
    _write_csv(OUT / "frame_role_claims.csv", role_rows)
    _write_csv(OUT / "frame_joint_distribution.csv", joint_distribution(frame_rows))
    _write_csv(OUT / "qualifying_frames.csv", qualifiers or [{key: "" for key in frame_rows[0]}])
    if not qualifiers:
        (OUT / "qualifying_frames.csv").write_text(",".join(frame_rows[0]) + "\n", encoding="ascii")
    _write_csv(OUT / "forwarded_for_solve.csv", forwarded or [{"clip": "", "source_clip": "", "frame_index": "", "stratum": "", "roles_detected": "", "qualifying_frame": "", "selection_rank": "", "render": "", "eye_check": "", "solve_handoff": ""}])
    if not forwarded:
        (OUT / "forwarded_for_solve.csv").write_text("clip,source_clip,frame_index,stratum,roles_detected,qualifying_frame,selection_rank,render,eye_check,solve_handoff\n", encoding="ascii")
    summary = {
        "seed": SEED, "frames_per_clip": STRATA_PER_CLIP, "drawn_frames": len(samples),
        "sampled_frames": len(frame_rows), "unreadable_sample_frames": len(unreadable_rows),
        "qualifying_frames": qualifying, "qualifying_rate": qualifying / len(frame_rows),
        "wilson_95_low": low, "wilson_95_high": high,
        "independence_reference_rate": 0.0379,
        "g135_reference_zero_of_30_probability": 0.321,
        "g84_overlap_count": _g84_overlap(samples),
        "role_assignment_constraint": "assign_paint_roles returns four roles or none; 1/2/3 cells are structurally unavailable",
        "selected_for_eye_check_count": len(forwarded),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    print(f"sampled_frames={len(frame_rows)} qualifying_frames={qualifying}")
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true", help="write the seeded read-only pod sample manifest")
    parser.add_argument("--write", action="store_true", help="score the fixed manifest and write G137 artifacts")
    arguments = parser.parse_args()
    if arguments.sample:
        rows = write_sample_manifest()
        print(f"sampled_frames={len(rows)} clips={len(rows) // STRATA_PER_CLIP}")
    if arguments.write:
        write_artifacts()
