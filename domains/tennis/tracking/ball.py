"""Conservative v1 ball-detection seam for fixed-camera tennis broadcasts."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, Sequence, Tuple, Union

import cv2
import numpy as np
import pandas as pd

from domains.tennis.tracking.ball_projection_guard import guard_ball_projection


BallPoint = Tuple[float, float, float]
RectifiedTrack = list[Optional[BallPoint]]
BALL_COLUMNS = ("frame", "track_id", "cls", "x", "y", "projection_status",
                "projection_rejection_reason", "raw_projected_x_ft", "raw_projected_y_ft")
_MIN_CONFIDENCE = 0.5


class BallDetector(Protocol):
    """Stateful detector interface for one ball candidate per video frame."""

    def detect(self, frame: np.ndarray) -> Optional[BallPoint]:
        """Return pixel x, y, confidence, or None when detection is uncertain."""


class MotionDiffDetector:
    """Detect a small moving blob, rejecting ambiguous motion explicitly."""

    def __init__(self, threshold: int = 40) -> None:
        self.threshold = threshold
        self._previous_gray: Optional[np.ndarray] = None

    def detect(self, frame: np.ndarray) -> Optional[BallPoint]:
        """Return the highest-scoring upper-court motion blob when unambiguous."""
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = np.asarray(gray, dtype=np.uint8)
        previous = self._previous_gray
        self._previous_gray = gray.copy()
        if previous is None or previous.shape != gray.shape:
            return None
        difference = cv2.absdiff(previous, gray)
        _, mask = cv2.threshold(difference, self.threshold, 255, cv2.THRESH_BINARY)
        blobs: list[BallPoint] = []
        upper_limit = gray.shape[0] * (2.0 / 3.0)
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for label in range(1, count):
            area = float(stats[label, cv2.CC_STAT_AREA])
            if not 4.0 <= area <= 120.0:
                continue
            x, y = map(float, centroids[label])
            if y >= upper_limit:
                continue
            component = np.where(labels == label, 255, 0).astype(np.uint8)
            intensity = float(cv2.mean(difference, mask=component)[0])
            blobs.append((x, y, area * intensity))
        if not blobs:
            return None
        candidates: list[BallPoint] = []
        for blob in blobs:
            for index, candidate in enumerate(candidates):
                if np.hypot(blob[0] - candidate[0], blob[1] - candidate[1]) <= 12.0:
                    score = blob[2] + candidate[2]
                    candidates[index] = (
                        (blob[0] * blob[2] + candidate[0] * candidate[2]) / score,
                        (blob[1] * blob[2] + candidate[1] * candidate[2]) / score,
                        score,
                    )
                    break
            else:
                candidates.append(blob)
        candidates.sort(key=lambda item: item[2], reverse=True)
        best = candidates[0]
        if len(candidates) > 1 and candidates[1][2] >= best[2] * 0.85:
            return None
        confidence = 0.5 + 0.5 * min(1.0, best[2] / (120.0 * 255.0))
        return (best[0], best[1], confidence)


class TrackNetV3Detector:
    """Run the licensed TrackNetV3 checkpoint without an ultralytics dependency.

    The checkpoint was trained for shuttlecocks, so this is deliberately a
    zero-shot candidate generator, not an asserted tennis-ball model.  It
    accepts a contiguous, independently selected sequence of broadcast frames
    and returns one optional pixel point per input frame.
    """

    _SIZE = (512, 288)

    def __init__(self, checkpoint: Union[str, Path], device: str = "cuda") -> None:
        try:
            import torch
            from torch import nn
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError("TrackNetV3 requires torch") from exc
        self._torch = torch
        self._device = torch.device(device if device != "cuda" or torch.cuda.is_available()
                                    else "cpu")
        payload = torch.load(str(checkpoint), map_location=self._device,
                             weights_only=False)
        params = payload["param_dict"]
        self._seq_len = int(params["seq_len"])
        if params["bg_mode"] != "concat":
            raise ValueError("Only the published concat TrackNetV3 checkpoint is supported")

        class ConvBlock(nn.Module):
            def __init__(self, in_dim: int, out_dim: int) -> None:
                super().__init__()
                self.conv = nn.Conv2d(in_dim, out_dim, 3, padding="same", bias=False)
                self.bn = nn.BatchNorm2d(out_dim)
                self.relu = nn.ReLU()

            def forward(self, value):  # type: ignore[no-untyped-def]
                return self.relu(self.bn(self.conv(value)))

        class Double(nn.Module):
            def __init__(self, in_dim: int, out_dim: int) -> None:
                super().__init__()
                self.conv_1 = ConvBlock(in_dim, out_dim)
                self.conv_2 = ConvBlock(out_dim, out_dim)

            def forward(self, value):  # type: ignore[no-untyped-def]
                return self.conv_2(self.conv_1(value))

        class Triple(nn.Module):
            def __init__(self, in_dim: int, out_dim: int) -> None:
                super().__init__()
                self.conv_1 = ConvBlock(in_dim, out_dim)
                self.conv_2 = ConvBlock(out_dim, out_dim)
                self.conv_3 = ConvBlock(out_dim, out_dim)

            def forward(self, value):  # type: ignore[no-untyped-def]
                return self.conv_3(self.conv_2(self.conv_1(value)))

        class TrackNet(nn.Module):
            def __init__(self, in_dim: int, out_dim: int) -> None:
                super().__init__()
                self.down_block_1, self.down_block_2 = Double(in_dim, 64), Double(64, 128)
                self.down_block_3, self.bottleneck = Triple(128, 256), Triple(256, 512)
                self.up_block_1 = Triple(768, 256)
                self.up_block_2, self.up_block_3 = Double(384, 128), Double(192, 64)
                self.predictor = nn.Conv2d(64, out_dim, 1)

            def forward(self, value):  # type: ignore[no-untyped-def]
                first = self.down_block_1(value)
                second = self.down_block_2(nn.functional.max_pool2d(first, 2))
                third = self.down_block_3(nn.functional.max_pool2d(second, 2))
                value = self.bottleneck(nn.functional.max_pool2d(third, 2))
                value = self.up_block_1(torch.cat((nn.functional.interpolate(value, scale_factor=2), third), 1))
                value = self.up_block_2(torch.cat((nn.functional.interpolate(value, scale_factor=2), second), 1))
                value = self.up_block_3(torch.cat((nn.functional.interpolate(value, scale_factor=2), first), 1))
                return torch.sigmoid(self.predictor(value))

        self._model = TrackNet((self._seq_len + 1) * 3, self._seq_len).to(self._device)
        self._model.load_state_dict(payload["model"])
        self._model.eval()

    def detect_sequence(self, frames: Sequence[np.ndarray]) -> RectifiedTrack:
        """Return TrackNetV3 detections for contiguous frames, padded at the tail."""
        if not frames:
            return []
        prepared = [cv2.resize(frame, self._SIZE, interpolation=cv2.INTER_AREA) for frame in frames]
        background = np.median(np.stack(prepared), axis=0).astype(np.uint8)
        output: RectifiedTrack = [None] * len(prepared)
        for start in range(0, len(prepared), self._seq_len):
            chunk = prepared[start:start + self._seq_len]
            valid = len(chunk)
            chunk.extend([chunk[-1]] * (self._seq_len - valid))
            rgb = [cv2.cvtColor(image, cv2.COLOR_BGR2RGB) for image in chunk]
            tensor = np.concatenate(rgb + [cv2.cvtColor(background, cv2.COLOR_BGR2RGB)], axis=2)
            tensor = self._torch.from_numpy(tensor.transpose(2, 0, 1)).unsqueeze(0).float() / 255.0
            with self._torch.no_grad():
                heatmaps = self._model(tensor.to(self._device))[0].cpu().numpy()
            for offset, heatmap in enumerate(heatmaps[:valid]):
                mask = (heatmap > 0.5).astype(np.uint8) * 255
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not contours:
                    continue
                contour = max(contours, key=cv2.contourArea)
                x, y, width, height = cv2.boundingRect(contour)
                original = frames[start + offset]
                scale_x = original.shape[1] / self._SIZE[0]
                scale_y = original.shape[0] / self._SIZE[1]
                output[start + offset] = ((x + width / 2) * scale_x,
                                          (y + height / 2) * scale_y,
                                          float(heatmap.max()))
        return output


def rectify_track(points: Sequence[Optional[BallPoint]]) -> RectifiedTrack:
    """Reject impossible jumps, fill short gaps, and remove isolated sightings."""
    cleaned: RectifiedTrack = [None] * len(points)
    accepted: list[int] = []
    last_index: Optional[int] = None
    for index, point in enumerate(points):
        if point is None or point[2] < _MIN_CONFIDENCE:
            continue
        x, y, confidence = map(float, point)
        if last_index is not None:
            previous = cleaned[last_index]
            assert previous is not None
            distance = float(np.hypot(x - previous[0], y - previous[1]))
            if distance / (index - last_index) > 80.0:
                continue
        cleaned[index] = (x, y, confidence)
        accepted.append(index)
        last_index = index

    groups: list[list[int]] = []
    for index in accepted:
        if not groups or index - groups[-1][-1] > 6:
            groups.append([index])
        else:
            groups[-1].append(index)
    for group in groups:
        if len(group) == 1:
            cleaned[group[0]] = None
            continue
        for start, end in zip(group, group[1:]):
            if end - start <= 1:
                continue
            first, last = cleaned[start], cleaned[end]
            assert first is not None and last is not None
            for index in range(start + 1, end):
                fraction = (index - start) / (end - start)
                cleaned[index] = (
                    first[0] + fraction * (last[0] - first[0]),
                    first[1] + fraction * (last[1] - first[1]),
                    0.0,
                )
    return cleaned


def ball_rows(rectified: Sequence[Optional[BallPoint]], homography: np.ndarray) -> pd.DataFrame:
    """Project confident pixel detections into canonical tennis tracking rows."""
    rows: list[dict[str, object]] = []
    for frame, point in enumerate(rectified):
        if point is None or point[2] < _MIN_CONFIDENCE:
            continue
        decision = guard_ball_projection(point, homography)
        rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                     "x": decision.raw_x if decision.status == "accepted" else float("nan"),
                     "y": decision.raw_y if decision.status == "accepted" else float("nan"),
                     "projection_status": decision.status,
                     "projection_rejection_reason": decision.rejection_reason,
                     "raw_projected_x_ft": decision.raw_x,
                     "raw_projected_y_ft": decision.raw_y})
    return pd.DataFrame(rows, columns=BALL_COLUMNS)


def attach_ball(
    adapter_df: pd.DataFrame,
    video_path: Union[str, Path],
    homography: np.ndarray,
    detector: BallDetector,
) -> pd.DataFrame:
    """Return existing tracking rows augmented with conservative ball detections."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video_path)
    points: list[Optional[BallPoint]] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            points.append(detector.detect(frame))
    finally:
        capture.release()
    balls = ball_rows(rectify_track(points), homography)
    return pd.concat((adapter_df.copy(), balls), ignore_index=True)
