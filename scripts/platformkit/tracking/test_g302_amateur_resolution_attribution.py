"""Contract checks for the G302 attempt-2 three-arm amateur-vs-resolution attribution."""
import csv
import json
import pathlib

import numpy as np

from scripts.platformkit.tracking import g302_amateur_resolution_attribution as g302
from scripts.platformkit.tracking import g302_score, g302_source_identity

ROOT = pathlib.Path(__file__).resolve().parents[3]
ARTIFACT = ROOT / "docs/evidence/tracking/g302_amateur_resolution_attribution_artifact"


class _Capture:
    """Minimal sequential-decode stand-in; each frame encodes its own index."""

    def __init__(self, size):
        self.size, self.position, self.released = size, 0, False

    def grab(self):
        self.position += 1
        return True

    def read(self):
        image = np.full((self.size[1], self.size[0], 3), self.position % 251, dtype=np.uint8)
        self.position += 1
        return True, image

    def release(self):
        self.released = True


class _Detector:
    """Records every production-style detector call the harness makes."""

    _infer_imgsz, _use_half, _device = 640, False, "cpu"

    def __init__(self):
        self.calls = []

    def model(self, frame, **kwargs):
        self.calls.append({"shape": frame.shape[:2], "value": int(frame[0, 0, 0]), "kwargs": dict(kwargs)})

        class _Result:
            boxes = None

        return [_Result()]


def test_denominator_is_seventy_two_per_arm_over_one_grid_shape():
    assert g302.SAMPLE_SIZE == 72
    assert g302.BIN_FRAMES == 16
    assert g302.PROCESSED == 72 * 16
    for arm, start in g302.ARM_SPAN_START.items():
        frames = g302.frame_indices(start)
        assert len(frames) == 1152, arm
        assert sorted(set(frames)) == frames
        assert frames[0] == start
        assert all(frames[i + 1] - frames[i] == g302.STRIDE for i in range(len(frames) - 1))


def test_arms_1_and_2_share_one_span_and_arm_3_uses_the_g280_clip_frames():
    """The broadcast span is inside G273's own inherited span; arm 3 is the clip's own frames."""
    assert g302.ARM_SPAN_START[g302.ARMS[0]] == g302.ARM_SPAN_START[g302.ARMS[1]] == 19599
    assert g302.ARM_SPAN_START[g302.ARMS[2]] == 0
    broadcast = g302.frame_indices(g302.BROADCAST_SPAN_START)
    assert 19599 <= broadcast[0] and broadcast[-1] <= 23399  # G273 inherited_source span
    amateur = g302.frame_indices(g302.AMATEUR_SPAN_START)
    assert amateur[-1] < 3729  # the G280 clip's recorded frame count


def test_four_g273_categories_unchanged_and_in_committed_order():
    assert g302.VERDICTS == ("PLAYER", "PERSON NOT PLAYER IN PLAY", "NOT A PERSON", "CANNOT JUDGE")


def test_three_arms_and_one_crop_geometry_shared_by_all_of_them():
    assert g302.ARMS == ("arm1_broadcast_1080_native", "arm2_broadcast_720_downscaled",
                         "arm3_amateur_720_native")
    assert (g302.CROP_W, g302.CROP_H) == (512, 640)
    for size in ((1080, 1920), (720, 1280)):
        out = g302.crop(np.zeros(size + (3,), dtype=np.uint8), 40.0, 30.0)
        assert out.shape == (g302.CROP_H, g302.CROP_W, 3)


def test_arm1_and_arm2_differ_only_in_source_resolution(monkeypatch):
    """Both arms must read the SAME decoded pixels and the SAME detector settings."""
    monkeypatch.setattr(g302, "PROCESSED", 4)
    monkeypatch.setattr(g302, "open_capture", lambda video, expected: _Capture(expected))
    detector = _Detector()
    g302.detect_pass(detector, "unused", (1920, 1080),
                     [(g302.ARMS[0], None), (g302.ARMS[1], g302.DOWNSCALE)], 0)
    assert len(detector.calls) == 8
    for native, scaled in zip(detector.calls[0::2], detector.calls[1::2]):
        assert native["shape"] == (1080, 1920)
        assert scaled["shape"] == (720, 1280)
        assert native["value"] == scaled["value"]
        assert native["kwargs"] == scaled["kwargs"]


