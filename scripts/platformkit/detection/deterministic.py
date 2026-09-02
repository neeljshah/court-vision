"""Pinned, repeatable detector setup for evidence-packet inference."""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np

BoxDetector = Callable[[np.ndarray], Sequence[Sequence[float]]]
_SEED = 20260901


def configure_deterministic_inference(seed: int = _SEED) -> None:
    """Set single-process inference controls before loading an evidence model."""
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.use_deterministic_algorithms(True, warn_only=True)
    except ImportError:
        pass


def pinned_detector_model_path() -> Path:
    """Resolve the model once rather than relying on a changing working directory."""
    configured = os.environ.get("CV_DETECTOR_MODEL")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "yolov8n.pt"


def build_soccer_packet_detector() -> BoxDetector:
    """Return the fixed-model detector used by soccer evidence packets."""
    from scripts.platformkit.detection.shim import get_box_detector

    configure_deterministic_inference()
    return get_box_detector(model_path=pinned_detector_model_path(), sport="soccer")


def read_packet_frame(path: Path) -> np.ndarray:
    """Decode a packet JPEG through one explicit BGR OpenCV path."""
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("could not read packet frame: %s" % path)
    return np.ascontiguousarray(frame)
