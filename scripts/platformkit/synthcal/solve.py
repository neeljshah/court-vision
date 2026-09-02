"""Inference, RANSAC fitting, and tennis held-out landmark evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .model import build_model
from .renderer import court_keypoints


def load_model(weights: Path, device: str = "cpu"):
    """Load only a SynthCal checkpoint and its declared named points."""
    import torch
    checkpoint = torch.load(weights, map_location=device, weights_only=False)
    model = build_model(len(checkpoint["names"])); model.load_state_dict(checkpoint["state_dict"])
    return model.to(device).eval(), tuple(checkpoint["names"]), checkpoint["sport"]


def predict(model, frame: np.ndarray, names: tuple[str, ...], device: str = "cpu") -> tuple[np.ndarray, np.ndarray]:
    """Return full-frame point predictions and peak confidences."""
    import torch
    resized = cv2.resize(frame, (320, 180)).astype(np.float32).transpose(2, 0, 1) / 255.
    with torch.no_grad(): heat = model(torch.from_numpy(resized[None]).to(device))[0].detach().cpu().numpy()
    points, confidence = [], []
    for channel in heat:
        y, x = np.unravel_index(channel.argmax(), channel.shape); points.append((x * 16 + 8, y * 16 + 8)); confidence.append(channel[y, x])
    return np.asarray(points, np.float32), np.asarray(confidence, np.float32)


def fit_homography(sport: str, names: tuple[str, ...], pixels: np.ndarray, confidence: np.ndarray,
                   threshold: float = .12) -> np.ndarray | None:
    """Fit image-to-rule-plane RANSAC homography from confident named predictions."""
    target = court_keypoints(sport); keep = confidence >= threshold
    if int(keep.sum()) < 4: return None
    image = pixels[keep]; metric = np.float32([target[name] for name, good in zip(names, keep) if good])
    homography, _ = cv2.findHomography(image, metric, cv2.RANSAC, 8.0)
    return homography


def _opposite_t(frame: np.ndarray):
    """Reuse the existing independent tennis reference-point detector exactly."""
    height, width = frame.shape[:2]
    bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
    found = cv2.HoughLinesP(bright, 1, np.pi / 180., threshold=45, minLineLength=max(40, width // 12), maxLineGap=20)
    if found is None: return None
    segments = found.reshape(-1, found.shape[-1])
    horizontal = [line.astype(float) for line in segments if abs(line[2] - line[0]) >= 1.5 * abs(line[3] - line[1])]
    vertical = [line.astype(float) for line in segments if abs(line[3] - line[1]) > abs(line[2] - line[0])]
    def fit(lines):
        points = np.float32([[x[0], x[1]] for x in lines] + [[x[2], x[3]] for x in lines]); return cv2.fitLine(points, cv2.DIST_L2, 0, .01, .01).reshape(-1)
    def position(line):
        return line[1] + (width / 2 - line[0]) * (line[3] - line[1]) / (line[2] - line[0]) if abs(line[2] - line[0]) > 1e-6 else (line[1] + line[3]) / 2
    def clusters(lines, horizontal_line):
        ordered = sorted(lines, key=lambda x: position(x) if horizontal_line else (x[0] + x[2]) / 2); out = []
        for line in ordered:
            value = position(line) if horizontal_line else (line[0] + line[2]) / 2
            if not out or abs(value - np.mean([position(x) if horizontal_line else (x[0] + x[2]) / 2 for x in out[-1]])) > 12: out.append([line])
            else: out[-1].append(line)
        return out
    horizontal, vertical = clusters(horizontal, True), clusters(vertical, False)
    if len(horizontal) < 4 or len(vertical) != 5: return None
    across = [(fit(group)[0] + fit(group)[2]) / 2 for group in vertical]; denominator = (across[2] - across[1]) * (across[4] - across[0])
    if abs(denominator) < 1e-6 or abs((across[2] - across[0]) * (across[4] - across[1]) / denominator - 7. / 6.) > .05: return None
    a, b = fit(horizontal[1]), fit(vertical[2]); line_a, line_b = np.cross((a[0] - 10000*a[2], a[1] - 10000*a[3], 1), (a[0] + 10000*a[2], a[1] + 10000*a[3], 1)), np.cross((b[0] - 10000*b[2], b[1] - 10000*b[3], 1), (b[0] + 10000*b[2], b[1] + 10000*b[3], 1))
    point = np.cross(line_a, line_b)
    return None if abs(point[2]) < 1e-8 else np.float32(point[:2] / point[2])


def evaluate_tennis(video: Path, weights: Path, max_frames: int = 900, stride: int = 3,
                    device: str = "cpu") -> dict[str, object]:
    """Score image-to-court error at the existing held-out opposite service-T."""
    model, names, sport = load_model(weights, device)
    if sport != "tennis": raise ValueError("tennis weights required")
    capture = cv2.VideoCapture(str(video)); errors = []; sampled = 0; source = 0
    if not capture.isOpened(): raise FileNotFoundError(video)
    try:
        while sampled < max_frames:
            ok, frame = capture.read()
            if not ok: break
            if source % stride == 0:
                sampled += 1; held = _opposite_t(frame)
                if held is not None:
                    points, confidence = predict(model, frame, names, device); homography = fit_homography(sport, names, points, confidence)
                    if homography is not None:
                        projected = cv2.perspectiveTransform(np.float32([[held]]), homography)[0, 0]
                        errors.append(float(np.linalg.norm(projected - (60., 18.))))
            source += 1
    finally:
        capture.release()
    return {"video": video.name, "sampled_frames": sampled, "held_out_landmark": "opposite_service_t",
            "n": len(errors), "median_ft": round(float(np.median(errors)), 3) if errors else None,
            "p95_ft": round(float(np.percentile(errors, 95)), 3) if errors else None,
            "provisional": len(errors) < 30, "baseline_median_ft": 5.28, "baseline_p95_ft": 21.85}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SynthCal on real tennis held-out landmarks.")
    parser.add_argument("video", type=Path); parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--max-frames", type=int, default=900); parser.add_argument("--stride", type=int, default=3); parser.add_argument("--device", default="cpu")
    args = parser.parse_args(); print(json.dumps(evaluate_tennis(args.video, args.weights, args.max_frames, args.stride, args.device), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
