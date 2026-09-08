"""G340 local-only compatibility shim for a known ONNX/ml_dtypes import failure."""
from __future__ import annotations

import importlib
import importlib.machinery
import subprocess
import sys
import types

from scripts.platformkit import env_sidecar

NO_ACTION = "none"
ONNX_ML_DTYPES_STUB = "onnx_stub_for_mldtypes_attribute_error"
ONNX_IMPORT_ERROR_STUB = "onnx_stub_for_import_error"
_ROUTE_PROBE = "from ultralytics import YOLO"


def _onnx_preflight() -> str:
    """Import ONNX, installing a narrow placeholder only for the known bad pair."""
    if "onnx" in sys.modules:
        return NO_ACTION
    try:
        importlib.import_module("onnx")
        return NO_ACTION
    except ModuleNotFoundError:
        return NO_ACTION
    except ImportError as exc:
        action = "%s: %s: %s" % (ONNX_IMPORT_ERROR_STUB, type(exc).__name__, str(exc))
    except AttributeError as exc:
        if "ml_dtypes" not in str(exc) and "float" not in str(exc).lower():
            raise
        action = ONNX_ML_DTYPES_STUB
    stub = types.ModuleType("onnx")
    stub.__spec__ = importlib.machinery.ModuleSpec("onnx", None)
    stub.__getattr__ = lambda _name: None
    sys.modules["onnx"] = stub
    return action


def _route_imports_cleanly() -> bool:
    """Probe the YOLO route in a child process without changing this process modules."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _ROUTE_PROBE],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def prepare_route_imports() -> str:
    """Prepare a YOLO inference-only process and record the action in its sidecar."""
    action = NO_ACTION if _route_imports_cleanly() else _onnx_preflight()
    env_sidecar.record_import_shim(action)
    return action
