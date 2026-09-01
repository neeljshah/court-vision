"""Small train-from-scratch heatmap model and on-the-fly synthetic trainer."""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from .renderer import court_keypoints, render_sample


def _torch():
    import torch
    from torch import nn
    return torch, nn


def build_model(keypoints: int):
    """Build a sub-2M parameter 1/4-resolution heatmap network."""
    _, nn = _torch()
    def block(a, b, stride=1):
        return nn.Sequential(nn.Conv2d(a, b, 3, stride, 1), nn.BatchNorm2d(b), nn.ReLU(inplace=True),
                             nn.Conv2d(b, b, 3, 1, 1), nn.BatchNorm2d(b), nn.ReLU(inplace=True))
    return nn.Sequential(block(3, 32, 2), block(32, 64, 2), block(64, 96), block(96, 128),
                         nn.Conv2d(128, keypoints, 1))


def _batch(sport: str, count: int, device, size: tuple[int, int] = (320, 180)):
    torch, _ = _torch(); width, height = size; heat_w, heat_h = width // 4, height // 4
    images, targets = [], []
    for _ in range(count):
        item = render_sample(sport)
        image = cv2.resize(item["image"], size).astype(np.float32) / 255.0
        points = item["points"].copy(); points[:, 0] *= width / 1280.; points[:, 1] *= height / 720.
        heat = np.zeros((len(points), heat_h, heat_w), np.float32)
        yy, xx = np.mgrid[:heat_h, :heat_w]
        for index, (point, visible) in enumerate(zip(points, item["visible"])):
            if visible:
                heat[index] = np.exp(-((xx - point[0] / 4) ** 2 + (yy - point[1] / 4) ** 2) / 4.5)
        images.append(image.transpose(2, 0, 1)); targets.append(heat)
    return torch.from_numpy(np.stack(images)).to(device), torch.from_numpy(np.stack(targets)).to(device)


def train(sport: str, steps: int, batch_size: int, output: Path, device_name: str | None = None) -> Path:
    """Train exclusively on freshly rendered samples and save an explicit local-only checkpoint."""
    torch, _ = _torch(); names = tuple(court_keypoints(sport))
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = build_model(len(names)).to(device); optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3)
    model.train()
    for step in range(steps):
        images, target = _batch(sport, batch_size, device)
        loss = torch.nn.functional.mse_loss(model(images), target)
        optimizer.zero_grad(); loss.backward(); optimizer.step()
        if step % max(1, steps // 10) == 0:
            print("SYNTHCAL step=%d loss=%.6f" % (step, loss.item()))
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"sport": sport, "names": names, "state_dict": model.state_dict(), "synthetic_only": True}, output)
    print("SYNTHCAL saved=%s parameters=%d" % (output, sum(p.numel() for p in model.parameters())))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a synthetic-only court keypoint model.")
    parser.add_argument("sport", choices=("tennis", "soccer", "basketball")); parser.add_argument("--steps", type=int, default=4000)
    parser.add_argument("--batch-size", type=int, default=16); parser.add_argument("--output", type=Path)
    parser.add_argument("--device")
    args = parser.parse_args(); output = args.output or Path("data/models/synthcal_%s.pt" % args.sport)
    if args.steps < 1 or args.batch_size < 1: parser.error("steps and batch-size must be positive")
    train(args.sport, args.steps, args.batch_size, output, args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
