"""The LLM-free self-improving prediction brain; all components default-OFF, see ARCHITECTURE.md.

ROADMAP phase: P2 (Control Brain) through P6 (Narration) — see .planning/brain/ROADMAP.md.
GATE: Every CV_* flag in this package must pass its individual gate (defined in flags.py)
before being flipped ON. The package itself is always import-safe; no heavy dep loads at import time.

This package provides:
  - ``src.brain.flags``  -- the single flag registry (FLAGS dict + is_on / all_flags / assert_registered)
  - ``src.brain.control_brain``  -- Rung 0/1 passthrough + GLS (P2, to be built by executor)

All flags default OFF; the package changes NO live prediction path when imported with all flags unset.
"""
from __future__ import annotations

__version__ = "0.1.0"

# Re-export the canonical flag helpers so callers can do:
#   from src.brain import is_on, all_flags, assert_registered
from .flags import all_flags, assert_registered, is_on

__all__ = ["is_on", "all_flags", "assert_registered"]