def test_every_arm_uses_the_unedited_production_detector_settings(monkeypatch):
    monkeypatch.setattr(g302, "PROCESSED", 2)
    monkeypatch.setattr(g302, "open_capture", lambda video, expected: _Capture(expected))
    detector = _Detector()
    g302.detect_pass(detector, "unused", (1280, 720), [(g302.ARMS[2], None)], 0)
    assert detector.calls
    for call in detector.calls:
        assert call["kwargs"] == {"classes": [0], "conf": 0.3, "verbose": False, "imgsz": 640,
                                  "half": False, "device": "cpu"}


def test_one_detection_drawn_from_each_of_seventy_two_equal_width_bins():
    for start in (g302.BROADCAST_SPAN_START, g302.AMATEUR_SPAN_START):
        rows = [{"source_frame": f, "foot_x_px": 1.0, "foot_y_px": 2.0} for f in g302.frame_indices(start)]
        picked = g302.select_evenly(rows, start)
        assert len(picked) == 72
        assert sorted(row["frame_bin"] for row in picked) == list(range(1, 73))
        assert len({row["source_frame"] for row in picked}) == 72


def test_two_proportion_reproduces_the_published_g280b_arithmetic():
    result = g302_score.two_proportion(43, 25)
    assert round(result["z"], 6) == 3.004640
    assert round(result["nominal_two_sided_p"], 6) == 0.002659


def test_identity_check_records_the_master_facts_it_must_match():
    """The re-acquired sources are qualified against what master recorded, not against a substitute."""
    assert g302_source_identity.PRIOR["g273"]["recorded"]["bytes"] == 2931985407
    assert g302_source_identity.PRIOR["g273"]["recorded"]["resolution_px"] == [1920, 1080]
    assert g302_source_identity.PRIOR["g280b"]["recorded"]["sha256"] == (
        "773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea")
    assert g302_source_identity.PRIOR["g280b"]["recorded"]["resolution_px"] == [1280, 720]
    rows, renders = g302_source_identity.prior_rows("g273", ROOT)
    assert len(rows) == 72 and renders.is_dir()
    rows, renders = g302_source_identity.prior_rows("g280b", ROOT)
    assert len(rows) == 72 and renders.is_dir()


def test_committed_identity_reports_show_both_sources_are_the_prior_populations():
    for name in ("g273_broadcast_identity.json", "g280b_amateur_identity.json"):
        report = json.loads((ARTIFACT / "identity" / name).read_text(encoding="ascii"))
        assert report["reproduction"]["crops"] == 72
        assert report["reproduction"]["crops_under_3_mad"] == 72
        assert report["resolution_equal"] is True
        assert report["verdict"] == "SAME POPULATION"


def test_decomposition_sums_to_the_arm1_arm3_gap_and_leaves_an_unresolved_remainder():
    assert round(g302.PRIOR_PLAYER_GAP, 6) == 0.25
    result = g302_score.summarize(ARTIFACT)
    assert all(sum(result["counts"][arm].values()) == 72 for arm in g302.ARMS)
    total = result["player_drop_total_arm1_vs_arm3"]
    assert round(result["player_drop_resolution"] + result["player_drop_amateur_matched"], 12) == round(total, 12)
    assert round(g302.PRIOR_PLAYER_GAP - total, 12) == round(result["unresolved_remainder"], 12)
    with (ARTIFACT / "eye_check.csv").open(newline="", encoding="ascii") as handle:
        eye = list(csv.DictReader(handle))
    assert len(eye) == 18
    assert sorted({int(r["frame_bin"]) for r in eye}) == list(g302_score.EYE_BINS)
    assert {r["arm"] for r in eye} == set(g302.ARMS)
    assert all(r["verdict"] in g302.VERDICTS for r in eye)
