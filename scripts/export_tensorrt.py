"""
export_tensorrt.py — Phase F1: Export YOLOv8 models + OSNet-x0.25 for fast GPU inference.

Priority order:
  1. TensorRT .engine (2–4× speedup) — requires `pip install tensorrt`
  2. ONNX + onnxruntime-gpu (1.5–2× speedup) — requires `pip install onnxruntime-gpu`

Run once per machine; .engine files are GPU-specific (can't copy across GPUs).

Usage:
    conda activate basketball_ai
    python scripts/export_tensorrt.py

Outputs written to resources/:
    yolov8n.engine  OR  yolov8n.onnx    (detection)
    yolov8n-pose.engine  OR  yolov8n-pose.onnx  (pose, if available)
    osnet_x025.engine   (OSNet-x0.25 player re-ID, dynamic batch FP16)

The tracker auto-detects: .engine > .onnx > .pt  (fastest available wins).
"""

from __future__ import annotations

import os
import shutil
import sys

ROOT      = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RESOURCES = os.path.join(ROOT, "resources")
os.makedirs(RESOURCES, exist_ok=True)

# Ensure TensorRT DLLs are findable (Windows: bin/ dir must be on PATH)
# On RunPod/Linux, TRT is on LD_LIBRARY_PATH already.
_TRT_BIN = r"C:\Windows\System32\TensorRT-10.16.0.72\bin"
if sys.platform == "win32" and os.path.isdir(_TRT_BIN) and _TRT_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _TRT_BIN + os.pathsep + os.environ.get("PATH", "")


def _try_export(model_name: str, fmt: str, out_path: str, imgsz: int = 640) -> bool:
    """Try exporting to `fmt`. Returns True on success."""
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("ERROR: ultralytics not installed")
        return False

    if os.path.exists(out_path):
        print(f"  EXISTS: {out_path}")
        return True

    print(f"  Exporting {model_name} → {fmt}  (imgsz={imgsz})")
    try:
        model    = YOLO(model_name)
        exported = model.export(
            format=fmt,
            half=(fmt == "engine"),   # FP16 for TensorRT; ONNX stays FP32 for compat
            device=0,
            imgsz=imgsz,
            dynamic=False,
            simplify=True,
        )
        src = str(exported) if exported else ""
        if src and os.path.exists(src):
            if src != out_path:
                shutil.move(src, out_path)
            print(f"  ✓ saved: {out_path}")
            return True
    except Exception as e:
        print(f"  ✗ {fmt} export failed: {e}")
    return False


def export_model(pt_name: str, stem: str, imgsz: int = 640) -> str | None:
    """Export one YOLO model. Returns path to best available file, or None."""
    engine_path = os.path.join(RESOURCES, f"{stem}.engine")
    onnx_path   = os.path.join(RESOURCES, f"{stem}.onnx")

    # 1. Try TensorRT (best)
    if _try_export(pt_name, "engine", engine_path, imgsz):
        return engine_path

    print("  TensorRT export failed — check CUDA/cuDNN compatibility.")
    return None


