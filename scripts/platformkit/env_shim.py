"""G340 local-only compatibility shim for a known ONNX/ml_dtypes import failure."""
from __future__ import annotations

import importlib
import importlib.machinery
import sys
import types

from scripts.platformkit import env_sidecar

NO_ACTION = "none"
ONNX_ML_DTYPES_STUB = "onnx_stub_for_mldtypes_attribute_error"


def _onnx_preflight() -> str:
    """Import ONNX, installing a narrow placeholder only for the known bad pair."""
    if "onnx" in sys.modules:
        return NO_ACTION
    try:
        importlib.import_module("onnx")
        return NO_ACTION
    except ModuleNotFoundError:
        return NO_ACTION
    except AttributeError as exc:
        if "ml_dtypes" not in str(exc) and "float" not in str(exc).lower():
            raise
    stub = types.ModuleType("onnx")
    stub.__spec__ = importlib.machinery.ModuleSpec("onnx", None)
    stub.__getattr__ = lambda _name: None
    sys.modules["onnx"] = stub
    return ONNX_ML_DTYPES_STUB


def prepare_route_imports() -> str:
    """Prepare a YOLO inference-only process and record the action in its sidecar."""
    action = _onnx_preflight()
    env_sidecar.record_import_shim(action)
    return action
