"""Quick check: is TensorRT actually being used at runtime?"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1. Can we import tensorrt?
try:
    import tensorrt as trt
    print(f"tensorrt importable: YES  version={trt.__version__}")
except Exception as e:
    print(f"tensorrt importable: NO  ({e})")

# 2. Which model files exist?
resources = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'resources')
for stem in ['yolov8n', 'yolov8n_ball', 'yolov8n-pose', 'osnet_x025']:
    engine = os.path.normpath(os.path.join(resources, f'{stem}.engine'))
    pt     = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', f'{stem}.pt')
    has_engine = os.path.exists(engine)
    has_pt     = os.path.exists(pt)
    size_mb    = os.path.getsize(engine) / 1e6 if has_engine else 0
    print(f"  {stem}: engine={'YES (' + f'{size_mb:.1f}MB)' if has_engine else 'NO':<20} pt={'YES' if has_pt else 'NO'}")

# 3. What does _best_yolo_model() actually return?
from src.tracking.player_detection import _best_yolo_model
selected = _best_yolo_model('yolov8n')
print(f"\n_best_yolo_model('yolov8n') → {selected}")
print(f"Using TRT: {'YES' if selected.endswith('.engine') else 'NO — falling back to .pt'}")
