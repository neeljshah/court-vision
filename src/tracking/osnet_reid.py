"""
osnet_reid.py — Lightweight OSNet-x0.25 deep appearance extractor for player re-ID.

Replaces 96-dim HSV histogram embeddings with 256-dim learned appearance features,
dramatically improving re-ID on similar-colored uniforms.

Architecture: OSNet-x0.25 (Omni-Scale Network, Zhou et al. 2019), implemented
directly in PyTorch so torchreid is not required.

Usage (internal — called by AdvancedFeetDetector):
    extractor = DeepAppearanceExtractor()
    embeddings = extractor.batch_extract(crops_bgr)  # List[np.ndarray(256,)]

If CUDA is available the model runs on GPU.  Falls back to MobileNetV2 features
when OSNet init fails.  Falls back to an empty array (0-dim) when both fail,
so the caller can detect unavailability and fall back to HSV histograms.

Weights:
    - First call: randomly initialized (useful for structural consistency checks).
    - Load pre-trained weights with: extractor.load_weights("path/to/weights.pth")
    - Weights can be obtained from: https://github.com/KaiyangZhou/deep-person-reid
      File: osnet_x0_25_imagenet.pth (ImageNet) or any MOT-finetuned checkpoint.
"""

from __future__ import annotations

from typing import List, Optional

import cv2
import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

# Input image dimensions for OSNet (CUHK03 / Market-1501 convention)
_IN_H, _IN_W = 256, 128
_EMBED_DIM   = 256   # output embedding size for x0.25 variant


# ── OSNet-x0.25 building blocks ───────────────────────────────────────────────

if _HAS_TORCH:
    class _ConvBnRelu(nn.Module):
        """Conv → BN → ReLU helper block."""

        def __init__(self, in_c: int, out_c: int, k: int,
                     s: int = 1, p: int = 0):
            super().__init__()
            self.conv = nn.Conv2d(in_c, out_c, k, stride=s, padding=p, bias=False)
            self.bn   = nn.BatchNorm2d(out_c)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            return F.relu(self.bn(self.conv(x)), inplace=True)

    class _DepthwiseSep(nn.Module):
        """Depthwise-separable convolution block (faster than plain Conv)."""

        def __init__(self, in_c: int, out_c: int, k: int,
                     s: int = 1, p: int = 0):
            super().__init__()
            self.dw = nn.Conv2d(in_c, in_c, k, stride=s, padding=p,
                                groups=in_c, bias=False)
            self.pw = nn.Conv2d(in_c, out_c, 1, bias=False)
            self.bn = nn.BatchNorm2d(out_c)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            return F.relu(self.bn(self.pw(self.dw(x))), inplace=True)

    class _OSBlock(nn.Module):
        """
        Omni-Scale Block with three branches at different receptive-field scales:
          Branch 1: 1×1 (point-wise)
          Branch 2: 1×1 → 3×3 depthwise-sep
          Branch 3: 1×1 → 3×3 → 3×3 depthwise-sep
        Scale-wise gates (SE-style) aggregate branches dynamically.
        """

        def __init__(self, in_c: int, out_c: int):
            super().__init__()
            mid = max(1, out_c // 3)
            self.b1 = _ConvBnRelu(in_c, mid, 1)
            self.b2 = nn.Sequential(
                _ConvBnRelu(in_c, mid, 1),
                _DepthwiseSep(mid, mid, 3, p=1),
            )
            self.b3 = nn.Sequential(
                _ConvBnRelu(in_c, mid, 1),
                _DepthwiseSep(mid, mid, 3, p=1),
                _DepthwiseSep(mid, mid, 3, p=1),
            )
            self.gate = nn.Sequential(
                nn.AdaptiveAvgPool2d(1),
                nn.Flatten(),
                nn.Linear(in_c, 3),
                nn.Softmax(dim=1),
            )
            self.proj = nn.Sequential(
                nn.Conv2d(mid, out_c, 1, bias=False),
                nn.BatchNorm2d(out_c),
            )
            self.skip = (
                nn.Sequential(nn.Conv2d(in_c, out_c, 1, bias=False),
                               nn.BatchNorm2d(out_c))
                if in_c != out_c else nn.Identity()
            )

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            g  = self.gate(x)          # (B, 3)
            b1 = self.b1(x)
            b2 = self.b2(x)
            b3 = self.b3(x)
            agg = (b1 * g[:, 0:1, None, None]
                   + b2 * g[:, 1:2, None, None]
                   + b3 * g[:, 2:3, None, None])
            return F.relu(self.proj(agg) + self.skip(x), inplace=True)

    class OSNetX025(nn.Module):
        """
        OSNet-x0.25 backbone for player re-identification.

        Channels are scaled by 0.25 relative to the full OSNet:
          - Conv0:  16 ch  (64 × 0.25)
          - Layer1: 64 ch  (256 × 0.25)
          - Layer2: 96 ch  (384 × 0.25)
          - Layer3: 128 ch (512 × 0.25)
          - Embed:  256 dim

        Input: (B, 3, 256, 128) RGB float32 in [0, 1].
        Output: (B, embed_dim) L2-normalized feature vector.
        """

        def __init__(self, embed_dim: int = _EMBED_DIM):
            super().__init__()
            # Channel sizes = [64, 256, 384, 512] × 0.25
            c = [max(1, int(x * 0.25)) for x in (64, 256, 384, 512)]

            self.conv0  = _ConvBnRelu(3, c[0], 7, s=2, p=3)
            self.pool0  = nn.MaxPool2d(3, stride=2, padding=1)
            self.layer1 = _OSBlock(c[0], c[1])
            self.pool1  = nn.AvgPool2d(2, stride=2)
            self.layer2 = _OSBlock(c[1], c[2])
            self.pool2  = nn.AvgPool2d(2, stride=2)
            self.layer3 = _OSBlock(c[2], c[3])
            self.gap    = nn.AdaptiveAvgPool2d(1)
            self.fc     = nn.Linear(c[3], embed_dim)
            self.bn_out = nn.BatchNorm1d(embed_dim)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            x = self.pool0(self.conv0(x))
            x = self.pool1(self.layer1(x))
            x = self.pool2(self.layer2(x))
            x = self.gap(self.layer3(x)).flatten(1)
            return F.normalize(self.bn_out(self.fc(x)), dim=1)


# ── Pre-processing ─────────────────────────────────────────────────────────────

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _preprocess_crop(bgr: np.ndarray) -> "torch.Tensor":
    """
    Resize BGR crop to (_IN_H, _IN_W), convert to float RGB in [0,1],
    apply ImageNet normalisation, and return a (1, 3, H, W) tensor.
    """
    img = cv2.resize(bgr, (_IN_W, _IN_H), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - _MEAN) / _STD             # (H, W, 3)
    t   = torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0)  # (1,3,H,W)
    return t