def export_osnet_trt() -> str | None:
    """
    Export OSNet-x0.25 to TensorRT FP16 with a dynamic batch axis.

    OSNet input shape: (N, 3, 256, 128) person crops.
    Output:           (N, 256) L2-normalised embedding vectors.

    Returns path to resources/osnet_x025.engine, or None on failure.
    """
    engine_path = os.path.join(RESOURCES, "osnet_x025.engine")
    onnx_path   = os.path.join(RESOURCES, "osnet_x025.onnx")

    if os.path.exists(engine_path):
        print(f"  EXISTS: {engine_path}")
        return engine_path

    print("  Exporting OSNet-x0.25 → ONNX (intermediate)...")

    # Build OSNet model from src module
    sys.path.insert(0, ROOT)
    try:
        import torch  # type: ignore
        from src.tracking.osnet_reid import OSNetX025  # type: ignore
    except ImportError as e:
        print(f"  ✗ OSNet import failed: {e}")
        return None

    try:
        model = OSNetX025(embed_dim=256)
        model.eval()

        # Dummy input: batch=1, 3 channels, 256×128
        dummy = torch.randn(1, 3, 256, 128)

        if not os.path.exists(onnx_path):
            torch.onnx.export(
                model,
                dummy,
                onnx_path,
                opset_version=12,
                input_names=["input"],
                output_names=["embedding"],
                dynamic_axes={
                    "input":     {0: "batch_size"},
                    "embedding": {0: "batch_size"},
                },
            )
            print(f"  ✓ ONNX saved: {onnx_path}")
        else:
            print(f"  ONNX EXISTS: {onnx_path}")

    except Exception as e:
        print(f"  ✗ ONNX export failed: {e}")
        return None

    # Convert ONNX → TensorRT FP16
    print("  Converting OSNet ONNX → TensorRT FP16...")
    try:
        import tensorrt as trt  # type: ignore

        TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
        builder    = trt.Builder(TRT_LOGGER)
        network    = builder.create_network(
            1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
        )
        parser = trt.OnnxParser(network, TRT_LOGGER)

        with open(onnx_path, "rb") as f:
            if not parser.parse(f.read()):
                for i in range(parser.num_errors):
                    print(f"    ONNX parse error: {parser.get_error(i)}")
                return None

        config = builder.create_builder_config()
        # L40S (48GB): use 4 GB workspace for larger optimization search space
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 1 << 32)  # 4 GB

        # Precision: FP8 > FP16 (Ada Lovelace / L40S has native FP8 Transformer Engine)
        _used_fp8 = False
        if hasattr(trt.BuilderFlag, "FP8") and builder.platform_has_fast_fp16:
            try:
                config.set_flag(trt.BuilderFlag.FP8)
                config.set_flag(trt.BuilderFlag.FP16)  # FP8 requires FP16 fallback layers
                _used_fp8 = True
                print("  FP8 mode enabled (L40S/Ada native)")
            except Exception:
                pass
        if not _used_fp8 and builder.platform_has_fast_fp16:
            config.set_flag(trt.BuilderFlag.FP16)
            print("  FP16 mode enabled")

        # Dynamic batch: min=1, opt=8, max=20
        profile = builder.create_optimization_profile()
        profile.set_shape("input", (1, 3, 256, 128), (8, 3, 256, 128), (20, 3, 256, 128))
        config.add_optimization_profile(profile)

        serialized = builder.build_serialized_network(network, config)
        if serialized is None:
            print("  ✗ TRT build_serialized_network returned None")
            return None

        with open(engine_path, "wb") as f:
            f.write(serialized)
        print(f"  ✓ TRT engine saved: {engine_path}")
        return engine_path

    except Exception as e:
        print(f"  ✗ TensorRT OSNet export failed: {e}")
        return None


def export_ball_model() -> str | None:
    """Export ball-detection YOLOv8n to TRT (if weights exist)."""
    ball_pt = os.path.join(ROOT, "models", "weights", "yolov8n_ball.pt")
    if not os.path.exists(ball_pt):
        print(f"  Ball weights not found ({ball_pt}) — run train_ball_yolo.py first")
        return None
    engine_path = os.path.join(RESOURCES, "yolov8n_ball.engine")
    if _try_export(ball_pt, "engine", engine_path, imgsz=480):
        return engine_path
    return None


def main() -> None:
    print("=== YOLOv8 export — detection model ===")
    det = export_model("yolov8n.pt", "yolov8n")

    print("\n=== YOLOv8 export — pose model ===")
    pose = export_model("yolov8n-pose.pt", "yolov8n-pose")

    print("\n=== YOLOv8 export — ball detection model ===")
    ball = export_ball_model()

    print("\n=== OSNet-x0.25 export — player re-ID ===")
    osnet = export_osnet_trt()

    print()
    if not det and not pose and not ball and not osnet:
        print("Nothing exported.")
        sys.exit(1)

    print("─" * 50)
    print("Done. The tracker auto-loads the fastest available model:")
    for label, path in [
        ("Detection", det), ("Pose", pose),
        ("Ball YOLO", ball), ("OSNet re-ID", osnet),
    ]:
        if path:
            rel = os.path.relpath(path, ROOT)
            print(f"  {label}: {rel}")
        else:
            print(f"  {label}: not exported (will use fallback)")

    if any(p and p.endswith(".onnx") for p in [det, pose] if p):
        print()
        print("ONNX exported. For maximum GPU speedup install onnxruntime-gpu:")
        print("  pip install onnxruntime-gpu")
        print("For full TensorRT (2–4×) install tensorrt:")
        print("  pip install tensorrt  (CUDA 11.x: pip install tensorrt==8.6.1)")


if __name__ == "__main__":
    main()
