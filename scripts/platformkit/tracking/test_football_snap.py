"""Synthetic-clip proof for the football image_px snap detector.

The synthetic clip mimics the mechanism the detector actually relies on: a
broadcast camera holds still while the offence is set, then pans with the play.
Small rectangles alone would not move the whole-frame median, so a generator
without the pan would test nothing.
"""
import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.tracking.football_snap import (
    MOTION_CLS, SNAP_CLS, STEP_FRAMES, detect_snaps, frame_energy)

FPS = 30.0
QUIET_LEN, PLAY_LEN, PLAYS = 70, 55, 8
TOLERANCE = int(round(0.5 * FPS))  # the memo's +/- 0.5 s primary tolerance


def _texture(height=180, width=560):
    rng = np.random.default_rng(7)
    field = rng.integers(60, 140, size=(height, width), dtype=np.uint8)
    smooth = np.repeat(np.repeat(field[::4, ::4], 4, axis=0), 4, axis=1)
    return np.dstack([smooth] * 3).astype(np.uint8)


def _synthetic_clip():
    """Yield frames and the ground-truth snap frame indices."""
    board = _texture()
    frames, truth, index, rng = [], [], 0, np.random.default_rng(11)
    pan = 0.0
    for play in range(PLAYS):
        players = rng.integers(20, 140, size=(11, 2)).astype(float)
        for step in range(QUIET_LEN + PLAY_LEN):
            snapped = step >= QUIET_LEN
            if snapped:
                pan += 2.5
                players += rng.normal(4.0, 1.0, size=players.shape)
            else:
                players += rng.normal(0.0, 0.15, size=players.shape)
            left = int(pan) % (board.shape[1] - 320)
            frame = board[:, left:left + 320].copy()
            for cx, cy in players:
                x, y = int(cx) % 300, int(cy) % 160
                frame[y:y + 14, x:x + 8] = (240, 240, 240)
            frames.append(frame)
            if snapped and step == QUIET_LEN:
                truth.append(index)
            index += 1
        pan += 40.0  # between plays the camera resets; a jump, not a snap
    return frames, truth


@pytest.fixture(scope="module")
def clip():
    frames, truth = _synthetic_clip()
    table = frame_energy(iter(frames))
    return frames, truth, table


def test_energy_matches_the_adapter_statistic(clip):
    """Reuse guarantee: this module reports the adapter's motion_magnitude."""
    from domains.football.tracking.adapter import FootballAdapter
    import cv2
    frames, _, table = clip
    scale = 320 / float(frames[0].shape[1])
    pair = [cv2.resize(f, (320, max(1, int(round(f.shape[0] * scale)))))
            for f in frames[40:42]]
    assert table.loc[table["frame"] == 41, "energy"].iloc[0] == pytest.approx(
        FootballAdapter.motion_magnitude(pair[0], pair[1]))


def test_snap_precision_and_recall_on_known_truth(clip):
    _, truth, table = clip
    events = detect_snaps(table["energy"].tolist(), FPS)
    detected = [event["frame"] for event in events]
    matched = {t for t in truth if any(abs(d - t) <= TOLERANCE for d in detected)}
    hits = [d for d in detected if any(abs(d - t) <= TOLERANCE for t in truth)]
    recall, precision = len(matched) / len(truth), len(hits) / max(1, len(detected))
    print("synthetic: %d truth, %d detected, recall %.3f, precision %.3f"
          % (len(truth), len(detected), recall, precision))
    assert recall >= 0.70, "memo primary gate: >=70%% of snaps within +/-0.5 s"
    assert precision >= 0.70


def test_shuffled_null_control_scores_below_half(clip):
    """The memo's null: the same detection count at uniformly random times."""
    _, truth, table = clip
    events = detect_snaps(table["energy"].tolist(), FPS)
    rng = np.random.default_rng(3)
    real = sum(any(abs(e["frame"] - t) <= TOLERANCE for e in events) for t in truth) / len(truth)
    trials = []
    for _ in range(200):
        fake = rng.integers(0, len(table), size=len(events))
        trials.append(sum(any(abs(f - t) <= TOLERANCE for f in fake) for t in truth) / len(truth))
    null = float(np.mean(trials))
    print("null control: real %.3f vs shuffled mean %.3f" % (real, null))
    assert null < 0.5 * real


def test_truncation_invariance(clip):
    """Causal + fixed lookahead: truncating cannot rewrite a settled event."""
    _, _, table = clip
    series = table["energy"].tolist()
    full = detect_snaps(series, FPS)
    cut = len(series) // 2
    partial = detect_snaps(series[:cut], FPS)
    settled = [e for e in full if e["frame"] + STEP_FRAMES < cut]
    assert settled, "truncation test needs at least one settled event"
    assert [e["frame"] for e in partial] == [e["frame"] for e in settled]
    for a, b in zip(partial, settled):
        assert a["confidence"] == pytest.approx(b["confidence"])


def test_rows_declare_image_px_and_carry_both_channels():
    from scripts.platformkit.tracking_schema import (
        CoordinateTransformUnavailable, normalize_tracking_frame)
    from scripts.platformkit.tracking.football_snap import _rows
    table = pd.DataFrame({"frame": [1, 2, 3], "energy": [1.0, 2.0, 3.0],
                          "x": [10.0, 11.0, 12.0], "y": [20.0, 21.0, 22.0]})
    rows = _rows(table, [{"frame": 2, "ts_s": 0.066, "confidence": 0.4, "energy": 9.0}], FPS)
    assert set(rows["coordinate_space"]) == {"image_px"}
    assert set(rows["calibration"]) == {"none"}
    assert (rows["cls"] == MOTION_CLS).sum() == 3 and (rows["cls"] == SNAP_CLS).sum() == 1
    # image_px rows must stay unscorable as court geometry.
    with pytest.raises(CoordinateTransformUnavailable):
        normalize_tracking_frame(rows.loc[:, ["frame", "track_id", "cls", "x", "y",
                                              "coordinate_space"]])
