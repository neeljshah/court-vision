"""G330 attempt 2 -- salted section selection, the route's own stateful matcher, held-out inliers.

Additive to `g330_panorama_identity.py`; the attempt-1 modules and artifacts are untouched.
`src/` is IMPORTED read-only and never edited: the frame-to-panorama step scored here is the
production method `UnifiedPipeline._get_homography` itself, called on an instance carrying only the
attributes that method and its drift check read. Heavy imports stay inside functions so the pure
selection and held-out arithmetic below unit-test without cv2, torch or ultralytics.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Sealed in docs/evidence/tracking/g330_prereg_attempt2_2026-09-08.md, section 1.
SALT = "G330-attempt2-2026-09-08"
MIN_HEIGHT = 720
N_EVAL = 40
MIN_HALF = 4  # cv2.findHomography needs four correspondences in each half
GAME_RE = re.compile(r"^(.*)_s\d+\.mp4$")


def game_id(basename: str) -> str:
    """The game a section belongs to: the basename with its trailing _s<digits>.mp4 removed."""
    hit = GAME_RE.match(basename)
    return hit.group(1) if hit else basename


def rank_key(basename: str, salt: str = SALT) -> str:
    """Sealed rank key: sha256 of the basename concatenated with the salt."""
    return hashlib.sha256((basename + salt).encode("ascii")).hexdigest()


def select_sections(candidates, salt: str = SALT, n: int = 3) -> list:
    """Lowest `n` distinct game ids under the salted rank -- a permutation, never a head slice.

    `candidates` is an iterable of (basename, height); a height below MIN_HEIGHT is not eligible.
    """
    ranked = sorted((rank_key(name, salt), name)
                    for name, height in candidates if int(height) >= MIN_HEIGHT)
    picked: list = []
    seen: set = set()
    for _, name in ranked:
        gid = game_id(name)
        if gid in seen:
            continue
        seen.add(gid)
        picked.append(name)
        if len(picked) == n:
            break
    return picked


def eval_indices(nb_frames: int, n: int = N_EVAL) -> list:
    """Sealed evaluation frames: a fixed stride from a mid-stride offset, spanning the whole file.

    Never the first n frames: the offset is half a stride and the last index sits near the end.
    """
    stride = max(1, int(nb_frames) // n)
    offset = stride // 2
    return [offset + i * stride for i in range(n)]


def heldout_split(n_matches: int):
    """The sealed split: even match indices FIT, odd match indices HELD-OUT."""
    return list(range(0, n_matches, 2)), list(range(1, n_matches, 2))


def reprojection_errors(homography, frame_pts, pano_pts):
    """Distance in panorama pixels between each projected frame point and its panorama point."""
    import numpy as np
    src = np.asarray(frame_pts, dtype=float).reshape(-1, 2)
    dst = np.asarray(pano_pts, dtype=float).reshape(-1, 2)
    homo = (np.asarray(homography, dtype=float) @ np.hstack(
        [src, np.ones((len(src), 1))]).T).T
    scale = homo[:, 2:3].copy()
    scale[np.abs(scale) < 1e-12] = 1e-12
    return np.linalg.norm(homo[:, :2] / scale - dst, axis=1)


def heldout_stats(frame_pts, pano_pts, ransac_px: float, fitter=None):
    """Fit on the FIT half, score the HELD-OUT half. Returns a dict or None when a half is short.

    `ransac_px` is the route's own reprojection threshold, passed in, never invented here.
    `fitter` defaults to cv2.findHomography; the driver passes the unwrapped one so this row's own
    fit is not captured by the recorder.
    """
    import cv2
    import numpy as np
    fitter = fitter or cv2.findHomography
    src = np.asarray(frame_pts, dtype=np.float32).reshape(-1, 1, 2)
    dst = np.asarray(pano_pts, dtype=np.float32).reshape(-1, 1, 2)
    fit_idx, held_idx = heldout_split(len(src))
    if len(fit_idx) < MIN_HALF or len(held_idx) < MIN_HALF:
        return None
    homography, mask = fitter(src[fit_idx], dst[fit_idx], cv2.RANSAC, ransac_px)
    if homography is None:
        return None
    errors = reprojection_errors(homography, src[held_idx], dst[held_idx])
    return {
        "n_fit": len(fit_idx),
        "n_held": len(held_idx),
        "fit_inliers": int(mask.sum()) if mask is not None else 0,
        "held_inliers": int((errors <= ransac_px).sum()),
        "held_median_px": float(np.median(errors)),
    }


class MatchRecorder:
    """Capture the correspondences the route's OWN findHomography call receives.

    The route builds them at `unified_pipeline.py:1297-1299` and hands them straight to
    `cv2.findHomography`; wrapping that symbol records the pair without changing a byte of `src/`
    and without changing the value the route gets back. `real` stays available so this row's own
    held-out fit does not record itself.
    """

    def __init__(self):
        self.calls: list = []
        self.real = None

    def __enter__(self):
        import cv2
        self.real = cv2.findHomography
        real = self.real
        calls = self.calls

        def wrapper(frame_pts, pano_pts, *args, **kwargs):
            calls.append((frame_pts, pano_pts))
            return real(frame_pts, pano_pts, *args, **kwargs)

        cv2.findHomography = wrapper
        return self

    def __exit__(self, *exc):
        import cv2
        cv2.findHomography = self.real
        return False

    def drain(self) -> list:
        # Clear IN PLACE: the wrapper closure holds this exact list, so rebinding self.calls to a
        # fresh one would orphan it and silently drop every call after the first drain.
        taken = list(self.calls)
        self.calls.clear()
        return taken


def make_arm(pano_bgr):
    """A route pipeline instance carrying ONLY what `_get_homography` and its drift check read.

    Built with `__new__` because a full `__init__` starts a checkpoint thread and constructs OCR,
    resolver and re-identification components this row does not use and that would write outside
    the job root (prereg section 5). The scored method is the route's own, unmodified.
    """
    import cv2
    import numpy as np
    from scripts.platformkit.tracking.g330_panorama_identity import route
    pipeline = route()
    arm = pipeline.UnifiedPipeline.__new__(pipeline.UnifiedPipeline)
    # The route pads the panorama with 100 black rows before SIFT (_load_pano lines 866, 877).
    padded = np.vstack((pano_bgr, np.zeros((100, pano_bgr.shape[1], 3), dtype=pano_bgr.dtype)))
    sift = cv2.SIFT_create()
    arm.sift = sift
    arm.pano = padded
    arm.kp1, arm.des1 = sift.compute(padded, sift.detect(padded))
    arm._kornia_matcher = None
    arm._M_ema = None
    arm._sift_frame_counter = 0
    arm._sift_last_hist = None
    arm._homography_suspended = False
    arm._frames_since_anchor = 0
    arm._M1_raw_clip = None
    resources = Path(pipeline._RESOURCES)
    arm.M1 = np.load(resources / "Rectify1.npy")
    arm.map_2d = cv2.imread(str(resources / "2d_map.png"))
    return arm


class ArmTally:
    """Per-cell counters for one section and one arm."""

    def __init__(self):
        self.n_frames = 0
        self.feet_total = 0
        self.valid = 0
        self.feet_eval = 0
        self.feet_in = 0
        self.fit_frames = 0
        self.good = 0
        self.n_fit = 0
        self.n_held = 0
        self.fit_inliers = 0
        self.held_inliers = 0
        self.medians: list = []

    def add_fit(self, stats, n_good: int):
        self.good += n_good
        self.fit_frames += 1
        if stats is None:
            return
        self.n_fit += stats["n_fit"]
        self.n_held += stats["n_held"]
        self.fit_inliers += stats["fit_inliers"]
        self.held_inliers += stats["held_inliers"]
        self.medians.append(stats["held_median_px"])

    def median_px(self) -> str:
        if not self.medians:
            return "-"
        ordered = sorted(self.medians)
        mid = len(ordered) // 2
        value = (ordered[mid] if len(ordered) % 2
                 else 0.5 * (ordered[mid - 1] + ordered[mid]))
        return "%.3f" % value


def step_arm(arm, frame, recorder, tally, ransac_px: float, rows=None, tag=()):
    """One frame through the route's own matcher, then the held-out split on what it matched."""
    homography = arm._get_homography(frame)
    for frame_pts, pano_pts in recorder.drain():
        stats = heldout_stats(frame_pts, pano_pts, ransac_px, fitter=recorder.real)
        tally.add_fit(stats, len(frame_pts))
        if rows is not None:
            rows.append(tuple(tag) + (len(frame_pts), stats))
    return homography
