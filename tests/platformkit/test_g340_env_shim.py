"""G340 construct coverage for the route-import workaround; no data or pod access."""
import sys

from scripts.platformkit import env_shim, env_sidecar


def test_known_mldtypes_attribute_error_gets_only_the_onnx_placeholder(monkeypatch):
    monkeypatch.delitem(sys.modules, "onnx", raising=False)

    def broken(name):
        assert name == "onnx"
        raise AttributeError("module ml_dtypes has no attribute float4_e2m1fn")

    monkeypatch.setattr(env_shim.importlib, "import_module", broken)
    assert env_shim.prepare_route_imports() == env_shim.ONNX_ML_DTYPES_STUB
    assert sys.modules["onnx"].__spec__.name == "onnx"
    assert env_sidecar.capture()["import_shim"] == env_shim.ONNX_ML_DTYPES_STUB


def test_clean_preflight_is_a_noop(monkeypatch):
    monkeypatch.delitem(sys.modules, "onnx", raising=False)
    sentinel = object()
    monkeypatch.setattr(env_shim.importlib, "import_module", lambda name: sentinel)
    assert env_shim.prepare_route_imports() == env_shim.NO_ACTION
    assert "onnx" not in sys.modules


def test_current_route_imports_after_preparation():
    env_shim.prepare_route_imports()
    from ultralytics import YOLO  # noqa: F401
    import src.tracking.osnet_reid  # noqa: F401
