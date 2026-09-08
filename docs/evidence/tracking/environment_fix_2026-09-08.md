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

## 2026-09-08 G347 system protobuf/onnx proposal (unexecuted)

The system interpreter reports protobuf 3.19.6 and onnx 1.17.0. The proposed compatibility pin is
`C:/Users/neelj/AppData/Local/Programs/Python/Python310/python.exe -m pip install "protobuf==3.20.3" "onnx==1.17.0"`.
It is documentation only: G347 does not execute it, install or remove any package, or claim that it resolves the unrelated system torchreid/numpy 2 failure.
