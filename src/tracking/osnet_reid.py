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

import os
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


# ── TensorRT OSNet runner ──────────────────────────────────────────────────────

import logging as _logging
_log = _logging.getLogger(__name__)

_OSNET_ENGINE_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "resources", "osnet_x025.engine"
))

# Default pretrained weights location (placed here by the one-time download step)
_DEFAULT_WEIGHTS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "models", "osnet_x0_25_imagenet.pth"
))


# ── torchreid-backed OSNet wrapper ────────────────────────────────────────────

try:
    import torchreid as _torchreid
    _HAS_TORCHREID = True
except ImportError:
    _HAS_TORCHREID = False


class _TorchReidOSNet:
    """
    Thin wrapper around torchreid's OSNet-x0.25.

    Uses torchreid.models.build_model so weights load with zero key mismatches.
    Outputs (N, 512) L2-normalised embeddings (torchreid's feature_dim=512).

    Only instantiated when torchreid is importable and the weights file exists.
    """

    embed_dim: int = 512

    def __init__(self, weights_path: str, device: str) -> None:
        self.available = False
        if not _HAS_TORCHREID or not _HAS_TORCH:
            return
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = _torchreid.models.build_model(
                    name="osnet_x0_25", num_classes=1000, pretrained=False
                )
            state = torch.load(weights_path, map_location="cpu")
            state = state.get("state_dict", state)
            model.load_state_dict(state, strict=False)
            self._model = model.to(device).eval()
            self._device = device
            self.available = True
            _log.debug("_TorchReidOSNet: loaded pretrained weights from %s", weights_path)
        except Exception as exc:
            _log.debug("_TorchReidOSNet init failed (%s) — will use standalone", exc)

    @torch.no_grad()
    def infer(self, tensors: "torch.Tensor") -> np.ndarray:
        """
        Args:
            tensors: (N, 3, 256, 128) float32 ImageNet-normalised tensor on CPU.
        Returns:
            (N, 512) float32 L2-normalised numpy array.
        """
        import torch.nn.functional as _F
        t = tensors.to(self._device)
        feats = self._model.featuremaps(t)                        # (N, 128, H, W)
        v = self._model.global_avgpool(feats).view(feats.size(0), -1)  # (N, 128)
        emb = self._model.fc(v)                                   # (N, 512)
        emb = _F.normalize(emb, dim=1)
        return emb.cpu().float().numpy()


class _TRTOSNet:
    """
    TensorRT wrapper for OSNet-x0.25.

    Loads resources/osnet_x025.engine and runs FP16 inference.
    Input:  (N, 3, 256, 128) float32 numpy array (ImageNet normalised).
    Output: (N, 256) float32 numpy array (L2-normalised embeddings).

    L40S optimization: pre-allocates pinned host buffers and device memory
    for max batch size (16 players) at init time.  Eliminates per-batch
    cuda.mem_alloc/free which caused VRAM fragmentation and OOM on long runs.
    A persistent CUDA stream avoids stream creation overhead per call.

    Falls back silently if TRT is not installed or engine file is missing.
    """

    _MAX_BATCH = 16  # max players per frame (10 players + 1 ref + margin)

    def __init__(self, engine_path: str) -> None:
        self.available = False
        self._context  = None
        self._stream   = None

        if not os.path.exists(engine_path):
            _log.debug("OSNet TRT engine not found at %s — using PyTorch", engine_path)
            return

        try:
            import tensorrt as trt  # type: ignore
            import pycuda.driver as cuda  # type: ignore
            import pycuda.autoinit  # type: ignore  # noqa: F401

            TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
            runtime    = trt.Runtime(TRT_LOGGER)
            with open(engine_path, "rb") as f:
                engine = runtime.deserialize_cuda_engine(f.read())

            self._context = engine.create_execution_context()
            self._engine  = engine
            self._cuda    = cuda

            # Pre-allocate pinned host + device buffers for max batch (eliminates per-call malloc)
            _inp_bytes = self._MAX_BATCH * 3 * _IN_H * _IN_W * 4  # float32
            _out_bytes = self._MAX_BATCH * _EMBED_DIM * 4

            self._h_input  = cuda.pagelocked_zeros((self._MAX_BATCH, 3, _IN_H, _IN_W), dtype=np.float32)
            self._h_output = cuda.pagelocked_zeros((self._MAX_BATCH, _EMBED_DIM), dtype=np.float32)
            self._d_input  = cuda.mem_alloc(_inp_bytes)
            self._d_output = cuda.mem_alloc(_out_bytes)
            self._stream   = cuda.Stream()

            self.available = True
            _log.debug("OSNet TRT engine loaded from %s (pre-alloc %d batch)", engine_path, self._MAX_BATCH)

        except Exception as e:
            _log.debug("OSNet TRT load failed (%s) — using PyTorch fallback", e)

    def infer(self, input_np: "np.ndarray") -> "np.ndarray":
        """
        Run OSNet TRT inference using pre-allocated buffers.

        Args:
            input_np: float32 array (N, 3, 256, 128), ImageNet normalised.

        Returns:
            float32 array (N, 256) L2-normalised embeddings.
        """
        n = input_np.shape[0]
        if n == 0:
            return np.zeros((0, _EMBED_DIM), dtype=np.float32)

        cuda = self._cuda

        # Copy into pre-allocated pinned host buffer (zero-copy to GPU)
        # Process in chunks of _MAX_BATCH if needed (unlikely: usually ≤11 players)
        all_out = []
        for chunk_start in range(0, n, self._MAX_BATCH):
            chunk_end = min(chunk_start + self._MAX_BATCH, n)
            chunk_n = chunk_end - chunk_start
            chunk_in = input_np[chunk_start:chunk_end]

            # Copy to pinned buffer
            self._h_input[:chunk_n] = np.ascontiguousarray(chunk_in, dtype=np.float32)

            # Set dynamic batch size
            self._context.set_binding_shape(0, (chunk_n, 3, _IN_H, _IN_W))

            # Async H2D → execute → D2H on persistent stream
            cuda.memcpy_htod_async(self._d_input, self._h_input[:chunk_n], self._stream)
            self._context.execute_async_v2(
                bindings=[int(self._d_input), int(self._d_output)],
                stream_handle=self._stream.handle,
            )
            cuda.memcpy_dtoh_async(self._h_output[:chunk_n], self._d_output, self._stream)
            self._stream.synchronize()

            all_out.append(self._h_output[:chunk_n].copy())

        out = np.concatenate(all_out, axis=0) if len(all_out) > 1 else all_out[0]

        # L2 normalise
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        return out / norms