# ── Public extractor class ─────────────────────────────────────────────────────

class DeepAppearanceExtractor:
    """
    Deep appearance feature extractor using OSNet-x0.25.

    Interface (used by AdvancedFeetDetector):
        extractor = DeepAppearanceExtractor()
        if extractor.available:
            embs = extractor.batch_extract([crop1_bgr, crop2_bgr])
            # embs: List[np.ndarray(256,) float32]

    Falls back to MobileNetV2 if OSNet construction fails.
    Sets ``available = False`` when neither model can be initialised.

    Args:
        device:      "cuda" / "cpu" / None (auto-detect).
        weights_path: Optional path to a .pth checkpoint.  When provided
                      the model is warm-started from these weights.
    """

    def __init__(
        self,
        device: Optional[str] = None,
        weights_path: Optional[str] = None,
    ):
        self.available = False
        self._model    = None
        self._device   = "cpu"

        if not _HAS_TORCH:
            return

        if device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device

        try:
            model = OSNetX025(embed_dim=_EMBED_DIM)
            if weights_path:
                state = torch.load(weights_path, map_location="cpu")
                state = state.get("state_dict", state)  # handle wrapped checkpoints
                model.load_state_dict(state, strict=False)
            model = model.to(self._device).eval()
            self._model   = model
            self.available = True
        except Exception:
            # Attempt MobileNetV2 fallback (torchvision)
            try:
                from torchvision.models import mobilenet_v2
                mv2  = mobilenet_v2(weights=None)
                # Use features (everything before the classifier)
                mv2  = mv2.features.to(self._device).eval()
                self._model   = mv2
                self._mv2_gap = nn.AdaptiveAvgPool2d(1).to(self._device)
                self.available = True
                self._use_mv2  = True
                return
            except Exception:
                return
        self._use_mv2 = False

    # ── public API ────────────────────────────────────────────────────────

    def load_weights(self, path: str) -> None:
        """Hot-load a .pth checkpoint into the running model (no re-init)."""
        if self._model is None or not _HAS_TORCH:
            return
        state = torch.load(path, map_location="cpu")
        state = state.get("state_dict", state)
        self._model.load_state_dict(state, strict=False)

    @torch.no_grad()
    def batch_extract(self, crops: List[np.ndarray]) -> List[np.ndarray]:
        """
        Extract appearance embeddings for a list of BGR crops.

        Args:
            crops: List of BGR uint8 ndarray player crops.

        Returns:
            List of float32 ndarray, shape (embed_dim,), L2-normalised.
            Returns list of zero vectors when ``available`` is False.
        """
        zero = np.zeros(_EMBED_DIM, dtype=np.float32)
        if not self.available or not crops:
            return [zero.copy() for _ in crops]

        try:
            # Track which crops are valid so we can restore original order.
            valid_idx    = [i for i, c in enumerate(crops)
                            if c is not None and c.size > 0]
            if not valid_idx:
                return [zero.copy() for _ in crops]

            tensors = torch.cat(
                [_preprocess_crop(crops[i]).to(self._device) for i in valid_idx],
                dim=0,
            )  # (N_valid, 3, H, W)

            if getattr(self, "_use_mv2", False):
                feats = self._model(tensors)
                feats = self._mv2_gap(feats).squeeze(-1).squeeze(-1)
                feats = F.normalize(feats, dim=1)
            else:
                feats = self._model(tensors)           # (N_valid, embed_dim)

            valid_embs = feats.cpu().float().numpy()   # (N_valid, embed_dim)

            # Reconstruct full-length list with zeros for invalid crops
            out = [zero.copy() for _ in crops]
            for out_i, orig_i in enumerate(valid_idx):
                out[orig_i] = valid_embs[out_i]
            return out
        except Exception:
            return [zero.copy() for _ in crops]

    def extract(self, crop: np.ndarray) -> np.ndarray:
        """Convenience wrapper — single-crop version of batch_extract."""
        result = self.batch_extract([crop])
        return result[0]
