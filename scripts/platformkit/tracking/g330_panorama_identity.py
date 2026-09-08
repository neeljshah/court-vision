"""G330 -- panorama cache identity census and frame-to-panorama registration proxies.

Additive and read-only with respect to `src/`: the route's constants, its validity gate, its
collage and its matcher parameters are IMPORTED or replicated from
`src/pipeline/unified_pipeline.py` and `src/tracking/player_detection.py`; nothing there is edited
and no threshold is set. Heavy imports stay inside functions so the pure census and arithmetic
helpers below can be unit-tested without cv2, torch or ultralytics.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

STEM_RE = re.compile(r"^pano_(.+)\.png$", re.IGNORECASE)
# The general fallback the route substitutes when a per-clip stitch fails
# (unified_pipeline.py lines 891 and 975).
GENERAL_NAMES = ("pano_enhanced.png", "pano.png")


def claimed_stem(path: str) -> str:
    """Video stem a panorama path claims, or '-' when the path claims no video."""
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    if base in GENERAL_NAMES:
        return "-"
    hit = STEM_RE.match(base)
    return hit.group(1) if hit else "-"


def parse_census_line(line: str) -> dict:
    """Parse one 'sha256|bytes|mtime|path' line produced by the pod census command."""
    sha, size, mtime, path = line.rstrip("\n").split("|", 3)
    return {"sha256": sha, "bytes": int(size), "mtime": mtime, "path": path,
            "stem": claimed_stem(path)}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_census(root: Path, subdirs=("data", "resources")) -> list:
    """Every regular file under root/<subdir> whose basename names a panorama."""
    out = []
    for sub in subdirs:
        base = root / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            low = p.name.lower()
            if "pano" not in low and "panorama" not in low:
                continue
            rel = p.relative_to(root).as_posix()
            out.append({"sha256": sha256_of(p), "bytes": p.stat().st_size,
                        "mtime": "%.10f" % p.stat().st_mtime, "path": rel,
                        "stem": claimed_stem(rel)})
    return out


def group_by_sha(rows) -> dict:
    """sha256 -> list of rows, insertion-ordered."""
    groups: dict = {}
    for row in rows:
        groups.setdefault(row["sha256"], []).append(row)
    return groups


def collisions(rows) -> list:
    """Groups holding at least two DIFFERENT claimed video stems, largest first."""
    out = []
    for sha, members in group_by_sha(rows).items():
        stems = sorted({m["stem"] for m in members if m["stem"] != "-"})
        if len(stems) >= 2:
            out.append({"sha256": sha, "size": len(members), "stems": stems,
                        "bytes": members[0]["bytes"]})
    out.sort(key=lambda g: -g["size"])
    return out


def premise_holds(rows) -> bool:
    """True when two panoramas claiming DIFFERENT videos are byte-identical."""
    return bool(collisions(rows))


def pad6(value: int) -> str:
    """Zero-pad an integer count to six digits (contract Q6 formatting)."""
    return "%06d" % int(value)


def frac(num: int, den: int) -> str:
    """A share written as a fraction, never as a decimal."""
    return "%d/%d" % (int(num), int(den))


def pano_provenance_fields(video_path: str, pano_path: str) -> dict:
    """NEW sidecar fields only -- what panorama a game was registered against.

    Additive by construction: this returns three field names that appear nowhere in the route's
    existing tracking sidecars, so a producer can merge them into its own record without changing
    or reinterpreting any field it already writes.
    """
    p = Path(pano_path)
    name = p.name
    return {
        "pano_path": p.as_posix(),
        "pano_sha256": sha256_of(p) if p.is_file() else "",
        "pano_is_general_fallback": name in GENERAL_NAMES,
        "video_stem": Path(video_path).stem,
    }


def write_pano_provenance(out_dir, video_path: str, pano_path: str) -> Path:
    """Write the additive sidecar so a census over past runs is recomputable."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "pano_provenance.json"
    dest.write_text(json.dumps(pano_provenance_fields(video_path, pano_path),
                               indent=2, sort_keys=True) + "\n", encoding="ascii")
    return dest


# ---------------------------------------------------------------------------
# Registration proxies. Heavy imports live inside these functions.
# ---------------------------------------------------------------------------

def route():
    """The production pipeline module, imported read-only with LoFTR off (CPU proxy)."""
    os.environ.setdefault("COURTV_NO_LOFTR", "1")
    import src.pipeline.unified_pipeline as up
    return up


def sift_reference(pano):
    """Panorama keypoints exactly as unified_pipeline.py lines 758-761 build them."""
    import cv2
    sift = cv2.SIFT_create()
    kp1, des1 = sift.compute(pano, sift.detect(pano))
    return sift, kp1, des1


