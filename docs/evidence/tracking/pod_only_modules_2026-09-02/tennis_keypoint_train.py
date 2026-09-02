"""Train a permissively licensed tennis court-keypoint heatmap student."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import torch
from torch import Tensor, nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset
from torchvision.models import ResNet18_Weights, resnet18
from torchvision.transforms import ColorJitter

INPUT_W, INPUT_H, HEAT_W, HEAT_H, KEYPOINTS = 640, 360, 160, 90, 14


def load_rows(paths: list[Path]) -> tuple[list[dict[str, Any]], int]:
    """Load JSONL labels and deduplicate by the source video and frame."""
    raw = [json.loads(line) for path in paths for line in path.read_text(encoding="ascii").splitlines()]
    unique: dict[tuple[str, int], dict[str, Any]] = {}
    for row in raw:
        unique.setdefault((row["video"], int(row["frame"])), row)
    return list(unique.values()), len(raw) - len(unique)


def match_name(row: dict[str, Any]) -> str:
    """Return the stable match name encoded by a G23 source video path."""
    name = Path(row["video"]).stem.lower()
    if "nyyk" in name:
        return "nyyk"
    if "tennis_09" in name:
        return "tennis09"
    if "tennis_10" in name:
        return "tennis10"
    raise ValueError("Unknown tennis match: %s" % row["video"])


def split_fold(rows: list[dict[str, Any]], fold: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Make the two required leave-one-match-out folds."""
    held_out = ("tennis09", "tennis10")[fold]
    test = [row for row in rows if match_name(row) == held_out]
    train = [row for row in rows if match_name(row) != held_out]
    return train, test, held_out


def make_heatmaps(points: Tensor, visible: Tensor, sigma: float = 2.0) -> Tensor:
    """Create quarter-resolution Gaussian heatmap targets for one image."""
    yy, xx = torch.meshgrid(torch.arange(HEAT_H), torch.arange(HEAT_W), indexing="ij")
    scaled = points / points.new_tensor((INPUT_W / HEAT_W, INPUT_H / HEAT_H))
    distance2 = (xx.unsqueeze(0) - scaled[:, 0, None, None]).square()
    distance2 += (yy.unsqueeze(0) - scaled[:, 1, None, None]).square()
    return torch.exp(-distance2 / (2.0 * sigma * sigma)) * visible[:, None, None]


def read_frame(row: dict[str, Any]) -> np.ndarray:
    """Decode the source frame referenced by one pseudo-label row."""
    capture = cv2.VideoCapture(row["video"])
    capture.set(cv2.CAP_PROP_POS_FRAMES, int(row["frame"]))
    ok, image = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError("Could not decode %s:%d" % (row["video"], row["frame"]))
    return image


class TennisDataset(Dataset[tuple[Tensor, Tensor, Tensor, Tensor]]):
    """Broadcast frames, pseudo-label heatmaps, original points, and visibility."""
    def __init__(self, rows: list[dict[str, Any]], augment: bool, cache: bool = False,
                 image_loader: Callable[[dict[str, Any]], np.ndarray] = read_frame) -> None:
        self.rows, self.augment, self.cache, self.image_loader = rows, augment, cache, image_loader
        self.images: dict[int, np.ndarray] = {}
        self.jitter = ColorJitter(0.2, 0.2, 0.2, 0.05)

    def __len__(self) -> int:
        return len(self.rows)

    def _image(self, index: int) -> np.ndarray:
        if index not in self.images:
            image = self.image_loader(self.rows[index])
            image = cv2.resize(image, (INPUT_W, INPUT_H), interpolation=cv2.INTER_AREA)
            if self.cache:
                self.images[index] = image
            return image
        return self.images[index]

    def preload(self) -> None:
        """Decode the small G23 corpus once to keep epochs GPU-bound."""
        for index in range(len(self)):
            self._image(index)

    def __getitem__(self, index: int) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        row = self.rows[index]
        image = self._image(index)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb.copy()).permute(2, 0, 1).float().div_(255.0)
        if self.augment:
            tensor = self.jitter(tensor)
        points = torch.tensor([(point["x"] * INPUT_W / row["width"], point["y"] * INPUT_H / row["height"])
                               for point in row["keypoints"]], dtype=torch.float32)
        original = torch.tensor([(point["x"], point["y"]) for point in row["keypoints"]], dtype=torch.float32)
        visible = torch.tensor([point["visible"] for point in row["keypoints"]], dtype=torch.bool)
        return tensor, make_heatmaps(points, visible), original, visible


class TennisKeypointNet(nn.Module):
    """ImageNet ResNet18 encoder with three learned upsampling stages."""
    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        weights = ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        base = resnet18(weights=weights)
        self.encoder = nn.Sequential(base.conv1, base.bn1, base.relu, base.maxpool,
                                     base.layer1, base.layer2, base.layer3, base.layer4)
        self.head = nn.Sequential(
            nn.ConvTranspose2d(512, 192, 2, 2), nn.ReLU(inplace=True),
            nn.ConvTranspose2d(192, 96, 2, 2), nn.ReLU(inplace=True),
            nn.ConvTranspose2d(96, 48, 2, 2), nn.ReLU(inplace=True), nn.Conv2d(48, KEYPOINTS, 1))

    def forward(self, image: Tensor) -> Tensor:
        return self.head(self.encoder(F.pad(image, (0, 0, 0, 24))))[:, :, :HEAT_H, :HEAT_W]


