"""G327 source selection and frame snapshot -- rotation-proof construct inputs.

The pod corpus is a LIVE ROTATING QUEUE: the tracking daemon deletes each clip after
tracking it, so a construct that names source FILES cannot survive to its own run. These
helpers implement the sealed SELECTION RULE and the IMMEDIATE SNAPSHOT that replace it
(`docs/evidence/tracking/g327_prereg_2026-09-08c.md`, seal 6548ebe7d3).

Split out of g327_detector_batch_stability.py to keep both modules inside the 300-line
PlatformKit rail. Reads the corpus; never writes, moves or deletes any corpus file.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

CORPUS = "/workspace/nba-ai-system/data/footage_corpus"
FRAMES = 40       # sealed
MIN_WIDTH = 1280  # sealed; excludes the 640x360 tier, a different capture regime
N_GAMES = 3       # sealed; FATAL if fewer than 3 distinct game ids qualify


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def probe(command: list[str]) -> dict:
    """Run an operational probe and record its output verbatim."""
    r = subprocess.run(command, capture_output=True, text=True)
    rec = {"command": command, "rc": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    print(json.dumps(rec), flush=True)
    return rec


def indices(anchor: int, n: int = FRAMES) -> list[int]:
    """The G324 rule verbatim: n evenly spaced indices spanning 0 .. the MEASURED last
    decodable index, never ffprobe's nb_frames."""
    return [round(k * anchor / (n - 1)) for k in range(n)]


def ffprobe(path: str) -> dict | None:
    """ONE combined -show_entries: passing the flag twice makes the second occurrence
    silently override the first, which is why attempts 1 and 2 aborted on `KeyError`.
    Returns None for a path that has already been rotated out of the corpus."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json",
         path], capture_output=True, text=True)
    d = json.loads(out.stdout or "{}")
    if not d.get("streams"):
        return None
    s = d["streams"][0]
    return {"path": path, "bytes": Path(path).stat().st_size, "width": int(s["width"]),
            "height": int(s["height"]), "fps": s["r_frame_rate"],
            "nb_frames": s.get("nb_frames"),
            "duration_s": float(d.get("format", {}).get("duration", 0.0))}


def game_id(stem: str) -> str:
    """The clip's game, i.e. the stem with a trailing `_s<digits>` segment removed."""
    return re.sub(r"_s\d+$", "", stem)


def select_sources() -> list[dict]:
    """The SEALED selection rule: width >= MIN_WIDTH, newest mtime first, first clip of
    each distinct game id, until N_GAMES are collected. FATAL below N_GAMES -- no
    substitution and no relaxation of the width floor."""
    paths = sorted(Path(CORPUS).glob("*.mp4"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    picked, seen = [], set()
    for p in paths:
        gid = game_id(p.stem)
        if gid in seen:
            continue
        src = ffprobe(str(p))
        if src is None or src["width"] < MIN_WIDTH:
            continue
        seen.add(gid)
        src["game"] = p.stem
        src["game_id"] = gid
        src["mtime"] = p.stat().st_mtime
        picked.append(src)
        if len(picked) == N_GAMES:
            return picked
    raise RuntimeError("FATAL: only %d of %d distinct games qualified" % (len(picked),
                                                                         N_GAMES))


def anchor_of(path: str) -> int:
    """Readable-anchor rule: the LAST DECODABLE index by binary search on the real cv2
    seek path, never ffprobe's nb_frames."""
    import cv2
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def ok(i: int) -> bool:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        r, f = cap.read()
        return bool(r and f is not None)

    lo, hi = 0, max(0, n - 1)
    if not ok(hi):
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if ok(mid):
                lo = mid
            else:
                hi = mid - 1
        hi = lo
    cap.release()
    return hi


def decode(path: str, idxs: list[int], topcut: int) -> tuple[list, str, list]:
    """One decode per game; every arm sees these exact arrays. A failed read is FATAL
    and is never dropped -- a silently short frame list would shrink the denominator."""
    import cv2
    cap = cv2.VideoCapture(path)
    frames, digest, per_frame = [], hashlib.sha256(), []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            raise RuntimeError("FATAL: frame %d unreadable in %s" % (i, path))
        frame = frame[topcut:]
        raw = frame.tobytes()
        digest.update(raw)
        per_frame.append(hashlib.sha256(raw).hexdigest())
        frames.append(frame)
    cap.release()
    return frames, digest.hexdigest(), per_frame


def save_frames(path, frames: list) -> None:
    """PERSIST the snapshot. Attempt 1 held its decoded frames in MEMORY only and
    recorded their hashes; when the process ended and the rotating corpus deleted all
    three clips, the sealed sample became unreachable and unverifiable. Writing the
    bytes is what makes the sealed hash list checkable by anyone, later."""
    import numpy as np
    np.save(path, np.stack(frames), allow_pickle=False)


def load_frames(path) -> list:
    """The snapshot back as per-frame arrays. Each is a contiguous view of the stack,
    so `tobytes()` reproduces the bytes that were hashed at snapshot time."""
    import numpy as np
    return list(np.load(path, allow_pickle=False))