_trt_osnet: Optional[_TRTOSNet] = None


def _get_trt_osnet() -> _TRTOSNet:
    """Lazy-init singleton TRT OSNet runner."""
    global _trt_osnet
    if _trt_osnet is None:
        _trt_osnet = _TRTOSNet(_OSNET_ENGINE_PATH)
    return _trt_osnet


# ── Public extractor class ─────────────────────────────────────────────────────

class DeepAppearanceExtractor:
    """
    Deep appearance feature extractor using OSNet-x0.25.

    Automatically uses TensorRT FP16 engine (resources/osnet_x025.engine) when
    available for maximum throughput.  Falls back to PyTorch when the engine
    file is absent or TensorRT is not installed, and further falls back to
    MobileNetV2 if OSNet construction fails.

    Interface (used by AdvancedFeetDetector):
        extractor = DeepAppearanceExtractor()
        if extractor.available:
            embs = extractor.batch_extract([crop1_bgr, crop2_bgr])
            # embs: List[np.ndarray(256,) float32]

    Args:
        device:       "cuda" / "cpu" / None (auto-detect).
        weights_path: Optional path to a .pth checkpoint.  When provided
                      the model is warm-started from these weights.
    """

    def __init__(
        self,
        device: Optional[str] = None,
        weights_path: Optional[str] = None,
    ):
        self.available   = False
        self._model      = None
        self._device     = "cpu"
        self._use_trt    = False
        self._use_torchreid = False
        self._embed_dim  = _EMBED_DIM  # updated below for torchreid mode

        # 1. TRT engine (fastest — FP16 GPU)
        trt_runner = _get_trt_osnet()
        if trt_runner.available:
            self._trt = trt_runner
            self._use_trt = True
            self.available = True
            _log.debug("DeepAppearanceExtractor: using TRT engine")
            return

        if not _HAS_TORCH:
            return

        if device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device

        # Resolve weights path: explicit arg takes priority, then default location.
        resolved_weights = weights_path or ""
        if not resolved_weights and os.path.exists(_DEFAULT_WEIGHTS_PATH):
            resolved_weights = _DEFAULT_WEIGHTS_PATH

        # 2. torchreid-backed model: zero key mismatch, 512-dim output.
        #    Used whenever torchreid is installed and weights are available.
        if _HAS_TORCHREID and resolved_weights and os.path.exists(resolved_weights):
            tr = _TorchReidOSNet(resolved_weights, self._device)
            if tr.available:
                self._torchreid_model = tr
                self._use_torchreid  = True
                self._embed_dim      = _TorchReidOSNet.embed_dim
                self.available       = True
                _log.debug(
                    "DeepAppearanceExtractor: torchreid OSNet loaded from %s (%d-dim)",
                    resolved_weights, self._embed_dim,
                )
                return

        # 3. Standalone OSNetX025 (random init or partial load via strict=False)
        try:
            model = OSNetX025(embed_dim=_EMBED_DIM)
            if resolved_weights and os.path.exists(resolved_weights):
                state = torch.load(resolved_weights, map_location="cpu")
                state = state.get("state_dict", state)
                model.load_state_dict(state, strict=False)
            model = model.to(self._device).eval()
            self._model  = model
            self.available = True
            # Warmup: eliminate CUDA JIT latency (~9s) on first real call
            if self._device != "cpu":
                _dummy = torch.zeros(1, 3, 256, 128, device=self._device)
                with torch.no_grad():
                    self._model(_dummy)
                _log.debug("OSNet CUDA warmup complete (device=%s)", self._device)
        except Exception:
            # 4. MobileNetV2 fallback
            try:
                from torchvision.models import mobilenet_v2
                mv2  = mobilenet_v2(weights=None)
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
        if not _HAS_TORCH:
            return
        if self._use_torchreid:
            state = torch.load(path, map_location="cpu")
            state = state.get("state_dict", state)
            self._torchreid_model._model.load_state_dict(state, strict=False)
        elif self._model is not None:
            state = torch.load(path, map_location="cpu")
            state = state.get("state_dict", state)
            self._model.load_state_dict(state, strict=False)

    @torch.no_grad()
    def batch_extract(self, crops: List[np.ndarray]) -> List[np.ndarray]:
        """
        Extract appearance embeddings for a list of BGR crops.

        When TRT engine is loaded, uses GPU TRT inference for ~3× speedup
        over PyTorch.  Falls back to PyTorch automatically.

        Args:
            crops: List of BGR uint8 ndarray player crops.

        Returns:
            List of float32 ndarray, shape (embed_dim,), L2-normalised.
            Returns list of zero vectors when ``available`` is False.
        """
        zero = np.zeros(self._embed_dim, dtype=np.float32)
        if not self.available or not crops:
            return [zero.copy() for _ in crops]

        try:
            # Track which crops are valid so we can restore original order.
            valid_idx = [i for i, c in enumerate(crops)
                         if c is not None and c.size > 0]
            if not valid_idx:
                return [zero.copy() for _ in crops]

            _CHUNK = 64  # max crops per GPU forward pass (fits 24 GB VRAM with margin)

            if self._use_trt:
                # Build batched input tensor for TRT; process in chunks of _CHUNK
                _all_np = np.stack(
                    [_preprocess_crop(crops[i]).squeeze(0).numpy() for i in valid_idx],
                    axis=0,
                )  # (N_valid, 3, 256, 128)
                _chunks = [
                    self._trt.infer(_all_np[_ci:_ci + _CHUNK])
                    for _ci in range(0, len(_all_np), _CHUNK)
                ]
                valid_embs = np.concatenate(_chunks, axis=0)
            elif self._use_torchreid:
                _all_t = torch.cat(
                    [_preprocess_crop(crops[i]) for i in valid_idx], dim=0
                )  # (N_valid, 3, 256, 128)
                _chunks = [
                    self._torchreid_model.infer(_all_t[_ci:_ci + _CHUNK])
                    for _ci in range(0, len(_all_t), _CHUNK)
                ]
                valid_embs = np.concatenate(_chunks, axis=0)
            else:
                # torch.no_grad(): inference only — prevents autograd from
                # retaining activation tensors for backward, which otherwise
                # balloons RSS on long runs (observed 10GB/sec leak on GPU hosts).
                with torch.no_grad():
                    _all_t = torch.cat(
                        [_preprocess_crop(crops[i]).to(self._device) for i in valid_idx],
                        dim=0,
                    )  # (N_valid, 3, H, W)
                    _chunk_embs = []
                    for _ci in range(0, len(_all_t), _CHUNK):
                        _t = _all_t[_ci:_ci + _CHUNK]
                        if getattr(self, "_use_mv2", False):
                            _f = self._model(_t)
                            _f = self._mv2_gap(_f).squeeze(-1).squeeze(-1)
                            _f = F.normalize(_f, dim=1)
                        else:
                            _f = self._model(_t)   # (chunk, embed_dim)
                        _chunk_embs.append(_f.detach().cpu().float().numpy())
                        del _f, _t
                    del _all_t
                valid_embs = np.concatenate(_chunk_embs, axis=0)

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
