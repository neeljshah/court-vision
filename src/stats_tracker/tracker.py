"""StatsTracker — stub that delegates to compiled .pyc if available, otherwise no-ops."""
from __future__ import annotations

try:
    # Try loading the compiled version (cpython-310 .pyc exists)
    import importlib.util, pathlib, sys

    _pyc = pathlib.Path(__file__).parent / "__pycache__" / "tracker.cpython-310.pyc"
    if _pyc.exists():
        spec = importlib.util.spec_from_file_location("_stats_tracker_compiled", str(_pyc))
        _mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)
        StatsTracker = _mod.StatsTracker
    else:
        raise ImportError("no pyc")
except Exception:
    class StatsTracker:  # type: ignore[no-redef]
        """No-op stub — compiled tracker unavailable."""
        def __init__(self, **kwargs):
            pass
        def track(self, *args, **kwargs):
            pass
        def get_stats(self, *args, **kwargs):
            return {}