def decode_heatmaps(heatmaps: Tensor, sizes: Tensor) -> Tensor:
    """Convert heatmap argmax coordinates to each original source resolution."""
    flat = heatmaps.flatten(2).argmax(2)
    points = torch.stack((flat.remainder(HEAT_W), flat.div(HEAT_W, rounding_mode="floor")), dim=-1).float()
    return points * sizes[:, None, :] / points.new_tensor((HEAT_W, HEAT_H))


def pck_metrics(predicted: Tensor, target: Tensor, visible: Tensor) -> dict[str, float]:
    """Calculate PCK@7, median error, and the four-in-seven solve proxy."""
    errors = torch.linalg.vector_norm(predicted - target, dim=-1)
    valid = errors[visible]
    per_frame = ((errors <= 7.0) & visible).sum(1) >= 4
    return {"pck_at_7": float((valid <= 7.0).float().mean()), "median_px": float(valid.median()),
            "frames_ge_4_in_7": float(per_frame.float().mean())}


def train_epoch(model: nn.Module, loader: DataLoader[Any], optimizer: torch.optim.Optimizer,
                device: torch.device) -> float:
    """Run one fixed-MSE training epoch."""
    model.train()
    total = 0.0
    for image, target, _, _ in loader:
        optimizer.zero_grad(set_to_none=True)
        loss = F.mse_loss(model(image.to(device)), target.to(device))
        loss.backward()
        optimizer.step()
        total += float(loss.detach())
    return total / max(len(loader), 1)


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader[Any], device: torch.device) -> dict[str, float]:
    """Measure held-out heatmaps after scaling their coordinates to source pixels."""
    model.eval()
    predicted, target, visible = [], [], []
    for image, _, points, mask in loader:
        sizes = torch.tensor([[row["width"], row["height"]] for row in loader.dataset.rows[len(predicted) * loader.batch_size:]], dtype=torch.float32)
        count = len(image)
        predicted.append(decode_heatmaps(model(image.to(device)).cpu(), sizes[:count]))
        target.append(points)
        visible.append(mask)
    return pck_metrics(torch.cat(predicted), torch.cat(target), torch.cat(visible))


@torch.no_grad()
def render(model: nn.Module, rows: list[dict[str, Any]], output_dir: Path, device: torch.device) -> None:
    """Render twelve evenly spaced held-out frames with teacher and student points."""
    output_dir.mkdir(parents=True, exist_ok=True)
    indices = np.linspace(0, len(rows) - 1, 12, dtype=int)
    model.eval()
    for ordinal, index in enumerate(indices):
        row, image = rows[int(index)], read_frame(rows[int(index)])
        small = cv2.resize(image, (INPUT_W, INPUT_H), interpolation=cv2.INTER_AREA)
        tensor = torch.from_numpy(cv2.cvtColor(small, cv2.COLOR_BGR2RGB).copy()).permute(2, 0, 1).float()[None] / 255.0
        predicted = decode_heatmaps(model(tensor.to(device)).cpu(), torch.tensor([[row["width"], row["height"]]], dtype=torch.float32))[0]
        for point, estimate in zip(row["keypoints"], predicted):
            cv2.circle(image, (round(point["x"]), round(point["y"])), 6, (0, 0, 255), -1)
            cv2.circle(image, tuple(estimate.round().int().tolist()), 5, (0, 255, 0), 2)
        cv2.imwrite(str(output_dir / ("%02d_f%06d.jpg" % (ordinal, row["frame"]))), image)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fold", type=int, choices=(0, 1), required=True)
    parser.add_argument("--labels-dir", type=Path, default=Path("docs/evidence/tracking/tennis_pseudolabels_2026-09-02"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--no-cache-images", action="store_true")
    parser.add_argument("--no-pretrained", action="store_true")
    args = parser.parse_args()
    paths = sorted(args.labels_dir.glob("g23_*.jsonl"))
    rows, duplicates = load_rows(paths)
    train_rows, test_rows, held_out = split_fold(rows, args.fold)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set, test_set = TennisDataset(train_rows, True, not args.no_cache_images), TennisDataset(test_rows, False, not args.no_cache_images)
    if not args.no_cache_images:
        train_set.preload(); test_set.preload()
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=0)
    test_loader = DataLoader(test_set, batch_size=args.batch_size, shuffle=False, num_workers=0)
    model = TennisKeypointNet(not args.no_pretrained).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    for epoch in range(args.epochs):
        print("fold=%d epoch=%d loss=%.6f" % (args.fold, epoch + 1, train_epoch(model, train_loader, optimizer, device)), flush=True)
    metrics = evaluate(model, test_loader, device)
    metrics.update({"fold": args.fold, "held_out": held_out, "raw_rows": len(rows) + duplicates,
                    "unique_rows": len(rows), "duplicates_dropped": duplicates, "train_frames": len(train_rows), "test_frames": len(test_rows)})
    checkpoint = Path("data/models/tennis_keypoints_fold%d.pt" % args.fold)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.state_dict(), "metrics": metrics}, checkpoint)
    evidence = Path("docs/evidence/tracking/tennis_keypoint_train_2026-09-02")
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / ("fold%d_metrics.json" % args.fold)).write_text(json.dumps(metrics, indent=2) + "\n", encoding="ascii")
    render(model, test_rows, evidence / ("fold%d" % args.fold), device)
    print(json.dumps(metrics, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
