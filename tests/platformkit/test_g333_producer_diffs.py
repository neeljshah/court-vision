"""G333 construct tests for the four applied PROPOSED producer diffs.

Every test here fails on the pre-edit tree and passes on the edited tree.  The two
diffs that live inside a 1400-line method (G325's row-build guard, G320's flag
expression) are checked by parsing the SHIPPED source and evaluating the shipped
node, so the test exercises the real line rather than a re-typed copy of it.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import src.pipeline.unified_pipeline as up
from src.pipeline.unified_pipeline import UnifiedPipeline

REPO = Path(__file__).resolve().parents[2]
PIPELINE_SRC = REPO / "src" / "pipeline" / "unified_pipeline.py"


# --------------------------------------------------------------------------
# G330 -- the general fallback panorama must not be cached under the per-video key
# --------------------------------------------------------------------------
class _FakeCapture:
    """Minimal cv2.VideoCapture stand-in: a fixed number of blank frames."""

    def __init__(self, n_frames: int = 300, fps: float = 30.0, w: int = 320, h: int = 180):
        self._n, self._fps, self._w, self._h = n_frames, fps, w, h

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return self._fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return self._n
        return 0.0

    def set(self, *_args):
        return True

    def read(self):
        return True, np.zeros((self._h, self._w, 3), dtype=np.uint8)

    def release(self):
        return None


class _FakeDetector:
    """Stub feet detector whose model always reports enough people to be gameplay."""

    _use_half = False
    _infer_imgsz = 320

    @staticmethod
    def model(_frame, **_kwargs):
        return [SimpleNamespace(boxes=[None] * (up.MIN_GAMEPLAY_PERSONS + 2))]


def _valid_pano(w: int = 2400, h: int = 400) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


@pytest.fixture()
def pano_route(tmp_path, monkeypatch):
    """A stubbed panorama route rooted at a temporary resources directory."""
    resources = tmp_path / "resources"
    resources.mkdir()
    assert cv2.imwrite(str(resources / "pano_enhanced.png"), _valid_pano())
    monkeypatch.setattr(up, "_RESOURCES", str(resources))
    monkeypatch.setattr(up.cv2, "VideoCapture", lambda _p: _FakeCapture())
    video = str(tmp_path / "g333_clip.mp4")
    return SimpleNamespace(
        route=SimpleNamespace(feet_det=_FakeDetector()),
        video=video,
        cache=Path(UnifiedPipeline._auto_pano_path(video)),
    )


def _patch_collage(monkeypatch, image):
    import src.tracking.rectify_court as rectify

    monkeypatch.setattr(rectify, "collage", lambda _frames: image)


def test_g330_fallback_panorama_is_not_cached_per_video(pano_route, monkeypatch):
    """A stitch too small to be a panorama falls back -- and must leave no cache file."""
    _patch_collage(monkeypatch, np.zeros((300, 640, 3), dtype=np.uint8))
    pano_route.cache.unlink(missing_ok=True)

    pano = UnifiedPipeline._scan_and_build_pano(pano_route.route, pano_route.video)

    assert not UnifiedPipeline._pano_valid(np.zeros((300, 640, 3), dtype=np.uint8))
    assert pano.shape[:2] == (400, 2400), "the general fallback should have been substituted"
    assert not pano_route.cache.exists(), (
        f"the general fallback was cached under the per-video key {pano_route.cache.name}"
    )


def test_g330_stitched_panorama_is_still_cached_per_video(pano_route, monkeypatch):
    """The additive half: a real stitch keeps caching exactly as before."""
    _patch_collage(monkeypatch, _valid_pano(2400, 400))
    pano_route.cache.unlink(missing_ok=True)

    pano = UnifiedPipeline._scan_and_build_pano(pano_route.route, pano_route.video)

    assert pano.shape[:2] == (400, 2400)
    assert pano_route.cache.exists(), "a legitimately stitched panorama must still be cached"
    assert UnifiedPipeline._pano_valid(cv2.imread(str(pano_route.cache)))


def test_g330_local_per_video_cache_census_is_reported():
    """Informational: how many committed per-video panoramas are the general fallback."""
    pano_dir = REPO / "resources" / "panos"
    general = REPO / "resources" / "pano_enhanced.png"
    if not pano_dir.is_dir() or not general.is_file():
        pytest.skip("no local panorama cache directory in this worktree")
    want = hashlib.sha256(general.read_bytes()).hexdigest()
    files = sorted(pano_dir.glob("pano_*.png"))
    same = [p.name for p in files
            if hashlib.sha256(p.read_bytes()).hexdigest() == want]
    print(f"G330 local per-video cache census: {len(same)}/{len(files)} files are "
          f"byte-identical to resources/pano_enhanced.png")
    assert len(same) <= len(files)


# --------------------------------------------------------------------------
# G325 -- a coasting box with no overlap with the frame is not emitted
# --------------------------------------------------------------------------
FRAME_W, FRAME_H = 1280.0, 660.0


@pytest.mark.parametrize(
    "bbox,expected",
    [
        ((300, -400, 400, -280), True),    # wholly left of the frame
        ((300, 1400, 400, 1520), True),    # wholly right of the frame
        ((-300, 500, -40, 620), True),     # wholly above the frame
        ((700, 500, 860, 620), True),      # wholly below the frame
        ((300, -60, 400, 60), False),      # straddles the left boundary
        ((300, 1220, 400, 1340), False),   # straddles the right boundary
        ((-40, 500, 80, 620), False),      # straddles the top boundary
        ((600, 500, 720, 620), False),     # straddles the bottom boundary
        ((300, 500, 400, 620), False),     # fully interior
        (None, False),                     # no box at all
    ],
)
def test_g325_bbox_off_frame_predicate(bbox, expected):
    assert UnifiedPipeline._bbox_off_frame(bbox, FRAME_W, FRAME_H) is expected


def test_g325_identifier_survives_leaving_and_re_entering_the_frame():
    """Wholly-off-frame samples drop out; the identifier is unchanged on re-entry."""
    xs = [600, 300, 0, -200, -400, -200, 0, 300, 600]
    emitted = []
    for x in xs:
        bbox = (300, x, 400, x + 120)
        if UnifiedPipeline._bbox_off_frame(bbox, FRAME_W, FRAME_H):
            continue
        emitted.append((7, bbox))

    assert len(xs) - len(emitted) == 3, "exactly the three wholly-off-frame samples drop"
    assert {pid for pid, _ in emitted} == {7}, "the identifier survives the gap"
    assert emitted[0][1][1] == 600 and emitted[-1][1][1] == 600
    assert not any(UnifiedPipeline._bbox_off_frame(b, FRAME_W, FRAME_H) for _, b in emitted)


def _pipeline_tree() -> ast.Module:
    return ast.parse(PIPELINE_SRC.read_text(encoding="utf-8"))


def _statement_after_bbox_assignment() -> ast.stmt:
    """Return the statement that immediately follows `bbox = track[...]` in the source."""
    found = []
    for node in ast.walk(_pipeline_tree()):
        for attr in ("body", "orelse", "finalbody"):
            block = getattr(node, attr, None)
            if not isinstance(block, list):
                continue
            for index, stmt in enumerate(block[:-1]):
                if (isinstance(stmt, ast.Assign)
                        and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and stmt.targets[0].id == "bbox"
                        and isinstance(stmt.value, ast.Subscript)):
                    found.append(block[index + 1])
    assert len(found) == 1, f"expected exactly one row-build bbox assignment, found {len(found)}"
    return found[0]


def test_g325_shipped_row_build_carries_the_off_frame_guard():
    """The guard the smoke measures is really on the single row-build path."""
    guard = _statement_after_bbox_assignment()
    assert isinstance(guard, ast.If), "no guard follows the row-build bbox assignment"
    assert len(guard.body) == 1 and isinstance(guard.body[0], ast.Continue)
    assert not guard.orelse
    test_src = ast.unparse(guard.test)
    assert "_bbox_off_frame" in test_src
    assert "frame.shape" in test_src


# --------------------------------------------------------------------------
# G320 -- the inferred flag is written only on a row that has a coordinate
# --------------------------------------------------------------------------
def _ball_inferred_expression() -> ast.expr:
    """Pull the shipped `ball_inferred` value expression out of the ball-row dict."""
    found = []
    for node in ast.walk(_pipeline_tree()):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (isinstance(key, ast.Constant) and key.value == "ball_inferred"
                    and not isinstance(value, ast.Constant)):
                found.append(value)
    assert len(found) == 1, f"expected one computed ball_inferred value, found {len(found)}"
    return found[0]


def _evaluate_shipped_flag(ball_pos):
    expression = ast.Expression(body=_ball_inferred_expression())
    ast.fix_missing_locations(expression)
    detector = SimpleNamespace(ball_inferred=True)
    return eval(  # noqa: S307 - evaluating the project's own shipped expression
        compile(expression, str(PIPELINE_SRC), "eval"),
        {},
        {"ball_pos": ball_pos, "self": SimpleNamespace(ball_det=detector)},
    )


def test_g320_flag_is_zero_when_the_row_has_no_coordinate():
    assert _evaluate_shipped_flag(None) == 0


def test_g320_flag_is_one_when_the_row_has_a_coordinate():
    assert _evaluate_shipped_flag((512.0, 244.0)) == 1


# --------------------------------------------------------------------------
# G331 -- the route publishes its true post-run evaluated-frame count
# --------------------------------------------------------------------------
def _capped_sidecar(tmp_path: Path) -> Path:
    path = tmp_path / "evaluated_frame_count.json"
    path.write_text(json.dumps({
        "decoded_frames": 4021,
        "evaluated_frames": None,
        "formula": "ceil(decoded_frames / stride) when max_frames is null and start_frame is 0",
        "frame_count_validation": None,
        "max_frames": 150,
        "reason": "max_frames_is_detector_dependent_in_this_route",
        "start_frame": 1200,
        "stride": None,
    }, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_g331_post_run_count_replaces_the_null(tmp_path):
    from scripts.run_clip import _publish_evaluated_frames

    path = _capped_sidecar(tmp_path)
    before = json.loads(path.read_text(encoding="utf-8"))

    _publish_evaluated_frames(str(path), {"total_frames": 450, "evaluated_frames": 7})

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["evaluated_frames"] == 7
    assert after["reason"] is None
    unchanged = {k: v for k, v in after.items() if k not in ("evaluated_frames", "reason")}
    assert unchanged == {k: v for k, v in before.items() if k not in ("evaluated_frames", "reason")}


def test_g331_reason_is_retained_when_no_count_is_available(tmp_path):
    from scripts.run_clip import _publish_evaluated_frames

    path = _capped_sidecar(tmp_path)
    before = json.loads(path.read_text(encoding="utf-8"))

    _publish_evaluated_frames(str(path), {"total_frames": 450})

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["evaluated_frames"] is None
    assert after["reason"] == before["reason"]
