"""repo-root conftest.py — test-infrastructure fixes.

P1-8  signals/ package shadowing:
      Ensure the repo-root signals/ namespace package is imported and
      resolved BEFORE scripts/team_system/signals (a regular package) can
      shadow it.  After the namespace is established we extend its __path__
      to also include scripts/team_system/signals so that signals.judge /
      signals.gates / signals.cluster_lab still resolve correctly for tests
      that add scripts/team_system to sys.path.

P1-9  pyarrow import-order Windows access violation:
      Eagerly import pyarrow.dataset at session start, before any other
      heavy native libs are loaded.  This is the proven fix for the DLL
      import-order crash that kills the interpreter mid-session when
      clv_capture.py triggers a lazy pyarrow.dataset import after ~100
      other test modules have already loaded native libs.
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# P1-9  Eager pyarrow.dataset preload (must be FIRST — before any other
#        heavy import that might pull in native DLLs on Windows)
# ---------------------------------------------------------------------------
try:
    import pyarrow.dataset  # noqa: F401
except ImportError:
    pass  # pyarrow not installed — fine, tests that need it will skip/fail

# ---------------------------------------------------------------------------
# P1-8  Repair sys.path so the repo-root signals/ namespace package wins
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_TS = os.path.join(_REPO_ROOT, "scripts", "team_system")
_SCRIPTS_TS_SIGNALS = os.path.join(_SCRIPTS_TS, "signals")

# 1. Ensure repo root is at the FRONT of sys.path.
#    Remove any existing entry first to avoid duplicates, then re-insert at 0.
for _entry in list(sys.path):
    if os.path.normcase(os.path.abspath(_entry)) == os.path.normcase(_REPO_ROOT):
        sys.path.remove(_entry)
sys.path.insert(0, _REPO_ROOT)

# 2. Import `signals` NOW while scripts/team_system is NOT yet on sys.path
#    (or is further back), so Python resolves it as the repo-root namespace
#    package rather than the scripts/team_system regular package.
#    We do this by temporarily removing scripts/team_system from sys.path,
#    importing signals, then putting scripts/team_system back.
_ts_entries = [e for e in sys.path if os.path.normcase(os.path.abspath(e)) == os.path.normcase(_SCRIPTS_TS)]
for _e in _ts_entries:
    sys.path.remove(_e)

# Also evict any already-cached signals module that resolved to the wrong pkg.
for _key in list(sys.modules.keys()):
    if _key == "signals" or _key.startswith("signals."):
        del sys.modules[_key]

import signals as _signals_pkg  # noqa: E402 — now resolves to namespace pkg

# 3. Restore scripts/team_system onto sys.path (after repo root).
for _e in _ts_entries:
    if _e not in sys.path:
        sys.path.append(_e)
if _SCRIPTS_TS not in sys.path:
    sys.path.append(_SCRIPTS_TS)

# 4. Extend the namespace package's __path__ to include
#    scripts/team_system/signals so that signals.judge / signals.gates /
#    signals.cluster_lab still resolve for tests that need them.
if hasattr(_signals_pkg, "__path__") and os.path.isdir(_SCRIPTS_TS_SIGNALS):
    _ns_path = list(_signals_pkg.__path__)
    if _SCRIPTS_TS_SIGNALS not in _ns_path:
        _signals_pkg.__path__.append(_SCRIPTS_TS_SIGNALS)
