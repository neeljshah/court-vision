"""Single authority for the repo root. Replaces all dirname-chain root hacks."""
from __future__ import annotations
import os
from pathlib import Path

_MARKERS = ("CLAUDE.md", ".git", "pyproject.toml")


def repo_root() -> Path:
    env = os.environ.get("COURTVISION_ROOT")
    if env:
        return Path(env)
    p = Path(__file__).resolve()
    for parent in p.parents:
        if any((parent / m).exists() for m in _MARKERS):
            return parent
    raise RuntimeError("repo root not found; set COURTVISION_ROOT")
