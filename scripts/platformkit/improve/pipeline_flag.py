"""scripts.platformkit.improve.pipeline_flag -- MF1 kill-switch helper.

Exposes a single function, pipeline_enabled(), that returns True ONLY when the
human-managed sentinel file data/cache/improve/PIPELINE_ENABLED is present on disk.

Design constraints (from SKEPTIC_REVIEW.md MF1 exact-fix spec):
  * Reads ONLY filesystem existence -- never an env var the loop could set.
  * Never creates the sentinel itself.
  * No third-party dependencies.  stdlib + pathlib only.
  * The canonical sentinel path is exported as SENTINEL_PATH so callers and tests
    can monkeypatch it without re-deriving the path.
  * ASCII-only stdout/strings.  <=300 LOC.

Usage in recalibrator (defense-in-depth layer A):
    from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
    def build_candidate(name, settled):
        if not pipeline_enabled():
            return None   # byte-identical to NO_CANDIDATE baseline
        ...

Usage in selfimprove_runner (defense-in-depth layer B -- MF1 exact-fix step 1b):
    from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
    def _default_recalibrate_fn(name, settled, *_a, **_kw):
        if not pipeline_enabled():
            return None   # inert even when recalibrator.py is importable
        ...
"""
from __future__ import annotations

import pathlib

# ---------------------------------------------------------------------------
# Canonical sentinel path.  Human creates; loop NEVER creates.
# ---------------------------------------------------------------------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # .../nba-ai-system
SENTINEL_PATH: pathlib.Path = (
    _REPO_ROOT / "data" / "cache" / "improve" / "PIPELINE_ENABLED"
)


def pipeline_enabled(*, _sentinel: pathlib.Path | None = None) -> bool:
    """Return True iff the PIPELINE_ENABLED sentinel file exists.

    Args:
        _sentinel: override the sentinel path (test-only injection point).
                   Callers MUST NOT pass this in production code.

    Returns:
        bool -- True only when the sentinel is present on disk.

    Invariants:
        * Never creates, touches, or modifies the sentinel.
        * Never reads an environment variable.
        * Never raises -- a filesystem error is treated as absent (-> False).
    """
    path = _sentinel if _sentinel is not None else SENTINEL_PATH
    try:
        return path.exists()
    except Exception:  # noqa: BLE001 -- permission/IO error -> treat as absent
        return False


__all__ = ["SENTINEL_PATH", "pipeline_enabled"]
