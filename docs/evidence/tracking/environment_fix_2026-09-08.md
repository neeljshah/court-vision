# PROPOSED G340 Local Import Repair

Status: PROPOSED ONLY. G340 does not run these commands or change any installed package.

For the conda traceback that names an ONNX import AttributeError through `ml_dtypes`, the proposed repair is:

```powershell
conda run -n basketball_ai python -m pip install --upgrade "ml_dtypes>=0.4" "onnx>=1.16"
conda run -n basketball_ai python -c "from ultralytics import YOLO; import src.tracking.osnet_reid"
```

If the system interpreter's traceback names `np.bool8` through tensorboard/torchreid, the proposed repair is:

```powershell
python -m pip install --upgrade "tensorboard>=2.17"
python -c "from ultralytics import YOLO; import src.tracking.osnet_reid"
```

The selected route is inference-only: `src/tracking/osnet_reid.py` has no ONNX import or export, and
`src/tracking/player_detection.py` intentionally chooses `.engine` or `.pt`, not `.onnx`. The G340
shim is consequently a temporary import guard, not a general ONNX replacement or environment repair.
