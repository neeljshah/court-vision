"""G347 construct coverage for probe-first environment-shim behavior."""
import sys
import types

from scripts.platformkit import env_shim, env_sidecar


def test_clean_route_probe_is_a_noop_and_does_not_touch_onnx(monkeypatch):
    monkeypatch.delitem(sys.modules, "onnx", raising=False)
    monkeypatch.setattr(env_shim, "_route_imports_cleanly", lambda: True)
    modules_before = set(sys.modules)
    assert env_shim.prepare_route_imports() == env_shim.NO_ACTION
    assert set(sys.modules) == modules_before
    assert env_sidecar.capture()["import_shim"] == env_shim.NO_ACTION


def test_plain_onnx_importerror_installs_stub_and_route_import_proceeds(monkeypatch):
    message = "cannot import name 'builder' from 'google.protobuf.internal'"
    monkeypatch.delitem(sys.modules, "onnx", raising=False)
    monkeypatch.setattr(env_shim, "_route_imports_cleanly", lambda: False)

    def broken(name):
        assert name == "onnx"
        raise ImportError(message)

    route = types.ModuleType("ultralytics")
    route.YOLO = object()
    monkeypatch.setattr(env_shim.importlib, "import_module", broken)
    monkeypatch.setitem(sys.modules, "ultralytics", route)
    action = env_shim.prepare_route_imports()
    from ultralytics import YOLO

    assert YOLO is route.YOLO
    assert sys.modules["onnx"].__spec__.name == "onnx"
    assert action == "%s: ImportError: %s" % (env_shim.ONNX_IMPORT_ERROR_STUB, message)
    assert env_sidecar.capture()["import_shim"] == action
