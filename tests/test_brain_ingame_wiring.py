"""P3.1/P3.4 — the live_engine.project_from_snapshot wiring of the in-game seam.

The seam logic itself is tested in test_brain_live_state_hook.py (no heavy models). This file proves the
WIRING contract structurally (per the mission: extract a testable seam, do not rely on a heavy full
ensemble run):
  - both in-game hooks are present and GATED on their exact CV_* env flags inside project_from_snapshot;
  - the gated call targets the seam functions;
  - the lazy import path used by the live server (`src.ingame.live_state_hook`) resolves and exposes both
    functions, so the runtime import inside the flag block can never NameError;
  - the flags are registered default-OFF in the brain registry (so OFF == byte-identical is the default).
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                       # for `src.ingame.*`
sys.path.insert(0, os.path.join(ROOT, "src"))  # for `brain.flags`

_LIVE = os.path.join(ROOT, "src", "prediction", "live_engine.py")


def _gated_call_exists(tree: ast.AST, flag: str, fn_name: str) -> bool:
    """True iff some `if os.environ.get("<flag>"): ...` block contains a call to <fn_name>."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        # match os.environ.get("<flag>") as the (whole) If test
        if not (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute)
                and test.func.attr == "get"):
            continue
        if not (test.args and isinstance(test.args[0], ast.Constant) and test.args[0].value == flag):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                    and inner.func.id == fn_name):
                return True
    return False


def test_ingame_state_block_is_gated_and_calls_seam():
    tree = ast.parse(open(_LIVE, encoding="utf-8").read())
    assert _gated_call_exists(tree, "CV_INGAME_STATE", "apply_ingame_state")


def test_universal_wp_block_is_gated_and_calls_seam():
    tree = ast.parse(open(_LIVE, encoding="utf-8").read())
    assert _gated_call_exists(tree, "CV_INGAME_UNIVERSAL_WP", "apply_universal_winprob")


def test_live_import_path_resolves():
    import importlib
    mod = importlib.import_module("src.ingame.live_state_hook")
    assert hasattr(mod, "apply_ingame_state")
    assert hasattr(mod, "apply_universal_winprob")


def test_flags_registered_default_off():
    from brain.flags import FLAGS, is_on
    for f in ("CV_INGAME_STATE", "CV_INGAME_UNIVERSAL_WP"):
        assert f in FLAGS and FLAGS[f]["default"] is False
    # with the env unset, both read OFF -> the wiring blocks are skipped (byte-identical default)
    os.environ.pop("CV_INGAME_STATE", None)
    os.environ.pop("CV_INGAME_UNIVERSAL_WP", None)
    assert is_on("CV_INGAME_STATE") is False
    assert is_on("CV_INGAME_UNIVERSAL_WP") is False
