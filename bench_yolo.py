import time, numpy as np, os, warnings
warnings.filterwarnings("ignore")
from ultralytics import YOLO
import torch

frame = np.zeros((640, 640, 3), dtype=np.uint8)
N = 20
results = {}

cuda = torch.cuda.is_available()
print(f"CUDA available: {cuda}")
if cuda:
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# ── .pt on GPU (fp16) ──────────────────────────────────────────────────────
print("\nTesting yolov8n.pt (GPU fp16)...")
m_pt = YOLO("yolov8n.pt")
m_pt(frame, verbose=False, half=cuda)  # warmup
t0 = time.perf_counter()
for _ in range(N):
    m_pt(frame, classes=[0], conf=0.5, verbose=False, imgsz=640, half=cuda)
results["pt  (GPU fp16)"] = (time.perf_counter() - t0) / N * 1000

# ── .onnx CPU ──────────────────────────────────────────────────────────────
for onnx_path in ["yolov8n.onnx", r"C:\Users\neelj\yolov8n.onnx"]:
    if os.path.exists(onnx_path):
        print(f"\nTesting {onnx_path} (CPU)...")
        try:
            m_onnx = YOLO(onnx_path)
            # Force CPU to avoid cuDNN 9 requirement
            m_onnx(frame, verbose=False, device="cpu")  # warmup
            t0 = time.perf_counter()
            for _ in range(N):
                m_onnx(frame, classes=[0], conf=0.5, verbose=False, imgsz=640, device="cpu")
            results["onnx (CPU)   "] = (time.perf_counter() - t0) / N * 1000
        except Exception as e:
            print(f"  ONNX CPU failed: {e}")
        break

# ── Summary ───────────────────────────────────────────────────────────────
print("\n" + "─" * 35)
baseline = None
for k, v in results.items():
    if baseline is None:
        baseline = v
    tag = ""
    if baseline and k != list(results.keys())[0]:
        ratio = baseline / v
        tag = f"  ({ratio:.2f}x faster)" if ratio > 1 else f"  ({1/ratio:.2f}x SLOWER)"
    print(f"  {k}: {v:6.1f} ms/frame{tag}")
print("─" * 35)
print("\nConclusion: use whichever is fastest above.")