def match_frame(frame, sift, kp1, des1):
    """Replicate unified_pipeline.py lines 1265-1301: bottom region, scale, Lowe 0.7, RANSAC 5.0.

    Returns (n_good_matches, n_inliers, M) with M mapping frame pixels to panorama pixels.
    """
    import cv2
    import numpy as np
    up = route()
    h = frame.shape[0]
    y_offset = int(h * 0.30)
    region = frame[y_offset:, :]
    small = cv2.resize(region, (int(region.shape[1] * up._SIFT_SCALE),
                                int(region.shape[0] * up._SIFT_SCALE)))
    kp2_small, des2 = sift.detectAndCompute(small, None)
    if des2 is None or len(des2) < 4 or des1 is None:
        return 0, 0, None
    inv_s = 1.0 / up._SIFT_SCALE
    kp2 = [cv2.KeyPoint(kp.pt[0] * inv_s, kp.pt[1] * inv_s + y_offset, kp.size * inv_s,
                        kp.angle, kp.response, kp.octave, kp.class_id) for kp in kp2_small]
    des2_capped = des2[:min(500, len(des2))]
    matches = up.FLANN.knnMatch(des1, des2_capped, k=2)
    good = [m for m, n in matches if m.distance < 0.7 * n.distance]
    if len(good) < 4:
        return len(good), 0, None
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, mask = cv2.findHomography(dst, src, cv2.RANSAC, 5.0)
    if M is None:
        return len(good), 0, None
    return len(good), int(mask.sum()) if mask is not None else 0, M


def feet_from_boxes(boxes, shape):
    """Foot point per person box: player_detection.py lines 126-151 ((x1c+x2c)//2, y2c)."""
    feet = []
    for box in boxes:
        x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
        y2c = min(shape[0], y2)
        x1c, x2c = max(0, x1), min(shape[1], x2)
        if x2c <= x1c or y2c <= max(0, y1):
            continue
        feet.append(((x1c + x2c) // 2, y2c))
    return feet


def inside_court(feet, M, M1, map_w, map_h):
    """Count feet whose court point lands in the map, player_detection.py lines 151-160."""
    import numpy as np
    hits = 0
    for x, y in feet:
        kpt = np.array([x, y, 1])
        homo = M1 @ (M @ kpt.reshape((3, -1)))
        homo = np.int32(homo / homo[-1]).ravel()
        if 0 <= homo[0] < map_w and 0 <= homo[1] < map_h:
            hits += 1
    return hits


def eval_frames(video_path, stride=90, limit=40):
    """Decode frames at 0, stride, 2*stride, ... applying the route's TOPCUT crop."""
    import cv2
    up = route()
    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for fno in range(0, max(total, 1), stride):
        if len(out) >= limit:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, frame = cap.read()
        if not ok:
            break
        out.append(frame[up.TOPCUT:])
    cap.release()
    return out


def build_arm_v(video_path, model):
    """The route's builder logic on this section only -- no general-fallback substitution.

    Mirrors unified_pipeline.py `_scan_and_build_pano` lines 899-986: person gate at
    MIN_GAMEPLAY_PERSONS, a five-second stitch window of _PANO_STITCH_FRAMES frames, the route's
    collage, its wide-crop (ratio above 10.0 cropped to 6.0) and its `_pano_valid` gate. The
    fallback substitution at lines 975-981 is deliberately NOT applied (see the prereg): it would
    make ARM V byte-identical to ARM F. Returns (pano, reason) with pano None when NOT BUILDABLE.
    """
    import cv2
    import src.tracking.rectify_court as rc
    from src.tracking.rectify_court import collage
    # CPU only, per the G330 spec, and the producer's own branch: kornia is NOT installed on the
    # pod (measured 2026-09-08), so `_warp_perspective` (rectify_court.py lines 16-31) takes its
    # cv2 branch there. Setting the flag at runtime touches no file under src/.
    rc._HAS_KORNIA = False
    up = route()
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    first = -1
    for fno in range(0, total, up._PANO_SCAN_INTERVAL):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, frame = cap.read()
        if not ok:
            break
        res = list(model(frame[up.TOPCUT:], classes=[0], conf=0.4, verbose=False,
                         imgsz=640, device="cpu", stream=True))
        n = len(res[0].boxes) if res[0].boxes is not None else 0
        if n >= up.MIN_GAMEPLAY_PERSONS:
            first = fno
            break
    if first < 0:
        cap.release()
        return None, "no gameplay frame at the route person gate"
    window = min(int(fps * 5), total - first)
    step = max(1, window // up._PANO_STITCH_FRAMES)
    stitch = []
    for fno in range(first, first + window, step):
        if len(stitch) >= up._PANO_STITCH_FRAMES:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, f = cap.read()
        if not ok:
            break
        stitch.append(f[up.TOPCUT:])
    cap.release()
    if not stitch:
        return None, "no stitch frames decoded"
    try:
        pano = collage(stitch)
    except Exception as exc:  # the route does the same at line 954
        detail = ("%s: %s" % (type(exc).__name__, exc)).replace(",", ";")
        return None, "collage raised %s" % detail[:160]
    h_p, w_p = pano.shape[:2]
    ratio = w_p / max(h_p, 1)
    if ratio > 10.0 and w_p >= 2000:
        target = int(h_p * 6.0)
        if target < w_p:
            x0 = (w_p - target) // 2
            pano = pano[:, x0:x0 + target]
    h_p, w_p = pano.shape[:2]
    if not up.UnifiedPipeline._pano_valid(pano):
        return None, "route validity gate rejected %dx%d" % (w_p, h_p)
    return pano, "built %dx%d from %d frames" % (w_p, h_p, len(stitch))
